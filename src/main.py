import asyncio
import signal
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
import uvicorn

from src.config import get_settings
from src.services.api_client import api_client
from src.services.config_service import config_service
from src.services.database import db_service
from src.services.sync import sync_service
from src.services.health_check import PanelHealthChecker
from src.services.report_scheduler import init_report_scheduler
from src.services.webhook import app as webhook_app
from src.utils.auth import AdminMiddleware
from src.utils.i18n import get_i18n_middleware
from src.utils.logger import logger
from src.handlers import register_handlers


async def run_migrations() -> bool:
    """
    Запускает миграции Alembic автоматически при старте.
    Возвращает True если миграции успешны или не требуются.
    """
    try:
        from alembic.config import Config
        from alembic import command
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine
        import asyncio
        
        settings = get_settings()
        if not settings.database_url:
            return True
        
        db_url = str(settings.database_url).replace("postgresql://", "postgresql+psycopg2://")
        
        def _run_migrations_sync():
            """Синхронная функция для запуска в executor."""
            engine = None
            try:
                # Создаём engine с явным управлением пулом соединений
                engine = create_engine(
                    db_url,
                    pool_pre_ping=True,  # Проверка соединений перед использованием
                    pool_recycle=3600,    # Переиспользование соединений каждый час
                )
                
                # Проверяем текущую версию
                with engine.connect() as conn:
                    context = MigrationContext.configure(conn)
                    current_rev = context.get_current_revision()
                
                # Настраиваем Alembic
                alembic_cfg = Config("alembic.ini")
                alembic_cfg.set_main_option("sqlalchemy.url", db_url)
                
                # Получаем head revision
                script = ScriptDirectory.from_config(alembic_cfg)
                head_rev = script.get_current_head()
                
                logger.info("📊 DB revision: current=%s, head=%s", current_rev or "None", head_rev)

                if current_rev == head_rev:
                    logger.info("✅ Database up to date")
                    return True

                logger.info("🔄 Running migrations...")
                # Используем наш engine для миграций, чтобы контролировать соединения
                connection = engine.connect()
                try:
                    alembic_cfg.attributes['connection'] = connection
                    command.upgrade(alembic_cfg, "head")
                    connection.commit()
                except Exception as e:
                    connection.rollback()
                    raise
                finally:
                    connection.close()
                
                # Проверяем новую версию
                with engine.connect() as conn:
                    context = MigrationContext.configure(conn)
                    new_rev = context.get_current_revision()
                    logger.info("✅ Migrated: %s → %s", current_rev or "None", new_rev)
                
                return True
                
            finally:
                # Явно закрываем все соединения и освобождаем ресурсы
                if engine:
                    engine.dispose(close=True)  # close=True закрывает все соединения в пуле
        
        # Запускаем в thread pool чтобы не блокировать event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run_migrations_sync)
        return result

    except Exception as e:
        logger.error("❌ Migration failed: %s", e)
        return False


async def check_api_connection() -> bool:
    """Проверяет подключение к API с повторными попытками."""
    from src.config import get_settings
    settings = get_settings()
    max_attempts = 5
    delay = 3

    api_url = str(settings.api_base_url).rstrip("/")
    logger.info("🔗 Connecting to API: %s", api_url)

    for attempt in range(1, max_attempts + 1):
        try:
            await api_client.get_health()
            logger.info("✅ API connection OK")
            return True
        except Exception as exc:
            logger.warning(
                "❌ API connection failed (%d/%d): %s",
                attempt, max_attempts, exc
            )
            if attempt < max_attempts:
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "❌ Cannot connect to API. Check API_BASE_URL and API_TOKEN"
                )
                return False

    return False


async def run_webhook_server(bot: Bot, port: int) -> None:
    """Запускает webhook сервер в фоновом режиме."""
    webhook_app.state.bot = bot

    import logging as _logging

    # Фильтр для подавления шумных логов uvicorn
    class _UvicornNoiseFilter(_logging.Filter):
        def filter(self, record):
            msg = str(record.getMessage())
            if "Invalid HTTP request" in msg:
                return False
            if "/api/v1/connections/" in msg:
                return False
            return True

    _filter = _UvicornNoiseFilter()
    _logging.getLogger("uvicorn.error").addFilter(_filter)
    _logging.getLogger("uvicorn.access").addFilter(_filter)

    config = uvicorn.Config(
        app=webhook_app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,
        log_config=None,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    settings = get_settings()

    # Конфигурация администраторов
    if settings.allowed_admins:
        logger.info("🔐 Admins: %s", settings.allowed_admins)
    else:
        logger.warning("⚠️ No administrators configured! Set ADMINS env var")

    # Уведомления
    if settings.notifications_chat_id:
        logger.info("📢 Notifications: chat_id=%s", settings.notifications_chat_id)
    else:
        logger.info("📢 Notifications disabled")

    # Проверяем подключение к API перед стартом
    if not await check_api_connection():
        logger.error(
            "🚨 Cannot start bot: API is unavailable. " 
            "Please check API_BASE_URL and API_TOKEN in your .env file. "
            "Make sure the API server is running and accessible."
        )
        sys.exit(1)
    
    # Подключаемся к базе данных (если настроена)
    db_connected = False
    if settings.database_enabled:
        logger.info("🗄️ Connecting to PostgreSQL...")
        await run_migrations()
        db_connected = await db_service.connect()
        if db_connected:
            logger.info("✅ Database connected")
        else:
            logger.warning("⚠️ Database connection failed, running without cache")
    else:
        logger.info("🗄️ Database not configured, running without cache")

    # parse_mode is left as default (None) to avoid HTML parsing issues with plain text translations
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # middlewares
    # Сначала проверка администратора (блокирует неавторизованных пользователей)
    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(AdminMiddleware())
    # Затем i18n middleware (для локализации)
    dp.message.middleware(get_i18n_middleware())
    dp.callback_query.middleware(get_i18n_middleware())

    register_handlers(dp)
    dp.shutdown.register(api_client.close)

    # Запускаем webhook сервер в фоне, если настроен порт
    webhook_task = None
    if settings.webhook_port:
        logger.info("🌐 Webhook on port %d", settings.webhook_port)
        webhook_task = asyncio.create_task(run_webhook_server(bot, settings.webhook_port))

    # Запускаем health checker для панели
    health_checker = PanelHealthChecker(bot, check_interval=60)
    health_checker_task = asyncio.create_task(health_checker.start())
    dp["health_checker"] = health_checker

    # Инициализируем MaxMind updater (если настроен лицензионный ключ)
    maxmind_updater = None
    if settings.maxmind_license_key:
        from src.services.maxmind_updater import MaxMindUpdater
        maxmind_updater = MaxMindUpdater(
            license_key=settings.maxmind_license_key,
            city_path=settings.maxmind_city_db,
            asn_path=settings.maxmind_asn_db,
        )
        await maxmind_updater.start()

    # Инициализируем сервисы (если БД подключена)
    if db_connected:
        config_initialized = await config_service.initialize()
        if config_initialized:
            logger.info("✅ Dynamic config initialized")
            config_service.start_auto_reload(interval_seconds=30)

        logger.info("🔄 Starting sync service...")
        await sync_service.start()

        report_scheduler = init_report_scheduler(bot)
        await report_scheduler.start()
        logger.info("📊 Report scheduler started")
    else:
        report_scheduler = None

    logger.info("🤖 Bot started")

    # Graceful shutdown: use an event so SIGTERM/SIGINT stop polling cleanly
    shutdown_event = asyncio.Event()

    def _signal_handler(sig: signal.Signals) -> None:
        logger.info("Received %s, initiating graceful shutdown...", sig.name)
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler, sig)

    # Run polling in a task so we can cancel it on signal
    polling_task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    )

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Stop polling gracefully
    logger.info("Shutting down...")

    # Stop health checker first — it uses api_client which gets closed by dp.shutdown
    health_checker.stop()
    health_checker_task.cancel()
    try:
        await health_checker_task
    except asyncio.CancelledError:
        pass

    await dp.stop_polling()
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass

    # Cleanup services
    if maxmind_updater:
        maxmind_updater.stop()
    config_service.stop_auto_reload()
    if report_scheduler and report_scheduler.is_running:
        await report_scheduler.stop()
    if sync_service.is_running:
        await sync_service.stop()
    if webhook_task:
        webhook_task.cancel()
        try:
            await webhook_task
        except asyncio.CancelledError:
            pass
    if db_service.is_connected:
        await db_service.disconnect()
    logger.info("👋 Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass

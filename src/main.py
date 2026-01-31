import asyncio
import sys
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
import uvicorn

from src.config import get_settings
from src.services.api_client import api_client
from src.services.config_service import config_service
from src.services.database import db_service
from src.services.sync import sync_service
from src.services.health_check import PanelHealthChecker
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
                
                logger.info("📊 Database revision: current=%s, head=%s", current_rev or "None", head_rev)
                
                # Если уже на head — пропускаем
                if current_rev == head_rev:
                    logger.info("✅ Database is up to date, no migrations needed")
                    return True
                
                # Запускаем миграции
                logger.info("🔄 Running database migrations...")
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
                    logger.info("✅ Migrations completed: %s → %s", current_rev or "None", new_rev)
                
                return True
                
            finally:
                # Явно закрываем все соединения и освобождаем ресурсы
                if engine:
                    engine.dispose(close=True)  # close=True закрывает все соединения в пуле
        
        # Запускаем в thread pool чтобы не блокировать event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run_migrations_sync)
        logger.info("🔄 Migration function completed, result: %s", result)
        return result
        
    except Exception as e:
        logger.error("❌ Failed to run database migrations: %s", e)
        logger.warning("⚠️ Bot will continue without database migrations. You may need to run them manually.")
        return False


async def check_api_connection() -> bool:
    """Проверяет подключение к API с повторными попытками."""
    from src.config import get_settings
    settings = get_settings()
    max_attempts = 5
    delay = 3  # секунды между попытками
    
    api_url = str(settings.api_base_url).rstrip("/")
    logger.info("🔍 Checking API connection to: %s", api_url)
    
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("Attempting connection... (attempt %d/%d)", attempt, max_attempts)
            await api_client.get_health()
            logger.info("✅ API connection successful")
            return True
        except Exception as exc:
            error_msg = str(exc)
            error_type = type(exc).__name__
            logger.warning(
                "❌ API connection failed (attempt %d/%d) [%s]: %s",
                attempt, max_attempts, error_type, error_msg
            )
            if attempt < max_attempts:
                logger.info("⏳ Retrying in %d seconds...", delay)
                await asyncio.sleep(delay)
            else:
                logger.error("❌ All connection attempts failed")
                logger.error(
                    "💡 Troubleshooting tips:\n"
                    "  1. Check that API_BASE_URL is correct (should be http://remnawave:3000 for Docker)\n"
                    "  2. Verify that both containers are in the same Docker network (remnawave-network)\n"
                    "  3. Ensure the API container (remnawave) is running and healthy\n"
                    "  4. Check API_TOKEN is set correctly in .env file"
                )
                return False
    
    return False


async def run_webhook_server(bot: Bot, port: int) -> None:
    """Запускает webhook сервер в фоновом режиме."""
    # Сохраняем бот в состоянии приложения для доступа из webhook handlers и collector API
    webhook_app.state.bot = bot
    
    # Настраиваем логирование uvicorn для подавления предупреждений о некорректных запросах
    import logging
    uvicorn_logger = logging.getLogger("uvicorn.error")
    
    # Создаем фильтр для подавления предупреждений "Invalid HTTP request"
    class InvalidRequestFilter(logging.Filter):
        def filter(self, record):
            # Подавляем предупреждения о некорректных HTTP-запросах
            if "Invalid HTTP request" in str(record.getMessage()):
                return False
            return True
    
    # Фильтр для подавления access логов Collector API (слишком частые)
    class CollectorAPIAccessFilter(logging.Filter):
        def filter(self, record):
            message = str(record.getMessage())
            # Подавляем access логи для Collector API
            if "/api/v1/connections/" in message:
                return False
            return True
    
    # Применяем фильтры к логгерам uvicorn
    invalid_request_filter = InvalidRequestFilter()
    uvicorn_logger.addFilter(invalid_request_filter)
    
    # Применяем фильтр к access логгеру
    access_logger = logging.getLogger("uvicorn.access")
    collector_api_filter = CollectorAPIAccessFilter()
    access_logger.addFilter(collector_api_filter)
    
    config = uvicorn.Config(
        app=webhook_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
        # Отключаем логирование некорректных запросов на уровне uvicorn
        log_config=None,  # Используем нашу собственную конфигурацию логирования
    )
    server = uvicorn.Server(config)
    
    logger.info("🌐 Starting webhook server on port %d", port)
    await server.serve()


async def main() -> None:
    import os
    # Логируем сырое значение переменной окружения для отладки
    raw_admins_env = os.getenv("ADMINS", "NOT_SET")
    logger.info("🔍 DEBUG: Raw ADMINS env var: %s", repr(raw_admins_env))
    
    settings = get_settings()
    
    # Логируем загруженных администраторов для отладки
    logger.info(
        "🔐 Loaded admin configuration: admins=%s allowed_admins=%s",
        settings.admins,
        settings.allowed_admins,
    )
    if not settings.allowed_admins:
        logger.warning(
            "⚠️ WARNING: No administrators configured! "
            "Set ADMINS environment variable with comma-separated user IDs (e.g., ADMINS=123456789,987654321)"
        )
    
    # Логируем настройки уведомлений
    raw_chat_id = os.getenv("NOTIFICATIONS_CHAT_ID", "NOT_SET")
    raw_topic_id = os.getenv("NOTIFICATIONS_TOPIC_ID", "NOT_SET")
    logger.info(
        "📢 Notifications config: raw_chat_id=%s raw_topic_id=%s parsed_chat_id=%s parsed_topic_id=%s",
        repr(raw_chat_id),
        repr(raw_topic_id),
        settings.notifications_chat_id,
        settings.notifications_topic_id,
    )
    if settings.notifications_chat_id:
        logger.info(
            "📢 Notifications enabled: chat_id=%s topic_id=%s",
            settings.notifications_chat_id,
            settings.notifications_topic_id,
        )
    else:
        logger.warning("📢 Notifications disabled: NOTIFICATIONS_CHAT_ID not set or invalid")

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
        logger.info("🗄️ Connecting to PostgreSQL database...")
        
        # Сначала запускаем автоматические миграции
        logger.info("🔄 Starting database migrations check...")
        migrations_ok = await run_migrations()
        if not migrations_ok:
            logger.warning("⚠️ Migrations failed, but continuing...")
        else:
            logger.info("✅ Migrations check completed successfully, continuing bot startup...")
        
        # Затем подключаемся через asyncpg для работы бота
        db_connected = await db_service.connect()
        if db_connected:
            logger.info("✅ Database connection established")
        else:
            logger.warning(
                "⚠️ Database connection failed. Bot will work without local caching. "
                "Check DATABASE_URL in your .env file."
            )
    else:
        logger.info("🗄️ Database not configured (DATABASE_URL not set), running without local cache")

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
        logger.info(
            "🌐 Webhook server will be started on port %d (WEBHOOK_SECRET=%s)",
            settings.webhook_port,
            "configured" if settings.webhook_secret else "not set (insecure!)"
        )
        webhook_task = asyncio.create_task(run_webhook_server(bot, settings.webhook_port))
    else:
        logger.info("🌐 Webhook server disabled (WEBHOOK_PORT not set)")

    # Запускаем health checker для панели
    health_checker = PanelHealthChecker(bot, check_interval=60)
    health_checker_task = asyncio.create_task(health_checker.start())
    
    # Сохраняем health checker в состоянии диспетчера для доступа из обработчиков
    dp["health_checker"] = health_checker
    
    # Инициализируем сервис динамической конфигурации (если БД подключена)
    if db_connected:
        logger.info("⚙️ Initializing dynamic config service...")
        config_initialized = await config_service.initialize()
        if config_initialized:
            logger.info("✅ Dynamic config service initialized")
        else:
            logger.warning("⚠️ Dynamic config service initialization failed, using .env only")

    # Запускаем сервис синхронизации (если БД подключена)
    if db_connected:
        logger.info("🔄 Starting data sync service...")
        await sync_service.start()

    logger.info("🤖 Starting bot")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        # Останавливаем sync service
        if sync_service.is_running:
            logger.info("🔄 Stopping sync service")
            await sync_service.stop()
        
        # Останавливаем health checker
        logger.info("🏥 Stopping panel health checker")
        health_checker.stop()
        health_checker_task.cancel()
        try:
            await health_checker_task
        except asyncio.CancelledError:
            pass
        
        # Останавливаем webhook сервер при остановке бота
        if webhook_task:
            logger.info("🌐 Stopping webhook server")
            webhook_task.cancel()
            try:
                await webhook_task
            except asyncio.CancelledError:
                pass
        
        # Закрываем подключение к базе данных
        if db_service.is_connected:
            logger.info("🗄️ Closing database connection")
            await db_service.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")

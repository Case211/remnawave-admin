import asyncio
import os
import signal
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
import uvicorn

from src.config import get_settings
from shared.internal_api import internal_api_client
from shared.config_service import config_service
from shared.database import db_service
from src.services.health_check import PanelHealthChecker
from src.services.report_scheduler import init_report_scheduler
from src.services.bot_callbacks import app as callbacks_app
from src.services.webhook import app as webhook_app
from src.utils.auth import AdminMiddleware
from src.utils.i18n import get_i18n_middleware
from shared.logger import logger
from src.handlers import register_handlers


async def run_migrations() -> bool:
    """
    Запускает миграции Alembic автоматически при старте.
    Возвращает True если миграции успешны или не требуются.
    """
    import traceback as _tb

    try:
        from alembic.config import Config
        from alembic import command
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, text
        import asyncio

        settings = get_settings()
        if not settings.database_url:
            return True

        # Normalise URL to sync psycopg2 driver
        raw_url = str(settings.database_url)
        if raw_url.startswith("postgresql+asyncpg://"):
            db_url = raw_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        elif raw_url.startswith("postgresql://"):
            db_url = raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        else:
            db_url = raw_url

        def _run_migrations_sync():
            """Синхронная функция для запуска в executor."""
            engine = None
            try:
                engine = create_engine(
                    db_url,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                )

                # Multi-head aware: панель может содержать ревизии от
                # установленных плагинов (отдельные ветки в alembic-графе).
                # У бота нет своих entry_points для plugin-миграций, но он
                # должен корректно жить с ними в alembic_version.
                with engine.connect() as conn:
                    ctx = MigrationContext.configure(conn)
                    current_heads = set(ctx.get_current_heads() or ())

                # Настраиваем Alembic
                alembic_cfg = Config("alembic.ini")
                alembic_cfg.set_main_option("sqlalchemy.url", db_url)

                script = ScriptDirectory.from_config(alembic_cfg)
                heads = set(script.get_heads())

                pending = heads - current_heads
                # unresolvable — ревизии из alembic_version, которых нет в
                # нашем графе вообще (плагин-ветки, чей wheel не загружен).
                # Сравниваем со ВСЕМИ известными ревизиями (walk_revisions),
                # не только головами, иначе 0069 (когда голова 0071) попал бы
                # сюда и был бы стёрт.
                known_revs = {sc.revision for sc in script.walk_revisions()}
                unresolvable = current_heads - known_revs
                if unresolvable:
                    logger.info(
                        "ℹ️  В БД есть ревизии, неизвестные коду бота: %s — это плагин-ветки от панели, бот их не трогает",
                        sorted(unresolvable),
                    )

                if not pending:
                    logger.info("📊 БД-схема: %s (актуальна)",
                                ", ".join(sorted(current_heads)) or "пусто")
                    return True

                logger.info("📊 БД-схема: %s → миграции: %s",
                            ", ".join(sorted(current_heads)) or "пусто",
                            ", ".join(sorted(pending)))

                # Одно соединение — используем его и в main.py, и в env.py
                # (env.py проверяет config.attributes['connection'])
                connection = engine.connect()
                try:
                    alembic_cfg.attributes['connection'] = connection
                    # unresolvable-ревизии (плагин-ветки, чей wheel не
                    # загружен) неразрешимы в графе, а alembic при upgrade
                    # обязан разрезолвить ВСЕ текущие головы — иначе падает и
                    # блокирует собственные pending-миграции. Отцепляем
                    # только их (никогда не известную панельную ревизию) на
                    # время апгрейда и возвращаем после, в одной транзакции:
                    # запись плагина в alembic_version сохраняется.
                    if unresolvable:
                        connection.execute(
                            text("DELETE FROM alembic_version WHERE version_num = ANY(:s)"),
                            {"s": list(unresolvable)},
                        )
                    command.upgrade(alembic_cfg, "heads")
                    if unresolvable:
                        connection.execute(
                            text(
                                "INSERT INTO alembic_version (version_num) VALUES (:v) "
                                "ON CONFLICT DO NOTHING"
                            ),
                            [{"v": s} for s in unresolvable],
                        )
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
                finally:
                    connection.close()

                with engine.connect() as conn:
                    ctx = MigrationContext.configure(conn)
                    new_heads = set(ctx.get_current_heads() or ())
                    logger.info(
                        "✅ Migrated: %s → %s",
                        sorted(current_heads) or "None",
                        sorted(new_heads),
                    )

                return True

            finally:
                if engine:
                    engine.dispose(close=True)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run_migrations_sync)
        return result

    except Exception as e:
        logger.error("❌ Migration failed: %s", e)
        logger.error("❌ Migration traceback:\n%s", _tb.format_exc())
        return False


async def check_api_connection() -> bool:
    """Проверяет подключение к API с повторными попытками."""
    from src.config import get_settings
    settings = get_settings()
    max_attempts = 5
    delay = 3

    api_url = str(settings.api_base_url).rstrip("/")

    for attempt in range(1, max_attempts + 1):
        try:
            await internal_api_client.get_health()
            logger.debug("API connection OK (%s)", api_url)
            return True
        except Exception as exc:
            logger.warning(
                "❌ API connection failed (%d/%d): %s",
                attempt, max_attempts, exc
            )
            if attempt < max_attempts:
                await asyncio.sleep(delay)
            else:
                if internal_api_client.proxy_mode:
                    import os as _os
                    backend_url = _os.environ.get("INTERNAL_API_BACKEND_URL", "http://web-backend:8081")
                    logger.error(
                        "❌ Cannot connect to API (proxy mode). Check web-backend at %s (INTERNAL_API_BACKEND_URL) and that INTERNAL_API_SECRET matches between bot and backend. Error: %s",
                        backend_url,
                        exc
                    )
                else:
                    logger.error(
                        "❌ Cannot connect to API (direct mode). Check API_BASE_URL and API_TOKEN. Error: %s",
                        exc
                    )
                return False

    return False


async def run_webhook_server(bot: Bot, port: int) -> None:
    """Запускает webhook и callback серверы в фоновом режиме."""
    webhook_app.state.bot = bot
    # Merge callbacks routes into webhook_app so both are served on one port
    webhook_app.include_router(callbacks_app.router)

    import logging as _logging

    # Фильтр для подавления шумных логов uvicorn
    class _UvicornNoiseFilter(_logging.Filter):
        def filter(self, record):
            msg = str(record.getMessage())
            if "Invalid HTTP request" in msg:
                return False
            if "/api/v1/connections/" in msg or "/api/v2/collector/" in msg:
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

    # Конфигурация администраторов (штатные значения — в сводке запуска)
    if not settings.allowed_admins:
        logger.warning("⚠️ No administrators configured! Set ADMINS env var")

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
        migrations_ok = await run_migrations()
        if not migrations_ok:
            logger.warning(
                "⚠️ Database migrations failed — the application will start "
                "but features requiring newer schema may not work. "
                "Check the migration traceback above for details."
            )
        db_connected = await db_service.connect()
        if db_connected:
            # сам факт коннекта логирует db-слой («Database connection established»)
            # VACUUM ANALYZE runs in web-backend only (avoid double maintenance)
            pass
        else:
            logger.warning("⚠️ Database connection failed, running without cache")
    else:
        logger.info("🗄️ Database not configured, running without cache")

    # parse_mode is left as default (None) to avoid HTML parsing issues with plain text translations
    # proxy=None — штатное значение aiogram, поэтому ветвиться незачем:
    # без BOT_PROXY_URL сессия создаётся ровно как раньше.
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(settings.bot_api_root),
        proxy=settings.bot_proxy_url.unicode_string() if settings.bot_proxy_url else None,
    )
    bot = Bot(token=settings.bot_token, session=session)
    dp = Dispatcher(storage=MemoryStorage())

    # middlewares
    # Сначала i18n middleware (нужен для переводов в AdminMiddleware)
    dp.message.middleware(get_i18n_middleware())
    dp.callback_query.middleware(get_i18n_middleware())
    # Затем проверка администратора (блокирует неавторизованных пользователей)
    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(AdminMiddleware())

    register_handlers(dp)
    dp.shutdown.register(internal_api_client.close)

    # Запускаем webhook сервер в фоне, если настроен порт
    webhook_task = None
    if settings.webhook_port:
        try:
            webhook_task = asyncio.create_task(run_webhook_server(bot, settings.webhook_port))
        except Exception as exc:
            logger.error("Failed to start webhook server: %s", exc, exc_info=True)
            webhook_task = None
            # Don't exit the bot if webhook fails - it's optional

    # Запускаем health checker для панели
    health_checker = PanelHealthChecker(bot, check_interval=60)
    health_checker_task = asyncio.create_task(health_checker.start())
    dp["health_checker"] = health_checker

    # MaxMind GeoIP databases are downloaded by web-backend/collector (shared geoip volume)

    # Инициализируем сервисы (если БД подключена)
    if db_connected:
        config_initialized = await config_service.initialize()
        if config_initialized:
            # config_service сам логирует «Dynamic config: N settings loaded»
            # Интервал из настройки (как в web-backend), а не хардкод — иначе
            # UI-значение config_auto_reload_interval на бот не влияло.
            reload_interval = int(config_service.get("config_auto_reload_interval", 30) or 30)
            config_service.start_auto_reload(interval_seconds=reload_interval)

        # sync_service запускается только в web-backend (единый источник синхронизации)

        report_scheduler = init_report_scheduler(bot)
        await report_scheduler.start()  # сам логирует «Report scheduler started»
    else:
        report_scheduler = None

    # ── Сводка запуска ─────────────────────────────────────────────
    try:
        _ver_path = Path("/app/VERSION")
        if not _ver_path.exists():
            _ver_path = Path(__file__).resolve().parent.parent / "VERSION"
        _version = _ver_path.read_text(encoding="utf-8").strip() if _ver_path.exists() else "unknown"
        api_mode = "proxy (RBAC)" if os.environ.get("INTERNAL_API_SECRET") else "direct (legacy)"
        logger.info("─" * 62)
        logger.info("🤖 Remnawave Admin v%s — Bot готов", _version)
        logger.info("   API: %s · БД: %s · Вебхук: %s",
                    api_mode,
                    "ok" if db_connected else "OFF",
                    f"порт {settings.webhook_port}" if settings.webhook_port else "выкл")
        logger.info("   Админы: %d · Уведомления: %s · Отчёты: %s",
                    len(settings.allowed_admins or []),
                    settings.notifications_chat_id or "выкл",
                    "вкл" if report_scheduler and report_scheduler.is_running else "выкл")
        logger.info("─" * 62)
    except Exception as e:  # сводка не должна уметь ронять старт
        logger.debug("Startup summary failed: %s", e)

    # Graceful shutdown: use an event so SIGTERM/SIGINT stop polling cleanly
    shutdown_event = asyncio.Event()

    def _signal_handler(sig: signal.Signals) -> None:
        logger.info("Received %s, initiating graceful shutdown...", sig.name)
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler, sig)

    # Надзор за фоновыми тасками: тихая смерть цикла должна попадать в логи
    def _watch(name: str, task: asyncio.Task | None) -> None:
        if task is None:
            return

        def _on_done(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                logger.error("Background task %r crashed: %s", name, exc, exc_info=exc)
            else:
                logger.warning("Background task %r exited unexpectedly", name)

        task.add_done_callback(_on_done)

    _watch("webhook_server", webhook_task)
    _watch("health_checker", health_checker_task)

    # Run polling in a task so we can cancel it on signal
    polling_task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    )

    # Ждём сигнал ИЛИ падение поллинга. Раньше main() ждал только
    # shutdown_event: упавший polling оставлял бот «живым», но мёртвым —
    # без единой строки в логах до самого рестарта контейнера.
    shutdown_wait_task = asyncio.create_task(shutdown_event.wait())
    done, _pending = await asyncio.wait(
        {polling_task, shutdown_wait_task}, return_when=asyncio.FIRST_COMPLETED,
    )
    if polling_task in done and not shutdown_event.is_set():
        exc = polling_task.exception() if not polling_task.cancelled() else None
        if exc is not None:
            logger.critical("Polling crashed — shutting down: %s", exc, exc_info=exc)
        else:
            logger.critical("Polling stopped unexpectedly — shutting down")
    shutdown_wait_task.cancel()

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
    config_service.stop_auto_reload()
    if report_scheduler and report_scheduler.is_running:
        await report_scheduler.stop()
    if webhook_task:
        webhook_task.cancel()
        try:
            await webhook_task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("Webhook task cleanup error: %s", exc)
    if db_service.is_connected:
        await db_service.disconnect()
    logger.info("👋 Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass

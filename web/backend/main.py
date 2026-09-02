"""
Remnawave Admin Web Panel - FastAPI Application.

This is the main entry point for the web panel backend.
It provides REST API and WebSocket endpoints for the admin dashboard.
"""
import asyncio
import gzip
import logging
import os
import shutil
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

# Add project root to path for importing src modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from web.backend.core.config import get_web_settings
from web.backend.core.ip_whitelist import get_allowed_ips, is_ip_allowed
from web.backend.core.rate_limit import limiter
from web.backend.core.update_checker import get_latest_version
from web.backend.api.v2 import auth, users, nodes, analytics, violations, hosts, websocket
from web.backend.api.v2 import settings as settings_api
from web.backend.api.v2 import diagnostics as diagnostics_api
from web.backend.api.v2 import admins as admins_api, roles as roles_api
from web.backend.api.v2 import access_policies as access_policies_api
from web.backend.api.v2 import audit as audit_api
from web.backend.api.v2 import logs as logs_api
from web.backend.api.v2 import advanced_analytics
from web.backend.api.v2 import automations as automations_api
from web.backend.api.v2 import notifications as notifications_api
from web.backend.api.v2 import me_devices as me_devices_api
from web.backend.api.v2 import mailserver as mailserver_api
from web.backend.api.v2 import agent_ws as agent_ws_api
from web.backend.api.v2 import fleet as fleet_api
from web.backend.api.v2 import terminal as terminal_api
from web.backend.api.v2 import scripts as scripts_api
from web.backend.api.v2 import templates as templates_api
from web.backend.api.v2 import snippets as snippets_api
from web.backend.api.v2 import config_profiles as config_profiles_api
from web.backend.api.v2 import user_presets as user_presets_api
from web.backend.api.v2 import finance as finance_api
from web.backend.api.v2 import dns as dns_api
from web.backend.api.v2 import bscheck as bscheck_api
from web.backend.api.v2 import reputation as reputation_api
from web.backend.api.v2 import reports as reports_api
from web.backend.api.v2 import asn as asn_api
from web.backend.api.v2 import collector as collector_api
from web.backend.api.v2 import backup as backup_api
from web.backend.api.v2 import api_keys as api_keys_api
from web.backend.api.v2 import blocked_ips as blocked_ips_api
from web.backend.api.v2 import webhooks as webhooks_api
from web.backend.api.v2 import squads as squads_api
from web.backend.api.v2.bedolaga import router as bedolaga_router
from web.backend.api.v2 import plugins as plugins_api
from web.backend.api.v2 import internal as internal_api
from web.backend.core import plugins as plugin_loader
from web.backend.api.v3 import public as public_api_v3


# ── Logging setup (structlog) ────────────────────────────────────

_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5
_LOG_DIR = Path("/app/logs")

# Короткие имена для сторонних логгеров
_LOGGER_NAME_MAP = {
    "uvicorn.error": "uvicorn",
    "uvicorn.access": "uvicorn",
    "web.backend.api.deps": "web",
    "web.backend.core.api_helper": "web",
    "httpx": "http",
    "httpcore": "http",
    "asyncpg": "db",
    "alembic": "migration",
    "sqlalchemy": "db",
}


class _CompressedRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler с gzip-сжатием ротированных файлов."""

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None

        for i in range(self.backupCount - 1, 0, -1):
            sfn = self.rotation_filename(f"{self.baseFilename}.{i}.gz")
            dfn = self.rotation_filename(f"{self.baseFilename}.{i + 1}.gz")
            if os.path.exists(sfn):
                if os.path.exists(dfn):
                    os.remove(dfn)
                os.rename(sfn, dfn)

        dfn = self.rotation_filename(f"{self.baseFilename}.1.gz")
        if os.path.exists(dfn):
            os.remove(dfn)
        if os.path.exists(self.baseFilename):
            with open(self.baseFilename, "rb") as f_in:
                with gzip.open(dfn, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            with open(self.baseFilename, "w"):
                pass

        if not self.delay:
            self.stream = self._open()


def _shorten_logger_name(logger: object, method_name: str, event_dict: dict) -> dict:
    """structlog processor: сокращает имена логгеров."""
    name = event_dict.get("logger", "")
    for prefix, short in _LOGGER_NAME_MAP.items():
        if name == prefix or name.startswith(prefix + "."):
            event_dict["logger"] = short
            return event_dict
    if "." in name:
        event_dict["logger"] = name.rsplit(".", 1)[-1]
    return event_dict


def _compact_kv(logger: object, method_name: str, event_dict: dict) -> dict:
    """structlog processor: компактный формат для api_call и api_error."""
    event = event_dict.get("event", "")
    if event == "api_call":
        method = event_dict.pop("method", "")
        endpoint = event_dict.pop("endpoint", "")
        status = event_dict.pop("status_code", "")
        duration = event_dict.pop("duration_ms", "")
        parts = []
        if method and endpoint:
            parts.append(f"{method} {endpoint}")
        if status:
            parts.append(f"→ {status}")
        if duration:
            parts.append(f"({duration}ms)")
        event_dict["event"] = " ".join(parts) if parts else event
    elif event == "api_error":
        method = event_dict.pop("method", "")
        endpoint = event_dict.pop("endpoint", "")
        status = event_dict.pop("status_code", "")
        error = event_dict.pop("error", "")
        parts = []
        if method and endpoint:
            parts.append(f"{method} {endpoint}")
        if status:
            parts.append(f"→ {status}")
        if error:
            parts.append(f"| {error}")
        event_dict["event"] = " ".join(parts) if parts else event
    return event_dict


# Цвета уровней логирования (ANSI)
_LEVEL_STYLES = {
    "critical": "\033[1;91m",   # bold bright red
    "exception": "\033[1;91m",  # bold bright red
    "error": "\033[91m",        # bright red
    "warn": "\033[93m",         # bright yellow
    "warning": "\033[93m",      # bright yellow
    "info": "\033[36m",         # cyan
    "debug": "\033[2;37m",      # dim white
    "notset": "\033[2m",        # dim
}


def _make_console_renderer() -> structlog.dev.ConsoleRenderer:
    """Создаёт ConsoleRenderer с красивым форматированием."""
    return structlog.dev.ConsoleRenderer(
        colors=True,
        force_colors=True,
        pad_event_to=40,
        level_styles=_LEVEL_STYLES,
    )


def _setup_web_logging():
    """Настраивает structlog логирование для web backend."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    console_level_name = os.environ.get("WEB_LOG_LEVEL", "INFO").upper()
    console_level = getattr(logging, console_level_name, logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # Console: цветной вывод
    console = logging.StreamHandler()
    console.setLevel(console_level)
    # Пульс коллектора (Batch received/upserted) — только в файлы/UI,
    # docker-вывод он превращает в стену шума
    from shared.logger import ConsoleNoiseFilter
    console.addFilter(ConsoleNoiseFilter())
    console.setFormatter(structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _shorten_logger_name,
            _compact_kv,
            _make_console_renderer(),
        ],
        foreign_pre_chain=shared_processors,
    ))
    root.addHandler(console)

    # File handler: JSON формат
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)

        json_formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                _shorten_logger_name,
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=shared_processors,
        )

        backend_path = _LOG_DIR / "backend.log"
        backend_h = _CompressedRotatingFileHandler(
            str(backend_path),
            maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8",
        )
        backend_h.setLevel(logging.INFO)
        backend_h.setFormatter(json_formatter)
        root.addHandler(backend_h)

        # Violations log (фильтрует записи о нарушениях из collector, violation_detector и т.д.)
        from shared.logger import ViolationLogFilter
        violations_path = _LOG_DIR / "violations.log"
        violations_h = _CompressedRotatingFileHandler(
            str(violations_path),
            maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8",
        )
        violations_h.setLevel(logging.DEBUG)
        violations_h.setFormatter(json_formatter)
        violations_h.addFilter(ViolationLogFilter())
        root.addHandler(violations_h)

        _verify_ok = backend_path.exists() and os.access(backend_path, os.W_OK)
        print(
            f"[LOGGING] File logging active: {_LOG_DIR} "
            f"(writable={_verify_ok})",
            file=sys.stderr,
            flush=True,
        )
    except OSError as exc:
        root.warning("Cannot create log files (%s), logging to console only", exc)
        print(
            f"[LOGGING] File logging DISABLED: {exc}. "
            f"Check that the volume mount is correct (./logs:/app/logs, NOT .logs:/app/logs)",
            file=sys.stderr,
            flush=True,
        )

    # Подавляем шумные логгеры
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Конфигурируем structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


_setup_web_logging()
logger = logging.getLogger("web")


# ── Database migrations ───────────────────────────────────────────


def _augment_with_plugin_versions(alembic_cfg) -> None:
    """Append plugin-contributed version_locations onto the alembic config.

    Mirrors what ``alembic/env.py`` does at runtime, but applied to the
    in-process Config so the static ScriptDirectory check in
    :func:`_run_migrations` sees plugin branches too. Without this the
    early "schema up to date" gate would only know about panel revisions
    and skip pending plugin migrations on every restart.
    """
    try:
        from importlib.metadata import entry_points
    except Exception:
        return

    locations: list[str] = []
    try:
        try:
            eps = list(entry_points(group="rwa.plugin.migrations"))
        except TypeError:
            eps = list(entry_points().get("rwa.plugin.migrations", []))
    except Exception:
        return

    for ep in eps:
        try:
            target = ep.load()
            path = target() if callable(target) else target
        except Exception:
            continue
        if not path:
            continue
        path_str = str(path)
        if os.path.isdir(path_str):
            locations.append(path_str)

    if not locations:
        return

    panel_versions = str(PROJECT_ROOT / "alembic" / "versions")
    all_locations = [panel_versions] + locations
    # Alembic accepts ``version_locations`` as an os.pathsep-separated
    # string or a space-separated one. We use os.pathsep for safety on
    # Windows (semicolon) vs Linux (colon).
    alembic_cfg.set_main_option("version_locations", os.pathsep.join(all_locations))


async def _run_migrations(database_url: str) -> bool:
    """
    Run Alembic migrations automatically on startup.
    Returns True if migrations succeed or are not needed.
    """
    import traceback as _tb

    try:
        from alembic.config import Config
        from alembic import command
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, text

        from shared.migration_lock import MIGRATION_LOCK_KEY

        # Normalise URL to sync psycopg2 driver
        raw_url = str(database_url)
        if raw_url.startswith("postgresql+asyncpg://"):
            db_url = raw_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        elif raw_url.startswith("postgresql://"):
            db_url = raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        else:
            db_url = raw_url

        def _run_sync():
            engine = None
            lock_conn = None
            try:
                engine = create_engine(
                    db_url,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                )

                # Панель, коллектор и бот стартуют одновременно и лезут в
                # alembic_version втроём. Каждый на время апгрейда убирает
                # оттуда плагинные ветки и возвращает их обратно — и пока
                # один планировал путь, другой уже вернул чужую ревизию:
                # «Can't locate revision identified by 'sst_002'» и старт с
                # ограниченной функциональностью. Блокировка выстраивает их
                # в очередь; дождавшийся видит схему уже применённой и
                # просто выходит. Ключ произвольный, но общий для всех трёх.
                lock_conn = engine.connect()
                lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": MIGRATION_LOCK_KEY})
                lock_conn.commit()

                with engine.connect() as conn:
                    ctx = MigrationContext.configure(conn)
                    current_heads = set(ctx.get_current_heads() or ())

                alembic_cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
                alembic_cfg.set_main_option("sqlalchemy.url", db_url)
                # Augment config with plugin migration paths *before* the
                # static head check below — env.py also discovers them at
                # ``command.upgrade`` time, but the early "schema up to
                # date" gate looks at ScriptDirectory which only sees
                # what's in alembic.ini. Without this every plugin branch
                # was invisible to the gate and migrations were skipped.
                _augment_with_plugin_versions(alembic_cfg)

                script = ScriptDirectory.from_config(alembic_cfg)
                heads = set(script.get_heads())

                pending = heads - current_heads
                # ``unresolvable`` = revisions stamped in alembic_version
                # that don't exist in our script graph at all — plugin
                # branches whose wheel isn't loaded this run. Compared
                # against *all* known revisions (walk_revisions), not just
                # heads, so a panel revision the DB merely sits behind
                # (e.g. 0069 while head is 0071) is NOT misclassified and
                # wiped. The plugin's pip install lands later in the
                # lifespan and reconciles its branch then.
                known_revs = {sc.revision for sc in script.walk_revisions()}
                unresolvable = current_heads - known_revs
                if unresolvable:
                    logger.info(
                        "Revisions present in DB but unknown to current code: %s "
                        "(plugin not loaded yet — will be reconciled after install)",
                        sorted(unresolvable),
                    )

                if not pending:
                    logger.info("📊 БД-схема: %s (актуальна)",
                                ", ".join(sorted(current_heads)) or "пусто")
                    return True

                logger.info("📊 БД-схема: %s → миграции: %s",
                            ", ".join(sorted(current_heads)) or "пусто",
                            ", ".join(sorted(pending)))

                connection = engine.connect()
                try:
                    alembic_cfg.attributes["connection"] = connection
                    # ``unresolvable`` heads are plugin branches whose wheel
                    # isn't loaded this run; ``alembic upgrade`` must resolve
                    # *every* current head to plan the path — so an unknown
                    # one would crash and block the panel's own pending
                    # migrations. Detach only those (never a known panel
                    # revision) for the upgrade and restore them after, in
                    # one transaction; the plugin's later pip install
                    # re-grafts its branch, so its migration record survives.
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
                        "Migrated: %s -> %s",
                        sorted(current_heads) or "None",
                        sorted(new_heads),
                    )

                return True

            finally:
                if lock_conn is not None:
                    try:
                        lock_conn.execute(
                            text("SELECT pg_advisory_unlock(:k)"), {"k": MIGRATION_LOCK_KEY}
                        )
                        lock_conn.commit()
                    except Exception:
                        # Соединение уже мертво — блокировка снимется сама
                        # вместе с сессией.
                        pass
                    lock_conn.close()
                if engine:
                    engine.dispose(close=True)

        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _run_sync)

    except Exception as e:
        logger.error("Migration failed: %s", e)
        logger.error("Migration traceback:\n%s", _tb.format_exc())
        return False


# ── FastAPI app ───────────────────────────────────────────────────

_bg_tasks: list[asyncio.Task] = []  # Background tasks to cancel on shutdown
_bg_names: list[str] = []           # Имена поднятых циклов — для сводки запуска


def _bg(name: str, coro) -> None:
    """Запустить фоновый цикл под надзором.

    Раньше 12 планировщиков стартовали молча (create_task без единого лога),
    а их тихая смерть оставалась незамеченной. Теперь: имя попадает в сводку
    запуска, а неожиданное завершение таска логируется ошибкой с трейсом.
    """
    task = asyncio.create_task(coro, name=name)

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return  # штатная остановка на shutdown
        exc = t.exception()
        if exc is not None:
            logger.error("Background loop %r crashed: %s", name, exc,
                         exc_info=exc)
        else:
            logger.warning("Background loop %r exited unexpectedly", name)

    task.add_done_callback(_on_done)
    _bg_tasks.append(task)
    _bg_names.append(name)

def _get_app_mode() -> str:
    """Get application mode: 'api', 'collector', or 'full' (default)."""
    return os.environ.get("APP_MODE", "full").lower()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_web_settings()
    app_mode = _get_app_mode()
    mode_label = {"api": "API-only", "collector": "Collector-only", "full": "Full"}.get(app_mode, "Full")
    logger.info("🚀 Web API starting on %s:%s (mode: %s)", settings.host, settings.port, mode_label)

    # Connect to database if configured
    database_url = os.environ.get("DATABASE_URL") or getattr(settings, "database_url", None)
    if database_url:
        # Run pending Alembic migrations before connecting
        migration_ok = await _run_migrations(database_url)
        if not migration_ok:
            logger.warning("Some migrations failed — app will start but may have limited functionality")

        try:
            from shared.database import db_service
            connected = await db_service.connect(database_url=database_url)
            if connected:
                # сам факт коннекта логирует db-слой; здесь собираем сводку
                _svc_names: list[str] = []

                # First-run admin setup
                # Verify RBAC tables exist
                from web.backend.core.rbac import ensure_rbac_tables, sync_superadmin_permissions
                await ensure_rbac_tables()

                # Ensure superadmin role has all permissions from AVAILABLE_RESOURCES
                # (auto-adds new resources/actions when code is updated)
                await sync_superadmin_permissions()

                # Initialize dynamic config service (DB settings cache)
                from shared.config_service import config_service
                await config_service.initialize()
                # Авто-reload конфига из БД для ВСЕХ режимов. В split-режиме (APP_MODE=collector/api
                # в разных процессах) collector иначе держит stale-кэш и не видит правок настроек
                # из UI (их обслуживает api-процесс) до рестарта контейнера.
                config_service.start_auto_reload(
                    int(config_service.get("config_auto_reload_interval", 30) or 30)
                )

                # ── Services for API and full mode ──
                if app_mode in ("api", "full"):
                    from web.backend.core.automation_engine import engine as automation_engine
                    await automation_engine.start()
                    _svc_names.append("automation")

                    from web.backend.core.alert_engine import alert_engine
                    await alert_engine.start()
                    _svc_names.append("alerts")

                    try:
                        from web.backend.core.mail.mail_service import mail_service
                        await mail_service.start()
                        _svc_names.append("mail")
                    except Exception as e:
                        logger.warning("Mail service start failed: %s", e)

                    from web.backend.api.v2.websocket import dashboard_publisher_loop
                    _bg("dashboard_publisher", dashboard_publisher_loop())

                    from web.backend.core.task_scheduler import task_scheduler_loop
                    _bg("task_scheduler", task_scheduler_loop())

                    from web.backend.core.backup_service import backup_scheduler_loop
                    _bg("backup_scheduler", backup_scheduler_loop())

                    from web.backend.core.bscheck_scheduler import bscheck_scheduler_loop
                    _bg("bscheck_scheduler", bscheck_scheduler_loop())

                    from web.backend.core.attack_detector import attack_detector_loop
                    _bg("attack_detector", attack_detector_loop())

                    from web.backend.core.throttle_sync import throttle_sync_loop
                    _bg("throttle_sync", throttle_sync_loop())

                    from web.backend.core.finance.rates import rates_update_loop
                    _bg("finance_rates", rates_update_loop())

                    from web.backend.core.finance.reminders import reminders_loop
                    _bg("finance_reminders", reminders_loop())

                    from web.backend.core.finance.sync import autosync_loop
                    _bg("finance_autosync", autosync_loop())

                    from web.backend.core.finance.bedolaga_income import deposits_loop
                    _bg("bedolaga_deposits", deposits_loop())

                # ── Services for collector and full mode ──
                if app_mode in ("collector", "full"):
                    async def _baseline_refresh_loop():
                        await asyncio.sleep(300)
                        while True:
                            try:
                                stale_users = await db_service.get_stale_baseline_users(max_age_seconds=3600, limit=50)
                                if stale_users:
                                    from shared.violation_detector import UserProfileAnalyzer
                                    analyzer = UserProfileAnalyzer(db_service)
                                    for user_uuid in stale_users:
                                        try:
                                            await analyzer.build_baseline(user_uuid, days=30)
                                        except Exception:
                                            pass
                                    logger.debug("Refreshed %d user baselines", len(stale_users))
                            except Exception as exc:
                                logger.warning("Baseline refresh failed: %s", exc)
                            await asyncio.sleep(1800)
                    _bg("baseline_refresh", _baseline_refresh_loop())

                    # C3: периодический HWID-скан. Детектор по батчам node-agent проверяет только
                    # юзеров с активными подключениями СЕЙЧАС, поэтому кросс-аккаунт HWID у оффлайн-
                    # абузеров не ловится. Этот цикл периодически ставит юзеров с общими HWID в очередь.
                    async def _hwid_scan_loop():
                        from web.backend.api.v2.collector import _enqueue_violation_users, _shared_hwid_user_uuids
                        await asyncio.sleep(600)
                        while True:
                            try:
                                if config_service.get("violations_enabled", True) and config_service.get("violations_analyzer_hwid", True):
                                    groups = await db_service.get_shared_hwids(min_users=2, limit=1000)
                                    uuids = _shared_hwid_user_uuids(groups)
                                    if uuids:
                                        _enqueue_violation_users(uuids)
                                        logger.info("HWID scan: %d users sharing HWIDs enqueued for violation check", len(uuids))
                            except Exception as exc:
                                logger.warning("HWID scan loop failed: %s", exc)
                            interval = int(config_service.get("violations_hwid_scan_interval_minutes", 30) or 30)
                            await asyncio.sleep(max(5, interval) * 60)
                    _bg("hwid_scan", _hwid_scan_loop())

                    # Сторож чёрного списка HWID. Скан выше идёт от устройств,
                    # присланных нодами, и блокирует однократно; подписку после
                    # этого может поднять что угодно — привязка telegram_id к
                    # email-подписке уже поднимала. Сторож ходит от самого
                    # списка и гасит воскресшие подписки снова.
                    from web.backend.core.hwid_guard import loop as _hwid_guard_loop
                    _bg("hwid_blacklist_guard", _hwid_guard_loop())

                    # Сторож адресов. HWID клиент называет сам и подделывает
                    # заголовком, адрес выдаёт провайдер — по нему повторные
                    # пробные видно даже там, где железо каждый раз «новое».
                    from web.backend.core.ip_guard import loop as _ip_guard_loop
                    _bg("ip_trial_guard", _ip_guard_loop())

                # ── Services for all modes ──
                async def _maintenance_loop():
                    while True:
                        await asyncio.sleep(6 * 3600)
                        try:
                            await db_service.run_table_maintenance()
                            logger.info("Periodic table maintenance completed")
                        except Exception as exc:
                            logger.warning("Table maintenance failed: %s", exc)
                        # M5: retention-очистка по расписанию, независимо от ingest
                        # коллектора — иначе при простое нод старые данные не чистятся.
                        # cleanup-методы идемпотентны, дубль с collector-путём безопасен.
                        try:
                            v_days = int(config_service.get("violation_retention_days", 90) or 90)
                            c_days = int(config_service.get("connections_retention_days", 30) or 30)
                            t_days = int(config_service.get("torrent_retention_days", 90) or 90)
                            m_days = int(config_service.get("metrics_retention_days", 30) or 30)
                            v = await db_service.cleanup_old_violations(v_days)
                            c = await db_service.cleanup_old_connections(c_days)
                            t = await db_service.cleanup_old_torrent_events(t_days)
                            # Снапшоты метрик чистились только внутри обработчика
                            # отчёта от ноды: пока ноды шлют данные — работает,
                            # а на простое таблица росла без ограничения.
                            m = await db_service.cleanup_old_metrics_snapshots(m_days)
                            # Партиции подключений создаются заранее: если ни одна
                            # нода не отчиталась, писать новый месяц было некуда и
                            # строки уезжали в DEFAULT-партицию, которую уже не
                            # отцепить одним движением.
                            await db_service.ensure_connection_partitions(months_ahead=3)
                            if (v or 0) + (c or 0) + (t or 0) + (m or 0) > 0:
                                logger.info(
                                    "Retention cleanup: %s violations, %s connections, %s torrent events, %s metrics",
                                    v, c, t, m,
                                )
                        except Exception as exc:
                            logger.warning("Retention cleanup failed: %s", exc)
                _bg("table_maintenance", _maintenance_loop())

                # ── Plugins (api and full only) ──
                if app_mode in ("api", "full"):
                    installed = []
                    try:
                        from web.backend.core.plugin_installer import scan_and_install_wheels
                        installed = scan_and_install_wheels()
                        if installed:
                            logger.info("Plugin wheels installed: %s", installed)
                    except Exception:
                        logger.exception("Plugin wheel scan failed")

                    # Повторный прогон миграций нужен только когда реально
                    # ставились plugin-wheels — иначе он лишь дублировал в
                    # логах весь блок миграций при каждом старте
                    if installed:
                        try:
                            import importlib
                            importlib.invalidate_caches()
                            await _run_migrations(database_url)
                        except Exception:
                            logger.exception("Plugin migrations replay failed")

                    try:
                        from web.backend.core import entitlements
                        await entitlements.startup()
                        _bg("license_heartbeat", entitlements.heartbeat_loop())
                    except Exception:
                        logger.exception("Entitlements startup failed")

                    try:
                        plugin_loader.register(app)
                    except Exception:
                        logger.exception("Plugin loader failed during startup")

                    try:
                        # RBAC-ресурсы плагинов появляются в реестре только после register(),
                        # а синхронизация прав суперадмина отработала намного раньше (см. выше)
                        # и их ещё не видела. Без повторного прохода право плагина не попадает
                        # даже суперадмину, NavEntry фильтруется по нему и пункт меню не рисуется
                        # вообще — со стороны выглядит как «плагин установился, но его нет».
                        # Проход идемпотентен: добавляет только недостающие права.
                        from web.backend.core.rbac import sync_superadmin_permissions as _sync_rbac
                        await _sync_rbac()
                    except Exception:
                        logger.exception("Superadmin permission sync after plugin registration failed")

                    try:
                        plugin_tasks = plugin_loader.start_scheduled_tasks()
                        if plugin_tasks:
                            _bg_tasks.extend(plugin_tasks)
                            logger.info("Plugin scheduled tasks started: %d", len(plugin_tasks))
                    except Exception:
                        logger.exception("Plugin scheduled tasks failed to start")

                # ── Sync service (collector and full only) ──
                if app_mode in ("collector", "full"):
                    try:
                        from shared.sync import sync_service
                        await sync_service.start(background=True)
                        _svc_names.append("sync")
                    except Exception as e:
                        logger.warning("Sync service start failed: %s", e)

                    try:
                        from web.backend.core.traffic_rate_monitor import traffic_rate_monitor
                        await traffic_rate_monitor.start()
                        _svc_names.append("traffic_monitor")
                    except Exception as e:
                        logger.warning("Traffic rate monitor start failed: %s", e)

                # ── Online snapshot, metrics, blacklist (api and full) ──
                if app_mode in ("api", "full"):
                    try:
                        from web.backend.core.online_snapshot_recorder import online_snapshot_recorder
                        await online_snapshot_recorder.start()
                        _svc_names.append("online_snapshots")
                    except Exception as e:
                        logger.warning("Online snapshot recorder start failed: %s", e)

                    async def _blacklist_sync_loop():
                        await asyncio.sleep(60)
                        while True:
                            try:
                                if config_service.get("user_blacklist_enabled", False):
                                    from web.backend.api.v2.user_blacklist import sync_external_blacklists
                                    result = await sync_external_blacklists()
                                    if result.get("synced", 0) > 0:
                                        logger.info("Blacklist sync: %d entries from %d sources",
                                                    result["synced"], len(result["sources"]))
                            except Exception as exc:
                                logger.warning("Blacklist sync failed: %s", exc)
                            interval_hours = config_service.get("user_blacklist_sync_hours", 6)
                            await asyncio.sleep(int(interval_hours) * 3600)
                    _bg("blacklist_sync", _blacklist_sync_loop())

                # ── Prometheus gauge updater (all modes) ──
                try:
                    from web.backend.core.metrics import gauge_updater
                    await gauge_updater.start()
                    _svc_names.append("prometheus")
                except Exception as e:
                    logger.warning("Prometheus gauge updater start failed: %s", e)
            else:
                logger.warning("Database connection failed")
        except Exception as e:
            # Этот catch-all оборачивает старт ВСЕХ сервисов — без трейса
            # реальная причина сбоя (RBAC/планировщик/плагин…) не видна
            logger.error("Startup services initialization failed: %s", e,
                         exc_info=True)
    else:
        logger.info("No DATABASE_URL, running without database")

    # Connect to Redis cache (optional, falls back to in-memory)
    redis_url = os.environ.get("REDIS_URL") or getattr(settings, "redis_url", None)
    try:
        from web.backend.core.cache import cache
        await cache.connect(redis_url)
    except Exception as e:
        logger.warning("Cache setup failed: %s", e)

    # Upgrade rate limiter to Redis backend (optional)
    try:
        from web.backend.core.rate_limit import configure_limiter
        configure_limiter(redis_url)
    except Exception as e:
        logger.debug("Rate limiter Redis upgrade skipped: %s", e)

    # Start webhook retry worker + API key usage buffer
    try:
        from web.backend.core.webhook_security import start_retry_worker
        start_retry_worker()
    except Exception as e:
        logger.warning("Webhook retry worker start failed: %s", e)
    try:
        from web.backend.core.api_key_usage import start as start_usage_buffer
        start_usage_buffer()
    except Exception as e:
        logger.warning("API key usage buffer start failed: %s", e)

    # Ensure MaxMind GeoLite2 databases are downloaded
    # Supports: license key (official), GitHub mirror (ltsdev/maxmind), or auto
    try:
        from shared.maxmind_updater import ensure_databases
        maxmind_key = os.environ.get("MAXMIND_LICENSE_KEY")
        maxmind_source = os.environ.get("MAXMIND_SOURCE", "auto")
        city_path = os.environ.get("MAXMIND_CITY_DB", "/app/geoip/GeoLite2-City.mmdb")
        asn_path = os.environ.get("MAXMIND_ASN_DB", "/app/geoip/GeoLite2-ASN.mmdb")
        await ensure_databases(
            license_key=maxmind_key,
            city_path=city_path,
            asn_path=asn_path,
            source=maxmind_source,
        )
    except Exception as e:
        logger.warning("MaxMind DB download failed: %s", e)

    # ── Сводка запуска: одна рамка вместо россыпи строк ────────────
    try:
        try:
            _version = Path("/app/VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            _version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() \
                if (PROJECT_ROOT / "VERSION").exists() else "unknown"
        from shared.database import db_service as _dbs
        from web.backend.core.cache import cache as _cache
        db_state = "ok" if getattr(_dbs, "is_connected", False) else "OFF"
        cache_state = "redis" if getattr(_cache, "_using_redis", False) else "memory"
        logger.info("─" * 62)
        logger.info("✅ Remnawave Admin v%s — Web API готов (режим: %s)",
                    _version, mode_label)
        logger.info("   БД: %s · Кэш: %s · Слушаем: %s:%s",
                    db_state, cache_state, settings.host, settings.port)
        _services = locals().get("_svc_names") or []
        if _services:
            logger.info("   Сервисы (%d): %s", len(_services), ", ".join(_services))
        if _bg_names:
            logger.info("   Фоновые циклы (%d): %s",
                        len(_bg_names), ", ".join(_bg_names))
        logger.info("─" * 62)
    except Exception as e:  # сводка не должна уметь ронять старт
        logger.debug("Startup summary failed: %s", e)

    yield

    # Shutdown — cancel background tasks first
    for task in _bg_tasks:
        task.cancel()
    for task in _bg_tasks:
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    _bg_tasks.clear()
    _bg_names.clear()

    # Stop webhook retry worker + API key usage buffer
    try:
        from web.backend.core.webhook_security import stop_retry_worker
        await stop_retry_worker()
    except Exception:
        pass
    try:
        from web.backend.core.api_key_usage import stop as stop_usage_buffer
        await stop_usage_buffer()
    except Exception:
        pass

    try:
        from web.backend.core.cache import cache
        await cache.close()
    except Exception:
        pass
    try:
        from web.backend.core.mail.mail_service import mail_service
        await mail_service.stop()
    except Exception:
        pass
    try:
        from web.backend.core.alert_engine import alert_engine
        await alert_engine.stop()
    except Exception:
        pass
    try:
        from web.backend.core.automation_engine import engine as automation_engine
        await automation_engine.stop()
    except Exception:
        pass
    try:
        from shared.sync import sync_service
        if sync_service.is_running:
            await sync_service.stop()
    except Exception:
        pass
    try:
        from web.backend.core.traffic_rate_monitor import traffic_rate_monitor
        await traffic_rate_monitor.stop()
    except Exception:
        pass
    try:
        from web.backend.core.online_snapshot_recorder import online_snapshot_recorder
        await online_snapshot_recorder.stop()
    except Exception:
        pass
    try:
        from web.backend.core.metrics import gauge_updater
        await gauge_updater.stop()
    except Exception:
        pass
    try:
        from shared.database import db_service
        if db_service.is_connected:
            await db_service.disconnect()
    except Exception:
        pass
    try:
        from web.backend.core.api_helper import close_client
        await close_client()
    except Exception:
        pass
    logger.info("👋 Web API stopped")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    settings = get_web_settings()

    app = FastAPI(
        title="Remnawave Admin Web API",
        description="REST API for Remnawave Admin Web Panel",
        version="0.0.0",  # Dynamic version served via /api/v2/health
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
        openapi_url="/api/openapi.json" if settings.debug else None,
        lifespan=lifespan,
        redirect_slashes=False,
    )

    # Rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Pydantic validation error handler — return structured JSON instead of raw errors
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        # Build human-readable summary
        fields = []
        for err in errors:
            loc = " → ".join(str(x) for x in err.get("loc", []) if x != "body")
            fields.append(f"{loc}: {err.get('msg', 'invalid')}")
        detail = "; ".join(fields) if fields else "Validation error"
        return JSONResponse(
            status_code=422,
            content={"detail": detail, "code": "VALIDATION_ERROR"},
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    # CORS middleware (restricted methods and headers)
    # Prevent insecure "*" with allow_credentials=True
    cors_origins = [o for o in settings.cors_origins if o != "*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    )

    # Request body size limit (10 MB)
    MAX_BODY_SIZE = 10 * 1024 * 1024

    @app.middleware("http")
    async def limit_request_body(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_SIZE:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "Request body too large", "code": "BODY_TOO_LARGE"}, status_code=413)
        return await call_next(request)

    # Распаковка сжатых тел (батчи агента 1.6.0+). Стоит после проверки
    # content-length: та смотрит на сжатое тело, эта ограничивает
    # распакованное тем же потолком — иначе десяток килобайт мог бы
    # развернуться в гигабайты.
    from web.backend.core.gzip_request import GzipRequestMiddleware
    app.add_middleware(GzipRequestMiddleware, max_decompressed_bytes=MAX_BODY_SIZE)

    # Security headers middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Swagger UI requires inline scripts — use relaxed CSP for docs pages
        path = request.url.path
        if path in ("/api/docs", "/api/redoc", "/api/v3/docs"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "connect-src 'self'"
            )
        else:
            # telegram.org убран из script-src: виджет логина теперь
            # вендорится фронтом (/vendor/telegram-widget.js), внешние
            # скрипты бэкенд-страницам не нужны.
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "connect-src 'self' wss: ws:; "
                "frame-ancestors 'none'"
            )
        return response

    # IP whitelist middleware (checked before routing)
    @app.middleware("http")
    async def ip_whitelist_middleware(request: Request, call_next):
        # Skip health check and collector API (agents connect from external IPs)
        if request.url.path in ("/", "/api/v2/health") or request.url.path.startswith("/api/v2/collector/"):
            return await call_next(request)

        allowed = get_allowed_ips()
        if allowed:
            from web.backend.api.deps import get_client_ip
            client_ip = get_client_ip(request)
            if not is_ip_allowed(client_ip, allowed):
                logger.warning("IP %s rejected by whitelist (path: %s)", client_ip, request.url.path)
                # Async notification (fire-and-forget)
                from web.backend.core.notification_service import notify_ip_rejected
                import asyncio
                asyncio.create_task(notify_ip_rejected(client_ip, str(request.url.path)))
                return Response(
                    content='{"detail":"Access denied"}',
                    status_code=403,
                    media_type="application/json",
                )
        return await call_next(request)

    # Audit middleware — logs all mutable API actions automatically
    from web.backend.core.audit_middleware import AuditMiddleware
    app.add_middleware(AuditMiddleware)

    # Prometheus metrics middleware (HTTP RPS / latency / in-progress)
    from web.backend.core.metrics import (
        MetricsMiddleware,
        metrics_auth_token,
        render_metrics,
    )
    app.add_middleware(MetricsMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics(request: Request):
        """Prometheus scrape endpoint (text format 0.0.4).

        If METRICS_AUTH_TOKEN is set, requires `Authorization: Bearer <token>`.
        """
        expected = metrics_auth_token()
        if expected:
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer ") or auth[len("Bearer "):].strip() != expected:
                return Response(status_code=401, content="Unauthorized")
        body, content_type = render_metrics()
        return Response(content=body, media_type=content_type)

    # Include routers based on APP_MODE
    app_mode = _get_app_mode()

    # Collector router — available in collector and full modes
    if app_mode in ("collector", "full"):
        app.include_router(collector_api.router, prefix="/api/v2/collector", tags=["collector"])

    # UI routers — available in api and full modes
    if app_mode in ("api", "full"):
        app.include_router(auth.router, prefix="/api/v2/auth", tags=["auth"])
        app.include_router(users.router, prefix="/api/v2/users", tags=["users"])
        app.include_router(nodes.router, prefix="/api/v2/nodes", tags=["nodes"])
        app.include_router(analytics.router, prefix="/api/v2/analytics", tags=["analytics"])
        app.include_router(violations.router, prefix="/api/v2/violations", tags=["violations"])
        app.include_router(hosts.router, prefix="/api/v2/hosts", tags=["hosts"])
        app.include_router(settings_api.router, prefix="/api/v2/settings", tags=["settings"])
        app.include_router(diagnostics_api.router, prefix="/api/v2/diagnostics", tags=["diagnostics"])
        app.include_router(admins_api.router, prefix="/api/v2/admins", tags=["admins"])
        app.include_router(roles_api.router, prefix="/api/v2/roles", tags=["roles"])
        app.include_router(access_policies_api.router, prefix="/api/v2/access-policies", tags=["access-policies"])
        app.include_router(audit_api.router, prefix="/api/v2/audit", tags=["audit"])
        app.include_router(logs_api.router, prefix="/api/v2/logs", tags=["logs"])
        app.include_router(advanced_analytics.router, prefix="/api/v2/analytics/advanced", tags=["advanced-analytics"])
        app.include_router(automations_api.router, prefix="/api/v2/automations", tags=["automations"])
        app.include_router(notifications_api.router, prefix="/api/v2", tags=["notifications"])
        app.include_router(me_devices_api.router, prefix="/api/v2", tags=["me-devices"])
        app.include_router(mailserver_api.router, prefix="/api/v2", tags=["mailserver"])
        app.include_router(websocket.router, prefix="/api/v2", tags=["websocket"])
        app.include_router(agent_ws_api.router, prefix="/api/v2", tags=["agent-ws"])
        app.include_router(fleet_api.router, prefix="/api/v2/fleet", tags=["fleet"])
        app.include_router(terminal_api.router, prefix="/api/v2", tags=["terminal"])
        app.include_router(scripts_api.router, prefix="/api/v2/fleet", tags=["scripts"])
        app.include_router(templates_api.router, prefix="/api/v2/templates", tags=["templates"])
        app.include_router(snippets_api.router, prefix="/api/v2/snippets", tags=["snippets"])
        app.include_router(config_profiles_api.router, prefix="/api/v2/config-profiles", tags=["config-profiles"])
        app.include_router(finance_api.router, prefix="/api/v2/finance", tags=["finance"])
        app.include_router(dns_api.router, prefix="/api/v2/dns", tags=["dns"])
        app.include_router(bscheck_api.router, prefix="/api/v2/bscheck", tags=["bscheck"])
        app.include_router(reputation_api.router, prefix="/api/v2/reputation", tags=["reputation"])
        app.include_router(user_presets_api.router, prefix="/api/v2/user-presets", tags=["user-presets"])
        app.include_router(reports_api.router, prefix="/api/v2/reports", tags=["reports"])
        app.include_router(asn_api.router, prefix="/api/v2/asn", tags=["asn"])
        app.include_router(backup_api.router, prefix="/api/v2/backups", tags=["backups"])
        app.include_router(api_keys_api.router, prefix="/api/v2/api-keys", tags=["api-keys"])
        app.include_router(blocked_ips_api.router, prefix="/api/v2/blocked-ips", tags=["blocked-ips"])

        from web.backend.api.v2 import user_blacklist as user_blacklist_api
        app.include_router(user_blacklist_api.router, prefix="/api/v2/user-blacklist", tags=["user-blacklist"])
        app.include_router(webhooks_api.router, prefix="/api/v2/webhooks", tags=["webhooks"])
        app.include_router(squads_api.router, prefix="/api/v2/squads", tags=["squads"])
        app.include_router(bedolaga_router, prefix="/api/v2/bedolaga", tags=["bedolaga"])

        app.include_router(plugins_api.router, prefix="/api/v2/plugins", tags=["plugins"])
        app.include_router(internal_api.router, prefix="/api/v2/internal", tags=["internal"])

        from web.backend.api.v2 import admin_plugins as admin_plugins_api
        app.include_router(
            admin_plugins_api.router,
            prefix="/api/v2/admin/plugins",
            tags=["admin-plugins"],
        )

    # Pip-install + register run inside lifespan instead of create_app
    # because they need both the event loop (for license cache priming
    # against the DB) and the DB pool to be ready. See lifespan() for
    # the actual call sequence.

    # Public API v3 — enabled via EXTERNAL_API_ENABLED=true
    if settings.external_api_enabled:
        app.include_router(public_api_v3.router, prefix="/api/v3", tags=["public-api"])
        # Serve local Swagger UI static files (no CDN dependency)
        from pathlib import Path as _Path
        _swagger_dir = _Path(__file__).parent / "static" / "swagger-ui"
        if _swagger_dir.is_dir():
            from fastapi.staticfiles import StaticFiles
            app.mount("/api/v3/swagger-ui", StaticFiles(directory=str(_swagger_dir)), name="swagger-ui")
        logger.info("External API v3 enabled")

    # Health check endpoint
    @app.get("/api/v2/health", tags=["health"])
    async def health_check():
        """Health check endpoint."""
        version = await get_latest_version()
        return {
            "status": "ok",
            "version": version,
            "service": "remnawave-admin-web",
        }

    # Root endpoint
    @app.get("/", tags=["health"])
    async def root():
        """Root endpoint."""
        version = await get_latest_version()
        return {
            "service": "remnawave-admin-web",
            "version": version,
            "docs": "/api/docs" if settings.debug else None,
        }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_web_settings()
    uvicorn.run(
        "web.backend.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        # Enable per-message deflate compression for WebSocket connections
        ws="websockets",
        ws_per_message_deflate=True,
    )

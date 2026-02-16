"""
Remnawave Admin Web Panel - FastAPI Application.

This is the main entry point for the web panel backend.
It provides REST API and WebSocket endpoints for the admin dashboard.
"""
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
from web.backend.api.v2 import admins as admins_api, roles as roles_api
from web.backend.api.v2 import audit as audit_api
from web.backend.api.v2 import logs as logs_api
from web.backend.api.v2 import advanced_analytics
from web.backend.api.v2 import automations as automations_api
from web.backend.api.v2 import notifications as notifications_api
from web.backend.api.v2 import mailserver as mailserver_api
from web.backend.api.v2 import agent_ws as agent_ws_api
from web.backend.api.v2 import fleet as fleet_api
from web.backend.api.v2 import terminal as terminal_api
from web.backend.api.v2 import scripts as scripts_api
from web.backend.api.v2 import tokens as tokens_api
from web.backend.api.v2 import templates as templates_api
from web.backend.api.v2 import snippets as snippets_api
from web.backend.api.v2 import config_profiles as config_profiles_api
from web.backend.api.v2 import billing as billing_api
from web.backend.api.v2 import reports as reports_api
from web.backend.api.v2 import asn as asn_api


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


def _shorten_logger_name(logger_name: str, event_dict: dict) -> dict:
    """structlog processor: сокращает имена логгеров."""
    name = event_dict.get("logger", logger_name or "")
    for prefix, short in _LOGGER_NAME_MAP.items():
        if name == prefix or name.startswith(prefix + "."):
            event_dict["logger"] = short
            return event_dict
    if "." in name:
        event_dict["logger"] = name.rsplit(".", 1)[-1]
    return event_dict


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
    console.setFormatter(structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _shorten_logger_name,
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
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

        # NOTE: violations.log is written by the bot process (shared/logger.py)
        # which has the proper ViolationLogFilter. The web backend must NOT add its
        # own handler for the same file.

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


# ── FastAPI app ───────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_web_settings()
    logger.info("🚀 Web API starting on %s:%s", settings.host, settings.port)

    # Connect to database if configured
    database_url = os.environ.get("DATABASE_URL") or getattr(settings, "database_url", None)
    if database_url:
        try:
            from shared.database import db_service
            connected = await db_service.connect(database_url=database_url)
            if connected:
                logger.info("Database connected")

                # First-run admin setup
                # Verify RBAC tables exist
                from web.backend.core.rbac import ensure_rbac_tables
                await ensure_rbac_tables()

                # Initialize dynamic config service (DB settings cache)
                from shared.config_service import config_service
                await config_service.initialize()

                # Start automation engine
                from web.backend.core.automation_engine import engine as automation_engine
                await automation_engine.start()

                # Start alert engine
                from web.backend.core.alert_engine import alert_engine
                await alert_engine.start()

                # Start mail service
                try:
                    from web.backend.core.mail.mail_service import mail_service
                    await mail_service.start()
                except Exception as e:
                    logger.warning("Mail service start failed: %s", e)
            else:
                logger.warning("Database connection failed")
        except Exception as e:
            logger.error("Database error: %s", e)
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

    yield

    # Shutdown
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

    # CORS middleware (restricted methods and headers)
    # Prevent insecure "*" with allow_credentials=True
    cors_origins = [o for o in settings.cors_origins if o != "*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Security headers middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://telegram.org; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self' wss: ws:; "
            "frame-ancestors 'none'"
        )
        return response

    # IP whitelist middleware (checked before routing)
    @app.middleware("http")
    async def ip_whitelist_middleware(request: Request, call_next):
        # Skip health check so monitoring still works
        if request.url.path in ("/", "/api/v2/health"):
            return await call_next(request)

        allowed = get_allowed_ips()
        if allowed:
            import ipaddress as _ipa
            forwarded = request.headers.get("x-forwarded-for")
            client_ip = request.client.host if request.client else "unknown"
            if forwarded:
                candidate = forwarded.split(",")[0].strip()
                # Validate it's a real IP to prevent header spoofing bypass
                try:
                    _ipa.ip_address(candidate)
                    client_ip = candidate
                except ValueError:
                    logger.warning("Invalid IP in X-Forwarded-For: %s", candidate)
            if not is_ip_allowed(client_ip, allowed):
                logger.warning("IP %s rejected by whitelist (path: %s)", client_ip, request.url.path)
                # Async notification (fire-and-forget)
                from web.backend.core.notifier import notify_ip_rejected
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

    # Include routers
    app.include_router(auth.router, prefix="/api/v2/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/v2/users", tags=["users"])
    app.include_router(nodes.router, prefix="/api/v2/nodes", tags=["nodes"])
    app.include_router(analytics.router, prefix="/api/v2/analytics", tags=["analytics"])
    app.include_router(violations.router, prefix="/api/v2/violations", tags=["violations"])
    app.include_router(hosts.router, prefix="/api/v2/hosts", tags=["hosts"])
    app.include_router(settings_api.router, prefix="/api/v2/settings", tags=["settings"])
    app.include_router(admins_api.router, prefix="/api/v2/admins", tags=["admins"])
    app.include_router(roles_api.router, prefix="/api/v2/roles", tags=["roles"])
    app.include_router(audit_api.router, prefix="/api/v2/audit", tags=["audit"])
    app.include_router(logs_api.router, prefix="/api/v2/logs", tags=["logs"])
    app.include_router(advanced_analytics.router, prefix="/api/v2/analytics/advanced", tags=["advanced-analytics"])
    app.include_router(automations_api.router, prefix="/api/v2/automations", tags=["automations"])
    app.include_router(notifications_api.router, prefix="/api/v2", tags=["notifications"])
    app.include_router(mailserver_api.router, prefix="/api/v2", tags=["mailserver"])
    app.include_router(websocket.router, prefix="/api/v2", tags=["websocket"])
    app.include_router(agent_ws_api.router, prefix="/api/v2", tags=["agent-ws"])
    app.include_router(fleet_api.router, prefix="/api/v2/fleet", tags=["fleet"])
    app.include_router(terminal_api.router, prefix="/api/v2", tags=["terminal"])
    app.include_router(scripts_api.router, prefix="/api/v2/fleet", tags=["scripts"])
    app.include_router(tokens_api.router, prefix="/api/v2/tokens", tags=["tokens"])
    app.include_router(templates_api.router, prefix="/api/v2/templates", tags=["templates"])
    app.include_router(snippets_api.router, prefix="/api/v2/snippets", tags=["snippets"])
    app.include_router(config_profiles_api.router, prefix="/api/v2/config-profiles", tags=["config-profiles"])
    app.include_router(billing_api.router, prefix="/api/v2/billing", tags=["billing"])
    app.include_router(reports_api.router, prefix="/api/v2/reports", tags=["reports"])
    app.include_router(asn_api.router, prefix="/api/v2/asn", tags=["asn"])

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

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

# Add project root to path for importing src modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.backend.core.config import get_web_settings
from web.backend.api.v2 import auth, users, nodes, analytics, violations, hosts, websocket
from web.backend.api.v2 import settings as settings_api


# ── Logging setup ─────────────────────────────────────────────────

_CONSOLE_FMT = "%(asctime)s | %(levelname)-7s | %(name)-10s | %(message)s"
_CONSOLE_DATEFMT = "%H:%M:%S"
_FILE_FMT = "%(asctime)s | %(levelname)-7s | %(name)-10s | %(message)s"
_FILE_DATEFMT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
_BACKUP_COUNT = 5
_LOG_DIR = Path("/app/logs")


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


def _setup_web_logging():
    """Настраивает логирование для web backend."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(fmt=_CONSOLE_FMT, datefmt=_CONSOLE_DATEFMT)

    # Console: WARNING+ только
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(fmt)
    root.addHandler(console)

    # File handlers
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_fmt = logging.Formatter(fmt=_FILE_FMT, datefmt=_FILE_DATEFMT)

        info_h = _CompressedRotatingFileHandler(
            str(_LOG_DIR / "web_INFO.log"),
            maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8",
        )
        info_h.setLevel(logging.INFO)
        info_h.setFormatter(file_fmt)
        root.addHandler(info_h)

        warn_h = _CompressedRotatingFileHandler(
            str(_LOG_DIR / "web_WARNING.log"),
            maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8",
        )
        warn_h.setLevel(logging.WARNING)
        warn_h.setFormatter(file_fmt)
        root.addHandler(warn_h)
    except OSError as exc:
        console.setLevel(logging.INFO)
        root.warning("⚠️ Cannot create log files (%s), logging to console only", exc)

    # Подавляем шумные логгеры
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)


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
            from src.services.database import db_service
            connected = await db_service.connect(database_url=database_url)
            if connected:
                logger.info("✅ Database connected")
            else:
                logger.warning("⚠️ Database connection failed")
        except Exception as e:
            logger.error("⚠️ Database error: %s", e)
    else:
        logger.info("🗄️ No DATABASE_URL, running without database")

    yield

    # Shutdown
    try:
        from src.services.database import db_service
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
        version="2.0.0",
        docs_url="/api/docs" if settings.debug else None,
        redoc_url="/api/redoc" if settings.debug else None,
        openapi_url="/api/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(auth.router, prefix="/api/v2/auth", tags=["auth"])
    app.include_router(users.router, prefix="/api/v2/users", tags=["users"])
    app.include_router(nodes.router, prefix="/api/v2/nodes", tags=["nodes"])
    app.include_router(analytics.router, prefix="/api/v2/analytics", tags=["analytics"])
    app.include_router(violations.router, prefix="/api/v2/violations", tags=["violations"])
    app.include_router(hosts.router, prefix="/api/v2/hosts", tags=["hosts"])
    app.include_router(settings_api.router, prefix="/api/v2/settings", tags=["settings"])
    app.include_router(websocket.router, prefix="/api/v2", tags=["websocket"])

    # Health check endpoint
    @app.get("/api/v2/health", tags=["health"])
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "ok",
            "version": "2.0.0",
            "service": "remnawave-admin-web",
        }

    # Root endpoint
    @app.get("/", tags=["health"])
    async def root():
        """Root endpoint."""
        return {
            "service": "remnawave-admin-web",
            "version": "2.0.0",
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
    )

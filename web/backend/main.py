"""
Remnawave Admin Web Panel - FastAPI Application.

This is the main entry point for the web panel backend.
It provides REST API and WebSocket endpoints for the admin dashboard.
"""
import sys
from pathlib import Path

# Add project root to path for importing src modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.backend.core.config import get_web_settings
from web.backend.api.v2 import auth, users, nodes, analytics


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    settings = get_web_settings()
    print(f"🚀 Starting Remnawave Admin Web API on {settings.host}:{settings.port}")
    print(f"📝 Debug mode: {settings.debug}")
    print(f"🔗 CORS origins: {settings.cors_origins}")

    yield

    # Shutdown
    print("👋 Shutting down Remnawave Admin Web API")


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

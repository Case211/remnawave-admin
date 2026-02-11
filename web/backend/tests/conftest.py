"""Shared test fixtures for backend tests.

Provides:
- FastAPI test app with dependency overrides
- httpx AsyncClient for API testing
- Mock admin users with different roles/permissions
- Environment variable fixtures
"""
import os
import sys
from pathlib import Path
from typing import Set, Tuple
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Set required environment variables BEFORE any app imports
os.environ.setdefault("WEB_SECRET_KEY", "test-secret-key-for-unit-tests-only")
os.environ.setdefault("BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
os.environ.setdefault("API_BASE_URL", "http://localhost:3000")
os.environ.setdefault("WEB_DEBUG", "true")
os.environ.setdefault("WEB_ALLOWED_IPS", "")

# Clear the lru_cache so test env vars take effect
from web.backend.core.config import get_web_settings
get_web_settings.cache_clear()

from httpx import ASGITransport, AsyncClient
from web.backend.api.deps import AdminUser, get_current_admin
from web.backend.main import create_app


# ── Admin user fixtures ───────────────────────────────────────

SUPERADMIN_PERMISSIONS: Set[Tuple[str, str]] = {
    ("users", "view"), ("users", "create"), ("users", "edit"), ("users", "delete"),
    ("nodes", "view"), ("nodes", "create"), ("nodes", "edit"), ("nodes", "delete"),
    ("hosts", "view"), ("hosts", "create"), ("hosts", "edit"), ("hosts", "delete"),
    ("violations", "view"), ("violations", "edit"),
    ("analytics", "view"),
    ("admins", "view"), ("admins", "create"), ("admins", "edit"), ("admins", "delete"),
    ("roles", "view"), ("roles", "create"), ("roles", "edit"), ("roles", "delete"),
    ("audit", "view"),
    ("settings", "view"), ("settings", "edit"),
    ("automations", "view"), ("automations", "create"), ("automations", "edit"), ("automations", "delete"),
    ("fleet", "view"),
    ("logs", "view"),
    ("bulk", "execute"),
}

VIEWER_PERMISSIONS: Set[Tuple[str, str]] = {
    ("users", "view"),
    ("nodes", "view"),
    ("hosts", "view"),
    ("violations", "view"),
    ("analytics", "view"),
    ("audit", "view"),
    ("fleet", "view"),
    ("logs", "view"),
}

OPERATOR_PERMISSIONS: Set[Tuple[str, str]] = VIEWER_PERMISSIONS | {
    ("users", "edit"),
    ("nodes", "edit"),
    ("violations", "edit"),
}

MANAGER_PERMISSIONS: Set[Tuple[str, str]] = OPERATOR_PERMISSIONS | {
    ("users", "create"), ("users", "delete"),
    ("nodes", "create"), ("nodes", "delete"),
    ("hosts", "create"), ("hosts", "edit"), ("hosts", "delete"),
    ("admins", "view"),
    ("automations", "view"), ("automations", "create"), ("automations", "edit"),
    ("settings", "view"),
    ("bulk", "execute"),
}


def make_admin(
    role: str = "superadmin",
    username: str = "testadmin",
    account_id: int = 1,
    permissions: Set[Tuple[str, str]] = None,
) -> AdminUser:
    """Create a test AdminUser with specified role."""
    if permissions is None:
        perm_map = {
            "superadmin": SUPERADMIN_PERMISSIONS,
            "manager": MANAGER_PERMISSIONS,
            "operator": OPERATOR_PERMISSIONS,
            "viewer": VIEWER_PERMISSIONS,
        }
        permissions = perm_map.get(role, set())

    return AdminUser(
        telegram_id=100000,
        username=username,
        role=role,
        role_id=1,
        auth_method="password",
        account_id=account_id,
        permissions=permissions,
    )


# ── App and client fixtures ──────────────────────────────────

@pytest.fixture()
def app():
    """Create a fresh FastAPI app for testing."""
    # Clear settings cache for each test
    get_web_settings.cache_clear()
    _app = create_app()
    yield _app
    # Clean up overrides
    _app.dependency_overrides.clear()


@pytest.fixture()
def superadmin():
    return make_admin("superadmin", "superadmin_user", account_id=1)


@pytest.fixture()
def manager():
    return make_admin("manager", "manager_user", account_id=2)


@pytest.fixture()
def operator():
    return make_admin("operator", "operator_user", account_id=3)


@pytest.fixture()
def viewer():
    return make_admin("viewer", "viewer_user", account_id=4)


@pytest_asyncio.fixture()
async def client(app, superadmin):
    """Async HTTP client authenticated as superadmin."""
    app.dependency_overrides[get_current_admin] = lambda: superadmin
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture()
async def viewer_client(app, viewer):
    """Async HTTP client authenticated as viewer."""
    app.dependency_overrides[get_current_admin] = lambda: viewer
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture()
async def manager_client(app, manager):
    """Async HTTP client authenticated as manager."""
    app.dependency_overrides[get_current_admin] = lambda: manager
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture()
async def operator_client(app, operator):
    """Async HTTP client authenticated as operator."""
    app.dependency_overrides[get_current_admin] = lambda: operator
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture()
async def anon_client(app):
    """Unauthenticated HTTP client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

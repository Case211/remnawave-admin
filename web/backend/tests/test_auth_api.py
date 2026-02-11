"""Tests for auth API endpoints — /api/v2/auth/*."""
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock

from web.backend.api.deps import get_current_admin
from web.backend.core.security import create_access_token, create_refresh_token


class TestSetupStatus:
    """GET /api/v2/auth/setup-status."""

    @pytest.mark.asyncio
    async def test_returns_setup_status(self, anon_client):
        resp = await anon_client.get("/api/v2/auth/setup-status")
        assert resp.status_code == 200
        data = resp.json()
        assert "needs_setup" in data

    @pytest.mark.asyncio
    @patch("web.backend.core.admin_credentials.admin_exists", new_callable=AsyncMock, return_value=False)
    @patch("web.backend.core.rbac.admin_account_exists", new_callable=AsyncMock, return_value=False)
    async def test_needs_setup_when_no_admin(self, mock_rbac_exists, mock_admin_exists, anon_client):
        resp = await anon_client.get("/api/v2/auth/setup-status")
        assert resp.status_code == 200


class TestPasswordLogin:
    """POST /api/v2/auth/login."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth.verify_admin_password_async", new_callable=AsyncMock, return_value=True)
    @patch("web.backend.core.rbac.admin_account_exists", new_callable=AsyncMock, return_value=True)
    @patch("web.backend.api.v2.auth.login_guard")
    @patch("web.backend.api.v2.auth.notify_login_success", new_callable=AsyncMock)
    async def test_successful_login(
        self, mock_notify, mock_guard, mock_exists, mock_verify, anon_client
    ):
        mock_guard.is_locked.return_value = False
        mock_guard.record_success.return_value = None
        resp = await anon_client.post(
            "/api/v2/auth/login",
            json={"username": "admin", "password": "TestP@ss1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth.verify_admin_password_async", new_callable=AsyncMock, return_value=False)
    @patch("web.backend.core.rbac.admin_account_exists", new_callable=AsyncMock, return_value=True)
    @patch("web.backend.api.v2.auth.login_guard")
    @patch("web.backend.api.v2.auth.notify_login_failed", new_callable=AsyncMock)
    async def test_wrong_credentials(
        self, mock_notify, mock_guard, mock_exists, mock_verify, anon_client
    ):
        mock_guard.is_locked.return_value = False
        mock_guard.record_failure.return_value = False
        resp = await anon_client.post(
            "/api/v2/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth.login_guard")
    async def test_locked_ip(self, mock_guard, anon_client):
        mock_guard.is_locked.return_value = True
        mock_guard.remaining_seconds.return_value = 600
        resp = await anon_client.post(
            "/api/v2/auth/login",
            json={"username": "admin", "password": "test"},
        )
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_missing_username(self, anon_client):
        resp = await anon_client.post(
            "/api/v2/auth/login",
            json={"password": "test"},
        )
        assert resp.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_missing_password(self, anon_client):
        resp = await anon_client.post(
            "/api/v2/auth/login",
            json={"username": "admin"},
        )
        assert resp.status_code == 422


class TestTokenRefresh:
    """POST /api/v2/auth/refresh."""

    @pytest.mark.asyncio
    @patch(
        "web.backend.core.rbac.get_admin_account_by_username",
        new_callable=AsyncMock,
        return_value={"id": 1, "username": "admin", "is_active": True, "role_id": 1},
    )
    async def test_valid_refresh(self, mock_account, anon_client):
        refresh = create_refresh_token("pwd:admin")
        resp = await anon_client.post(
            "/api/v2/auth/refresh",
            json={"refresh_token": refresh},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_invalid_refresh_token(self, anon_client):
        resp = await anon_client.post(
            "/api/v2/auth/refresh",
            json={"refresh_token": "invalid.token"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_access_token_as_refresh_fails(self, anon_client):
        access = create_access_token("pwd:admin", "admin")
        resp = await anon_client.post(
            "/api/v2/auth/refresh",
            json={"refresh_token": access},
        )
        assert resp.status_code == 401


class TestGetCurrentUser:
    """GET /api/v2/auth/me."""

    @pytest.mark.asyncio
    async def test_get_me(self, client, superadmin):
        resp = await client.get("/api/v2/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == superadmin.username
        assert data["role"] == "superadmin"
        assert isinstance(data["permissions"], list)

    @pytest.mark.asyncio
    async def test_unauthenticated(self, anon_client):
        resp = await anon_client.get("/api/v2/auth/me")
        assert resp.status_code in (401, 403)


class TestLogout:
    """POST /api/v2/auth/logout."""

    @pytest.mark.asyncio
    async def test_logout(self, client):
        resp = await client.post("/api/v2/auth/logout")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestRegisterEndpoint:
    """POST /api/v2/auth/register."""

    @pytest.mark.asyncio
    @patch("web.backend.core.admin_credentials.admin_exists", new_callable=AsyncMock, return_value=True)
    @patch("web.backend.core.rbac.admin_account_exists", new_callable=AsyncMock, return_value=True)
    async def test_register_blocked_when_admin_exists(self, mock_rbac, mock_exists, anon_client):
        resp = await anon_client.post(
            "/api/v2/auth/register",
            json={"username": "newadmin", "password": "SecureP@ss1"},
        )
        assert resp.status_code == 403

"""Tests for auth API endpoints — /api/v2/auth/*."""
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from web.backend.api.deps import get_current_admin
from web.backend.core.security import create_access_token, create_refresh_token, create_password_reset_token


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


# ── Password reset tests ─────────────────────────────────────


class TestForgotPassword:
    """POST /api/v2/auth/forgot-password."""

    @pytest.mark.asyncio
    async def test_forgot_password_returns_success_always(self, anon_client):
        """forgot-password should always return success (prevent email enumeration)."""
        response = await anon_client.post(
            "/api/v2/auth/forgot-password",
            json={"email": "nonexistent@test.com"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_forgot_password_rate_limited(self, anon_client):
        """forgot-password should be rate-limited to 3/minute."""
        for _ in range(4):
            response = await anon_client.post(
                "/api/v2/auth/forgot-password",
                json={"email": "test@test.com"},
            )
        assert response.status_code == 429


class TestResetPassword:
    """POST /api/v2/auth/reset-password."""

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, anon_client):
        """reset-password with invalid token should return error."""
        response = await anon_client.post(
            "/api/v2/auth/reset-password",
            json={
                "token": "invalid-token-here-that-is-long-enough",
                "new_password": "NewSecureP@ss1!",
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_valid_flow(self, anon_client):
        """reset-password with valid token should work."""
        token = create_password_reset_token(admin_id=1, username="admin")

        with patch("web.backend.core.rbac.get_admin_account_by_id", new_callable=AsyncMock) as mock_get, \
             patch("web.backend.core.rbac.update_admin_account", new_callable=AsyncMock) as mock_update:
            mock_get.return_value = {"id": 1, "username": "admin", "is_active": True, "password_hash": "old"}
            mock_update.return_value = {"id": 1}

            response = await anon_client.post(
                "/api/v2/auth/reset-password",
                json={
                    "token": token,
                    "new_password": "NewSecureP@ss1!",
                },
            )
            assert response.status_code == 200


def _sign_init_data(pairs: dict, bot_token: str) -> str:
    """Build a signed Mini App initData query string the way Telegram does."""
    import hashlib
    import hmac
    from urllib.parse import urlencode

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**pairs, "hash": signature})


def _make_init_data(tg_id: int = 777, bot_token: str = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11") -> str:
    import json
    import time

    return _sign_init_data(
        {
            "user": json.dumps({"id": tg_id, "first_name": "Mini", "username": "miniapp"},
                               separators=(",", ":")),
            "auth_date": str(int(time.time())),
        },
        bot_token,
    )


class TestTelegramWebAppLogin:
    """POST /api/v2/auth/telegram/webapp — Telegram Mini App auto-login."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth._get_rbac_account", new_callable=AsyncMock, return_value=None)
    @patch("web.backend.api.v2.auth.login_guard")
    @patch("web.backend.api.v2.auth.notify_login_success", new_callable=AsyncMock)
    async def test_successful_login(self, mock_notify, mock_guard, mock_account, anon_client):
        mock_guard.is_locked.return_value = False
        with patch("web.backend.api.v2.auth.get_web_settings") as mock_settings:
            mock_settings.return_value.admins = [777]
            resp = await anon_client.post(
                "/api/v2/auth/telegram/webapp",
                json={"init_data": _make_init_data(777)},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["access_token"]
        assert data["refresh_token"]
        assert data["expires_in"] > 0

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth.login_guard")
    @patch("web.backend.api.v2.auth.notify_login_failed", new_callable=AsyncMock)
    async def test_invalid_signature_rejected(self, mock_notify, mock_guard, anon_client):
        mock_guard.is_locked.return_value = False
        mock_guard.record_failure.return_value = False
        resp = await anon_client.post(
            "/api/v2/auth/telegram/webapp",
            json={"init_data": _make_init_data(777) + "&chat_instance=1"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth.login_guard")
    @patch("web.backend.api.v2.auth.notify_login_failed", new_callable=AsyncMock)
    async def test_non_admin_rejected(self, mock_notify, mock_guard, anon_client):
        mock_guard.is_locked.return_value = False
        mock_guard.record_failure.return_value = False
        with patch("web.backend.api.v2.auth.get_web_settings") as mock_settings:
            mock_settings.return_value.admins = [1]
            resp = await anon_client.post(
                "/api/v2/auth/telegram/webapp",
                json={"init_data": _make_init_data(777)},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_disabled_by_toggle(self, anon_client):
        def fake_get(key, default=None):
            if key == "auth_telegram_webapp_enabled":
                return False
            return default

        with patch("web.backend.api.v2.auth.config_service.get", side_effect=fake_get):
            resp = await anon_client.post(
                "/api/v2/auth/telegram/webapp",
                json={"init_data": _make_init_data(777)},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_disabled_when_telegram_auth_off(self, anon_client):
        def fake_get(key, default=None):
            if key == "auth_telegram_enabled":
                return False
            return default

        with patch("web.backend.api.v2.auth.config_service.get", side_effect=fake_get):
            resp = await anon_client.post(
                "/api/v2/auth/telegram/webapp",
                json={"init_data": _make_init_data(777)},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth.login_guard")
    async def test_locked_ip(self, mock_guard, anon_client):
        mock_guard.is_locked.return_value = True
        mock_guard.remaining_seconds.return_value = 300
        resp = await anon_client.post(
            "/api/v2/auth/telegram/webapp",
            json={"init_data": _make_init_data(777)},
        )
        assert resp.status_code == 429

    @pytest.mark.asyncio
    async def test_empty_init_data_rejected(self, anon_client):
        resp = await anon_client.post("/api/v2/auth/telegram/webapp", json={"init_data": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth._get_rbac_account", new_callable=AsyncMock)
    @patch("web.backend.api.v2.auth.login_guard")
    async def test_method_policy_blocks_login(self, mock_guard, mock_account, anon_client):
        """Аккаунт с allowed_auth_methods без telegram не пускается и через мини-апп."""
        mock_guard.is_locked.return_value = False
        mock_account.return_value = {"id": 1, "allowed_auth_methods": '["password"]'}
        with patch("web.backend.api.v2.auth.get_web_settings") as mock_settings:
            mock_settings.return_value.admins = [777]
            resp = await anon_client.post(
                "/api/v2/auth/telegram/webapp",
                json={"init_data": _make_init_data(777)},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth._get_rbac_account", new_callable=AsyncMock)
    @patch("web.backend.api.v2.auth.login_guard")
    async def test_2fa_required_returns_temp_token(self, mock_guard, mock_account, anon_client):
        mock_guard.is_locked.return_value = False
        mock_account.return_value = {"id": 1, "totp_enabled": True, "allowed_auth_methods": None}

        def fake_get(key, default=None):
            if key == "auth_totp_required":
                return True
            return default

        with patch("web.backend.api.v2.auth.get_web_settings") as mock_settings, \
                patch("web.backend.api.v2.auth.config_service.get", side_effect=fake_get):
            mock_settings.return_value.admins = [777]
            resp = await anon_client.post(
                "/api/v2/auth/telegram/webapp",
                json={"init_data": _make_init_data(777)},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["requires_2fa"] is True
        assert data["temp_token"]


class TestAuthMethods:
    """GET /api/v2/auth/methods."""

    @pytest.mark.asyncio
    async def test_reports_telegram_webapp_flag(self, anon_client):
        resp = await anon_client.get("/api/v2/auth/methods")
        assert resp.status_code == 200
        data = resp.json()
        assert set(["telegram", "telegram_webapp", "password", "totp_required"]) <= set(data)

    @pytest.mark.asyncio
    async def test_webapp_off_when_telegram_off(self, anon_client):
        def fake_get(key, default=None):
            if key == "auth_telegram_enabled":
                return False
            return default

        with patch("web.backend.api.v2.auth.config_service.get", side_effect=fake_get):
            resp = await anon_client.get("/api/v2/auth/methods")
        assert resp.json()["telegram_webapp"] is False


class TestTelegramWidgetLogin:
    """POST /api/v2/auth/telegram — Login Widget. Регресс после выделения
    общего хвоста Telegram-входа (_finish_telegram_login)."""

    BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

    @classmethod
    def _widget_payload(cls, tg_id: int = 555) -> dict:
        import hashlib
        import hmac
        import time

        data = {
            "id": tg_id,
            "first_name": "Widget",
            "username": "widgetuser",
            "auth_date": int(time.time()),
        }
        check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data))
        secret_key = hashlib.sha256(cls.BOT_TOKEN.encode()).digest()
        data["hash"] = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        return data

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth._get_rbac_account", new_callable=AsyncMock, return_value=None)
    @patch("web.backend.api.v2.auth.login_guard")
    @patch("web.backend.api.v2.auth.notify_login_success", new_callable=AsyncMock)
    async def test_successful_login(self, mock_notify, mock_guard, mock_account, anon_client):
        mock_guard.is_locked.return_value = False
        with patch("web.backend.api.v2.auth.get_web_settings") as mock_settings:
            mock_settings.return_value.admins = [555]
            resp = await anon_client.post("/api/v2/auth/telegram", json=self._widget_payload(555))
        assert resp.status_code == 200, resp.text
        assert resp.json()["access_token"]

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth.login_guard")
    @patch("web.backend.api.v2.auth.notify_login_failed", new_callable=AsyncMock)
    async def test_bad_hash_rejected(self, mock_notify, mock_guard, anon_client):
        mock_guard.is_locked.return_value = False
        mock_guard.record_failure.return_value = False
        payload = self._widget_payload(555)
        payload["hash"] = "0" * 64
        resp = await anon_client.post("/api/v2/auth/telegram", json=payload)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth.login_guard")
    @patch("web.backend.api.v2.auth.notify_login_failed", new_callable=AsyncMock)
    async def test_non_admin_rejected(self, mock_notify, mock_guard, anon_client):
        mock_guard.is_locked.return_value = False
        mock_guard.record_failure.return_value = False
        with patch("web.backend.api.v2.auth.get_web_settings") as mock_settings:
            mock_settings.return_value.admins = [1]
            resp = await anon_client.post("/api/v2/auth/telegram", json=self._widget_payload(555))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_disabled_by_toggle(self, anon_client):
        def fake_get(key, default=None):
            if key == "auth_telegram_enabled":
                return False
            return default

        with patch("web.backend.api.v2.auth.config_service.get", side_effect=fake_get):
            resp = await anon_client.post("/api/v2/auth/telegram", json=self._widget_payload(555))
        assert resp.status_code == 403

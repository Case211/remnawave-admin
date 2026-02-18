"""Extended tests for web.backend.core.security.

Covers: verify_telegram_auth success path, verify_telegram_auth_simple,
verify_admin_password with bcrypt, verify_admin_password_async.
"""
import hashlib
import hmac
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core.security import (
    verify_admin_password,
    verify_admin_password_async,
    verify_telegram_auth,
    verify_telegram_auth_simple,
    create_access_token,
    create_refresh_token,
    decode_token,
)


# ── verify_telegram_auth: success path ────────────────────────


class TestTelegramAuthSuccess:
    """Verify valid Telegram auth returns (True, "")."""

    def _make_valid_auth(self, extra_fields=None):
        from web.backend.core.config import get_web_settings
        bot_token = get_web_settings().telegram_bot_token

        data = {
            "id": "12345",
            "first_name": "Test",
            "auth_date": str(int(time.time())),
        }
        if extra_fields:
            data.update(extra_fields)

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items()) if v is not None
        )
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        data["hash"] = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        return data

    def test_valid_auth(self):
        data = self._make_valid_auth()
        is_valid, error = verify_telegram_auth(data)
        assert is_valid is True
        assert error == ""

    def test_valid_auth_with_all_fields(self):
        data = self._make_valid_auth({
            "last_name": "User",
            "username": "testuser",
            "photo_url": "https://example.com/photo.jpg",
        })
        is_valid, error = verify_telegram_auth(data)
        assert is_valid is True

    def test_invalid_hash(self):
        data = self._make_valid_auth()
        data["hash"] = "0" * 64
        is_valid, error = verify_telegram_auth(data)
        assert is_valid is False
        assert "Invalid signature" in error

    def test_missing_hash(self):
        data = {"id": "12345", "auth_date": str(int(time.time()))}
        is_valid, error = verify_telegram_auth(data)
        assert is_valid is False
        assert "Missing hash" in error

    def test_expired_auth(self):
        data = self._make_valid_auth()
        # Override auth_date to 2 days ago
        data.pop("hash")
        data["auth_date"] = str(int(time.time()) - 200000)

        from web.backend.core.config import get_web_settings
        bot_token = get_web_settings().telegram_bot_token
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items()) if v is not None
        )
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        data["hash"] = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        is_valid, error = verify_telegram_auth(data)
        assert is_valid is False
        assert "expired" in error

    def test_missing_auth_date(self):
        data = {"id": "12345", "hash": "abc"}
        is_valid, error = verify_telegram_auth(data)
        assert is_valid is False
        assert "Missing auth_date" in error


# ── verify_telegram_auth_simple ───────────────────────────────


class TestTelegramAuthSimple:

    def test_returns_true_for_valid(self):
        from web.backend.core.config import get_web_settings
        bot_token = get_web_settings().telegram_bot_token

        data = {"id": "111", "first_name": "Bob", "auth_date": str(int(time.time()))}
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items()) if v is not None
        )
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        data["hash"] = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        assert verify_telegram_auth_simple(data) is True

    def test_returns_false_for_invalid(self):
        data = {"id": "111", "auth_date": str(int(time.time())), "hash": "0" * 64}
        assert verify_telegram_auth_simple(data) is False


# ── verify_admin_password with bcrypt ─────────────────────────


class TestPasswordBcrypt:

    def test_bcrypt_correct_password(self):
        import bcrypt
        hashed = bcrypt.hashpw(b"my-secret", bcrypt.gensalt()).decode()

        with patch("web.backend.core.security.get_web_settings") as ms:
            ms.return_value.admin_login = "admin"
            ms.return_value.admin_password = hashed
            assert verify_admin_password("admin", "my-secret") is True

    def test_bcrypt_wrong_password(self):
        import bcrypt
        hashed = bcrypt.hashpw(b"correct", bcrypt.gensalt()).decode()

        with patch("web.backend.core.security.get_web_settings") as ms:
            ms.return_value.admin_login = "admin"
            ms.return_value.admin_password = hashed
            assert verify_admin_password("admin", "wrong") is False

    def test_plaintext_password(self):
        with patch("web.backend.core.security.get_web_settings") as ms:
            ms.return_value.admin_login = "admin"
            ms.return_value.admin_password = "plain123"
            assert verify_admin_password("admin", "plain123") is True
            assert verify_admin_password("admin", "wrong") is False

    def test_wrong_username(self):
        with patch("web.backend.core.security.get_web_settings") as ms:
            ms.return_value.admin_login = "admin"
            ms.return_value.admin_password = "pass"
            assert verify_admin_password("other", "pass") is False

    def test_empty_credentials(self):
        with patch("web.backend.core.security.get_web_settings") as ms:
            ms.return_value.admin_login = ""
            ms.return_value.admin_password = ""
            assert verify_admin_password("admin", "pass") is False


# ── verify_admin_password_async ───────────────────────────────


class TestPasswordAsync:

    @patch("web.backend.core.security.verify_admin_password")
    async def test_db_account_matches(self, mock_sync):
        account = {"id": 1, "password_hash": "$2b$12$hash", "is_active": True}

        with patch(
            "web.backend.core.rbac.get_admin_account_by_username",
            new_callable=AsyncMock, return_value=account,
        ), patch(
            "web.backend.core.admin_credentials.verify_password",
            return_value=True,
        ):
            result = await verify_admin_password_async("admin", "pass")
            assert result is True
            mock_sync.assert_not_called()

    async def test_db_account_disabled(self):
        account = {"id": 2, "password_hash": "$2b$12$hash", "is_active": False}

        with patch(
            "web.backend.core.rbac.get_admin_account_by_username",
            new_callable=AsyncMock, return_value=account,
        ):
            assert await verify_admin_password_async("admin", "pass") is False

    async def test_db_account_wrong_password(self):
        account = {"id": 3, "password_hash": "$2b$12$hash", "is_active": True}

        with patch(
            "web.backend.core.rbac.get_admin_account_by_username",
            new_callable=AsyncMock, return_value=account,
        ), patch(
            "web.backend.core.admin_credentials.verify_password",
            return_value=False,
        ):
            assert await verify_admin_password_async("admin", "wrong") is False

    @patch("web.backend.core.security.verify_admin_password", return_value=True)
    async def test_falls_back_to_env(self, mock_sync):
        with patch(
            "web.backend.core.rbac.get_admin_account_by_username",
            new_callable=AsyncMock, return_value=None,
        ):
            result = await verify_admin_password_async("admin", "secret")
            assert result is True
            mock_sync.assert_called_once_with("admin", "secret")

    @patch("web.backend.core.security.verify_admin_password", return_value=True)
    async def test_falls_back_on_db_exception(self, mock_sync):
        with patch(
            "web.backend.core.rbac.get_admin_account_by_username",
            new_callable=AsyncMock, side_effect=Exception("DB down"),
        ):
            result = await verify_admin_password_async("admin", "secret")
            assert result is True

    @patch("web.backend.core.security.verify_admin_password", return_value=False)
    async def test_both_fail(self, mock_sync):
        with patch(
            "web.backend.core.rbac.get_admin_account_by_username",
            new_callable=AsyncMock, return_value=None,
        ):
            assert await verify_admin_password_async("admin", "wrong") is False


# ── JWT token round-trip ──────────────────────────────────────


class TestJwtTokens:

    def test_access_token_roundtrip(self):
        token = create_access_token("12345", "testuser", "password")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "12345"
        assert payload["username"] == "testuser"
        assert payload["auth_method"] == "password"
        assert payload["type"] == "access"

    def test_refresh_token_roundtrip(self):
        token = create_refresh_token("12345")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "12345"
        assert payload["type"] == "refresh"

    def test_invalid_token_returns_none(self):
        assert decode_token("invalid.token.here") is None

    def test_empty_token(self):
        assert decode_token("") is None

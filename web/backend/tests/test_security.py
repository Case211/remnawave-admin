"""Tests for web.backend.core.security — JWT tokens and Telegram auth."""
import time
from unittest.mock import patch

import pytest

from web.backend.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_telegram_auth,
    verify_admin_password,
)


class TestJWTTokens:
    """JWT token creation and validation."""

    def test_create_access_token(self):
        token = create_access_token("pwd:admin", "admin", auth_method="password")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token(self):
        token = create_refresh_token("pwd:admin")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_access_token(self):
        token = create_access_token("pwd:testuser", "testuser", auth_method="password")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "pwd:testuser"
        assert payload["username"] == "testuser"
        assert payload["type"] == "access"
        assert payload["auth_method"] == "password"

    def test_decode_valid_refresh_token(self):
        token = create_refresh_token("12345")
        payload = decode_token(token, token_type="refresh")
        assert payload is not None
        assert payload["sub"] == "12345"
        assert payload["type"] == "refresh"

    def test_decode_invalid_token(self):
        payload = decode_token("invalid.token.here")
        assert payload is None

    def test_decode_empty_token(self):
        payload = decode_token("")
        assert payload is None

    def test_access_token_contains_iat(self):
        token = create_access_token("pwd:admin", "admin")
        payload = decode_token(token)
        assert "iat" in payload
        assert "exp" in payload
        assert payload["exp"] > payload["iat"]

    def test_access_token_telegram_method(self):
        token = create_access_token("12345", "tg_user", auth_method="telegram")
        payload = decode_token(token)
        assert payload["auth_method"] == "telegram"
        assert payload["sub"] == "12345"

    def test_refresh_token_has_no_username(self):
        token = create_refresh_token("pwd:admin")
        payload = decode_token(token, token_type="refresh")
        assert "username" not in payload

    def test_token_expiry_is_in_future(self):
        token = create_access_token("pwd:admin", "admin")
        payload = decode_token(token)
        assert payload["exp"] > time.time()


class TestTelegramAuth:
    """Telegram Login Widget verification."""

    def test_missing_hash(self):
        is_valid, error = verify_telegram_auth({"id": 1, "auth_date": int(time.time())})
        assert not is_valid
        assert "Missing hash" in error

    def test_missing_auth_date(self):
        is_valid, error = verify_telegram_auth({"id": 1, "hash": "abc123"})
        assert not is_valid
        assert "Missing auth_date" in error

    def test_expired_auth_data(self):
        old_timestamp = int(time.time()) - 100000  # Way past 24h
        is_valid, error = verify_telegram_auth({
            "id": 1,
            "auth_date": old_timestamp,
            "hash": "abc123",
        })
        assert not is_valid
        assert "expired" in error.lower()

    def test_future_timestamp(self):
        future_timestamp = int(time.time()) + 3600  # 1 hour in future
        is_valid, error = verify_telegram_auth({
            "id": 1,
            "auth_date": future_timestamp,
            "hash": "abc123",
        })
        assert not is_valid
        assert "future" in error.lower()

    def test_invalid_auth_date_format(self):
        is_valid, error = verify_telegram_auth({
            "id": 1,
            "auth_date": "not-a-number",
            "hash": "abc123",
        })
        assert not is_valid
        assert "Invalid auth_date" in error

    def test_invalid_signature(self):
        is_valid, error = verify_telegram_auth({
            "id": 12345,
            "first_name": "Test",
            "auth_date": int(time.time()),
            "hash": "0000000000000000000000000000000000000000000000000000000000000000",
        })
        assert not is_valid
        assert "Invalid signature" in error

    def test_none_values_excluded_from_check_string(self):
        """None values should not be included in the data-check-string."""
        is_valid, error = verify_telegram_auth({
            "id": 12345,
            "first_name": "Test",
            "last_name": None,
            "username": None,
            "auth_date": int(time.time()),
            "hash": "wrong_hash",
        })
        # Should fail due to wrong hash, not due to None handling
        assert not is_valid
        assert "Invalid signature" in error


class TestPasswordVerification:
    """verify_admin_password (sync .env fallback)."""

    def test_no_env_credentials(self):
        """When admin_login/password not set, should return False."""
        from web.backend.core.config import get_web_settings
        settings = get_web_settings()
        # In test env, these are typically None
        if not settings.admin_login:
            assert not verify_admin_password("admin", "password")

    def test_wrong_username(self):
        with patch("web.backend.core.security.get_web_settings") as mock:
            mock.return_value.admin_login = "admin"
            mock.return_value.admin_password = "secret"
            assert not verify_admin_password("wrong_user", "secret")

    def test_wrong_password(self):
        with patch("web.backend.core.security.get_web_settings") as mock:
            mock.return_value.admin_login = "admin"
            mock.return_value.admin_password = "secret"
            assert not verify_admin_password("admin", "wrong_password")

    def test_correct_plaintext_credentials(self):
        with patch("web.backend.core.security.get_web_settings") as mock:
            mock.return_value.admin_login = "admin"
            mock.return_value.admin_password = "secret"
            assert verify_admin_password("admin", "secret")

    def test_case_insensitive_username(self):
        with patch("web.backend.core.security.get_web_settings") as mock:
            mock.return_value.admin_login = "Admin"
            mock.return_value.admin_password = "secret"
            assert verify_admin_password("admin", "secret")


# ── Password reset token tests ──

def test_create_password_reset_token():
    from web.backend.core.security import create_password_reset_token, decode_token
    token = create_password_reset_token(admin_id=42, username="testuser")
    payload = decode_token(token, token_type="password_reset")
    assert payload is not None
    assert payload["sub"] == "42"
    assert payload["username"] == "testuser"
    assert payload["type"] == "password_reset"

def test_password_reset_token_wrong_type():
    from web.backend.core.security import create_password_reset_token, decode_token
    token = create_password_reset_token(admin_id=1, username="admin")
    # Should fail when checking as access token
    payload = decode_token(token, token_type="access")
    assert payload is None

def test_password_reset_token_expired():
    from web.backend.core.security import decode_token
    from jose import jwt
    from datetime import datetime, timezone, timedelta
    from web.backend.core.config import get_web_settings
    settings = get_web_settings()
    # Create an already-expired token
    payload = {
        "sub": "1",
        "username": "admin",
        "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
        "iat": int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()),
        "type": "password_reset",
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    result = decode_token(token, token_type="password_reset")
    assert result is None

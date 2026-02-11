"""Tests for web.backend.core.config — application configuration."""
import os
from unittest.mock import patch

import pytest

from web.backend.core.config import WebSettings


class TestWebSettings:
    """Configuration parsing and validation."""

    def _make_settings(self, **overrides):
        """Create settings with required fields + overrides."""
        env = {
            "WEB_SECRET_KEY": "test-key",
            "BOT_TOKEN": "123:abc",
            "API_BASE_URL": "http://localhost:3000",
        }
        env.update(overrides)
        with patch.dict(os.environ, env, clear=False):
            return WebSettings(**env)

    def test_default_values(self):
        s = self._make_settings()
        assert s.host == "0.0.0.0"
        assert s.port == 8081
        assert s.jwt_algorithm == "HS256"
        assert s.jwt_expire_minutes == 30
        assert s.jwt_refresh_hours == 6

    def test_debug_flag(self):
        s = self._make_settings(WEB_DEBUG="false")
        assert s.debug is False
        s = self._make_settings(WEB_DEBUG="true")
        assert s.debug is True

    def test_cors_origins_parsing(self):
        s = self._make_settings(WEB_CORS_ORIGINS="http://a.com,http://b.com")
        assert s.cors_origins == ["http://a.com", "http://b.com"]

    def test_cors_origins_empty(self):
        s = self._make_settings(WEB_CORS_ORIGINS="")
        assert s.cors_origins == []

    def test_admins_parsing(self):
        s = self._make_settings(ADMINS="123,456,789")
        assert s.admins == [123, 456, 789]

    def test_admins_empty(self):
        s = self._make_settings(ADMINS="")
        assert s.admins == []

    def test_admins_with_whitespace(self):
        s = self._make_settings(ADMINS=" 123 , 456 ")
        assert s.admins == [123, 456]

    def test_admins_ignores_invalid(self):
        s = self._make_settings(ADMINS="123,not_a_number,456")
        assert s.admins == [123, 456]

    def test_jwt_algorithm_validation(self):
        # Valid algorithms
        for alg in ("HS256", "HS384", "HS512"):
            s = self._make_settings(WEB_JWT_ALGORITHM=alg)
            assert s.jwt_algorithm == alg

    def test_jwt_invalid_algorithm_rejected(self):
        with pytest.raises(Exception):
            self._make_settings(WEB_JWT_ALGORITHM="RS256")

    def test_allowed_ips_default_empty(self):
        s = self._make_settings()
        assert s.allowed_ips == ""

    def test_database_url_optional(self):
        s = self._make_settings()
        assert s.database_url is None

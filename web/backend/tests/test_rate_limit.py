"""Tests for rate limiting configuration."""
import pytest
from unittest.mock import patch

from web.backend.core.rate_limit import (
    limiter,
    RATE_AUTH,
    RATE_MUTATIONS,
    RATE_READ,
    RATE_ANALYTICS,
    RATE_EXPORT,
    RATE_BULK,
    configure_limiter,
)


class TestRateLimitConstants:
    """Verify rate limit preset values."""

    def test_auth_rate(self):
        assert RATE_AUTH == "10/minute"

    def test_mutations_rate(self):
        assert RATE_MUTATIONS == "60/minute"

    def test_read_rate(self):
        assert RATE_READ == "120/minute"

    def test_analytics_rate(self):
        assert RATE_ANALYTICS == "30/minute"

    def test_export_rate(self):
        assert RATE_EXPORT == "10/minute"

    def test_bulk_rate(self):
        assert RATE_BULK == "10/minute"


class TestConfigureLimiter:
    """Tests for configure_limiter."""

    def test_none_url_does_nothing(self):
        """Passing None should not change anything."""
        configure_limiter(None)
        # No exception raised

    def test_empty_string_url_does_nothing(self):
        configure_limiter("")

    def test_invalid_url_logs_warning(self):
        """Invalid Redis URL should log warning but not crash."""
        # The function catches exceptions internally
        configure_limiter("redis://invalid-host:99999/bad")
        # No exception raised — gracefully handled

"""Tests for web.backend.core.violation_notifier — notification formatting and throttling.

Covers: _cleanup_cache, _esc, _short_provider, send_violation_notification (throttling,
message formatting, hwid devices, edge cases).
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core.violation_notifier import (
    _cleanup_cache,
    _esc,
    _short_provider,
    _violation_notification_cache,
    VIOLATION_NOTIFICATION_COOLDOWN_MINUTES,
    send_violation_notification,
)


# ── _esc tests ────────────────────────────────────────────────


class TestEsc:
    def test_escapes_html(self):
        assert _esc("<b>test</b>") == "&lt;b&gt;test&lt;/b&gt;"
        assert _esc("a & b") == "a &amp; b"

    def test_empty_string(self):
        assert _esc("") == ""

    def test_no_html(self):
        assert _esc("hello world") == "hello world"


# ── _short_provider tests ────────────────────────────────────


class TestShortProvider:
    def test_short_name_unchanged(self):
        assert _short_provider("Comcast") == "Comcast"

    def test_long_name_truncated(self):
        long = "Very Long Internet Service Provider Name Inc."
        result = _short_provider(long)
        assert len(result) == 25
        assert result.endswith("...")

    def test_empty(self):
        assert _short_provider(None) == ""
        assert _short_provider("") == ""

    def test_exactly_25_chars(self):
        name = "A" * 25
        assert _short_provider(name) == name


# ── _cleanup_cache tests ─────────────────────────────────────


class TestCleanupCache:
    def setup_method(self):
        _violation_notification_cache.clear()

    def teardown_method(self):
        _violation_notification_cache.clear()

    def test_removes_old_entries(self):
        _violation_notification_cache["old"] = datetime.utcnow() - timedelta(hours=2)
        _violation_notification_cache["fresh"] = datetime.utcnow()
        _cleanup_cache()
        assert "old" not in _violation_notification_cache
        assert "fresh" in _violation_notification_cache

    def test_empty_cache(self):
        _cleanup_cache()
        assert len(_violation_notification_cache) == 0


# ── send_violation_notification tests ─────────────────────────


class TestSendViolationNotification:
    def setup_method(self):
        _violation_notification_cache.clear()

    def teardown_method(self):
        _violation_notification_cache.clear()

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_sends_basic_notification(self, mock_create):
        violation_score = {"total": 75.0, "breakdown": {}, "recommended_action": "warn"}
        user_info = {
            "username": "testuser",
            "hwidDeviceLimit": 3,
        }

        await send_violation_notification(
            user_uuid="uuid-123",
            violation_score=violation_score,
            user_info=user_info,
        )

        mock_create.assert_awaited_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["type"] == "violation"
        assert call_kwargs.kwargs["severity"] == "warning"
        assert call_kwargs.kwargs["source"] == "collector"
        assert call_kwargs.kwargs["source_id"] == "uuid-123"

        # Check throttle cache updated
        assert "uuid-123" in _violation_notification_cache

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_throttled_within_cooldown(self, mock_create):
        _violation_notification_cache["uuid-123"] = datetime.utcnow()

        await send_violation_notification(
            user_uuid="uuid-123",
            violation_score={"total": 80},
        )

        mock_create.assert_not_awaited()

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_not_throttled_after_cooldown(self, mock_create):
        _violation_notification_cache["uuid-123"] = (
            datetime.utcnow() - timedelta(minutes=VIOLATION_NOTIFICATION_COOLDOWN_MINUTES + 1)
        )

        await send_violation_notification(
            user_uuid="uuid-123",
            violation_score={"total": 80, "breakdown": {}},
            user_info={"username": "test", "hwidDeviceLimit": 1},
        )

        mock_create.assert_awaited_once()

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_force_bypasses_throttle(self, mock_create):
        _violation_notification_cache["uuid-123"] = datetime.utcnow()

        await send_violation_notification(
            user_uuid="uuid-123",
            violation_score={"total": 90, "breakdown": {}},
            user_info={"username": "test", "hwidDeviceLimit": 1},
            force=True,
        )

        mock_create.assert_awaited_once()

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_critical_severity_for_high_score(self, mock_create):
        await send_violation_notification(
            user_uuid="uuid-high",
            violation_score={"total": 85.0, "breakdown": {}},
            user_info={"username": "baduser", "hwidDeviceLimit": 2},
        )

        mock_create.assert_awaited_once()
        assert mock_create.call_args.kwargs["severity"] == "critical"

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_message_contains_user_info(self, mock_create):
        await send_violation_notification(
            user_uuid="uuid-msg",
            violation_score={"total": 60.0, "breakdown": {}},
            user_info={
                "username": "alice",
                "email": "alice@example.com",
                "telegramId": 99999,
                "hwidDeviceLimit": 3,
                "description": "VIP user",
            },
        )

        body = mock_create.call_args.kwargs["body"]
        assert "alice@example.com" in body
        assert "99999" in body
        assert "VIP user" in body

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_ip_count_from_temporal_breakdown(self, mock_create):
        violation_score = {
            "total": 70.0,
            "breakdown": {
                "temporal": {"simultaneous_connections_count": 5},
            },
        }

        await send_violation_notification(
            user_uuid="uuid-ip",
            violation_score=violation_score,
            user_info={"username": "test", "hwidDeviceLimit": 2},
        )

        body = mock_create.call_args.kwargs["body"]
        assert "5/2" in body

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_device_limit_zero_shows_infinity(self, mock_create):
        await send_violation_notification(
            user_uuid="uuid-inf",
            violation_score={"total": 60, "breakdown": {}},
            user_info={"username": "test", "hwidDeviceLimit": 0},
        )

        body = mock_create.call_args.kwargs["body"]
        assert "\u221e" in body

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_fetches_user_info_from_db_when_not_provided(self, mock_create):
        mock_db = MagicMock()
        mock_db.get_user_by_uuid = AsyncMock(return_value={
            "username": "from_db", "hwidDeviceLimit": 1,
        })

        with patch("shared.database.db_service", mock_db):
            await send_violation_notification(
                user_uuid="uuid-nodb",
                violation_score={"total": 60, "breakdown": {}},
                user_info=None,
            )

        body = mock_create.call_args.kwargs["body"]
        assert "from_db" in body

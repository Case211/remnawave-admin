"""Tests for security notification functions (consolidated in notification_service)."""
import pytest
from unittest.mock import patch, AsyncMock

from web.backend.core.notification_service import (
    _esc_html,
    _now_str,
    notify_login_failed,
    notify_login_success,
    notify_ip_blocked,
    notify_ip_rejected,
)


class TestEscHtml:
    def test_escapes_special_chars(self):
        assert _esc_html("<b>test&") == "&lt;b&gt;test&amp;"

    def test_plain_text_unchanged(self):
        assert _esc_html("hello world") == "hello world"


class TestNowStr:
    def test_returns_string_in_panel_zone(self):
        from unittest.mock import patch
        from shared import timefmt

        with patch.object(timefmt, "zone_name", return_value="Asia/Yekaterinburg"):
            result = _now_str()
        assert result.endswith("UTC+5")
        assert len(result) > 10


class TestNotifyFunctions:

    @pytest.mark.asyncio
    @patch("web.backend.core.notification_service._send_to_global_telegram", new_callable=AsyncMock)
    async def test_notify_login_failed(self, mock_send):
        await notify_login_failed(
            ip="1.2.3.4", username="admin", auth_method="password",
            reason="wrong password", failures_count=3,
        )

    @pytest.mark.asyncio
    @patch("web.backend.core.notification_service._send_to_global_telegram", new_callable=AsyncMock)
    async def test_notify_login_success(self, mock_send):
        await notify_login_success(ip="1.2.3.4", username="admin", auth_method="telegram")

    @pytest.mark.asyncio
    @patch("web.backend.core.notification_service._send_to_global_telegram", new_callable=AsyncMock)
    async def test_notify_ip_blocked(self, mock_send):
        await notify_ip_blocked(ip="5.6.7.8", lockout_seconds=600, failures=10)

    @pytest.mark.asyncio
    @patch("web.backend.core.notification_service._send_to_global_telegram", new_callable=AsyncMock)
    async def test_notify_ip_rejected(self, mock_send):
        await notify_ip_rejected(ip="9.10.11.12", path="/api/v2/users")

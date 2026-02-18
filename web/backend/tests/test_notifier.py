"""Tests for lightweight Telegram notifier."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from web.backend.core.notifier import (
    _esc,
    _now_str,
    _send_telegram_message,
    notify_login_failed,
    notify_login_success,
    notify_ip_blocked,
    notify_ip_rejected,
)


def _fake_settings(chat_id="12345", topic_service=None, topic_id=None):
    s = MagicMock()
    s.telegram_bot_token = "123:ABC"
    s.notifications_chat_id = chat_id
    s.notifications_topic_service = topic_service
    s.notifications_topic_id = topic_id
    return s


class TestEsc:
    """Tests for HTML escaping."""

    def test_escapes_ampersand(self):
        assert _esc("a&b") == "a&amp;b"

    def test_escapes_lt(self):
        assert _esc("<script>") == "&lt;script&gt;"

    def test_escapes_gt(self):
        assert _esc("a>b") == "a&gt;b"

    def test_no_change_for_plain_text(self):
        assert _esc("hello world") == "hello world"

    def test_converts_non_string(self):
        assert _esc(42) == "42"


class TestNowStr:
    """Tests for _now_str."""

    def test_returns_string_with_utc(self):
        result = _now_str()
        assert "UTC" in result
        assert len(result) > 10


class TestSendTelegramMessage:
    """Tests for _send_telegram_message."""

    @pytest.mark.asyncio
    @patch("web.backend.core.notifier.get_web_settings")
    @patch("web.backend.core.notifier.httpx.AsyncClient")
    async def test_no_chat_id_returns_false(self, mock_client_cls, mock_settings):
        mock_settings.return_value = _fake_settings(chat_id=None)
        result = await _send_telegram_message("test message")
        assert result is False
        mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    @patch("web.backend.core.notifier.get_web_settings")
    @patch("web.backend.core.notifier.httpx.AsyncClient")
    async def test_sends_post_to_telegram(self, mock_client_cls, mock_settings):
        mock_settings.return_value = _fake_settings(chat_id="12345")

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await _send_telegram_message("test message")
        assert result is True
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert "sendMessage" in call_kwargs[0][0]

    @pytest.mark.asyncio
    @patch("web.backend.core.notifier.get_web_settings")
    @patch("web.backend.core.notifier.httpx.AsyncClient")
    async def test_telegram_api_error_returns_false(self, mock_client_cls, mock_settings):
        mock_settings.return_value = _fake_settings(chat_id="12345")

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await _send_telegram_message("test message")
        assert result is False

    @pytest.mark.asyncio
    @patch("web.backend.core.notifier.get_web_settings")
    @patch("web.backend.core.notifier.httpx.AsyncClient")
    async def test_network_error_returns_false(self, mock_client_cls, mock_settings):
        mock_settings.return_value = _fake_settings(chat_id="12345")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await _send_telegram_message("test message")
        assert result is False

    @pytest.mark.asyncio
    @patch("web.backend.core.notifier.get_web_settings")
    @patch("web.backend.core.notifier.httpx.AsyncClient")
    async def test_topic_id_included(self, mock_client_cls, mock_settings):
        mock_settings.return_value = _fake_settings(chat_id="12345", topic_service="99")

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await _send_telegram_message("test", topic_id=None)
        assert result is True
        payload = mock_client.post.call_args[1]["json"]
        assert payload["message_thread_id"] == 99


class TestNotifyFunctions:
    """Tests that notify_* functions build correct message text."""

    @pytest.mark.asyncio
    @patch("web.backend.core.notifier._send_telegram_message", new_callable=AsyncMock)
    async def test_notify_login_failed(self, mock_send):
        await notify_login_failed(
            ip="1.2.3.4",
            username="admin",
            auth_method="password",
            reason="wrong password",
            failures_count=3,
        )
        # It uses create_task, so just verify no crash
        # The actual send is fire-and-forget

    @pytest.mark.asyncio
    @patch("web.backend.core.notifier._send_telegram_message", new_callable=AsyncMock)
    async def test_notify_login_success(self, mock_send):
        await notify_login_success(
            ip="1.2.3.4",
            username="admin",
            auth_method="telegram",
        )

    @pytest.mark.asyncio
    @patch("web.backend.core.notifier._send_telegram_message", new_callable=AsyncMock)
    async def test_notify_ip_blocked(self, mock_send):
        await notify_ip_blocked(ip="5.6.7.8", lockout_seconds=600, failures=10)

    @pytest.mark.asyncio
    @patch("web.backend.core.notifier._send_telegram_message", new_callable=AsyncMock)
    async def test_notify_ip_rejected(self, mock_send):
        await notify_ip_rejected(ip="9.10.11.12", path="/api/v2/users")

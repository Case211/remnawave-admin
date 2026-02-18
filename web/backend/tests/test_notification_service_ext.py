"""Extended tests for web.backend.core.notification_service.

Covers: send_telegram, send_webhook, send_email, create_notification,
_dispatch_external, _send_to_global_telegram, test_smtp.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core.notification_service import (
    send_telegram,
    send_webhook,
    send_email,
    create_notification,
    _dispatch_external,
    _send_to_global_telegram,
)
from web.backend.core import notification_service as ns_mod


# ── send_telegram ──────────────────────────────────────────────


class TestSendTelegram:

    @patch("web.backend.core.notification_service.httpx.AsyncClient")
    async def test_success(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_telegram("12345", "Title", "Body", bot_token="123:ABC")
        assert result is True

    @patch("web.backend.core.notification_service.httpx.AsyncClient")
    async def test_failure(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_telegram("12345", "Title", "Body", bot_token="123:ABC")
        assert result is False

    async def test_no_bot_token(self):
        with patch("web.backend.core.config.get_web_settings") as ms:
            ms.return_value.telegram_bot_token = None
            result = await send_telegram("12345", "Title", "Body")
        assert result is False

    @patch("web.backend.core.notification_service.httpx.AsyncClient")
    async def test_with_topic_id(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await send_telegram("12345", "T", "B", topic_id="99", bot_token="123:ABC")
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["message_thread_id"] == 99

    @patch("web.backend.core.notification_service.httpx.AsyncClient")
    async def test_topic_id_zero_ignored(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await send_telegram("12345", "T", "B", topic_id="0", bot_token="123:ABC")
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "message_thread_id" not in payload

    @patch("web.backend.core.notification_service.httpx.AsyncClient")
    async def test_exception_returns_false(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network err"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_telegram("12345", "T", "B", bot_token="123:ABC")
        assert result is False


# ── send_webhook ───────────────────────────────────────────────


class TestSendWebhook:

    @patch("web.backend.core.notification_service.httpx.AsyncClient")
    async def test_generic_webhook(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_webhook("https://example.com/hook", "Title", "Body")
        assert result is True

    @patch("web.backend.core.notification_service.httpx.AsyncClient")
    async def test_discord_webhook(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_webhook(
            "https://discord.com/api/webhooks/123/abc",
            "Alert", "Body", severity="critical",
        )
        assert result is True
        payload = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
        assert "embeds" in payload

    @patch("web.backend.core.notification_service.httpx.AsyncClient")
    async def test_slack_webhook(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_webhook(
            "https://hooks.slack.com/services/T/B/x",
            "Title", "Body",
        )
        assert result is True
        payload = mock_client.post.call_args.kwargs.get("json") or mock_client.post.call_args[1].get("json")
        assert "text" in payload

    @patch("web.backend.core.notification_service.httpx.AsyncClient")
    async def test_webhook_failure(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Server Error"
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_webhook("https://example.com/hook", "Title", "Body")
        assert result is False

    @patch("web.backend.core.notification_service.httpx.AsyncClient")
    async def test_webhook_exception(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await send_webhook("https://example.com/hook", "T", "B")
        assert result is False


# ── send_email ─────────────────────────────────────────────────


class TestSendEmail:

    async def test_no_smtp_no_builtin_returns_false(self):
        """When both built-in mail server and SMTP relay are unavailable."""
        with patch.object(ns_mod, "_get_smtp_config",
                          new_callable=AsyncMock, return_value=None):
            # Built-in mail import will fail inside the function
            result = await send_email("test@example.com", "Title", "Body")
        assert result is False


# ── create_notification ─────────────────────────────────────────


class TestCreateNotification:

    async def test_single_admin_notification(self):
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=42)
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)

        db = MagicMock()
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.api.v2.websocket.manager", MagicMock(broadcast=AsyncMock())), \
             patch("web.backend.core.notification_service.asyncio") as mock_asyncio:
            mock_asyncio.create_task = MagicMock()
            nid = await create_notification(
                title="Test", body="Body", admin_id=1,
            )

        assert nid == 42

    async def test_broadcast_notification(self):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
        conn.fetchval = AsyncMock(return_value=100)
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)

        db = MagicMock()
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.api.v2.websocket.manager", MagicMock(broadcast=AsyncMock())), \
             patch("web.backend.core.notification_service.asyncio") as mock_asyncio:
            mock_asyncio.create_task = MagicMock()
            nid = await create_notification(
                title="Broadcast", body="Body",
            )

        assert nid == 100

    async def test_deduplication(self):
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=99)  # existing notification ID
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)

        db = MagicMock()
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.api.v2.websocket.manager", MagicMock(broadcast=AsyncMock())):
            nid = await create_notification(
                title="Dup", body="Body", admin_id=1, group_key="dup-key",
            )

        assert nid == 99

    async def test_handles_db_exception(self):
        db = MagicMock()
        db.acquire.side_effect = Exception("DB down")

        with patch("shared.database.db_service", db):
            nid = await create_notification(title="Err", body="Body")

        assert nid is None


# ── _send_to_global_telegram ──────────────────────────────────


class TestSendToGlobalTelegram:

    @patch("web.backend.core.notification_service.send_telegram", new_callable=AsyncMock, return_value=True)
    @patch("web.backend.core.notification_service._get_global_telegram_config")
    async def test_sends_message(self, mock_config, mock_send):
        mock_config.return_value = ("123:ABC", "12345", "99")
        await _send_to_global_telegram("Alert", "Body", "warning")
        mock_send.assert_awaited_once()

    @patch("web.backend.core.notification_service._get_global_telegram_config")
    async def test_skips_when_no_chat_id(self, mock_config):
        mock_config.return_value = ("123:ABC", None, None)
        await _send_to_global_telegram("Alert", "Body", "info")
        # No error, just skips

    @patch("web.backend.core.notification_service._get_global_telegram_config")
    async def test_skips_when_no_bot_token(self, mock_config):
        mock_config.return_value = (None, "12345", None)
        await _send_to_global_telegram("Alert", "Body", "info")


# ── _dispatch_external ────────────────────────────────────────


class TestDispatchExternal:

    async def test_telegram_channel(self):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {"channel_type": "telegram", "config": {"chat_id": "111", "topic_id": None}},
        ])
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)

        db = MagicMock()
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.send_telegram", new_callable=AsyncMock) as mock_tg:
            await _dispatch_external(1, "Title", "Body", "info", None, ["telegram"])

        mock_tg.assert_awaited_once()

    async def test_webhook_channel(self):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {"channel_type": "webhook", "config": {"url": "https://example.com/hook"}},
        ])
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)

        db = MagicMock()
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.send_webhook", new_callable=AsyncMock) as mock_wh:
            await _dispatch_external(1, "T", "B", "info", None, ["webhook"])

        mock_wh.assert_awaited_once()

    async def test_email_channel(self):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {"channel_type": "email", "config": {"email": "admin@test.com"}},
        ])
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)

        db = MagicMock()
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.send_email", new_callable=AsyncMock) as mock_email:
            await _dispatch_external(1, "T", "B", "info", None, ["email"])

        mock_email.assert_awaited_once()

    async def test_no_channels_configured(self):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)

        db = MagicMock()
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db):
            await _dispatch_external(1, "T", "B", "info", None, ["telegram"])
            # Should not raise

    async def test_skips_non_requested_channel(self):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {"channel_type": "telegram", "config": {"chat_id": "111"}},
        ])
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)

        db = MagicMock()
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.send_telegram", new_callable=AsyncMock) as mock_tg:
            await _dispatch_external(1, "T", "B", "info", None, ["email"])

        mock_tg.assert_not_awaited()

    async def test_all_channels_requested(self):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[
            {"channel_type": "telegram", "config": {"chat_id": "111"}},
        ])
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)

        db = MagicMock()
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.send_telegram", new_callable=AsyncMock) as mock_tg:
            await _dispatch_external(1, "T", "B", "info", None, ["all"])

        mock_tg.assert_awaited_once()


# ── test_smtp ─────────────────────────────────────────────────


class TestTestSmtp:

    @patch("web.backend.core.notification_service.send_email", new_callable=AsyncMock, return_value=True)
    async def test_success(self, mock_send):
        result = await ns_mod.test_smtp("test@example.com")
        assert result["success"] is True
        assert result["to"] == "test@example.com"

    @patch("web.backend.core.notification_service.send_email", new_callable=AsyncMock, return_value=False)
    async def test_failure(self, mock_send):
        result = await ns_mod.test_smtp("test@example.com")
        assert result["success"] is False

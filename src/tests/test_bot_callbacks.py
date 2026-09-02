"""Tests for src/services/bot_callbacks.py — notification dispatch & HTML escaping."""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request with .app.state.bot."""
    bot = AsyncMock()
    app = MagicMock()
    app.state.bot = bot
    req = MagicMock()
    req.app = app
    return req


@pytest.fixture
def set_secret():
    os.environ["INTERNAL_API_SECRET"] = "test-secret-123"
    yield
    os.environ.pop("INTERNAL_API_SECRET", None)


# ── _verify_internal_secret ────────────────────────────────────


class TestVerifySecret:
    @pytest.mark.asyncio
    async def test_missing_env_var_returns_false(self):
        os.environ.pop("INTERNAL_API_SECRET", None)
        from src.services.bot_callbacks import _verify_internal_secret
        req = MagicMock()
        req.headers.get.return_value = "anything"
        assert _verify_internal_secret(req) is False

    @pytest.mark.asyncio
    async def test_missing_header_returns_false(self):
        os.environ["INTERNAL_API_SECRET"] = "my-secret"
        from src.services.bot_callbacks import _verify_internal_secret
        req = MagicMock()
        req.headers.get.return_value = ""
        assert _verify_internal_secret(req) is False
        del os.environ["INTERNAL_API_SECRET"]

    @pytest.mark.asyncio
    async def test_mismatch_returns_false(self):
        os.environ["INTERNAL_API_SECRET"] = "my-secret"
        from src.services.bot_callbacks import _verify_internal_secret
        req = MagicMock()
        req.headers.get.return_value = "wrong-secret"
        assert _verify_internal_secret(req) is False
        del os.environ["INTERNAL_API_SECRET"]

    @pytest.mark.asyncio
    async def test_match_returns_true(self):
        os.environ["INTERNAL_API_SECRET"] = "my-secret"
        from src.services.bot_callbacks import _verify_internal_secret
        req = MagicMock()
        req.headers.get.return_value = "my-secret"
        assert _verify_internal_secret(req) is True
        del os.environ["INTERNAL_API_SECRET"]


# ── telegram_send endpoint ──────────────────────────────────────


class TestTelegramSend:
    @pytest.mark.asyncio
    async def test_missing_chat_id_returns_400(self, set_secret):
        from src.services.bot_callbacks import telegram_send
        req = MagicMock()
        req.app.state.bot = AsyncMock()
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={"title": "Test", "body": "Body"})
        with pytest.raises(HTTPException) as exc:
            await telegram_send(req)
        assert exc.value.status_code == 400

    async def test_no_bot_returns_500(self, set_secret):
        from src.services.bot_callbacks import telegram_send
        req = MagicMock()
        req.app.state.bot = None
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={"chat_id": "123", "title": "Hi", "body": "Msg"})
        with pytest.raises(HTTPException) as exc:
            await telegram_send(req)
        assert exc.value.status_code == 500

    async def test_unauthorized(self):
        os.environ["INTERNAL_API_SECRET"] = "real-secret"
        from src.services.bot_callbacks import telegram_send
        req = MagicMock()
        req.app.state.bot = AsyncMock()
        req.headers.get.return_value = ""
        req.json = AsyncMock(return_value={"chat_id": "123", "title": "Hi", "body": "Msg"})
        with pytest.raises(HTTPException) as exc:
            await telegram_send(req)
        assert exc.value.status_code == 401
        os.environ.pop("INTERNAL_API_SECRET", None)

    # Транспорт сменился в 3.1.0: rich-уведомления уходят через
    # shared.tg_rich (raw httpx), а не через aiogram. Тесты этого не
    # заметили — они продолжали ждать bot.send_message и молча краснели,
    # то есть отправку из bot_callbacks вообще ничто не проверяло.
    @pytest.fixture
    def rich_send(self):
        with patch("shared.tg_rich.send_rich_or_html", new_callable=AsyncMock) as mock:
            mock.return_value = True
            yield mock

    @staticmethod
    def _request(payload: dict):
        req = MagicMock()
        req.app.state.bot = AsyncMock()
        req.app.state.bot.token = "123:abc"
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value=payload)
        return req

    async def test_successful_send(self, set_secret, rich_send):
        from src.services.bot_callbacks import telegram_send
        req = self._request({"chat_id": "456", "title": "Hello", "body": "World"})
        resp = await telegram_send(req)
        assert resp.status_code == 200
        rich_send.assert_awaited_once()
        token, chat_id, text = rich_send.await_args.args
        assert token == "123:abc"
        assert chat_id == "456"
        assert text == "<b>Hello</b>\n\nWorld"
        assert rich_send.await_args.kwargs["message_thread_id"] is None

    async def test_with_topic_id(self, set_secret, rich_send):
        from src.services.bot_callbacks import telegram_send
        req = self._request({"chat_id": "456", "title": "T", "body": "B", "topic_id": "789"})
        resp = await telegram_send(req)
        assert resp.status_code == 200
        assert rich_send.await_args.kwargs["message_thread_id"] == 789

    async def test_topic_id_zero_ignored(self, set_secret, rich_send):
        """Ноль — не топик, а его отсутствие."""
        from src.services.bot_callbacks import telegram_send
        req = self._request({"chat_id": "456", "title": "T", "body": "B", "topic_id": "0"})
        resp = await telegram_send(req)
        assert resp.status_code == 200
        assert rich_send.await_args.kwargs["message_thread_id"] is None

    async def test_html_escaping_in_title(self, set_secret, rich_send):
        """Title should be html.escape()'d before wrapping in <b> tags."""
        from src.services.bot_callbacks import telegram_send
        req = self._request({"chat_id": "1", "title": "<script>alert('xss')</script>", "body": "safe"})
        resp = await telegram_send(req)
        assert resp.status_code == 200
        sent = rich_send.await_args.args[2]
        assert "<script>" not in sent
        assert "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;" in sent

    async def test_no_title_skips_b_tag(self, set_secret, rich_send):
        from src.services.bot_callbacks import telegram_send
        req = self._request({"chat_id": "1", "body": "Just body"})
        resp = await telegram_send(req)
        assert resp.status_code == 200
        assert rich_send.await_args.args[2] == "Just body"

    async def test_bot_send_failure_returns_500(self, set_secret, rich_send):
        from src.services.bot_callbacks import telegram_send
        rich_send.side_effect = Exception("TG API down")
        req = self._request({"chat_id": "1", "title": "T", "body": "B"})
        with pytest.raises(HTTPException) as exc:
            await telegram_send(req)
        assert exc.value.status_code == 500


# ── panel_event endpoint ────────────────────────────────────────


class TestPanelEvent:
    async def test_unauthorized(self):
        os.environ["INTERNAL_API_SECRET"] = "s"
        from src.services.bot_callbacks import panel_event
        req = MagicMock()
        req.app.state.bot = AsyncMock()
        req.headers.get.return_value = ""
        req.json = AsyncMock(return_value={"event": "user.created", "data": {}})
        with pytest.raises(HTTPException) as exc:
            await panel_event(req)
        assert exc.value.status_code == 401
        os.environ.pop("INTERNAL_API_SECRET", None)

    async def test_no_bot_returns_500(self, set_secret):
        from src.services.bot_callbacks import panel_event
        req = MagicMock()
        req.app.state.bot = None
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={"event": "user.created", "data": {}})
        with pytest.raises(HTTPException) as exc:
            await panel_event(req)
        assert exc.value.status_code == 500

    async def test_user_created_event(self, set_secret):
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={
            "event": "user.created",
            "data": {"uuid": "abc-123", "username": "alice"},
        })
        with patch("src.utils.notifications.send_user_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        mock_notif.assert_called_once()
        args, kwargs = mock_notif.call_args
        assert kwargs["bot"] is bot
        assert kwargs["action"] == "created"
        assert kwargs["event_type"] == "user.created"

    async def test_user_event_response_wrapping(self, set_secret):
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={
            "event": "user.created",
            "data": {"uuid": "x", "response": {"uuid": "x", "username": "bob"}},
        })
        with patch("src.utils.notifications.send_user_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        user_info = mock_notif.call_args.kwargs["user_info"]
        assert "response" in user_info

    async def test_user_expired_event_maps_action(self, set_secret):
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={
            "event": "user.expired",
            "data": {"uuid": "abc"},
        })
        with patch("src.utils.notifications.send_user_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        assert mock_notif.call_args.kwargs["action"] == "expired"

    async def test_user_event_missing_uuid_skipped(self, set_secret):
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={"event": "user.expired", "data": {}})
        with patch("src.utils.notifications.send_user_notification") as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        mock_notif.assert_not_called()

    async def test_user_event_v3_numeric_id_not_skipped(self, set_secret):
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={
            "event": "user.modified",
            "data": {"id": 42, "username": "alice", "status": "ACTIVE"},
        })
        with patch("src.utils.notifications.send_user_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        mock_notif.assert_called_once()
        assert mock_notif.call_args.kwargs["action"] == "updated"

    async def test_user_modified_passes_diff_from_collector(self, set_secret):
        """Старое состояние и изменения приезжают от коллектора и уходят в уведомление.

        Бот сам их не восстановит: коллектор уже записал новое состояние в
        общую базу, и без переданного diff уведомление выходило с
        «Изменения не определены».
        """
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        old = {"uuid": "u-1", "username": "alice", "expireAt": "2026-09-07T21:51:00Z"}
        req.json = AsyncMock(return_value={
            "event": "user.modified",
            "data": {"uuid": "u-1", "username": "alice", "expireAt": "2026-09-12T21:51:00Z"},
            "diff": {"old_data": old, "changes": ["• Срок действия: 07.09 → 12.09"]},
        })
        with patch("src.utils.notifications.send_user_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        kw = mock_notif.call_args.kwargs
        assert kw["old_user_info"] == old
        assert kw["changes"] == ["• Срок действия: 07.09 → 12.09"]

    async def test_user_modified_without_diff_keeps_working(self, set_secret):
        """Старый коллектор без поля diff — уведомление всё равно уходит."""
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={
            "event": "user.modified",
            "data": {"uuid": "u-1", "username": "alice"},
        })
        with patch("src.utils.notifications.send_user_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        kw = mock_notif.call_args.kwargs
        assert kw["old_user_info"] is None
        assert kw["changes"] is None


class TestUserIdentifierHelpers:
    @pytest.mark.asyncio
    async def test_local_user_uuid_v2_uuid_present(self):
        from src.utils.notifications import _local_user_uuid
        assert await _local_user_uuid({"uuid": "abc-123", "id": 7}) == "abc-123"

    @pytest.mark.asyncio
    async def test_local_user_uuid_v3_id_resolves_to_local(self):
        from src.utils.notifications import _local_user_uuid
        with patch("shared.data_access.db_service", is_connected=True) as db:
            db.get_user_uuid_by_panel_id = AsyncMock(return_value="local-uuid-9")
            assert await _local_user_uuid({"id": 42}) == "local-uuid-9"
            db.get_user_uuid_by_panel_id.assert_awaited_once_with(42)

    @pytest.mark.asyncio
    async def test_local_user_uuid_v3_unknown_returns_none(self):
        from src.utils.notifications import _local_user_uuid
        with patch("shared.data_access.db_service", is_connected=True) as db:
            db.get_user_uuid_by_panel_id = AsyncMock(return_value=None)
            assert await _local_user_uuid({"id": 42}) is None

    @pytest.mark.asyncio
    async def test_local_user_uuid_v3_no_db_disconnected(self):
        from src.utils.notifications import _local_user_uuid
        with patch("shared.data_access.db_service", is_connected=False):
            assert await _local_user_uuid({"id": 42}) is None

    @pytest.mark.asyncio
    async def test_local_user_uuid_empty_payload(self):
        from src.utils.notifications import _local_user_uuid
        assert await _local_user_uuid({}) is None

    async def test_node_event(self, set_secret):
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={
            "event": "node.created",
            "data": {"uuid": "node-1", "name": "Node1"},
        })
        with patch("src.utils.notifications.send_node_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        mock_notif.assert_called_once()

    async def test_service_event(self, set_secret):
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={
            "event": "service.started",
            "data": {"service": "panel"},
        })
        with patch("src.utils.notifications.send_service_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        mock_notif.assert_called_once()

    async def test_hwid_event(self, set_secret):
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={
            "event": "user_hwid_devices.created",
            "data": {"uuid": "hwid-1"},
        })
        with patch("src.utils.notifications.send_hwid_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        mock_notif.assert_called_once()

    async def test_error_event(self, set_secret):
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={
            "event": "errors.panel_crash",
            "data": {"error": "OOM"},
        })
        with patch("src.utils.notifications.send_error_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        mock_notif.assert_called_once()

    async def test_crm_event(self, set_secret):
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={
            "event": "crm.ticket_created",
            "data": {"ticket_id": 1},
        })
        with patch("src.utils.notifications.send_crm_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        mock_notif.assert_called_once()

    async def test_unknown_event_uses_generic(self, set_secret):
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={
            "event": "unknown.event_type",
            "data": {"key": "val"},
        })
        with patch("src.utils.notifications.send_generic_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        mock_notif.assert_called_once()
        msg = mock_notif.call_args.kwargs["message"]
        assert "unknown.event_type" in msg

    async def test_html_escaping_in_unknown_event(self, set_secret):
        from src.services.bot_callbacks import panel_event
        bot = AsyncMock()
        req = MagicMock()
        req.app.state.bot = bot
        req.headers.get.return_value = "test-secret-123"
        req.json = AsyncMock(return_value={
            "event": "<script>alert(1)</script>",
            "data": {"a": "<b>bold</b>"},
        })
        with patch("src.utils.notifications.send_generic_notification", new=AsyncMock()) as mock_notif:
            resp = await panel_event(req)
        assert resp.status_code == 200
        msg = mock_notif.call_args.kwargs["message"]
        assert "<script>" not in msg
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in msg
        assert "<b>bold</b>" not in msg

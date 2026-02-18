"""Tests for web.backend.core.terminal_sessions.

Covers: TerminalSession (touch, is_idle, duration_seconds),
TerminalSessionManager (create, close, get, cleanup, cooldown, active_count).
"""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core.terminal_sessions import (
    TerminalSession,
    TerminalSessionManager,
    IDLE_TIMEOUT_SECONDS,
    SESSION_COOLDOWN_SECONDS,
)


# ── TerminalSession ──────────────────────────────────────────


class TestTerminalSession:

    def test_touch_updates_last_activity(self):
        session = TerminalSession(
            session_id="s1", node_uuid="n1", admin_id=1, admin_username="admin",
        )
        old_activity = session.last_activity
        time.sleep(0.01)
        session.touch()
        assert session.last_activity > old_activity

    def test_is_idle_false_when_fresh(self):
        session = TerminalSession(
            session_id="s1", node_uuid="n1", admin_id=1, admin_username="admin",
        )
        assert session.is_idle is False

    def test_is_idle_true_when_expired(self):
        session = TerminalSession(
            session_id="s1", node_uuid="n1", admin_id=1, admin_username="admin",
        )
        session.last_activity = time.time() - IDLE_TIMEOUT_SECONDS - 1
        assert session.is_idle is True

    def test_duration_seconds(self):
        session = TerminalSession(
            session_id="s1", node_uuid="n1", admin_id=1, admin_username="admin",
        )
        session.created_at = time.time() - 120
        assert session.duration_seconds >= 119

    def test_default_terminal_size(self):
        session = TerminalSession(
            session_id="s1", node_uuid="n1", admin_id=1, admin_username="admin",
        )
        assert session.cols == 80
        assert session.rows == 24

    def test_custom_terminal_size(self):
        session = TerminalSession(
            session_id="s1", node_uuid="n1", admin_id=1, admin_username="admin",
            cols=120, rows=40,
        )
        assert session.cols == 120
        assert session.rows == 40


# ── TerminalSessionManager ────────────────────────────────────


class TestTerminalSessionManager:

    async def test_create_session(self):
        mgr = TerminalSessionManager()
        ws = AsyncMock()

        with patch.object(mgr, "_log_session_start", new_callable=AsyncMock):
            session = await mgr.create_session("n1", 1, "admin", ws)

        assert session is not None
        assert session.node_uuid == "n1"
        assert session.admin_id == 1
        assert mgr.active_count == 1

    async def test_cannot_create_duplicate_active_session(self):
        mgr = TerminalSessionManager()
        ws = AsyncMock()

        with patch.object(mgr, "_log_session_start", new_callable=AsyncMock):
            s1 = await mgr.create_session("n1", 1, "admin", ws)
            assert s1 is not None

            # Second session for same node should fail
            s2 = await mgr.create_session("n1", 2, "admin2", ws)
            assert s2 is None

    async def test_replaces_idle_session(self):
        mgr = TerminalSessionManager()
        ws = AsyncMock()

        with patch.object(mgr, "_log_session_start", new_callable=AsyncMock):
            s1 = await mgr.create_session("n1", 1, "admin", ws)
            # Make session idle
            s1.last_activity = time.time() - IDLE_TIMEOUT_SECONDS - 1

            # Wait for cooldown to expire
            mgr._node_last_close["n1"] = 0

            s2 = await mgr.create_session("n1", 2, "admin2", ws)
            assert s2 is not None
            assert s2.admin_id == 2
            assert mgr.active_count == 1

    async def test_cooldown_blocks_creation(self):
        mgr = TerminalSessionManager()
        ws = AsyncMock()
        mgr._node_last_close["n1"] = time.time()  # Just closed

        with patch.object(mgr, "_log_session_start", new_callable=AsyncMock):
            session = await mgr.create_session("n1", 1, "admin", ws)

        assert session is None

    async def test_close_session(self):
        mgr = TerminalSessionManager()
        ws = AsyncMock()

        with patch.object(mgr, "_log_session_start", new_callable=AsyncMock):
            session = await mgr.create_session("n1", 1, "admin", ws)

        with patch.object(mgr, "_log_session_end", new_callable=AsyncMock):
            await mgr.close_session(session.session_id, reason="test")

        assert mgr.active_count == 0
        assert mgr.get_session(session.session_id) is None

    async def test_close_nonexistent_session(self):
        mgr = TerminalSessionManager()
        with patch.object(mgr, "_log_session_end", new_callable=AsyncMock) as mock_log:
            await mgr.close_session("nonexistent")
        mock_log.assert_not_awaited()

    async def test_get_session(self):
        mgr = TerminalSessionManager()
        ws = AsyncMock()

        with patch.object(mgr, "_log_session_start", new_callable=AsyncMock):
            session = await mgr.create_session("n1", 1, "admin", ws)

        found = mgr.get_session(session.session_id)
        assert found is session

    async def test_get_session_for_node(self):
        mgr = TerminalSessionManager()
        ws = AsyncMock()

        with patch.object(mgr, "_log_session_start", new_callable=AsyncMock):
            session = await mgr.create_session("n1", 1, "admin", ws)

        found = mgr.get_session_for_node("n1")
        assert found is session

    async def test_get_session_for_node_not_found(self):
        mgr = TerminalSessionManager()
        assert mgr.get_session_for_node("n999") is None

    async def test_active_count(self):
        mgr = TerminalSessionManager()
        ws = AsyncMock()

        assert mgr.active_count == 0

        with patch.object(mgr, "_log_session_start", new_callable=AsyncMock):
            await mgr.create_session("n1", 1, "admin1", ws)
            # Need to bypass cooldown for second node
            await mgr.create_session("n2", 2, "admin2", ws)

        assert mgr.active_count == 2

    async def test_cleanup_idle(self):
        mgr = TerminalSessionManager()
        ws = AsyncMock()

        with patch.object(mgr, "_log_session_start", new_callable=AsyncMock):
            session = await mgr.create_session("n1", 1, "admin", ws)
        session.last_activity = time.time() - IDLE_TIMEOUT_SECONDS - 1

        with patch.object(mgr, "_log_session_end", new_callable=AsyncMock):
            await mgr._cleanup_idle()

        assert mgr.active_count == 0

    async def test_close_session_closes_websocket(self):
        mgr = TerminalSessionManager()
        ws = AsyncMock()
        ws.close = AsyncMock()

        with patch.object(mgr, "_log_session_start", new_callable=AsyncMock):
            session = await mgr.create_session("n1", 1, "admin", ws)

        with patch.object(mgr, "_log_session_end", new_callable=AsyncMock):
            await mgr.close_session(session.session_id)

        ws.close.assert_awaited_once()

    async def test_close_session_sets_cooldown(self):
        mgr = TerminalSessionManager()
        ws = AsyncMock()

        with patch.object(mgr, "_log_session_start", new_callable=AsyncMock):
            session = await mgr.create_session("n1", 1, "admin", ws)

        with patch.object(mgr, "_log_session_end", new_callable=AsyncMock):
            await mgr.close_session(session.session_id)

        assert "n1" in mgr._node_last_close


# ── DB logging ────────────────────────────────────────────────


class TestSessionDbLogging:

    async def test_log_session_start(self):
        mgr = TerminalSessionManager()
        session = TerminalSession(
            session_id="s1", node_uuid="n1", admin_id=1, admin_username="admin",
        )

        conn = AsyncMock()
        conn.execute = AsyncMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        db = MagicMock()
        db.is_connected = True
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db):
            await mgr._log_session_start(session)

        conn.execute.assert_awaited_once()

    async def test_log_session_end(self):
        mgr = TerminalSessionManager()
        session = TerminalSession(
            session_id="s1", node_uuid="n1", admin_id=1, admin_username="admin",
        )

        conn = AsyncMock()
        conn.execute = AsyncMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        db = MagicMock()
        db.is_connected = True
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db):
            await mgr._log_session_end(session, "closed")

        conn.execute.assert_awaited_once()

    async def test_log_session_start_handles_disconnect(self):
        mgr = TerminalSessionManager()
        session = TerminalSession(
            session_id="s1", node_uuid="n1", admin_id=1, admin_username="admin",
        )
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            await mgr._log_session_start(session)  # should not raise

    async def test_log_session_end_handles_error(self):
        mgr = TerminalSessionManager()
        session = TerminalSession(
            session_id="s1", node_uuid="n1", admin_id=1, admin_username="admin",
        )
        db = MagicMock()
        db.is_connected = True
        db.acquire.side_effect = Exception("err")

        with patch("shared.database.db_service", db):
            await mgr._log_session_end(session, "error")  # should not raise

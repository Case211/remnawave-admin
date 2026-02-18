"""Tests for AgentConnectionManager — WebSocket connection tracking."""
import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from web.backend.core.agent_manager import AgentConnectionManager


@pytest.fixture()
def manager():
    return AgentConnectionManager()


@pytest.fixture()
def mock_ws():
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


class TestRegister:
    """Tests for registering agent connections."""

    @pytest.mark.asyncio
    async def test_register_adds_connection(self, manager, mock_ws):
        await manager.register("node-1", mock_ws)
        assert manager.is_connected("node-1")
        assert manager.count == 1

    @pytest.mark.asyncio
    async def test_register_replaces_old_connection(self, manager):
        old_ws = AsyncMock()
        old_ws.close = AsyncMock()
        new_ws = AsyncMock()

        await manager.register("node-1", old_ws)
        await manager.register("node-1", new_ws)

        old_ws.close.assert_called_once_with(code=4000, reason="replaced")
        assert manager.count == 1

    @pytest.mark.asyncio
    async def test_register_old_close_error_ignored(self, manager):
        old_ws = AsyncMock()
        old_ws.close = AsyncMock(side_effect=Exception("already closed"))
        new_ws = AsyncMock()

        await manager.register("node-1", old_ws)
        await manager.register("node-1", new_ws)
        assert manager.is_connected("node-1")


class TestUnregister:
    """Tests for unregistering agent connections."""

    @pytest.mark.asyncio
    async def test_unregister_removes_connection(self, manager, mock_ws):
        await manager.register("node-1", mock_ws)
        await manager.unregister("node-1")
        assert not manager.is_connected("node-1")
        assert manager.count == 0

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_no_error(self, manager):
        await manager.unregister("nonexistent")
        assert manager.count == 0


class TestIsConnected:
    """Tests for is_connected check."""

    @pytest.mark.asyncio
    async def test_not_connected_returns_false(self, manager):
        assert manager.is_connected("node-1") is False

    @pytest.mark.asyncio
    async def test_connected_returns_true(self, manager, mock_ws):
        await manager.register("node-1", mock_ws)
        assert manager.is_connected("node-1") is True


class TestListConnected:
    """Tests for list_connected."""

    @pytest.mark.asyncio
    async def test_empty(self, manager):
        assert manager.list_connected() == []

    @pytest.mark.asyncio
    async def test_multiple_nodes(self, manager):
        await manager.register("node-a", AsyncMock())
        await manager.register("node-b", AsyncMock())
        connected = manager.list_connected()
        assert set(connected) == {"node-a", "node-b"}


class TestSendCommand:
    """Tests for sending commands to agents."""

    @pytest.mark.asyncio
    async def test_send_success(self, manager, mock_ws):
        await manager.register("node-1", mock_ws)
        result = await manager.send_command("node-1", {"action": "restart"})
        assert result is True
        mock_ws.send_text.assert_called_once()
        sent = json.loads(mock_ws.send_text.call_args[0][0])
        assert sent["action"] == "restart"

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_returns_false(self, manager):
        result = await manager.send_command("missing", {"action": "restart"})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_error_removes_connection(self, manager):
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=Exception("broken pipe"))
        await manager.register("node-1", ws)

        result = await manager.send_command("node-1", {"action": "restart"})
        assert result is False
        assert not manager.is_connected("node-1")


class TestGetWebsocket:
    """Tests for get_websocket."""

    @pytest.mark.asyncio
    async def test_returns_websocket(self, manager, mock_ws):
        await manager.register("node-1", mock_ws)
        ws = await manager.get_websocket("node-1")
        assert ws is mock_ws

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self, manager):
        ws = await manager.get_websocket("missing")
        assert ws is None

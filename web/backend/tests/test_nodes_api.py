"""Tests for nodes API — /api/v2/nodes/*."""
import pytest
from unittest.mock import patch, AsyncMock

from web.backend.api.deps import get_current_admin
from .conftest import make_admin


MOCK_NODES = [
    {
        "uuid": "node-aaa",
        "name": "EU-1",
        "address": "1.2.3.4",
        "port": 443,
        "is_disabled": False,
        "is_connected": True,
        "is_xray_running": True,
        "xray_version": "1.8.4",
        "traffic_used_bytes": 1_000_000,
        "traffic_total_bytes": 1_000_000,
        "traffic_today_bytes": 500_000,
        "users_online": 5,
        "cpu_usage": 25.0,
        "memory_usage": 40.0,
        "uptime_seconds": 86400,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-02-01T00:00:00Z",
        "last_seen_at": "2026-02-16T10:00:00Z",
    },
    {
        "uuid": "node-bbb",
        "name": "US-1",
        "address": "5.6.7.8",
        "port": 443,
        "is_disabled": True,
        "is_connected": False,
        "is_xray_running": False,
        "xray_version": None,
        "traffic_used_bytes": 0,
        "traffic_total_bytes": 0,
        "traffic_today_bytes": 0,
        "users_online": 0,
        "cpu_usage": 0,
        "memory_usage": 0,
        "uptime_seconds": 0,
        "created_at": "2026-01-02T00:00:00Z",
        "updated_at": "2026-02-01T00:00:00Z",
        "last_seen_at": None,
    },
]


class TestListNodes:
    """GET /api/v2/nodes."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes._get_nodes_list", new_callable=AsyncMock, return_value=MOCK_NODES)
    @patch("web.backend.api.v2.nodes.fetch_nodes_usage_by_range", new_callable=AsyncMock, return_value=None)
    @patch("web.backend.api.v2.nodes.fetch_nodes_realtime_usage", new_callable=AsyncMock, return_value=None)
    async def test_list_nodes_success(self, mock_realtime, mock_range, mock_get, client):
        resp = await client.get("/api/v2/nodes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes._get_nodes_list", new_callable=AsyncMock, return_value=MOCK_NODES)
    @patch("web.backend.api.v2.nodes.fetch_nodes_usage_by_range", new_callable=AsyncMock, return_value=None)
    @patch("web.backend.api.v2.nodes.fetch_nodes_realtime_usage", new_callable=AsyncMock, return_value=None)
    async def test_list_nodes_filter_connected(self, mock_realtime, mock_range, mock_get, client):
        resp = await client.get("/api/v2/nodes?is_connected=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "EU-1"

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes._get_nodes_list", new_callable=AsyncMock, return_value=MOCK_NODES)
    @patch("web.backend.api.v2.nodes.fetch_nodes_usage_by_range", new_callable=AsyncMock, return_value=None)
    @patch("web.backend.api.v2.nodes.fetch_nodes_realtime_usage", new_callable=AsyncMock, return_value=None)
    async def test_list_nodes_search(self, mock_realtime, mock_range, mock_get, client):
        resp = await client.get("/api/v2/nodes?search=EU")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_nodes_as_viewer_allowed(self, app, viewer):
        """Viewers have nodes.view permission."""
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            with patch("web.backend.api.v2.nodes._get_nodes_list", new_callable=AsyncMock, return_value=[]):
                with patch("web.backend.api.v2.nodes.fetch_nodes_usage_by_range", new_callable=AsyncMock, return_value=None):
                    with patch("web.backend.api.v2.nodes.fetch_nodes_realtime_usage", new_callable=AsyncMock, return_value=None):
                        resp = await ac.get("/api/v2/nodes")
                        assert resp.status_code == 200


class TestListNodesRBAC:
    """RBAC tests for node endpoints."""

    @pytest.mark.asyncio
    async def test_anon_get_nodes_unauthorized(self, anon_client):
        resp = await anon_client.get("/api/v2/nodes")
        assert resp.status_code == 401


class TestEnsureNodeSnakeCase:
    """Tests for _ensure_node_snake_case helper."""

    def test_maps_camel_to_snake(self):
        from web.backend.api.v2.nodes import _ensure_node_snake_case
        node = {"isDisabled": True, "isConnected": False, "xrayVersion": "1.8.4"}
        result = _ensure_node_snake_case(node)
        assert result["is_disabled"] is True
        assert result["is_connected"] is False
        assert result["xray_version"] == "1.8.4"

    def test_traffic_total_fallback(self):
        from web.backend.api.v2.nodes import _ensure_node_snake_case
        node = {"traffic_used_bytes": 100}
        result = _ensure_node_snake_case(node)
        assert result["traffic_total_bytes"] == 100

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


class TestAgentMeta:
    """GET /api/v2/nodes/agent-meta — статический роут НЕ должен проваливаться
    в /{node_uuid} (боевой 500: get_node("agent-meta") уходил в Panel API)."""

    @pytest.mark.asyncio
    async def test_returns_latest_version(self, client):
        from shared.agent_version import LATEST_AGENT_VERSION
        resp = await client.get("/api/v2/nodes/agent-meta")
        assert resp.status_code == 200
        assert resp.json()["latest_agent_version"] == LATEST_AGENT_VERSION

    @pytest.mark.asyncio
    async def test_requires_auth(self, anon_client):
        resp = await anon_client.get("/api/v2/nodes/agent-meta")
        assert resp.status_code == 401


class TestGetNodeInvalidUuid:
    @pytest.mark.asyncio
    async def test_non_uuid_is_clean_404(self, client):
        """Мусор вместо UUID — 404, а не поход в панель и необработанный 500."""
        resp = await client.get("/api/v2/nodes/definitely-not-a-uuid")
        assert resp.status_code == 404


def test_panel_node_fields_reach_the_list_item():
    """«Последний раз в сети» на карточке всегда пустовал: поля lastSeenAt панель
    не присылает. Карточка показывает момент смены статуса — он должен доходить."""
    from web.backend.api.v2.nodes import _ensure_node_snake_case, _normalize
    from web.backend.schemas.node import NodeListItem

    raw = {
        "uuid": "6a4a7ce3-5574-4c2f-83ff-7cd979c82251", "name": "Finland", "address": "100.108.75.189",
        "port": 3000, "isConnected": True, "isDisabled": False, "usersOnline": 0,
        "lastStatusChange": "2026-09-23T10:53:31.400Z", "countryCode": "FI",
        "trafficResetDay": 1, "isTrafficTrackingActive": False, "trafficUsedBytes": 25_070_198_691_136,
        "versions": {"xray": "26.6.27", "node": "2.8.0"},
        "system": {"info": {"cpus": 1, "memoryTotal": 2058178560},
                   "stats": {"memoryUsed": 630784000, "uptime": 694.61, "loadAvg": [0, 0.03, 0.04],
                             "interface": {"rxBytesPerSec": 9176, "txBytesPerSec": 8350}}},
    }
    item = NodeListItem(**_ensure_node_snake_case(_normalize(raw))).model_dump()
    assert item["last_status_change"].isoformat().startswith("2026-09-23T10:53:31")
    assert item["country_code"] == "FI"
    assert item["node_version"] == "2.8.0" and item["xray_version"] == "26.6.27"
    assert item["traffic_reset_day"] == 1
    assert item["uptime_seconds"] == 694 and item["memory_usage"] == 30.6

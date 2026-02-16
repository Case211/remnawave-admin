"""Tests for analytics API — /api/v2/analytics/*."""
import pytest
from unittest.mock import patch, AsyncMock

from web.backend.api.deps import get_current_admin
from .conftest import make_admin


MOCK_USERS = [
    {"status": "active", "used_traffic_bytes": 1000, "uuid": "u1"},
    {"status": "active", "used_traffic_bytes": 2000, "uuid": "u2"},
    {"status": "disabled", "used_traffic_bytes": 500, "uuid": "u3"},
]

MOCK_NODES = [
    {"uuid": "n1", "name": "EU-1", "is_connected": True, "is_disabled": False, "users_online": 5},
    {"uuid": "n2", "name": "US-1", "is_connected": False, "is_disabled": True, "users_online": 0},
]

MOCK_HOSTS = [
    {"uuid": "h1", "remark": "host-1"},
]


class TestOverview:
    """GET /api/v2/analytics/overview."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.analytics.fetch_users_from_api", new_callable=AsyncMock, return_value=MOCK_USERS)
    @patch("web.backend.api.v2.analytics.fetch_nodes_from_api", new_callable=AsyncMock, return_value=MOCK_NODES)
    @patch("web.backend.api.v2.analytics.fetch_hosts_from_api", new_callable=AsyncMock, return_value=MOCK_HOSTS)
    @patch("web.backend.api.v2.analytics.fetch_bandwidth_stats", new_callable=AsyncMock, return_value=None)
    async def test_overview_success(self, mock_bw, mock_hosts, mock_nodes, mock_users, client):
        # Clear any cached values
        from web.backend.core.cache import cache
        await cache.delete("analytics:overview")

        resp = await client.get("/api/v2/analytics/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_users"] == 3
        assert data["active_users"] == 2
        assert data["total_nodes"] == 2
        assert data["online_nodes"] == 1

    @pytest.mark.asyncio
    async def test_overview_as_viewer_allowed(self, app, viewer):
        """Viewers have analytics.view permission."""
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            with patch("web.backend.api.v2.analytics.fetch_users_from_api", new_callable=AsyncMock, return_value=[]):
                with patch("web.backend.api.v2.analytics.fetch_nodes_from_api", new_callable=AsyncMock, return_value=[]):
                    with patch("web.backend.api.v2.analytics.fetch_hosts_from_api", new_callable=AsyncMock, return_value=[]):
                        with patch("web.backend.api.v2.analytics.fetch_bandwidth_stats", new_callable=AsyncMock, return_value=None):
                            from web.backend.core.cache import cache
                            await cache.delete("analytics:overview")
                            resp = await ac.get("/api/v2/analytics/overview")
                            assert resp.status_code == 200


class TestAnalyticsRBAC:
    """RBAC tests for analytics endpoints."""

    @pytest.mark.asyncio
    async def test_anon_overview_unauthorized(self, anon_client):
        resp = await anon_client.get("/api/v2/analytics/overview")
        assert resp.status_code == 401


class TestOverviewModels:
    """Tests for analytics Pydantic models."""

    def test_overview_stats_defaults(self):
        from web.backend.api.v2.analytics import OverviewStats
        stats = OverviewStats()
        assert stats.total_users == 0
        assert stats.active_users == 0
        assert stats.total_nodes == 0
        assert stats.violations_today == 0

    def test_traffic_stats_defaults(self):
        from web.backend.api.v2.analytics import TrafficStats
        stats = TrafficStats()
        assert stats.total_bytes == 0
        assert stats.today_bytes == 0

    def test_timeseries_point(self):
        from web.backend.api.v2.analytics import TimeseriesPoint
        point = TimeseriesPoint(timestamp="2026-02-16T00:00:00Z", value=100)
        assert point.value == 100

    def test_delta_stats_defaults(self):
        from web.backend.api.v2.analytics import DeltaStats
        delta = DeltaStats()
        assert delta.users_delta is None
        assert delta.traffic_delta is None

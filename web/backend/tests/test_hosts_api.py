"""Tests for hosts API — /api/v2/hosts/*."""
import pytest
from unittest.mock import patch, AsyncMock

from web.backend.api.deps import get_current_admin
from .conftest import make_admin


MOCK_HOST_API = {
    "uuid": "host-111",
    "remark": "my-host",
    "address": "example.com",
    "port": 443,
    "isDisabled": False,
    "viewPosition": 0,
    "inbound": {"configProfileInboundUuid": "inbound-1"},
    "sni": "example.com",
    "host": "example.com",
    "path": "/ws",
    "security": "tls",
    "securityLayer": "tls",
    "alpn": "h2,http/1.1",
    "fingerprint": "chrome",
    "tag": None,
    "serverDescription": None,
    "isHidden": False,
    "shuffleHost": False,
    "mihomoX25519": False,
    "nodes": [],
    "excludedInternalSquads": [],
    "createdAt": "2026-01-01T00:00:00Z",
    "updatedAt": "2026-02-01T00:00:00Z",
}


class TestMapHost:
    """Tests for _map_host and _map_host_detail helpers."""

    def test_map_host_basic(self):
        from web.backend.api.v2.hosts import _map_host
        result = _map_host(MOCK_HOST_API)
        assert result["uuid"] == "host-111"
        assert result["remark"] == "my-host"
        assert result["is_disabled"] is False
        assert result["inbound_uuid"] == "inbound-1"
        assert result["sni"] == "example.com"

    def test_map_host_detail(self):
        from web.backend.api.v2.hosts import _map_host_detail
        result = _map_host_detail(MOCK_HOST_API)
        assert result["created_at"] == "2026-01-01T00:00:00Z"
        assert result["allow_insecure"] is False


class TestListHosts:
    """GET /api/v2/hosts."""

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.hosts._get_hosts_list",
        new_callable=AsyncMock,
        return_value=[MOCK_HOST_API, MOCK_HOST_API],
    )
    async def test_list_hosts_success(self, mock_get, client):
        resp = await client.get("/api/v2/hosts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.hosts._get_hosts_list",
        new_callable=AsyncMock,
        return_value=[],
    )
    async def test_list_hosts_empty(self, mock_get, client):
        resp = await client.get("/api/v2/hosts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_hosts_as_viewer_allowed(self, app, viewer):
        """Viewers have hosts.view permission."""
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            with patch("web.backend.api.v2.hosts._get_hosts_list", new_callable=AsyncMock, return_value=[]):
                resp = await ac.get("/api/v2/hosts")
                assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_hosts_anon_unauthorized(self, anon_client):
        resp = await anon_client.get("/api/v2/hosts")
        assert resp.status_code == 401


class TestListHostsRBAC:
    """RBAC tests for host write operations."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_host(self, app, viewer):
        """Viewers don't have hosts.create permission."""
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v2/hosts", json={"remark": "test"})
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_operator_cannot_create_host(self, app, operator):
        """Operators don't have hosts.create permission."""
        app.dependency_overrides[get_current_admin] = lambda: operator
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v2/hosts", json={"remark": "test"})
            assert resp.status_code == 403

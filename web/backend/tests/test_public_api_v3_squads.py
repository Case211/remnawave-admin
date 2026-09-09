"""Tests for /api/v3/squads/* and squad fields of POST /api/v3/users."""
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from web.backend.core.config import get_web_settings
from web.backend.main import create_app


READ_KEY = {"id": 1, "name": "read-key", "scopes": ["users:read"]}
WRITE_KEY = {"id": 2, "name": "write-key", "scopes": ["users:write"]}
NODES_KEY = {"id": 3, "name": "nodes-key", "scopes": ["nodes:read"]}

INTERNAL_PAYLOAD = {"response": {"internalSquads": [
    {
        "uuid": "S1", "name": "Standard",
        "info": {"membersCount": 5, "inboundsCount": 1},
        "inbounds": [{"uuid": "i1", "tag": "VLESS-Reality", "type": "vless"}],
    },
    {"name": "без uuid — пропускается"},
]}}
EXTERNAL_PAYLOAD = {"response": {"externalSquads": [
    {"uuid": "E1", "name": "Partners", "info": {"membersCount": 2}},
]}}


@pytest.fixture()
def v3_app(monkeypatch):
    monkeypatch.setenv("EXTERNAL_API_ENABLED", "true")
    get_web_settings.cache_clear()
    _app = create_app()
    yield _app
    _app.dependency_overrides.clear()
    get_web_settings.cache_clear()


@pytest_asyncio.fixture()
async def v3_client(v3_app):
    transport = ASGITransport(app=v3_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestSquadsV3:
    @pytest.mark.asyncio
    async def test_missing_api_key(self, v3_client):
        resp = await v3_client.get("/api/v3/squads/internal")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=NODES_KEY)
    async def test_missing_scope(self, _v, v3_client):
        resp = await v3_client.get("/api/v3/squads/external", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 403
        assert "users:read" in resp.json()["detail"]

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=READ_KEY)
    async def test_internal_squads_flattened(self, _v, v3_client):
        from shared.api_client import api_client

        with patch.object(api_client, "get_internal_squads", new_callable=AsyncMock,
                          return_value=INTERNAL_PAYLOAD):
            resp = await v3_client.get("/api/v3/squads/internal", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 200
        assert resp.json() == [{
            "uuid": "S1", "name": "Standard", "members_count": 5,
            "inbounds": [{"uuid": "i1", "tag": "VLESS-Reality"}],
        }]

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=READ_KEY)
    async def test_external_squads(self, _v, v3_client):
        from shared.api_client import api_client

        with patch.object(api_client, "get_external_squads", new_callable=AsyncMock,
                          return_value=EXTERNAL_PAYLOAD):
            resp = await v3_client.get("/api/v3/squads/external", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 200
        assert resp.json() == [{"uuid": "E1", "name": "Partners", "members_count": 2, "inbounds": None}]

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=READ_KEY)
    async def test_panel_down_is_503(self, _v, v3_client):
        from shared.api_client import api_client

        with patch.object(api_client, "get_internal_squads", new_callable=AsyncMock,
                          side_effect=RuntimeError("panel down")):
            resp = await v3_client.get("/api/v3/squads/internal", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 503


class TestCreateUserSquadsV3:
    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=WRITE_KEY)
    async def test_squads_are_forwarded_to_panel(self, _v, v3_client):
        """Просьба интеграторов: POST /users не принимал external_squad_uuid
        и active_internal_squads, хотя клиент панели их умеет."""
        from shared.api_client import api_client

        with patch.object(api_client, "create_user", new_callable=AsyncMock,
                          return_value={"response": {"uuid": "u1"}}) as create:
            resp = await v3_client.post(
                "/api/v3/users",
                headers={"X-API-Key": "rwa_test"},
                json={
                    "username": "alice", "expire_at": "2027-01-01T00:00:00Z",
                    "external_squad_uuid": "E1", "active_internal_squads": ["S1", "S2"],
                },
            )
        assert resp.status_code == 201
        kwargs = create.call_args.kwargs
        assert kwargs["external_squad_uuid"] == "E1"
        assert kwargs["active_internal_squads"] == ["S1", "S2"]

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=WRITE_KEY)
    async def test_squads_default_to_none(self, _v, v3_client):
        from shared.api_client import api_client

        with patch.object(api_client, "create_user", new_callable=AsyncMock,
                          return_value={"response": {}}) as create:
            resp = await v3_client.post(
                "/api/v3/users",
                headers={"X-API-Key": "rwa_test"},
                json={"username": "bob", "expire_at": "2027-01-01T00:00:00Z"},
            )
        assert resp.status_code == 201
        kwargs = create.call_args.kwargs
        assert kwargs["external_squad_uuid"] is None
        assert kwargs["active_internal_squads"] is None

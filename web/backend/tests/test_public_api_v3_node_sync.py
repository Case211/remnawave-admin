"""Tests for /api/v3/nodes/sync (scope nodes:write)."""
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from web.backend.core.config import get_web_settings
from web.backend.main import create_app


VALID_KEY = {"id": 1, "name": "test-key", "scopes": ["nodes:write"]}
READ_ONLY_KEY = {"id": 2, "name": "limited-key", "scopes": ["nodes:read"]}


@pytest.fixture()
def v3_app(monkeypatch):
    """FastAPI app with the public API v3 enabled."""
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


class TestSyncNodesV3:
    """POST /api/v3/nodes/sync."""

    @pytest.mark.asyncio
    async def test_missing_api_key(self, v3_client):
        resp = await v3_client.post("/api/v3/nodes/sync")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=READ_ONLY_KEY)
    async def test_missing_scope(self, _mock_validate, v3_client):
        resp = await v3_client.post("/api/v3/nodes/sync", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 403
        assert "nodes:write" in resp.json()["detail"]

    @pytest.mark.asyncio
    @patch("shared.sync.sync_service.sync_nodes", new_callable=AsyncMock, return_value=7)
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_sync_success(self, _mock_validate, mock_sync, v3_client):
        resp = await v3_client.post("/api/v3/nodes/sync", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "synced": 7}
        mock_sync.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("shared.sync.sync_service.sync_nodes", new_callable=AsyncMock, side_effect=RuntimeError("panel unreachable"))
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_panel_error_returns_502(self, _mock_validate, _mock_sync, v3_client):
        resp = await v3_client.post("/api/v3/nodes/sync", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 502
        assert "panel unreachable" in resp.json()["detail"]

    @pytest.mark.asyncio
    @patch("shared.sync.sync_service.sync_nodes", new_callable=AsyncMock, return_value=0)
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_db_disconnected_returns_zero_synced(self, _mock_validate, _mock_sync, v3_client):
        """sync_nodes() itself no-ops to 0 when db_service isn't connected — not our
        concern to special-case, just pass the count through."""
        resp = await v3_client.post("/api/v3/nodes/sync", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "synced": 0}

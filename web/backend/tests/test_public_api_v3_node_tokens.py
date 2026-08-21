"""Tests for /api/v3/nodes/{uuid}/agent-token/* (scope nodes:token)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from web.backend.core.config import get_web_settings
from web.backend.main import create_app


NODE_UUID = "11111111-2222-3333-4444-555555555555"

VALID_KEY = {"id": 1, "name": "test-key", "scopes": ["nodes:token"]}
WRITE_ONLY_KEY = {"id": 2, "name": "limited-key", "scopes": ["nodes:write"]}


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


def _mock_db(node_exists=True, connected=True):
    """Build a db_service mock whose acquire() yields a conn mock."""
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=1 if node_exists else None)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)

    db = MagicMock()
    db.is_connected = connected
    db.acquire = MagicMock(return_value=cm)
    return db, conn


class TestGenerateNodeAgentTokenV3:
    """POST /api/v3/nodes/{uuid}/agent-token/generate."""

    @pytest.mark.asyncio
    async def test_missing_api_key(self, v3_client):
        resp = await v3_client.post(f"/api/v3/nodes/{NODE_UUID}/agent-token/generate")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=WRITE_ONLY_KEY)
    async def test_missing_scope(self, _mock_validate, v3_client):
        resp = await v3_client.post(
            f"/api/v3/nodes/{NODE_UUID}/agent-token/generate", headers={"X-API-Key": "rwa_test"}
        )
        assert resp.status_code == 403
        assert "nodes:token" in resp.json()["detail"]

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_node_not_found(self, _mock_validate, v3_client):
        db, _conn = _mock_db(node_exists=False)
        with patch("shared.database.db_service", db):
            resp = await v3_client.post(
                f"/api/v3/nodes/{NODE_UUID}/agent-token/generate", headers={"X-API-Key": "rwa_test"}
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_db_unavailable(self, _mock_validate, v3_client):
        db, _conn = _mock_db(connected=False)
        with patch("shared.database.db_service", db):
            resp = await v3_client.post(
                f"/api/v3/nodes/{NODE_UUID}/agent-token/generate", headers={"X-API-Key": "rwa_test"}
            )
        assert resp.status_code == 503

    @pytest.mark.asyncio
    @patch("web.backend.core.audit.write_audit_log", new_callable=AsyncMock)
    @patch("shared.agent_tokens.set_node_agent_token", new_callable=AsyncMock, return_value="tok_abc123")
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_generate_success(self, _mock_validate, mock_set_token, mock_audit, v3_client):
        db, _conn = _mock_db(node_exists=True)
        with patch("shared.database.db_service", db):
            resp = await v3_client.post(
                f"/api/v3/nodes/{NODE_UUID}/agent-token/generate", headers={"X-API-Key": "rwa_test"}
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["token"] == "tok_abc123"
        mock_set_token.assert_awaited_once()
        mock_audit.assert_awaited_once()
        assert mock_audit.call_args.kwargs["action"] == "node.generate_agent_token"
        assert mock_audit.call_args.kwargs["admin_username"] == "apikey:test-key"

    @pytest.mark.asyncio
    @patch("shared.agent_tokens.set_node_agent_token", new_callable=AsyncMock, return_value=None)
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_generate_failure_returns_500(self, _mock_validate, _mock_set_token, v3_client):
        db, _conn = _mock_db(node_exists=True)
        with patch("shared.database.db_service", db):
            resp = await v3_client.post(
                f"/api/v3/nodes/{NODE_UUID}/agent-token/generate", headers={"X-API-Key": "rwa_test"}
            )
        assert resp.status_code == 500


class TestRevokeNodeAgentTokenV3:
    """POST /api/v3/nodes/{uuid}/agent-token/revoke."""

    @pytest.mark.asyncio
    async def test_missing_api_key(self, v3_client):
        resp = await v3_client.post(f"/api/v3/nodes/{NODE_UUID}/agent-token/revoke")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=WRITE_ONLY_KEY)
    async def test_missing_scope(self, _mock_validate, v3_client):
        resp = await v3_client.post(
            f"/api/v3/nodes/{NODE_UUID}/agent-token/revoke", headers={"X-API-Key": "rwa_test"}
        )
        assert resp.status_code == 403
        assert "nodes:token" in resp.json()["detail"]

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_node_not_found(self, _mock_validate, v3_client):
        db, _conn = _mock_db(node_exists=False)
        with patch("shared.database.db_service", db):
            resp = await v3_client.post(
                f"/api/v3/nodes/{NODE_UUID}/agent-token/revoke", headers={"X-API-Key": "rwa_test"}
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @patch("web.backend.core.audit.write_audit_log", new_callable=AsyncMock)
    @patch("shared.agent_tokens.revoke_node_agent_token", new_callable=AsyncMock, return_value=True)
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_revoke_success(self, _mock_validate, mock_revoke, mock_audit, v3_client):
        db, _conn = _mock_db(node_exists=True)
        with patch("shared.database.db_service", db):
            resp = await v3_client.post(
                f"/api/v3/nodes/{NODE_UUID}/agent-token/revoke", headers={"X-API-Key": "rwa_test"}
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_revoke.assert_awaited_once()
        mock_audit.assert_awaited_once()
        assert mock_audit.call_args.kwargs["action"] == "node.revoke_agent_token"

    @pytest.mark.asyncio
    @patch("shared.agent_tokens.revoke_node_agent_token", new_callable=AsyncMock, return_value=False)
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_revoke_failure_returns_500(self, _mock_validate, _mock_revoke, v3_client):
        db, _conn = _mock_db(node_exists=True)
        with patch("shared.database.db_service", db):
            resp = await v3_client.post(
                f"/api/v3/nodes/{NODE_UUID}/agent-token/revoke", headers={"X-API-Key": "rwa_test"}
            )
        assert resp.status_code == 500


class TestScopeRegistered:
    """nodes:token должен быть в списке допустимых скоупов API-ключей."""

    def test_scope_in_available_scopes(self):
        from web.backend.api.v2.api_keys import AVAILABLE_SCOPES
        assert "nodes:token" in AVAILABLE_SCOPES

"""Tests for /api/v3/violations (scope violations:read)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from web.backend.core.config import get_web_settings
from web.backend.main import create_app


MOCK_VIOLATION_ROW = {
    "id": 9123,
    "user_uuid": "11111111-2222-3333-4444-555555555555",
    "username": "alice",
    "score": 87.5,
    "confidence": 0.9,
    "recommended_action": "hard_block",
    "action_taken": None,
    "reasons": ["4 simultaneous connections"],
    "ip_addresses": ["1.2.3.4"],
    "countries": ["RU", "NL"],
    "detected_at": datetime(2026, 6, 7, 12, 0, 0, tzinfo=timezone.utc),
}

MOCK_VIOLATION_DETAIL_ROW = {
    **MOCK_VIOLATION_ROW,
    "email": "alice@example.com",
    "telegram_id": 123456789,
    "temporal_score": 0.9,
    "geo_score": 0.6,
    "asn_score": None,
    "profile_score": None,
    "device_score": None,
    "hwid_score": None,
    "user_agent_score": None,
    "cities": ["Moscow"],
    "asn_types": ["datacenter"],
    "os_list": None,
    "client_list": None,
    "simultaneous_connections": 4,
    "unique_ips_count": 3,
    "impossible_travel": False,
    "is_mobile": False,
    "is_datacenter": True,
    "is_vpn": False,
    "admin_comment": None,
    "action_taken_at": None,
}

VALID_KEY = {"id": 1, "name": "test-key", "scopes": ["violations:read"]}
NO_SCOPE_KEY = {"id": 2, "name": "limited-key", "scopes": ["users:read"]}


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


def _mock_db(fetch_result=None, fetchrow_result=None):
    """Build a db_service mock whose acquire() yields a conn mock."""
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch_result or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow_result)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)

    db = MagicMock()
    db.is_connected = True
    db.acquire = MagicMock(return_value=cm)
    return db, conn


class TestListViolationsV3:
    """GET /api/v3/violations."""

    @pytest.mark.asyncio
    async def test_missing_api_key(self, v3_client):
        resp = await v3_client.get("/api/v3/violations")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=NO_SCOPE_KEY)
    async def test_missing_scope(self, _mock_validate, v3_client):
        resp = await v3_client.get("/api/v3/violations", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 403
        assert "violations:read" in resp.json()["detail"]

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_list_success(self, _mock_validate, v3_client):
        db, conn = _mock_db(fetch_result=[MOCK_VIOLATION_ROW])
        with patch("shared.database.db_service", db):
            resp = await v3_client.get("/api/v3/violations", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["id"] == 9123
        assert items[0]["username"] == "alice"
        assert items[0]["recommended_action"] == "hard_block"
        assert items[0]["detected_at"].startswith("2026-06-07T12:00:00")

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_filters_are_parameterized(self, _mock_validate, v3_client):
        db, conn = _mock_db(fetch_result=[])
        with patch("shared.database.db_service", db):
            resp = await v3_client.get(
                "/api/v3/violations",
                params={
                    "user_uuid": MOCK_VIOLATION_ROW["user_uuid"],
                    "min_score": 50,
                    "recommended_action": "hard_block",
                    "resolved": "false",
                    "limit": 10,
                    "offset": 5,
                },
                headers={"X-API-Key": "rwa_test"},
            )
        assert resp.status_code == 200
        assert resp.json() == []
        sql = conn.fetch.call_args.args[0]
        assert "user_uuid = $1::uuid" in sql
        assert "score >= $2" in sql
        assert "action_taken IS NULL" in sql
        # limit/offset идут последними параметрами
        assert conn.fetch.call_args.args[-2:] == (10, 5)

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_db_unavailable_returns_empty(self, _mock_validate, v3_client):
        db = MagicMock()
        db.is_connected = False
        with patch("shared.database.db_service", db):
            resp = await v3_client.get("/api/v3/violations", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetViolationV3:
    """GET /api/v3/violations/{id}."""

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_detail_success(self, _mock_validate, v3_client):
        db, conn = _mock_db(fetchrow_result=MOCK_VIOLATION_DETAIL_ROW)
        with patch("shared.database.db_service", db):
            resp = await v3_client.get("/api/v3/violations/9123", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 9123
        assert data["temporal_score"] == 0.9
        assert data["is_datacenter"] is True
        assert data["cities"] == ["Moscow"]
        conn.fetchrow.assert_awaited_once()
        assert conn.fetchrow.call_args.args[-1] == 9123

    @pytest.mark.asyncio
    @patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
    async def test_detail_not_found(self, _mock_validate, v3_client):
        db, _conn = _mock_db(fetchrow_result=None)
        with patch("shared.database.db_service", db):
            resp = await v3_client.get("/api/v3/violations/777", headers={"X-API-Key": "rwa_test"})
        assert resp.status_code == 404


class TestScopeRegistered:
    """violations:read должен быть в списке допустимых скоупов API-ключей."""

    def test_scope_in_available_scopes(self):
        from web.backend.api.v2.api_keys import AVAILABLE_SCOPES
        assert "violations:read" in AVAILABLE_SCOPES

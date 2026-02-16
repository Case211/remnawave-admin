"""Tests for users API — /api/v2/users/*."""
import pytest
from unittest.mock import patch, AsyncMock

from web.backend.api.deps import get_current_admin
from .conftest import make_admin


MOCK_USERS = [
    {
        "uuid": "aaa-111",
        "short_uuid": "aaa",
        "username": "alice",
        "status": "active",
        "subscription_uuid": "sub-1",
        "traffic_limit_bytes": 10_000_000_000,
        "used_traffic_bytes": 1_000_000,
        "lifetime_used_traffic_bytes": 5_000_000,
        "expire_at": "2026-12-31T00:00:00Z",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-02-01T00:00:00Z",
        "online_at": None,
        "telegram_id": None,
        "hwid_device_limit": 3,
        "hwid_device_count": 1,
        "note": "",
        "sub_last_user_agent": None,
        "sub_revoked_at": None,
        "last_traffic_reset_at": None,
        "traffic_limit_strategy": "no_reset",
        "email": "alice@example.com",
    },
    {
        "uuid": "bbb-222",
        "short_uuid": "bbb",
        "username": "bob",
        "status": "disabled",
        "subscription_uuid": "sub-2",
        "traffic_limit_bytes": 0,
        "used_traffic_bytes": 0,
        "lifetime_used_traffic_bytes": 0,
        "expire_at": None,
        "created_at": "2026-01-02T00:00:00Z",
        "updated_at": "2026-02-01T00:00:00Z",
        "online_at": None,
        "telegram_id": 12345,
        "hwid_device_limit": 0,
        "hwid_device_count": 0,
        "note": "test user",
        "sub_last_user_agent": None,
        "sub_revoked_at": None,
        "last_traffic_reset_at": None,
        "traffic_limit_strategy": "no_reset",
        "email": None,
    },
]


class TestListUsers:
    """GET /api/v2/users."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=MOCK_USERS)
    async def test_list_users_success(self, mock_get, client):
        resp = await client.get("/api/v2/users")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=MOCK_USERS)
    async def test_list_users_pagination(self, mock_get, client):
        resp = await client.get("/api/v2/users?page=1&per_page=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["total"] == 2

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=MOCK_USERS)
    async def test_list_users_search(self, mock_get, client):
        resp = await client.get("/api/v2/users?search=alice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["username"] == "alice"

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=MOCK_USERS)
    async def test_list_users_filter_status(self, mock_get, client):
        resp = await client.get("/api/v2/users?status=active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_list_users_as_viewer_allowed(self, app, viewer):
        """Viewers have users.view permission."""
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            with patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=[]):
                resp = await ac.get("/api/v2/users")
                assert resp.status_code == 200

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=[])
    async def test_list_users_empty(self, mock_get, client):
        resp = await client.get("/api/v2/users")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


class TestListUsersRBAC:
    """RBAC tests for user endpoints."""

    @pytest.mark.asyncio
    async def test_anon_get_users_unauthorized(self, anon_client):
        resp = await anon_client.get("/api/v2/users")
        assert resp.status_code == 401


class TestEnsureSnakeCase:
    """Tests for _ensure_snake_case helper."""

    def test_maps_camel_to_snake(self):
        from web.backend.api.v2.users import _ensure_snake_case
        user = {"shortUuid": "abc", "subscriptionUuid": "sub-1"}
        result = _ensure_snake_case(user)
        assert result["short_uuid"] == "abc"
        assert result["subscription_uuid"] == "sub-1"

    def test_normalizes_status_to_lowercase(self):
        from web.backend.api.v2.users import _ensure_snake_case
        user = {"status": "ACTIVE"}
        result = _ensure_snake_case(user)
        assert result["status"] == "active"

    def test_flattens_user_traffic(self):
        from web.backend.api.v2.users import _ensure_snake_case
        user = {
            "userTraffic": {
                "usedTrafficBytes": 1000,
                "lifetimeUsedTrafficBytes": 5000,
                "onlineAt": "2026-01-01",
            }
        }
        result = _ensure_snake_case(user)
        assert result["used_traffic_bytes"] == 1000
        assert result["lifetime_used_traffic_bytes"] == 5000


class TestParseDt:
    """Tests for _parse_dt helper."""

    def test_none(self):
        from web.backend.api.v2.users import _parse_dt
        assert _parse_dt(None) is None

    def test_iso_string(self):
        from web.backend.api.v2.users import _parse_dt
        result = _parse_dt("2026-01-15T10:30:00Z")
        assert result is not None
        assert result.year == 2026

    def test_datetime_passthrough(self):
        from web.backend.api.v2.users import _parse_dt
        from datetime import datetime
        dt = datetime(2026, 1, 1)
        assert _parse_dt(dt) is dt

    def test_invalid_string(self):
        from web.backend.api.v2.users import _parse_dt
        assert _parse_dt("not-a-date") is None

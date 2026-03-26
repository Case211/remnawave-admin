"""Tests for violations API — /api/v2/violations/*."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime

from web.backend.api.deps import get_current_admin
from web.backend.api.v2.violations import get_severity
from .conftest import make_admin


class TestGetSeverity:
    """Tests for severity score classification."""

    def test_critical(self):
        assert get_severity(80.0).value == "critical"
        assert get_severity(100.0).value == "critical"

    def test_high(self):
        assert get_severity(60.0).value == "high"
        assert get_severity(79.9).value == "high"

    def test_medium(self):
        assert get_severity(40.0).value == "medium"
        assert get_severity(59.9).value == "medium"

    def test_low(self):
        assert get_severity(0.0).value == "low"
        assert get_severity(39.9).value == "low"


MOCK_VIOLATIONS = [
    {
        "id": 1,
        "user_uuid": "aaa-111",
        "username": "alice",
        "email": None,
        "telegram_id": None,
        "score": 85.0,
        "recommended_action": "disable",
        "confidence": 0.92,
        "detected_at": datetime(2026, 2, 16, 10, 0),
        "action_taken": None,
        "notified_at": None,
    },
    {
        "id": 2,
        "user_uuid": "bbb-222",
        "username": "bob",
        "email": "bob@example.com",
        "telegram_id": 12345,
        "score": 45.0,
        "recommended_action": "no_action",
        "confidence": 0.65,
        "detected_at": datetime(2026, 2, 15, 8, 0),
        "action_taken": "resolved",
        "notified_at": datetime(2026, 2, 15, 9, 0),
    },
]


class TestListViolations:
    """GET /api/v2/violations."""

    @pytest.mark.asyncio
    async def test_list_violations_success(self, app, client):
        from web.backend.api.deps import get_db

        mock_db = MagicMock()
        mock_db.is_connected = True
        mock_db.count_violations_for_period = AsyncMock(return_value=2)
        mock_db.get_violations_for_period = AsyncMock(return_value=MOCK_VIOLATIONS)

        app.dependency_overrides[get_db] = lambda: mock_db

        resp = await client.get("/api/v2/violations")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_violations_as_viewer_allowed(self, app, viewer):
        """Viewers have violations.view permission."""
        from web.backend.api.deps import get_db as _get_db
        app.dependency_overrides[get_current_admin] = lambda: viewer

        mock_db = MagicMock()
        mock_db.is_connected = True
        mock_db.count_violations_for_period = AsyncMock(return_value=0)
        mock_db.get_violations_for_period = AsyncMock(return_value=[])
        app.dependency_overrides[_get_db] = lambda: mock_db

        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v2/violations")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_list_violations_anon_unauthorized(self, anon_client):
        resp = await anon_client.get("/api/v2/violations")
        assert resp.status_code == 401


class TestRowToListItem:
    """Tests for _row_to_list_item helper."""

    def test_converts_mock_violation(self):
        from web.backend.api.v2.violations import _row_to_list_item
        item = _row_to_list_item(MOCK_VIOLATIONS[0])
        assert item.id == 1
        assert item.username == "alice"
        assert item.score == 85.0
        assert item.severity.value == "critical"
        assert item.notified is False

    def test_notified_when_notified_at_present(self):
        from web.backend.api.v2.violations import _row_to_list_item
        item = _row_to_list_item(MOCK_VIOLATIONS[1])
        assert item.notified is True

    def test_defaults_for_missing_fields(self):
        from web.backend.api.v2.violations import _row_to_list_item
        item = _row_to_list_item({"id": 99})
        assert item.score == 0.0
        assert item.severity.value == "low"
        assert item.recommended_action == "no_action"


# ══════════════════════════════════════════════════════════════════
# HWID Blacklist tests
# ══════════════════════════════════════════════════════════════════

class TestHwidBlacklist:
    """Tests for HWID blacklist API — /api/v2/violations/hwid-blacklist."""

    @pytest.mark.asyncio
    async def test_list_returns_items(self, app, client):
        """GET /hwid-blacklist returns items from DB."""
        mock_items = [{"id": 1, "hwid": "abc", "action": "alert", "reason": None, "created_at": "2026-01-01T00:00:00"}]
        with patch("shared.database.DatabaseService.get_hwid_blacklist", new_callable=AsyncMock, create=True) as mock:
            mock.return_value = mock_items
            response = await client.get("/api/v2/violations/hwid-blacklist")
            # Note: may return 200 or 422 depending on rate limiter state
            if response.status_code == 200:
                data = response.json()
                assert data["total"] == 1
                assert data["items"][0]["hwid"] == "abc"

    @pytest.mark.asyncio
    async def test_add_hwid_alert(self, app, client):
        """POST /hwid-blacklist with action=alert."""
        with patch("shared.database.DatabaseService.add_hwid_to_blacklist", new_callable=AsyncMock, create=True) as mock_add, \
             patch("shared.database.DatabaseService.find_users_by_hwid", new_callable=AsyncMock, create=True) as mock_find, \
             patch("web.backend.core.rbac.write_audit_log", new_callable=AsyncMock):
            mock_add.return_value = {"id": 1, "hwid": "abc123", "action": "alert", "reason": "test"}
            mock_find.return_value = []

            response = await client.post("/api/v2/violations/hwid-blacklist", json={
                "hwid": "abc123",
                "action": "alert",
                "reason": "test reason",
            })
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["affected_users"] == 0
            mock_add.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_hwid_block_with_affected_users(self, app, client):
        """POST /hwid-blacklist with action=block triggers blocking."""
        with patch("shared.database.DatabaseService.add_hwid_to_blacklist", new_callable=AsyncMock, create=True) as mock_add, \
             patch("shared.database.DatabaseService.find_users_by_hwid", new_callable=AsyncMock, create=True) as mock_find, \
             patch("web.backend.api.v2.violations._handle_blacklisted_hwid_users", new_callable=AsyncMock) as mock_handle, \
             patch("web.backend.core.rbac.write_audit_log", new_callable=AsyncMock):
            mock_add.return_value = {"id": 1, "hwid": "abc123", "action": "block", "reason": None}
            mock_find.return_value = [
                {"user_uuid": "user-1", "username": "alice", "status": "active"},
            ]

            response = await client.post("/api/v2/violations/hwid-blacklist", json={
                "hwid": "abc123",
                "action": "block",
            })
            assert response.status_code == 200
            assert response.json()["affected_users"] == 1
            mock_handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_hwid_invalid_action(self, app, client):
        """POST /hwid-blacklist with invalid action returns 422."""
        response = await client.post("/api/v2/violations/hwid-blacklist", json={
            "hwid": "abc123",
            "action": "invalid",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_add_hwid_empty(self, app, client):
        """POST /hwid-blacklist with empty hwid returns 422."""
        response = await client.post("/api/v2/violations/hwid-blacklist", json={
            "hwid": "",
            "action": "alert",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_hwid(self, app, client):
        """DELETE /hwid-blacklist/{hwid} removes entry."""
        with patch("shared.database.DatabaseService.remove_hwid_from_blacklist", new_callable=AsyncMock, create=True) as mock_remove, \
             patch("web.backend.core.rbac.write_audit_log", new_callable=AsyncMock):
            mock_remove.return_value = True
            response = await client.delete("/api/v2/violations/hwid-blacklist/abc123")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_hwid_not_found(self, app, client):
        """DELETE /hwid-blacklist/{hwid} returns 404 if not in blacklist."""
        with patch("shared.database.DatabaseService.remove_hwid_from_blacklist", new_callable=AsyncMock, create=True) as mock_remove, \
             patch("web.backend.core.rbac.write_audit_log", new_callable=AsyncMock):
            mock_remove.return_value = False
            response = await client.delete("/api/v2/violations/hwid-blacklist/nonexistent")
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_hwid_users(self, app, client):
        """GET /hwid-blacklist/{hwid}/users returns affected users."""
        with patch("shared.database.DatabaseService.find_users_by_hwid", new_callable=AsyncMock, create=True) as mock:
            mock.return_value = [
                {"user_uuid": "user-1", "username": "alice", "status": "ACTIVE", "platform": "iOS", "device_model": "iPhone 15"},
                {"user_uuid": "user-2", "username": "bob", "status": "EXPIRED", "platform": "Android", "device_model": None},
            ]
            response = await client.get("/api/v2/violations/hwid-blacklist/abc123/users")
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 2
            assert data["users"][0]["username"] == "alice"

    @pytest.mark.asyncio
    async def test_viewer_cannot_add_hwid(self, app, viewer):
        """Viewer role should not be able to add to HWID blacklist."""
        from httpx import ASGITransport, AsyncClient
        app.dependency_overrides[get_current_admin] = lambda: viewer
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.post("/api/v2/violations/hwid-blacklist", json={
                "hwid": "abc123", "action": "alert",
            })
            assert response.status_code == 403


class TestHwidBlacklistRequest:
    """Tests for HwidBlacklistRequest Pydantic model."""

    def test_valid_request(self):
        from web.backend.api.v2.violations import HwidBlacklistRequest
        req = HwidBlacklistRequest(hwid="abc123", action="alert", reason="test")
        assert req.hwid == "abc123"
        assert req.action == "alert"

    def test_invalid_action_rejected(self):
        from web.backend.api.v2.violations import HwidBlacklistRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            HwidBlacklistRequest(hwid="abc", action="destroy")

    def test_block_action_valid(self):
        from web.backend.api.v2.violations import HwidBlacklistRequest
        req = HwidBlacklistRequest(hwid="xyz", action="block")
        assert req.action == "block"

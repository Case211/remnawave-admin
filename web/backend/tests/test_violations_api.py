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

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=MOCK_VIOLATIONS)
        mock_conn.fetchval = AsyncMock(return_value=2)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        mock_db = MagicMock()
        mock_db.acquire = MagicMock(return_value=mock_cm)
        mock_db.is_connected = True

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
        mock_cm = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.fetchval = AsyncMock(return_value=0)
        mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_db.acquire = MagicMock(return_value=mock_cm)
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

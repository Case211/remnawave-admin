"""Tests for automations API — /api/v2/automations/*."""
import pytest
from unittest.mock import patch, AsyncMock

from web.backend.api.deps import get_current_admin
from .conftest import make_admin


MOCK_RULE = {
    "id": 1,
    "name": "Auto disable expired",
    "description": "Disable users when they expire",
    "is_enabled": True,
    "category": "users",
    "trigger_type": "schedule",
    "trigger_config": {"cron": "*/5 * * * *"},
    "conditions": [{"field": "status", "op": "==", "value": "expired"}],
    "action_type": "disable_user",
    "action_config": {},
    "last_triggered_at": "2026-02-16T10:00:00Z",
    "trigger_count": 42,
    "created_by": 1,
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-02-01T00:00:00Z",
}


class TestListAutomations:
    """GET /api/v2/automations."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.automations.list_automation_rules", new_callable=AsyncMock, return_value=([MOCK_RULE], 1))
    @patch("web.backend.api.v2.automations.get_automation_rules_stats", new_callable=AsyncMock, return_value={"total_active": 1, "total_triggers": 42})
    async def test_list_rules_success(self, mock_stats, mock_list, client):
        resp = await client.get("/api/v2/automations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Auto disable expired"

    @pytest.mark.asyncio
    async def test_list_rules_as_viewer_forbidden(self, app, viewer):
        """Viewers don't have automations.view permission."""
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v2/automations")
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_list_rules_anon_unauthorized(self, anon_client):
        resp = await anon_client.get("/api/v2/automations")
        assert resp.status_code == 401


class TestGetAutomation:
    """GET /api/v2/automations/{rule_id}."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.automations.get_automation_rule_by_id", new_callable=AsyncMock, return_value=MOCK_RULE)
    async def test_get_rule_success(self, mock_get, client):
        resp = await client.get("/api/v2/automations/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Auto disable expired"

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.automations.get_automation_rule_by_id", new_callable=AsyncMock, return_value=None)
    async def test_get_rule_not_found(self, mock_get, client):
        resp = await client.get("/api/v2/automations/999")
        assert resp.status_code == 404


class TestCreateAutomation:
    """POST /api/v2/automations."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.automations.write_audit_log", new_callable=AsyncMock)
    @patch("web.backend.api.v2.automations.create_automation_rule", new_callable=AsyncMock, return_value=MOCK_RULE)
    async def test_create_rule_success(self, mock_create, mock_audit, client):
        resp = await client.post("/api/v2/automations", json={
            "name": "New rule",
            "category": "users",
            "trigger_type": "schedule",
            "trigger_config": {"cron": "0 * * * *"},
            "conditions": [],
            "action_type": "disable_user",
            "action_config": {},
        })
        assert resp.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_create_rule_as_viewer_forbidden(self, app, viewer):
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v2/automations", json={"name": "x"})
            assert resp.status_code == 403


class TestDeleteAutomation:
    """DELETE /api/v2/automations/{rule_id}."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.automations.write_audit_log", new_callable=AsyncMock)
    @patch("web.backend.api.v2.automations.get_automation_rule_by_id", new_callable=AsyncMock, return_value=MOCK_RULE)
    @patch("web.backend.api.v2.automations.delete_automation_rule", new_callable=AsyncMock, return_value=True)
    async def test_delete_rule_success(self, mock_delete, mock_get, mock_audit, client):
        resp = await client.delete("/api/v2/automations/1")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.automations.get_automation_rule_by_id", new_callable=AsyncMock, return_value=None)
    async def test_delete_rule_not_found(self, mock_get, client):
        resp = await client.delete("/api/v2/automations/999")
        assert resp.status_code == 404


class TestRuleToResponse:
    """Tests for _rule_to_response helper."""

    def test_parses_json_strings(self):
        from web.backend.api.v2.automations import _rule_to_response
        rule = dict(MOCK_RULE)
        rule["trigger_config"] = '{"cron": "*/5 * * * *"}'
        rule["conditions"] = '[]'
        rule["action_config"] = '{}'
        result = _rule_to_response(rule)
        assert result.trigger_config == {"cron": "*/5 * * * *"}
        assert result.conditions == []

    def test_handles_dict_fields(self):
        from web.backend.api.v2.automations import _rule_to_response
        result = _rule_to_response(MOCK_RULE)
        assert result.name == "Auto disable expired"
        assert result.trigger_count == 42

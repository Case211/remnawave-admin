"""Tests for billing API — /api/v2/billing/*."""
import pytest
from unittest.mock import patch, AsyncMock

from web.backend.api.deps import get_current_admin
from .conftest import make_admin


MOCK_PROVIDERS_RESPONSE = {
    "response": {
        "providers": [
            {"uuid": "prov-1", "name": "Hetzner", "faviconLink": None, "loginUrl": "https://hetzner.com"},
            {"uuid": "prov-2", "name": "OVH", "faviconLink": None, "loginUrl": None},
        ]
    }
}

MOCK_PROVIDER_DETAIL = {
    "response": {
        "uuid": "prov-1",
        "name": "Hetzner",
        "faviconLink": None,
        "loginUrl": "https://hetzner.com",
    }
}

MOCK_BILLING_NODES_RESPONSE = {
    "response": {
        "billingNodes": [
            {"uuid": "bn-1", "nodeUuid": "node-1", "providerUuid": "prov-1", "nextBillingAt": "2099-01-01T00:00:00Z"},
        ],
        "stats": {
            "currentMonthPayments": 150.0,
            "totalSpent": 1200.0,
            "upcomingNodesCount": 1,
        },
    }
}

MOCK_HISTORY_RESPONSE = {
    "response": {
        "records": [
            {"uuid": "rec-1", "providerUuid": "prov-1", "amount": 50.0, "billedAt": "2026-03-01T00:00:00Z"},
        ]
    }
}


class TestListProviders:
    """GET /api/v2/billing/providers."""

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.get_infra_providers", new_callable=AsyncMock, return_value=MOCK_PROVIDERS_RESPONSE)
    async def test_list_providers_success(self, mock_get, client):
        resp = await client.get("/api/v2/billing/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["name"] == "Hetzner"

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.get_infra_providers", new_callable=AsyncMock, return_value={"response": {}})
    async def test_list_providers_empty(self, mock_get, client):
        resp = await client.get("/api/v2/billing/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.get_infra_providers", new_callable=AsyncMock, side_effect=Exception("Connection refused"))
    async def test_list_providers_api_error(self, mock_get, client):
        resp = await client.get("/api/v2/billing/providers")
        assert resp.status_code == 502


class TestGetProvider:
    """GET /api/v2/billing/providers/{uuid}."""

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.get_infra_provider", new_callable=AsyncMock, return_value=MOCK_PROVIDER_DETAIL)
    async def test_get_provider_success(self, mock_get, client):
        resp = await client.get("/api/v2/billing/providers/prov-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["uuid"] == "prov-1"
        assert data["name"] == "Hetzner"


class TestCreateProvider:
    """POST /api/v2/billing/providers."""

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.create_infra_provider", new_callable=AsyncMock, return_value={"response": {"uuid": "prov-new", "name": "New"}})
    async def test_create_provider_success(self, mock_create, client):
        resp = await client.post("/api/v2/billing/providers", json={"name": "New"})
        assert resp.status_code == 200
        mock_create.assert_called_once_with(name="New", favicon_link=None, login_url=None)


class TestUpdateProvider:
    """PATCH /api/v2/billing/providers."""

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.update_infra_provider", new_callable=AsyncMock, return_value={"response": {"uuid": "prov-1", "name": "Updated"}})
    async def test_update_provider_success(self, mock_update, client):
        resp = await client.patch("/api/v2/billing/providers", json={"uuid": "prov-1", "name": "Updated"})
        assert resp.status_code == 200


class TestDeleteProvider:
    """DELETE /api/v2/billing/providers/{uuid}."""

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.delete_infra_provider", new_callable=AsyncMock)
    async def test_delete_provider_success(self, mock_delete, client):
        resp = await client.delete("/api/v2/billing/providers/prov-1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestBillingSummary:
    """GET /api/v2/billing/summary."""

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.get_infra_billing_nodes", new_callable=AsyncMock, return_value=MOCK_BILLING_NODES_RESPONSE)
    @patch("shared.api_client.api_client.get_infra_providers", new_callable=AsyncMock, return_value=MOCK_PROVIDERS_RESPONSE)
    async def test_summary_success(self, mock_providers, mock_nodes, client):
        resp = await client.get("/api/v2/billing/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_providers"] == 2
        assert data["current_month_payments"] == 150.0
        assert data["total_spent"] == 1200.0
        assert data["upcoming_nodes"] == 1
        assert data["next_payment_date"] is not None

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.get_infra_billing_nodes", new_callable=AsyncMock, return_value={"response": {}})
    @patch("shared.api_client.api_client.get_infra_providers", new_callable=AsyncMock, return_value={"response": {}})
    async def test_summary_empty(self, mock_providers, mock_nodes, client):
        resp = await client.get("/api/v2/billing/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_providers"] == 0
        assert data["next_payment_date"] is None


class TestBillingHistory:
    """GET/POST/DELETE /api/v2/billing/history."""

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.get_infra_billing_history", new_callable=AsyncMock, return_value=MOCK_HISTORY_RESPONSE)
    async def test_list_history_success(self, mock_get, client):
        resp = await client.get("/api/v2/billing/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.create_infra_billing_record", new_callable=AsyncMock, return_value={"response": {"uuid": "rec-new"}})
    async def test_create_record_success(self, mock_create, client):
        resp = await client.post("/api/v2/billing/history", json={
            "providerUuid": "prov-1",
            "amount": 50.0,
            "billedAt": "2026-03-01T00:00:00Z",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.delete_infra_billing_record", new_callable=AsyncMock)
    async def test_delete_record_success(self, mock_delete, client):
        resp = await client.delete("/api/v2/billing/history/rec-1")
        assert resp.status_code == 200


class TestBillingNodes:
    """GET/POST/PATCH/DELETE /api/v2/billing/nodes."""

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.get_infra_billing_nodes", new_callable=AsyncMock, return_value=MOCK_BILLING_NODES_RESPONSE)
    async def test_list_nodes_success(self, mock_get, client):
        resp = await client.get("/api/v2/billing/nodes")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.create_infra_billing_node", new_callable=AsyncMock, return_value={"response": {"uuid": "bn-new"}})
    async def test_create_node_success(self, mock_create, client):
        resp = await client.post("/api/v2/billing/nodes", json={
            "providerUuid": "prov-1",
            "nodeUuid": "node-1",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.update_infra_billing_nodes", new_callable=AsyncMock, return_value={"response": {}})
    async def test_update_nodes_success(self, mock_update, client):
        resp = await client.patch("/api/v2/billing/nodes", json={
            "uuids": ["bn-1"],
            "nextBillingAt": "2026-05-01T00:00:00Z",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client.delete_infra_billing_node", new_callable=AsyncMock)
    async def test_delete_node_success(self, mock_delete, client):
        resp = await client.delete("/api/v2/billing/nodes/bn-1")
        assert resp.status_code == 200


class TestBillingRBAC:
    """RBAC tests for billing endpoints."""

    @pytest.mark.asyncio
    async def test_anon_unauthorized(self, anon_client):
        resp = await anon_client.get("/api/v2/billing/providers")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_no_billing_access(self, app, viewer):
        """Viewer has no billing permissions."""
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v2/billing/providers")
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_create(self, app, viewer):
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v2/billing/providers", json={"name": "Test"})
            assert resp.status_code == 403

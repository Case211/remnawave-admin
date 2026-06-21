"""Tests for webhooks API — /api/v2/webhooks/*."""
import hashlib
import hmac
import json
import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

from web.backend.api.deps import get_current_admin
from .conftest import make_admin


MOCK_WEBHOOK_ROW = {
    "id": 1,
    "name": "My Webhook",
    "url": "https://example.com/hook",
    "secret": "my-secret-123",
    "events": ["user.created", "violation.created"],
    "is_active": True,
    "last_triggered_at": None,
    "failure_count": 0,
    "created_at": datetime(2026, 2, 1, 12, 0, 0),
    "updated_at": None,
    "created_by_admin_id": 1,
}

MOCK_WEBHOOK_ROW_NO_SECRET = {
    **MOCK_WEBHOOK_ROW,
    "id": 2,
    "secret": None,
}


def _mock_db_service(fetch_return=None, fetchrow_return=None, execute_return="DELETE 1"):
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=fetch_return or [])
    mock_conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    mock_conn.fetchval = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock(return_value=execute_return)

    mock_svc = MagicMock()
    mock_svc.is_connected = True
    mock_svc.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_svc.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_svc, mock_conn


class TestListWebhooks:
    """GET /api/v2/webhooks/."""

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_list_webhooks_success(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service(fetch_return=[MOCK_WEBHOOK_ROW, MOCK_WEBHOOK_ROW_NO_SECRET])
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.get("/api/v2/webhooks/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Secret should be hidden, replaced by has_secret
        assert data[0]["has_secret"] is True
        assert data[1]["has_secret"] is False
        assert "secret" not in data[0]

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_list_webhooks_db_disconnected(self, mock_db_svc, client):
        mock_db_svc.is_connected = False
        resp = await client.get("/api/v2/webhooks/")
        assert resp.status_code == 200
        assert resp.json() == []


class TestListEvents:
    """GET /api/v2/webhooks/events."""

    @pytest.mark.asyncio
    async def test_list_events(self, client):
        resp = await client.get("/api/v2/webhooks/events")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "user.created" in data["events"]
        assert "violation.created" in data["events"]
        assert "user.blocked" in data["events"]
        assert "automation.triggered" in data["events"]
        assert len(data["events"]) == 9


class TestCreateWebhook:
    """POST /api/v2/webhooks/."""

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_create_webhook_success(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service(fetchrow_return=MOCK_WEBHOOK_ROW)
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.post("/api/v2/webhooks/", json={
            "name": "My Webhook",
            "url": "https://example.com/hook",
            "events": ["user.created"],
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Webhook"
        assert data["has_secret"] is True

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_create_webhook_invalid_event(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.post("/api/v2/webhooks/", json={
            "name": "Bad Webhook",
            "url": "https://example.com/hook",
            "events": ["invalid.event"],
        })
        assert resp.status_code == 400


class TestUpdateWebhook:
    """PATCH /api/v2/webhooks/{id}."""

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_update_webhook_success(self, mock_db_svc, client):
        updated = {**MOCK_WEBHOOK_ROW, "name": "Updated"}
        mock_svc, _ = _mock_db_service(fetchrow_return=updated)
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.patch("/api/v2/webhooks/1", json={"name": "Updated"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated"

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_update_webhook_no_fields(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.patch("/api/v2/webhooks/1", json={})
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_update_webhook_not_found(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service(fetchrow_return=None)
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.patch("/api/v2/webhooks/999", json={"name": "X"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_update_webhook_invalid_event(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.patch("/api/v2/webhooks/1", json={"events": ["bad.event"]})
        assert resp.status_code == 400


class TestDeleteWebhook:
    """DELETE /api/v2/webhooks/{id}."""

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_delete_webhook_success(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service(execute_return="DELETE 1")
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.delete("/api/v2/webhooks/1")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_delete_webhook_not_found(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service(execute_return="DELETE 0")
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.delete("/api/v2/webhooks/999")
        assert resp.status_code == 404


class TestDispatchWebhookEvent:
    """Unit tests for dispatch_webhook_event."""

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_dispatch_no_active_webhooks(self, mock_db_svc):
        mock_svc, _ = _mock_db_service(fetch_return=[])
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        from web.backend.api.v2.webhooks import dispatch_webhook_event
        # Should not raise
        await dispatch_webhook_event("user.created", {"user_uuid": "test-uuid"})

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_dispatch_db_disconnected(self, mock_db_svc):
        mock_db_svc.is_connected = False

        from web.backend.api.v2.webhooks import dispatch_webhook_event
        await dispatch_webhook_event("user.created", {"user_uuid": "test-uuid"})

    @pytest.mark.asyncio
    @patch("httpx.AsyncClient.post", new_callable=AsyncMock)
    @patch("shared.database.db_service")
    async def test_dispatch_sends_with_hmac(self, mock_db_svc, mock_post):
        """Verify HMAC signature is computed correctly."""
        webhook_row = {"id": 1, "url": "https://example.com/hook", "secret": "test-secret", "signature_version": "v1"}
        mock_svc, mock_conn = _mock_db_service(fetch_return=[webhook_row])
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        mock_resp = MagicMock()
        mock_resp.is_success = True
        mock_post.return_value = mock_resp

        from web.backend.api.v2.webhooks import dispatch_webhook_event
        await dispatch_webhook_event("user.created", {"user_uuid": "uuid-1"})

        # Verify post was called
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        headers = call_kwargs.kwargs.get("headers", {}) if call_kwargs.kwargs else call_kwargs[1].get("headers", {})
        body = call_kwargs.kwargs.get("content", "") if call_kwargs.kwargs else call_kwargs[1].get("content", "")

        # Verify HMAC header present
        assert "X-Webhook-Signature" in headers
        expected_sig = hmac.new(b"test-secret", body.encode(), hashlib.sha256).hexdigest()
        assert headers["X-Webhook-Signature"] == f"sha256={expected_sig}"


class TestWebhooksRBAC:
    """RBAC tests for webhooks endpoints."""

    @pytest.mark.asyncio
    async def test_anon_unauthorized(self, anon_client):
        resp = await anon_client.get("/api/v2/webhooks/")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_no_webhook_access(self, app, viewer):
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v2/webhooks/")
            assert resp.status_code == 403

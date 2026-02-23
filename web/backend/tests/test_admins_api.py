"""Tests for admin account management API — /api/v2/admins/*."""
import pytest
from unittest.mock import patch, AsyncMock

from web.backend.api.deps import get_current_admin
from .conftest import make_admin


# Mock admin account data
MOCK_ACCOUNTS = [
    {
        "id": 1,
        "username": "superadmin_user",
        "telegram_id": 100000,
        "role_id": 1,
        "role_name": "superadmin",
        "role_display_name": "Суперадмин",
        "max_users": None,
        "max_traffic_gb": None,
        "max_nodes": None,
        "max_hosts": None,
        "users_created": 10,
        "traffic_used_bytes": 0,
        "nodes_created": 2,
        "hosts_created": 5,
        "is_active": True,
        "is_generated_password": False,
        "created_by": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    },
    {
        "id": 2,
        "username": "viewer_user",
        "telegram_id": None,
        "role_id": 4,
        "role_name": "viewer",
        "role_display_name": "Наблюдатель",
        "max_users": 50,
        "max_traffic_gb": 100,
        "max_nodes": 5,
        "max_hosts": 10,
        "users_created": 3,
        "traffic_used_bytes": 0,
        "nodes_created": 1,
        "hosts_created": 2,
        "is_active": True,
        "is_generated_password": True,
        "created_by": 1,
        "created_at": "2026-01-02T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
    },
]


class TestListAdmins:
    """GET /api/v2/admins."""

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.list_admin_accounts",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS,
    )
    async def test_list_as_superadmin(self, mock_list, client):
        resp = await client.get("/api/v2/admins")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_as_viewer_forbidden(self, viewer_client):
        resp = await viewer_client.get("/api/v2/admins")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.list_admin_accounts",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS,
    )
    async def test_list_as_manager(self, mock_list, manager_client):
        resp = await manager_client.get("/api/v2/admins")
        assert resp.status_code == 200


class TestGetAdmin:
    """GET /api/v2/admins/{admin_id}."""

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[0],
    )
    async def test_get_existing_admin(self, mock_get, client):
        resp = await client.get("/api/v2/admins/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "superadmin_user"

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=None,
    )
    async def test_get_nonexistent_admin(self, mock_get, client):
        resp = await client.get("/api/v2/admins/999")
        assert resp.status_code == 404


class TestCreateAdmin:
    """POST /api/v2/admins."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.admins.write_audit_log", new_callable=AsyncMock)
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[1],
    )
    @patch(
        "web.backend.api.v2.admins.create_admin_account",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[1],
    )
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_username",
        new_callable=AsyncMock,
        return_value=None,
    )
    @patch(
        "web.backend.api.v2.admins.get_role_by_id",
        new_callable=AsyncMock,
        return_value={"id": 4, "name": "viewer"},
    )
    async def test_create_admin(
        self, mock_role, mock_dup, mock_create, mock_refetch, mock_audit, client
    ):
        resp = await client.post(
            "/api/v2/admins",
            json={
                "username": "new_admin",
                "password": "SecureP@ss1",
                "role_id": 4,
            },
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_admin_as_viewer_forbidden(self, viewer_client):
        resp = await viewer_client.post(
            "/api/v2/admins",
            json={
                "username": "new_admin",
                "password": "SecureP@ss1",
                "role_id": 4,
            },
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.get_role_by_id",
        new_callable=AsyncMock,
        return_value=None,
    )
    async def test_create_with_invalid_role(self, mock_role, client):
        resp = await client.post(
            "/api/v2/admins",
            json={
                "username": "new_admin",
                "password": "SecureP@ss1",
                "role_id": 999,
            },
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_username",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[0],
    )
    @patch(
        "web.backend.api.v2.admins.get_role_by_id",
        new_callable=AsyncMock,
        return_value={"id": 1, "name": "superadmin"},
    )
    async def test_create_duplicate_username(self, mock_role, mock_dup, client):
        resp = await client.post(
            "/api/v2/admins",
            json={
                "username": "superadmin_user",
                "password": "SecureP@ss1",
                "role_id": 1,
            },
        )
        assert resp.status_code == 409


class TestUpdateAdmin:
    """PUT /api/v2/admins/{admin_id}."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.admins.write_audit_log", new_callable=AsyncMock)
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[1],
    )
    @patch(
        "web.backend.api.v2.admins.update_admin_account",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[1],
    )
    async def test_update_admin(self, mock_update, mock_get, mock_audit, client):
        resp = await client.put(
            "/api/v2/admins/2",
            json={"is_active": False},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[0],
    )
    async def test_cannot_change_own_role(self, mock_get, app, superadmin):
        """Admin cannot change their own role."""
        app.dependency_overrides[get_current_admin] = lambda: superadmin
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v2/admins/1",  # Same as superadmin.account_id
                json={"role_id": 4},
            )
            assert resp.status_code == 400
            detail = resp.json()["detail"]
            msg = detail["detail"] if isinstance(detail, dict) else detail
            assert "own role" in msg.lower()

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[0],
    )
    async def test_cannot_deactivate_self(self, mock_get, app, superadmin):
        app.dependency_overrides[get_current_admin] = lambda: superadmin
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v2/admins/1",
                json={"is_active": False},
            )
            assert resp.status_code == 400


class TestDeleteAdmin:
    """DELETE /api/v2/admins/{admin_id}."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.admins.write_audit_log", new_callable=AsyncMock)
    @patch(
        "web.backend.api.v2.admins.delete_admin_account",
        new_callable=AsyncMock,
        return_value=True,
    )
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[1],
    )
    async def test_delete_other_admin(self, mock_get, mock_delete, mock_audit, client):
        resp = await client.delete("/api/v2/admins/2")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_cannot_delete_self(self, app, superadmin):
        app.dependency_overrides[get_current_admin] = lambda: superadmin
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.delete("/api/v2/admins/1")
            assert resp.status_code == 400
            detail = resp.json()["detail"]
            msg = detail["detail"] if isinstance(detail, dict) else detail
            assert "yourself" in msg.lower()

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=None,
    )
    async def test_delete_nonexistent(self, mock_get, client):
        resp = await client.delete("/api/v2/admins/999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_as_viewer_forbidden(self, viewer_client):
        resp = await viewer_client.delete("/api/v2/admins/2")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_as_operator_forbidden(self, operator_client):
        resp = await operator_client.delete("/api/v2/admins/2")
        assert resp.status_code == 403

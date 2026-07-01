"""Tests for admin account management API — /api/v2/admins/*."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

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
        "web.backend.api.v2.admins.update_admin_account",
        new_callable=AsyncMock,
    )
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[0],
    )
    async def test_cannot_null_own_role(self, mock_get, mock_update, app, superadmin):
        """Regression: the only superadmin blanking their own role via an explicit
        null (frontend sending parseInt("superadmin")=NaN → JSON null) must be
        rejected — otherwise role_id=NULL demotes them to a roleless "admin"."""
        app.dependency_overrides[get_current_admin] = lambda: superadmin
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v2/admins/1",  # self
                json={"role_id": None},
            )
            assert resp.status_code == 400
            detail = resp.json()["detail"]
            msg = detail["detail"] if isinstance(detail, dict) else detail
            assert "own role" in msg.lower()
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.update_admin_account",
        new_callable=AsyncMock,
    )
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[1],
    )
    async def test_cannot_clear_role_of_other_admin(self, mock_get, mock_update, app, superadmin):
        """role_id can never be cleared to null for anyone — a roleless admin loses
        all RBAC resolution (deps.py falls back to "admin")."""
        app.dependency_overrides[get_current_admin] = lambda: superadmin
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v2/admins/2",  # another admin
                json={"role_id": None},
            )
            assert resp.status_code == 400
        mock_update.assert_not_called()

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

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.update_admin_account",
        new_callable=AsyncMock,
    )
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[1],
    )
    async def test_clearing_telegram_id_with_null(
        self, mock_get, mock_update, app, superadmin
    ):
        """Sending null for telegram_id should be accepted and the field cleared.

        Regression test: previously the endpoint used `is not None` guards which
        silently dropped explicit null values, leaving the original number in
        place while reporting success to the caller.
        """
        mock_update.return_value = MOCK_ACCOUNTS[1]
        app.dependency_overrides[get_current_admin] = lambda: superadmin
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v2/admins/2",
                json={"telegram_id": None},
            )
            assert resp.status_code == 200
        # Confirm null was passed through to the update helper
        assert "telegram_id" in mock_update.call_args.kwargs
        assert mock_update.call_args.kwargs["telegram_id"] is None

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.update_admin_account",
        new_callable=AsyncMock,
    )
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[1],
    )
    async def test_clearing_quota_with_null(
        self, mock_get, mock_update, app, superadmin
    ):
        """Sending null for max_users / max_traffic_gb clears the limit."""
        mock_update.return_value = MOCK_ACCOUNTS[1]
        app.dependency_overrides[get_current_admin] = lambda: superadmin
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v2/admins/2",
                json={"max_users": None, "max_traffic_gb": None, "max_nodes": None, "max_hosts": None},
            )
            assert resp.status_code == 200
        for field in ("max_users", "max_traffic_gb", "max_nodes", "max_hosts"):
            assert field in mock_update.call_args.kwargs
            assert mock_update.call_args.kwargs[field] is None

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.update_admin_account",
        new_callable=AsyncMock,
    )
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[1],
    )
    async def test_negative_quota_rejected(
        self, mock_get, mock_update, app, superadmin
    ):
        """Negative quota values are rejected by pydantic's `ge=0` constraint."""
        app.dependency_overrides[get_current_admin] = lambda: superadmin
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.put(
                "/api/v2/admins/2",
                json={"max_users": -1},
            )
            # 422 is the standard pydantic validation error (handled by
            # FastAPI before our handler runs).
            assert resp.status_code == 422
        # And the update helper was never called
        mock_update.assert_not_called()


class TestAdminCacheInvalidation:
    """Regression tests for the admin-account cache.

    The cache lives in web/backend/core/admin_accounts.py. Mutations
    (create user, edit admin, etc.) must invalidate it so the next
    /auth/me call returns fresh counter values — otherwise the UI
    shows stale "remaining traffic" numbers for up to the cache TTL.
    """

    @pytest.mark.asyncio
    async def test_increment_invalidates_cache_for_admin(self):
        """Direct test: calling increment_usage_counter drops the cache entry.

        Uses mocked DB execution to avoid hitting a real database.
        """
        from unittest.mock import MagicMock, patch
        from web.backend.core import admin_accounts
        import shared.database as shared_db_module

        # Pre-populate the cache
        admin_accounts._admin_account_cache[42] = {"id": 42, "traffic_used_bytes": 0}
        admin_accounts._admin_cache_ts[42] = __import__("time").time()
        assert 42 in admin_accounts._admin_account_cache

        # Mock the DB connection so increment_usage_counter thinks it ran
        # a successful UPDATE.
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")
        mock_acquire = MagicMock()
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.__aexit__ = AsyncMock(return_value=False)

        with patch.object(shared_db_module, "db_service") as mock_db:
            mock_db.is_connected = True
            mock_db.acquire = MagicMock(return_value=mock_acquire)
            result = await admin_accounts.increment_usage_counter(
                42, "traffic_used_bytes", 500_000_000_000
            )

        assert result is True
        # Cache for admin 42 must be gone — next getMe will read fresh
        assert 42 not in admin_accounts._admin_account_cache

    @pytest.mark.asyncio
    async def test_update_admin_account_invalidates_cache(self):
        """update_admin_account also invalidates the cache (max_traffic_gb etc.)."""
        from unittest.mock import MagicMock, patch
        from web.backend.core import admin_accounts
        import shared.database as shared_db_module

        admin_accounts._admin_account_cache[7] = {"id": 7, "max_traffic_gb": 100}
        admin_accounts._admin_cache_ts[7] = __import__("time").time()

        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(
            return_value={"id": 7, "max_traffic_gb": 999}
        )
        mock_acquire = MagicMock()
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.__aexit__ = AsyncMock(return_value=False)

        with patch.object(shared_db_module, "db_service") as mock_db:
            mock_db.is_connected = True
            mock_db.acquire = MagicMock(return_value=mock_acquire)
            result = await admin_accounts.update_admin_account(7, max_traffic_gb=999)

        assert result is not None
        assert result["max_traffic_gb"] == 999
        # Cache must be invalidated
        assert 7 not in admin_accounts._admin_account_cache

    def test_per_admin_cache_isolation(self):
        """Invalidating one admin must not affect others."""
        from web.backend.core import admin_accounts
        admin_accounts.invalidate_admin_cache()
        admin_accounts._admin_account_cache[1] = {"id": 1, "x": 1}
        admin_accounts._admin_account_cache[2] = {"id": 2, "x": 2}
        admin_accounts._cache_put(1, {"id": 1, "x": 1})
        admin_accounts._cache_put(2, {"id": 2, "x": 2})

        admin_accounts.invalidate_admin_cache(1)
        assert 1 not in admin_accounts._admin_account_cache
        # Admin 2 should still be cached
        assert admin_accounts._cache_get(2) is not None

        admin_accounts.invalidate_admin_cache()
        assert admin_accounts._cache_get(2) is None


class TestCounterFloorAtZero:
    """Regression test: counters like `traffic_used_bytes` must never go negative.

    The user reported: "after some creates, edits, deletes I see -202 GB of 1024 GB
    used" in the dashboard. Root cause: counter increments are gated by
    `unlimited_traffic_policy` (skipping for `policy="allowed"`/enforced)
    but deletes always subtract — so a user created under "allowed" and
    later deleted could drive the counter negative. The fix is a
    GREATEST(0, ...) safety floor in the SQL, plus always tracking
    counter changes regardless of policy.
    """

    @pytest.mark.asyncio
    async def test_increment_with_negative_amount_floors_at_zero(self):
        """A negative amount on traffic_used_bytes must clamp to 0, not go negative."""
        from unittest.mock import MagicMock
        from web.backend.core import admin_accounts

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")
        mock_acquire = MagicMock()
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.__aexit__ = AsyncMock(return_value=False)

        with patch("shared.database.db_service") as mock_db:
            mock_db.is_connected = True
            mock_db.acquire = MagicMock(return_value=mock_acquire)
            result = await admin_accounts.increment_usage_counter(
                1, "traffic_used_bytes", -500
            )

        assert result is True
        # The SQL passed to the DB must include GREATEST(0, ...) for the floor
        sql = mock_conn.execute.call_args[0][0]
        assert "GREATEST(0," in sql

    @pytest.mark.asyncio
    async def test_increment_with_positive_amount_does_not_floor(self):
        """Positive amounts should use the normal "+ $1" path, not the floor."""
        from unittest.mock import MagicMock
        from web.backend.core import admin_accounts

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")
        mock_acquire = MagicMock()
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.__aexit__ = AsyncMock(return_value=False)

        with patch("shared.database.db_service") as mock_db:
            mock_db.is_connected = True
            mock_db.acquire = MagicMock(return_value=mock_acquire)
            await admin_accounts.increment_usage_counter(1, "traffic_used_bytes", 500)

        sql = mock_conn.execute.call_args[0][0]
        assert "GREATEST" not in sql

    @pytest.mark.asyncio
    async def test_users_created_does_not_floor(self):
        """users_created is a lifetime event count — must NOT be floored at 0."""
        from unittest.mock import MagicMock
        from web.backend.core import admin_accounts

        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")
        mock_acquire = MagicMock()
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.__aexit__ = AsyncMock(return_value=False)

        with patch("shared.database.db_service") as mock_db:
            mock_db.is_connected = True
            mock_db.acquire = MagicMock(return_value=mock_acquire)
            await admin_accounts.increment_usage_counter(1, "users_created", -1)

        # users_created keeps the raw subtraction — lifetime counter
        sql = mock_conn.execute.call_args[0][0]
        assert "GREATEST" not in sql

    @pytest.mark.asyncio
    async def test_recompute_traffic_counter(self):
        """recompute_admin_traffic_counter sums (limit - used) across owned users."""
        from unittest.mock import MagicMock
        from web.backend.core import admin_accounts

        mock_conn = MagicMock()
        # Return two owned users with limits 100 and 50, used 10 and 0
        mock_conn.fetchrow = AsyncMock(return_value={"total": 140})
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")
        mock_acquire = MagicMock()
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.__aexit__ = AsyncMock(return_value=False)

        with patch("shared.database.db_service") as mock_db:
            mock_db.is_connected = True
            mock_db.acquire = MagicMock(return_value=mock_acquire)
            result = await admin_accounts.recompute_admin_traffic_counter(7)

        assert result == 140
        # Cache should be invalidated
        assert 7 not in admin_accounts._admin_account_cache

    @pytest.mark.asyncio
    async def test_recompute_fixes_negative_counter(self):
        """Recomputing a negative counter fixes it to the correct positive value."""
        from unittest.mock import MagicMock
        from web.backend.core import admin_accounts

        # Even if the SUM returns negative (e.g. due to historic bad data),
        # the recompute path uses GREATEST(0, ...) to clamp it.
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value={"total": -200})
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")
        mock_acquire = MagicMock()
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.__aexit__ = AsyncMock(return_value=False)

        with patch("shared.database.db_service") as mock_db:
            mock_db.is_connected = True
            mock_db.acquire = MagicMock(return_value=mock_acquire)
            result = await admin_accounts.recompute_admin_traffic_counter(7)

        # The query used to compute total should use GREATEST(0, ...) per row
        select_sql = mock_conn.fetchrow.call_args[0][0]
        assert "GREATEST(0," in select_sql


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


class TestResetAdminCounter:
    """POST /api/v2/admins/{admin_id}/counters/reset."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.admins.write_audit_log", new_callable=AsyncMock)
    @patch(
        "web.backend.api.v2.admins.reset_admin_counter",
        new_callable=AsyncMock,
        return_value={**MOCK_ACCOUNTS[0], "users_created": 0},
    )
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[0],
    )
    async def test_reset_users_counter(
        self, mock_get, mock_reset, mock_audit, client,
    ):
        resp = await client.post(
            "/api/v2/admins/1/counters/reset",
            json={"counter": "users_created"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["users_created"] == 0
        mock_reset.assert_called_once_with(1, "users_created")

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.admins.write_audit_log", new_callable=AsyncMock)
    @patch(
        "web.backend.api.v2.admins.reset_admin_counter",
        new_callable=AsyncMock,
        return_value={**MOCK_ACCOUNTS[0], "traffic_used_bytes": 0},
    )
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[0],
    )
    async def test_reset_traffic_counter(
        self, mock_get, mock_reset, mock_audit, client,
    ):
        resp = await client.post(
            "/api/v2/admins/1/counters/reset",
            json={"counter": "traffic_used_bytes"},
        )
        assert resp.status_code == 200
        mock_reset.assert_called_once_with(1, "traffic_used_bytes")

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[0],
    )
    async def test_reset_invalid_counter(self, mock_get, client):
        resp = await client.post(
            "/api/v2/admins/1/counters/reset",
            json={"counter": "invalid_counter"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=None,
    )
    async def test_reset_nonexistent_admin(self, mock_get, client):
        resp = await client.post(
            "/api/v2/admins/999/counters/reset",
            json={"counter": "users_created"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reset_as_viewer_forbidden(self, viewer_client):
        resp = await viewer_client.post(
            "/api/v2/admins/1/counters/reset",
            json={"counter": "users_created"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.admins.write_audit_log", new_callable=AsyncMock)
    @patch(
        "web.backend.api.v2.admins.reset_admin_counter",
        new_callable=AsyncMock,
        return_value=None,
    )
    @patch(
        "web.backend.api.v2.admins.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value=MOCK_ACCOUNTS[0],
    )
    async def test_reset_failure(self, mock_get, mock_reset, mock_audit, client):
        resp = await client.post(
            "/api/v2/admins/1/counters/reset",
            json={"counter": "users_created"},
        )
        assert resp.status_code == 500


# ── Traffic counter rollback (defense in depth) ────────────────


class TestTrafficCounterRollback:
    """Regression: if `increment_usage_counter(traffic_used_bytes)` fails
    on user create, the user must be deleted so the counter math stays
    consistent. Otherwise the next delete subtracts from a counter that
    was never incremented, driving it negative.
    """

    @pytest.mark.asyncio
    @patch("shared.api_client.api_client")
    @patch("web.backend.api.v2.users._validate_user_create_input", new_callable=AsyncMock)
    @patch(
        "web.backend.api.v2.users.get_admin_account_by_id",
        new_callable=AsyncMock,
        return_value={
            "id": 2, "username": "test_admin", "max_traffic_gb": 100,
            "traffic_used_bytes": 0, "unlimited_traffic_policy": "allowed",
        },
    )
    @patch(
        "web.backend.api.v2.users.get_current_admin",
        new_callable=AsyncMock,
        return_value=make_admin(account_id=2, role="admin"),
    )
    async def test_create_rolls_back_on_traffic_counter_failure(
        self, mock_admin, mock_acct, mock_validate, mock_api_client
    ):
        """When increment_usage_counter(traffic_used_bytes) fails, the
        user must be deleted (rolled back) so the counter math stays
        consistent."""
        from web.backend.api.v2.users import create_user
        from web.backend.core.errors import E

        # Mock the Panel API create_user
        async def fake_create_user(**kwargs):
            return {"response": {"uuid": "test-uuid-rollback-1", "username": "rollback_user"}}
        mock_api_client.create_user = fake_create_user

        # Mock delete_user (rollback) — capture the call
        delete_calls = []
        async def fake_delete_user(uuid):
            delete_calls.append(uuid)
            return True
        mock_api_client.delete_user = fake_delete_user

        # Mock increment_usage_counter: succeed for users_created,
        # FAIL for traffic_used_bytes (simulate quota check failure)
        async def mock_inc(admin_id, counter, amount=1):
            if counter == "traffic_used_bytes":
                return False
            return True

        with patch("web.backend.core.rbac.increment_usage_counter", new=mock_inc):
            from web.backend.schemas.user import UserCreate
            from fastapi import HTTPException
            payload = UserCreate(
                username="rollback_user",
                traffic_limit_bytes=200 * 1073741824,  # 200 GB
                traffic_limit_strategy="NO_RESET",
            )
            with pytest.raises(HTTPException) as exc_info:
                await create_user(
                    request=MagicMock(),
                    data=payload,
                    admin=mock_admin.return_value,
                )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail.get("code") == E.TRAFFIC_QUOTA_EXCEEDED.value
        # The user MUST have been deleted to keep counters consistent
        assert delete_calls == ["test-uuid-rollback-1"], \
            f"Expected rollback delete, got: {delete_calls}"

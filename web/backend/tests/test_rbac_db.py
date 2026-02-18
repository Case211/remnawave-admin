"""Tests for web.backend.core.rbac — database operations, caching, quota checking.

Covers: _ensure_cache, invalidate_cache, has_permission, get_role_permissions,
get_all_permissions_for_role_id, admin account CRUD, role CRUD, audit log,
check_quota, ensure_rbac_tables.
"""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import web.backend.core.rbac as rbac_mod


# ── Helpers ─────────────────────────────────────────────────────

def _make_db_mock(conn):
    """Create a mock db_service with acquire() returning conn."""
    db = MagicMock()
    db.is_connected = True
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    db.acquire.return_value = cm
    return db


def _make_conn(**overrides):
    """Create mock asyncpg connection."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="")
    # transaction() must be a regular call that returns an async context manager
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock()
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    for k, v in overrides.items():
        setattr(conn, k, v)
    return conn


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset the permission cache between tests."""
    rbac_mod._permissions_cache.clear()
    rbac_mod._cache_ts = 0
    yield
    rbac_mod._permissions_cache.clear()
    rbac_mod._cache_ts = 0


# ── _ensure_cache / invalidate_cache ────────────────────────────


class TestEnsureCache:

    async def test_populates_cache(self):
        conn = _make_conn()
        conn.fetch = AsyncMock(return_value=[
            {"role_id": 1, "resource": "users", "action": "view"},
            {"role_id": 1, "resource": "users", "action": "edit"},
            {"role_id": 2, "resource": "nodes", "action": "view"},
        ])
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            await rbac_mod._ensure_cache()

        assert rbac_mod._permissions_cache[1] == {("users", "view"), ("users", "edit")}
        assert rbac_mod._permissions_cache[2] == {("nodes", "view")}
        assert rbac_mod._cache_ts > 0

    async def test_skips_when_fresh(self):
        rbac_mod._permissions_cache = {1: {("a", "b")}}
        rbac_mod._cache_ts = time.time()

        conn = _make_conn()
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            await rbac_mod._ensure_cache()

        conn.fetch.assert_not_awaited()

    async def test_skips_when_not_connected(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            await rbac_mod._ensure_cache()

        assert rbac_mod._permissions_cache == {}

    async def test_handles_exception(self):
        db = MagicMock()
        db.is_connected = True
        db.acquire.side_effect = Exception("DB error")

        with patch("shared.database.db_service", db):
            await rbac_mod._ensure_cache()  # should not raise


class TestInvalidateCache:

    def test_sets_cache_ts_to_zero(self):
        rbac_mod._cache_ts = time.time()
        rbac_mod.invalidate_cache()
        assert rbac_mod._cache_ts == 0


# ── Permission checking ────────────────────────────────────────


class TestHasPermission:

    async def test_returns_false_for_none_role_id(self):
        assert await rbac_mod.has_permission(None, "users", "view") is False

    async def test_permission_found(self):
        rbac_mod._permissions_cache = {1: {("users", "view")}}
        rbac_mod._cache_ts = time.time()
        assert await rbac_mod.has_permission(1, "users", "view") is True

    async def test_permission_not_found(self):
        rbac_mod._permissions_cache = {1: {("users", "view")}}
        rbac_mod._cache_ts = time.time()
        assert await rbac_mod.has_permission(1, "users", "delete") is False

    async def test_unknown_role(self):
        rbac_mod._permissions_cache = {1: {("users", "view")}}
        rbac_mod._cache_ts = time.time()
        assert await rbac_mod.has_permission(99, "users", "view") is False


class TestGetRolePermissions:

    async def test_returns_sorted_list(self):
        rbac_mod._permissions_cache = {
            1: {("users", "view"), ("nodes", "edit"), ("analytics", "view")}
        }
        rbac_mod._cache_ts = time.time()
        result = await rbac_mod.get_role_permissions(1)
        assert isinstance(result, list)
        assert all("resource" in p and "action" in p for p in result)
        # Sorted
        resources = [p["resource"] for p in result]
        assert resources == sorted(resources)

    async def test_unknown_role_returns_empty(self):
        rbac_mod._permissions_cache = {}
        rbac_mod._cache_ts = time.time()
        result = await rbac_mod.get_role_permissions(999)
        assert result == []


class TestGetAllPermissionsForRoleId:

    async def test_returns_set(self):
        rbac_mod._permissions_cache = {1: {("a", "b"), ("c", "d")}}
        rbac_mod._cache_ts = time.time()
        result = await rbac_mod.get_all_permissions_for_role_id(1)
        assert result == {("a", "b"), ("c", "d")}

    async def test_unknown_role(self):
        rbac_mod._permissions_cache = {}
        rbac_mod._cache_ts = time.time()
        result = await rbac_mod.get_all_permissions_for_role_id(42)
        assert result == set()


# ── Admin account operations ────────────────────────────────────


class TestGetAdminAccountByUsername:

    async def test_returns_dict(self):
        row = {"id": 1, "username": "admin", "role_name": "superadmin", "role_display_name": "Super Admin"}
        conn = _make_conn(fetchrow=AsyncMock(return_value=row))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_admin_account_by_username("admin")

        assert result == dict(row)

    async def test_returns_none_when_not_found(self):
        conn = _make_conn(fetchrow=AsyncMock(return_value=None))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_admin_account_by_username("nobody")

        assert result is None

    async def test_returns_none_when_disconnected(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_admin_account_by_username("admin")

        assert result is None

    async def test_returns_none_on_exception(self):
        db = MagicMock()
        db.is_connected = True
        db.acquire.side_effect = Exception("fail")

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_admin_account_by_username("admin")

        assert result is None


class TestGetAdminAccountByTelegramId:

    async def test_returns_dict(self):
        row = {"id": 1, "telegram_id": 12345}
        conn = _make_conn(fetchrow=AsyncMock(return_value=row))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_admin_account_by_telegram_id(12345)

        assert result == dict(row)

    async def test_returns_none_when_disconnected(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_admin_account_by_telegram_id(12345)

        assert result is None


class TestGetAdminAccountById:

    async def test_returns_dict(self):
        row = {"id": 5, "username": "admin5"}
        conn = _make_conn(fetchrow=AsyncMock(return_value=row))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_admin_account_by_id(5)

        assert result == dict(row)

    async def test_returns_none_on_error(self):
        db = MagicMock()
        db.is_connected = True
        db.acquire.side_effect = Exception("err")

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_admin_account_by_id(5)

        assert result is None


class TestListAdminAccounts:

    async def test_returns_list(self):
        rows = [{"id": 1, "username": "a"}, {"id": 2, "username": "b"}]
        conn = _make_conn(fetch=AsyncMock(return_value=rows))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.list_admin_accounts()

        assert len(result) == 2
        assert result[0]["username"] == "a"

    async def test_returns_empty_when_disconnected(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            result = await rbac_mod.list_admin_accounts()

        assert result == []


class TestCreateAdminAccount:

    async def test_creates_account(self):
        row = {"id": 1, "username": "newadmin", "role_id": 1}
        conn = _make_conn(fetchrow=AsyncMock(return_value=row))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.create_admin_account(
                username="newadmin",
                password_hash="$2b$12$hash",
                telegram_id=None,
                role_id=1,
            )

        assert result["username"] == "newadmin"
        conn.fetchrow.assert_awaited_once()

    async def test_returns_none_when_disconnected(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            result = await rbac_mod.create_admin_account("u", "h", None, 1)

        assert result is None

    async def test_returns_none_on_error(self):
        db = MagicMock()
        db.is_connected = True
        db.acquire.side_effect = Exception("dup key")

        with patch("shared.database.db_service", db):
            result = await rbac_mod.create_admin_account("u", "h", None, 1)

        assert result is None


class TestUpdateAdminAccount:

    async def test_no_fields_delegates_to_get(self):
        row = {"id": 1, "username": "admin"}
        conn = _make_conn(fetchrow=AsyncMock(return_value=row))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.update_admin_account(1)

        assert result == dict(row)

    async def test_filters_disallowed_fields(self):
        row = {"id": 1, "username": "admin"}
        conn = _make_conn(fetchrow=AsyncMock(return_value=row))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.update_admin_account(1, evil_field="hack")

        # Should call get_admin_account_by_id since no valid fields
        assert result == dict(row)

    async def test_updates_allowed_fields(self):
        updated_row = {"id": 1, "username": "new_name", "is_active": True}
        conn = _make_conn(fetchrow=AsyncMock(return_value=updated_row))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.update_admin_account(1, username="new_name")

        assert result["username"] == "new_name"

    async def test_returns_none_when_disconnected(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            result = await rbac_mod.update_admin_account(1, username="x")

        assert result is None


class TestDeleteAdminAccount:

    async def test_successful_delete(self):
        conn = _make_conn(execute=AsyncMock(return_value="DELETE 1"))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.delete_admin_account(1)

        assert result is True

    async def test_not_found(self):
        conn = _make_conn(execute=AsyncMock(return_value="DELETE 0"))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.delete_admin_account(999)

        assert result is False

    async def test_returns_false_when_disconnected(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            result = await rbac_mod.delete_admin_account(1)

        assert result is False


class TestIncrementUsageCounter:

    async def test_valid_counter(self):
        conn = _make_conn()
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.increment_usage_counter(1, "users_created", 1)

        assert result is True
        conn.execute.assert_awaited_once()

    async def test_invalid_counter(self):
        result = await rbac_mod.increment_usage_counter(1, "invalid_counter")
        assert result is False

    async def test_returns_false_when_disconnected(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            result = await rbac_mod.increment_usage_counter(1, "users_created")

        assert result is False


class TestAdminAccountExists:

    async def test_exists(self):
        conn = _make_conn(fetchrow=AsyncMock(return_value={"?column?": 1}))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.admin_account_exists()

        assert result is True

    async def test_not_exists(self):
        conn = _make_conn(fetchrow=AsyncMock(return_value=None))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.admin_account_exists()

        assert result is False


# ── Role operations ────────────────────────────────────────────


class TestListRoles:

    async def test_returns_list(self):
        rows = [
            {"id": 1, "name": "superadmin", "permissions_count": 10, "admins_count": 1},
        ]
        conn = _make_conn(fetch=AsyncMock(return_value=rows))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.list_roles()

        assert len(result) == 1
        assert result[0]["name"] == "superadmin"

    async def test_returns_empty_when_disconnected(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            result = await rbac_mod.list_roles()

        assert result == []


class TestGetRoleById:

    async def test_returns_role_with_permissions(self):
        role_row = {"id": 1, "name": "admin", "display_name": "Admin"}
        perm_rows = [
            {"resource": "users", "action": "view"},
            {"resource": "nodes", "action": "view"},
        ]
        conn = _make_conn()
        conn.fetchrow = AsyncMock(return_value=role_row)
        conn.fetch = AsyncMock(return_value=perm_rows)
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_role_by_id(1)

        assert result["name"] == "admin"
        assert len(result["permissions"]) == 2

    async def test_returns_none_when_not_found(self):
        conn = _make_conn(fetchrow=AsyncMock(return_value=None))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_role_by_id(999)

        assert result is None


class TestGetRoleByName:

    async def test_returns_role(self):
        row = {"id": 1, "name": "superadmin"}
        conn = _make_conn(fetchrow=AsyncMock(return_value=row))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_role_by_name("superadmin")

        assert result["name"] == "superadmin"

    async def test_returns_none_when_not_found(self):
        conn = _make_conn(fetchrow=AsyncMock(return_value=None))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_role_by_name("nonexistent")

        assert result is None


class TestCreateRole:

    async def test_creates_role_with_permissions(self):
        role_row = {"id": 10, "name": "custom", "display_name": "Custom Role"}
        conn = _make_conn(fetchrow=AsyncMock(return_value=role_row))
        db = _make_db_mock(conn)

        perms = [{"resource": "users", "action": "view"}]

        with patch("shared.database.db_service", db):
            result = await rbac_mod.create_role("custom", "Custom Role", "Desc", perms)

        assert result["name"] == "custom"
        assert result["permissions"] == perms
        # Inserted permission
        assert conn.execute.await_count >= 1

    async def test_creates_role_without_permissions(self):
        role_row = {"id": 11, "name": "empty"}
        conn = _make_conn(fetchrow=AsyncMock(return_value=role_row))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.create_role("empty", "Empty Role")

        assert result["permissions"] == []

    async def test_returns_none_when_disconnected(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            result = await rbac_mod.create_role("x", "X")

        assert result is None


class TestUpdateRole:

    async def test_updates_display_name(self):
        # update_role opens transaction, runs UPDATE, then calls get_role_by_id
        conn = _make_conn()
        db = _make_db_mock(conn)

        # get_role_by_id is called at the end — mock it to return result
        role_result = {"id": 1, "display_name": "New Name", "permissions": []}
        with patch("shared.database.db_service", db), \
             patch.object(rbac_mod, "get_role_by_id", new_callable=AsyncMock,
                          return_value=role_result):
            result = await rbac_mod.update_role(1, display_name="New Name")

        assert result["display_name"] == "New Name"
        conn.execute.assert_awaited_once()  # UPDATE statement

    async def test_replaces_permissions(self):
        conn = _make_conn()
        db = _make_db_mock(conn)
        new_perms = [{"resource": "users", "action": "view"}]

        role_result = {"id": 1, "permissions": new_perms}
        with patch("shared.database.db_service", db), \
             patch.object(rbac_mod, "get_role_by_id", new_callable=AsyncMock,
                          return_value=role_result):
            result = await rbac_mod.update_role(1, permissions=new_perms)

        # Should have: DELETE old perms + INSERT new perm = 2 execute calls
        assert conn.execute.await_count == 2

    async def test_returns_none_on_error(self):
        db = MagicMock()
        db.is_connected = True
        db.acquire.side_effect = Exception("err")

        with patch("shared.database.db_service", db):
            result = await rbac_mod.update_role(1, display_name="X")

        assert result is None


class TestDeleteRole:

    async def test_successful_delete(self):
        conn = _make_conn(execute=AsyncMock(return_value="DELETE 1"))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.delete_role(1)

        assert result is True

    async def test_system_role_not_deleted(self):
        conn = _make_conn(execute=AsyncMock(return_value="DELETE 0"))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.delete_role(1)

        assert result is False

    async def test_returns_false_on_error(self):
        db = MagicMock()
        db.is_connected = True
        db.acquire.side_effect = Exception("err")

        with patch("shared.database.db_service", db):
            result = await rbac_mod.delete_role(1)

        assert result is False


# ── Audit log ──────────────────────────────────────────────────


class TestWriteAuditLog:

    async def test_writes_entry(self):
        conn = _make_conn()
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            await rbac_mod.write_audit_log(
                admin_id=1,
                admin_username="admin",
                action="create",
                resource="users",
                resource_id="uuid-123",
            )

        conn.execute.assert_awaited_once()

    async def test_handles_disconnection(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            await rbac_mod.write_audit_log(1, "admin", "create")  # should not raise


class TestGetAuditLogs:

    async def test_basic_query(self):
        count_row = [10]
        rows = [{"id": 1, "action": "create", "admin_username": "admin"}]
        conn = _make_conn()
        conn.fetchrow = AsyncMock(return_value=count_row)
        conn.fetch = AsyncMock(return_value=rows)
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            logs, total = await rbac_mod.get_audit_logs(limit=50, offset=0)

        assert total == 10
        assert len(logs) == 1

    async def test_with_filters(self):
        conn = _make_conn()
        conn.fetchrow = AsyncMock(return_value=[5])
        conn.fetch = AsyncMock(return_value=[])
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            logs, total = await rbac_mod.get_audit_logs(
                admin_id=1, action="create", resource="users",
                date_from="2026-01-01", date_to="2026-12-31",
                search="test",
            )

        assert total == 5

    async def test_cursor_based_pagination(self):
        conn = _make_conn()
        conn.fetchrow = AsyncMock(return_value=[100])
        conn.fetch = AsyncMock(return_value=[])
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            logs, total = await rbac_mod.get_audit_logs(cursor=50, limit=20)

        assert total == 100

    async def test_returns_empty_on_error(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            logs, total = await rbac_mod.get_audit_logs()

        assert logs == []
        assert total == 0


class TestGetAuditLogsForResource:

    async def test_returns_logs(self):
        rows = [{"id": 1, "action": "update"}]
        conn = _make_conn(fetch=AsyncMock(return_value=rows))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_audit_logs_for_resource("users", "uuid-1")

        assert len(result) == 1

    async def test_returns_empty_when_disconnected(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_audit_logs_for_resource("users", "uuid-1")

        assert result == []


class TestGetAuditDistinctActions:

    async def test_returns_actions(self):
        rows = [{"action": "create"}, {"action": "delete"}]
        conn = _make_conn(fetch=AsyncMock(return_value=rows))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_audit_distinct_actions()

        assert result == ["create", "delete"]

    async def test_returns_empty_when_disconnected(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            result = await rbac_mod.get_audit_distinct_actions()

        assert result == []


# ── Quota checking ─────────────────────────────────────────────


class TestCheckQuota:

    async def test_unlimited_quota(self):
        with patch.object(rbac_mod, "get_admin_account_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": 1, "is_active": True,
                "max_users": None, "users_created": 5,
            }
            allowed, msg = await rbac_mod.check_quota(1, "users")

        assert allowed is True
        assert msg == ""

    async def test_within_quota(self):
        with patch.object(rbac_mod, "get_admin_account_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": 1, "is_active": True,
                "max_users": 10, "users_created": 5,
            }
            allowed, msg = await rbac_mod.check_quota(1, "users")

        assert allowed is True

    async def test_quota_exceeded(self):
        with patch.object(rbac_mod, "get_admin_account_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "id": 1, "is_active": True,
                "max_users": 5, "users_created": 5,
            }
            allowed, msg = await rbac_mod.check_quota(1, "users")

        assert allowed is False
        assert "Quota exceeded" in msg

    async def test_account_not_found(self):
        with patch.object(rbac_mod, "get_admin_account_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            allowed, msg = await rbac_mod.check_quota(999, "users")

        assert allowed is False
        assert "not found" in msg

    async def test_account_disabled(self):
        with patch.object(rbac_mod, "get_admin_account_by_id", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"id": 1, "is_active": False}
            allowed, msg = await rbac_mod.check_quota(1, "users")

        assert allowed is False
        assert "disabled" in msg


# ── ensure_rbac_tables ────────────────────────────────────────


class TestEnsureRbacTables:

    async def test_tables_exist(self):
        conn = _make_conn(fetchrow=AsyncMock(return_value={"?column?": 1}))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            await rbac_mod.ensure_rbac_tables()  # should not raise

    async def test_tables_missing_logs_warning(self):
        conn = _make_conn(fetchrow=AsyncMock(return_value=None))
        db = _make_db_mock(conn)

        with patch("shared.database.db_service", db):
            await rbac_mod.ensure_rbac_tables()  # should log warning but not raise

    async def test_handles_disconnection(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            await rbac_mod.ensure_rbac_tables()  # should not raise

    async def test_handles_exception(self):
        db = MagicMock()
        db.is_connected = True
        db.acquire.side_effect = Exception("err")

        with patch("shared.database.db_service", db):
            await rbac_mod.ensure_rbac_tables()  # should not raise

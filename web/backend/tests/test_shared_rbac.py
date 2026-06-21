"""Tests for shared/rbac.py — permission checking, scope, quota."""
from unittest.mock import patch, AsyncMock

import pytest

pytestmark = pytest.mark.asyncio


# ── filter_by_scope ─────────────────────────────────────────────


class TestFilterByScope:
    """Pure function — no DB needed."""

    def test_none_scope_returns_all(self):
        from shared.rbac import filter_by_scope
        items = [{"uuid": "a"}, {"uuid": "b"}]
        assert filter_by_scope(items, None) == items

    def test_empty_scope_returns_empty(self):
        from shared.rbac import filter_by_scope
        items = [{"uuid": "a"}, {"uuid": "b"}]
        assert filter_by_scope(items, set()) == []

    def test_scope_filters_correctly(self):
        from shared.rbac import filter_by_scope
        items = [{"uuid": "aaa"}, {"uuid": "bbb"}, {"uuid": "ccc"}]
        result = filter_by_scope(items, {"aaa", "ccc"})
        assert len(result) == 2
        assert result[0]["uuid"] == "aaa"
        assert result[1]["uuid"] == "ccc"

    def test_scope_is_case_insensitive(self):
        from shared.rbac import filter_by_scope
        items = [{"uuid": "ABC"}, {"uuid": "def"}]
        result = filter_by_scope(items, {"abc"})
        assert len(result) == 1
        assert result[0]["uuid"] == "ABC"

    def test_custom_uuid_key(self):
        from shared.rbac import filter_by_scope
        items = [{"id": "x"}, {"id": "y"}]
        result = filter_by_scope(items, {"x"}, uuid_key="id")
        assert len(result) == 1
        assert result[0]["id"] == "x"

    def test_missing_uuid_key_skipped(self):
        from shared.rbac import filter_by_scope
        items = [{"uuid": "a"}, {"name": "b"}]
        result = filter_by_scope(items, {"a"})
        assert len(result) == 1
        assert result[0]["uuid"] == "a"


# ── Cache invalidation ──────────────────────────────────────────


class TestCacheInvalidation:
    def test_invalidate_cache_resets_ts(self):
        import shared.rbac
        shared.rbac._cache_ts = 999
        shared.rbac.invalidate_cache()
        assert shared.rbac._cache_ts == 0

    def test_invalidate_scope_cache_clears_dict(self):
        import shared.rbac
        shared.rbac._scope_cache = {(1, 2): {("users", "view"): {"a"}}}
        shared.rbac._scope_cache_ts = 999
        shared.rbac.invalidate_scope_cache()
        assert shared.rbac._scope_cache == {}
        assert shared.rbac._scope_cache_ts == 0


# ── has_permission ──────────────────────────────────────────────


class TestHasPermission:
    async def test_none_role_id_returns_false(self):
        from shared.rbac import has_permission
        result = await has_permission(None, "users", "view")
        assert result is False

    async def test_permission_found_in_cache(self):
        import shared.rbac
        shared.rbac._cache_ts = 999
        shared.rbac._permissions_cache = {1: {("users", "view")}}
        result = await shared.rbac.has_permission(1, "users", "view")
        assert result is True

    async def test_permission_not_found_returns_false(self):
        import shared.rbac
        shared.rbac._cache_ts = 999
        shared.rbac._permissions_cache = {1: {("users", "view")}}
        result = await shared.rbac.has_permission(1, "users", "delete")
        assert result is False

    async def test_empty_cache_for_role_returns_false(self):
        import shared.rbac
        shared.rbac._cache_ts = 999
        shared.rbac._permissions_cache = {}
        result = await shared.rbac.has_permission(999, "users", "view")
        assert result is False

    async def test_cache_ttl_triggers_reload(self):
        import shared.rbac
        import time
        shared.rbac._cache_ts = 0
        shared.rbac._permissions_cache = {1: {("users", "view")}}
        with patch("shared.rbac.db_service") as mock_db:
            mock_db.is_connected = False
            result = await shared.rbac.has_permission(1, "users", "view")
            assert result is True


# ── get_role_permissions ────────────────────────────────────────


class TestGetRolePermissions:
    async def test_returns_sorted_list(self):
        import shared.rbac
        shared.rbac._cache_ts = 999
        shared.rbac._permissions_cache = {1: {("z", "a"), ("a", "z"), ("m", "m")}}
        result = await shared.rbac.get_role_permissions(1)
        assert result == [
            {"resource": "a", "action": "z"},
            {"resource": "m", "action": "m"},
            {"resource": "z", "action": "a"},
        ]

    async def test_unknown_role_returns_empty(self):
        import shared.rbac
        shared.rbac._cache_ts = 999
        shared.rbac._permissions_cache = {}
        result = await shared.rbac.get_role_permissions(999)
        assert result == []


class TestGetAllPermissionsForRoleId:
    async def test_returns_set(self):
        import shared.rbac
        shared.rbac._cache_ts = 999
        shared.rbac._permissions_cache = {1: {("users", "view")}}
        result = await shared.rbac.get_all_permissions_for_role_id(1)
        assert result == {("users", "view")}

    async def test_alias_matches(self):
        import shared.rbac
        shared.rbac._cache_ts = 999
        shared.rbac._permissions_cache = {1: {("x", "y")}}
        r1 = await shared.rbac.get_all_permissions_for_role_id(1)
        r2 = await shared.rbac.get_role_permission_set(1)
        assert r1 == r2


# ── check_quota ─────────────────────────────────────────────────


class TestCheckQuota:
    async def test_account_not_found(self):
        from shared.rbac import check_quota
        with patch("shared.rbac.get_admin_account_by_id", new=AsyncMock(return_value=None)):
            allowed, msg = await check_quota(1, "users")
        assert allowed is False
        assert "not found" in msg

    async def test_account_disabled(self):
        from shared.rbac import check_quota
        with patch("shared.rbac.get_admin_account_by_id", new=AsyncMock(return_value={"is_active": False})):
            allowed, msg = await check_quota(1, "users")
        assert allowed is False
        assert "disabled" in msg

    async def test_no_limit_set_allowed(self):
        from shared.rbac import check_quota
        with patch("shared.rbac.get_admin_account_by_id", new=AsyncMock(return_value={
            "is_active": True, "max_users": None, "users_created": 0,
        })):
            allowed, msg = await check_quota(1, "users")
        assert allowed is True
        assert msg == ""

    async def test_within_quota_allowed(self):
        from shared.rbac import check_quota
        with patch("shared.rbac.get_admin_account_by_id", new=AsyncMock(return_value={
            "is_active": True, "max_users": 10, "users_created": 5,
        })):
            allowed, msg = await check_quota(1, "users")
        assert allowed is True

    async def test_quota_exceeded_denied(self):
        from shared.rbac import check_quota
        with patch("shared.rbac.get_admin_account_by_id", new=AsyncMock(return_value={
            "is_active": True, "max_users": 10, "users_created": 10,
        })):
            allowed, msg = await check_quota(1, "users")
        assert allowed is False
        assert "Quota exceeded" in msg

    async def test_over_quota_denied(self):
        from shared.rbac import check_quota
        with patch("shared.rbac.get_admin_account_by_id", new=AsyncMock(return_value={
            "is_active": True, "max_users": 10, "users_created": 15,
        })):
            allowed, msg = await check_quota(1, "users")
        assert allowed is False
        assert "Quota exceeded" in msg

    async def test_different_resource_types(self):
        from shared.rbac import check_quota
        for resource in ("nodes", "hosts"):
            with patch("shared.rbac.get_admin_account_by_id", new=AsyncMock(return_value={
                "is_active": True, f"max_{resource}": None, f"{resource}_created": 0,
            })):
                allowed, msg = await check_quota(1, resource)
            assert allowed is True, f"Failed for {resource}"


# ── get_scope edge cases (DB mocked) ────────────────────────────


class TestGetScope:
    async def test_superadmin_returns_none(self):
        from shared.rbac import get_scope
        result = await get_scope(1, 1, "superadmin", "node", "view")
        assert result is None

    async def test_no_account_id_returns_none(self):
        from shared.rbac import get_scope
        result = await get_scope(None, None, None, "node", "view")
        assert result is None

    async def test_db_disconnected_failclosed(self):
        # fail-closed (#1): при недоступной БД get_scope не выдаёт полный доступ (None),
        # а пустой scope (нет доступа) — как get_visible_user_uuids
        from shared.rbac import get_scope
        with patch("shared.rbac.db_service") as mock_db:
            mock_db.is_connected = False
            result = await get_scope(1, 1, "admin", "node", "view")
        assert result == set()

    async def test_no_rules_returns_none(self):
        from shared.rbac import get_scope
        mock_db = AsyncMock()
        mock_db.is_connected = True
        mock_db.get_effective_policy_rules = AsyncMock(return_value=[])
        with patch("shared.rbac.db_service", mock_db):
            result = await get_scope(1, 1, "admin", "node", "view")
        assert result is None

    async def test_uuid_scope_resolved(self):
        from shared.rbac import get_scope, invalidate_scope_cache
        invalidate_scope_cache()
        mock_db = AsyncMock()
        mock_db.is_connected = True
        mock_db.get_effective_policy_rules = AsyncMock(return_value=[
            {"resource_type": "node", "scope_type": "uuid", "scope_value": "abc-123", "actions": ["view", "edit"]},
        ])
        with patch("shared.rbac.db_service", mock_db):
            result = await get_scope(1, 1, "admin", "node", "view")
        assert result == {"abc-123"}

    async def test_irrelevant_resource_type_returns_none(self):
        from shared.rbac import get_scope, invalidate_scope_cache
        invalidate_scope_cache()
        mock_db = AsyncMock()
        mock_db.is_connected = True
        mock_db.get_effective_policy_rules = AsyncMock(return_value=[
            {"resource_type": "host", "scope_type": "uuid", "scope_value": "x", "actions": ["view"]},
        ])
        with patch("shared.rbac.db_service", mock_db):
            result = await get_scope(1, 1, "admin", "node", "view")
        assert result is None

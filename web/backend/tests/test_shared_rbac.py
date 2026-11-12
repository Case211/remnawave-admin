"""Tests for shared/rbac.py — permission checking, scope, quota."""
from contextlib import asynccontextmanager
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


# ── get_visible_user_uuids ──────────────────────────────────────


def _fake_scope(node=None, squad=None, user=None):
    """Подмена get_scope: возвращает заданный scope по типу ресурса."""
    async def fake_scope(account_id, role_id, role, resource, action):
        if resource == "node":
            return node
        if resource == "squad":
            return squad
        return user
    return fake_scope


class TestGetVisibleUserUuids:
    """Видимость юзеров: база по чекбоксу, сужение по политике юзеров.

    Чекбокс «Может видеть всех пользователей» задаёт базу: включён — все
    юзеры, снят — только свои (created_by_admin_id). Политика с
    resource_type='user' СУЖАЕТ базу и никогда её не расширяет. Политики по
    нодам/хостам/сквадам ограничивают доступ к самим ресурсам и на видимость
    юзеров не влияют.
    """

    OWN = "11111111-1111-1111-1111-111111111111"
    FOREIGN = "22222222-2222-2222-2222-222222222222"

    def _db(self, creator_rows, unrestricted=False):
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            return_value={"unrestricted_user_access": unrestricted, "role_id": 5}
        )
        conn.fetch = AsyncMock(return_value=creator_rows)

        db = AsyncMock()
        db.is_connected = True

        @asynccontextmanager
        async def acquire():
            yield conn

        db.acquire = acquire
        db.conn = conn  # для проверок выданного SQL
        return db

    async def test_own_user_visible_before_first_connection(self):
        """Создал юзера — видишь сразу.

        Юзер попадает в policy-набор только через трафик по разрешённой
        ноде или через сквад, а только что созданный ещё ни разу не
        подключался. При пересечении он выпадал, и создатель видел
        пустой список, уже потратив квоту.
        """
        from shared.rbac import get_visible_user_uuids

        db = self._db(creator_rows=[{"uuid": self.OWN}])
        with patch("shared.rbac.db_service", db), \
             patch("shared.rbac.get_scope", _fake_scope(node={"node-1"})):
            result = await get_visible_user_uuids(42, "manager")
        assert result == {self.OWN}

    async def test_checked_flag_shows_all_users(self):
        """Включённый чекбокс — все юзеры; политики по нодам не сужают.

        Раньше видимость считалась как «свои ∪ юзеры разрешённых нод», и
        чекбокс работал наоборот: включённый админ видел МЕНЬШЕ юзеров,
        чем снятый, а снятый — больше, чем «только свои».
        """
        from shared.rbac import get_visible_user_uuids

        db = self._db(creator_rows=[{"uuid": self.OWN}], unrestricted=True)
        with patch("shared.rbac.db_service", db), \
             patch("shared.rbac.get_scope", _fake_scope(node={"node-1"})):
            result = await get_visible_user_uuids(42, "manager")
        assert result is None

    async def test_user_policy_narrows_all_users(self):
        """Политика по юзерам сужает базу «все юзеры»."""
        from shared.rbac import get_visible_user_uuids

        db = self._db(creator_rows=[], unrestricted=True)
        with patch("shared.rbac.db_service", db), \
             patch("shared.rbac.get_scope", _fake_scope(user={self.OWN})):
            result = await get_visible_user_uuids(42, "manager")
        assert result == {self.OWN}

    async def test_user_policy_cannot_widen_creator_scope(self):
        """Снятый чекбокс: политика сужает, но не расширяет «своих».

        Политика может выдать чужого юзера — он не появится: снятый чекбокс
        означает «только свои», и политика лишь сужает.
        """
        from shared.rbac import get_visible_user_uuids

        db = self._db(creator_rows=[{"uuid": self.OWN}])
        with patch("shared.rbac.db_service", db), \
             patch("shared.rbac.get_scope", _fake_scope(user={self.FOREIGN})):
            result = await get_visible_user_uuids(42, "manager")
        assert result == set()

    async def test_without_policies_creator_scope_applies(self):
        from shared.rbac import get_visible_user_uuids

        db = self._db(creator_rows=[{"uuid": self.OWN}])
        with patch("shared.rbac.db_service", db), \
             patch("shared.rbac.get_scope", _fake_scope()):
            result = await get_visible_user_uuids(42, "manager")
        assert result == {self.OWN}

    async def test_creator_scope_query_filters_by_admin_id(self):
        """Свои юзеры берутся по created_by_admin_id = id админа.

        Заодно: выборка «своих» — единственный запрос к users, политики по
        нодам не подмешивают в неё чужих юзеров.
        """
        from shared.rbac import get_visible_user_uuids

        db = self._db(creator_rows=[{"uuid": self.OWN}])
        with patch("shared.rbac.db_service", db), \
             patch("shared.rbac.get_scope", _fake_scope(node={"node-1"})):
            await get_visible_user_uuids(42, "manager")

        assert db.conn.fetch.await_count == 1
        sql, params = db.conn.fetch.await_args[0]
        assert "created_by_admin_id" in sql
        assert params == 42

    async def test_superadmin_unrestricted(self):
        from shared.rbac import get_visible_user_uuids

        assert await get_visible_user_uuids(1, "superadmin") is None

    async def test_db_down_fails_closed(self):
        """Недоступная БД не должна открывать доступ ко всем юзерам."""
        from shared.rbac import get_visible_user_uuids

        db = AsyncMock()
        db.is_connected = False
        with patch("shared.rbac.db_service", db):
            result = await get_visible_user_uuids(42, "manager")
        assert result == set()


# ── список юзеров уважает видимость ─────────────────────────────


class TestUsersListVisibility:
    """GET /api/v2/users отдаёт только то, что админ имеет право видеть."""

    OWN = "11111111-1111-1111-1111-111111111111"
    FOREIGN = "22222222-2222-2222-2222-222222222222"

    async def _list(self, app, admin, *, unrestricted, creator_rows, user_scope=None):
        """Запрашивает список юзеров и возвращает (whitelist, uuid'ы в ответе)."""
        import shared.database as shared_database

        from httpx import ASGITransport, AsyncClient

        from web.backend.api.deps import get_current_admin

        app.dependency_overrides[get_current_admin] = lambda: admin

        conn = AsyncMock()
        conn.fetchrow = AsyncMock(
            return_value={"unrestricted_user_access": unrestricted, "role_id": 5}
        )
        conn.fetch = AsyncMock(return_value=creator_rows)

        rbac_db = AsyncMock()
        rbac_db.is_connected = True

        @asynccontextmanager
        async def acquire():
            yield conn

        rbac_db.acquire = acquire
        rbac_db.get_effective_policy_rules = AsyncMock(return_value=[])

        captured = {}
        async def get_users_paginated(**kwargs):
            captured.update(kwargs)
            whitelist = kwargs.get("uuid_whitelist")
            candidates = [
                {"uuid": self.OWN, "username": "own"},
                {"uuid": self.FOREIGN, "username": "foreign"},
            ]
            if whitelist is not None:
                allowed = {u.lower() for u in whitelist}
                candidates = [
                    u for u in candidates if str(u["uuid"]).lower() in allowed
                ]
            return candidates, len(candidates)

        list_db = AsyncMock()
        list_db.is_connected = True
        list_db.get_users_paginated = AsyncMock(side_effect=get_users_paginated)
        list_db.get_hwid_device_counts_for_uuids = AsyncMock(return_value={})
        list_db.get_raw_traffic_for_uuids = AsyncMock(return_value={})

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            with patch("shared.rbac.db_service", rbac_db), \
                 patch("shared.rbac.get_scope", _fake_scope(user=user_scope)), \
                 patch.object(shared_database, "db_service", list_db):
                resp = await ac.get("/api/v2/users")

        assert resp.status_code == 200, resp.text
        return captured.get("uuid_whitelist"), [u["uuid"] for u in resp.json()["items"]]

    async def test_unchecked_admin_sees_only_own_users(self, app, manager):
        """Снятый чекбокс — в списке только собственные юзеры."""
        whitelist, uuids = await self._list(
            app, manager,
            unrestricted=False,
            creator_rows=[{"uuid": self.OWN}],
        )
        assert whitelist is not None, "фильтр по видимости не применён"
        assert uuids == [self.OWN]
        assert self.FOREIGN not in uuids

    async def test_checked_admin_narrowed_by_user_policy(self, app, manager):
        """Включённый чекбокс + политика по юзерам — список сужен политикой."""
        whitelist, uuids = await self._list(
            app, manager,
            unrestricted=True,
            creator_rows=[],
            user_scope={self.OWN},
        )
        assert whitelist is not None
        assert set(whitelist) == {self.OWN.lower()}
        assert uuids == [self.OWN]
        assert self.FOREIGN not in uuids


# ── разворачивание тега в uuid ───────────────────────────────────


class TestGetUuidsByTag:
    """Разный SQL для юзеров и нод/хостов.

    У нод и хостов теги лежат массивом в raw_data (Panel API payload),
    у юзеров — в отдельной колонке `tag` с одним точным значением.
    """

    async def _sql_for(self, resource_type: str) -> str:
        from shared.db.network import NetworkMixin

        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[{"uuid": "x"}])

        @asynccontextmanager
        async def acquire():
            yield conn

        mixin = NetworkMixin()
        mixin.is_connected = True
        mixin.acquire = acquire

        await mixin.get_uuids_by_tag(resource_type, "vip")
        return conn.fetch.call_args[0][0]

    async def test_user_tag_uses_dedicated_column(self):
        sql = await self._sql_for("user")
        assert "FROM users" in sql
        assert "tag = $1" in sql
        assert "raw_data" not in sql

    async def test_node_tag_still_uses_raw_data(self):
        sql = await self._sql_for("node")
        assert "FROM nodes" in sql
        assert "raw_data" in sql

    async def test_unknown_resource_type_returns_empty(self):
        from shared.db.network import NetworkMixin

        mixin = NetworkMixin()
        mixin.is_connected = True
        assert await mixin.get_uuids_by_tag("squad", "vip") == []

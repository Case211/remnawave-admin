"""Tests for plugin RBAC resources reaching the superadmin role.

Regression cover for issue #268: sync_superadmin_permissions() used to run only
before plugin_loader.register(app), so resources declared by a plugin were never
in the map at sync time. The permission never landed on the superadmin role and
NavEntry — filtered by that permission — hid the plugin page from everyone.

Covers: get_resources_map() merging plugin resources, sync_superadmin_permissions()
inserting the missing ones, its idempotency, and the lifespan call order that made
the bug possible in the first place.
"""
import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import web.backend.api.v2.roles as roles_mod
import web.backend.core.rbac as rbac_mod


# ── Helpers ─────────────────────────────────────────────────────

def _make_conn(existing_perms=None, role_id=1):
    """Mock asyncpg connection: superadmin role lookup + existing permissions."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"id": role_id} if role_id else None)
    conn.fetch = AsyncMock(return_value=[
        {"resource": r, "action": a} for r, a in (existing_perms or [])
    ])
    conn.execute = AsyncMock(return_value="")
    tx = AsyncMock()
    tx.__aenter__ = AsyncMock()
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    return conn


def _make_db(conn):
    db = MagicMock()
    db.is_connected = True
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    db.acquire.return_value = cm
    return db


def _inserted_pairs(conn):
    """Extract (resource, action) tuples from conn.execute() calls."""
    pairs = set()
    for call in conn.execute.await_args_list:
        args = call.args
        if len(args) >= 3:
            pairs.add((args[-2], args[-1]))
    return pairs


# ── get_resources_map: plugin resources are merged in ───────────

class TestResourcesMapMergesPlugins:

    def test_new_plugin_resource_is_added(self):
        with patch.object(roles_mod, "get_extra_rbac_resources", return_value={"myplugin": ["view", "edit"]}):
            merged = roles_mod.get_resources_map()

        assert merged["myplugin"] == ["view", "edit"]
        # built-ins survive the merge
        assert "users" in merged and "view" in merged["users"]

    def test_plugin_actions_extend_builtin_resource(self):
        with patch.object(roles_mod, "get_extra_rbac_resources", return_value={"users": ["impersonate"]}):
            merged = roles_mod.get_resources_map()

        assert "impersonate" in merged["users"]
        assert "view" in merged["users"], "plugin actions must extend, not replace"

    def test_no_plugins_leaves_builtins_untouched(self):
        with patch.object(roles_mod, "get_extra_rbac_resources", return_value={}):
            merged = roles_mod.get_resources_map()

        assert merged == {res: list(actions) for res, actions in roles_mod.AVAILABLE_RESOURCES.items()}


# ── sync_superadmin_permissions: plugin permission is granted ───

class TestSyncGrantsPluginPermission:

    async def test_plugin_permission_is_inserted(self):
        conn = _make_conn(existing_perms=[("users", "view")])
        db = _make_db(conn)

        with patch("shared.database.db_service", db), \
             patch.object(roles_mod, "get_resources_map",
                          return_value={"users": ["view"], "myplugin": ["view"]}):
            await rbac_mod.sync_superadmin_permissions()

        assert ("myplugin", "view") in _inserted_pairs(conn)

    async def test_already_present_permission_is_not_reinserted(self):
        """Idempotency: a second pass over the same state must be a no-op."""
        conn = _make_conn(existing_perms=[("users", "view"), ("myplugin", "view")])
        db = _make_db(conn)

        with patch("shared.database.db_service", db), \
             patch.object(roles_mod, "get_resources_map",
                          return_value={"users": ["view"], "myplugin": ["view"]}):
            await rbac_mod.sync_superadmin_permissions()

        conn.execute.assert_not_awaited()

    async def test_missing_superadmin_role_is_survivable(self):
        conn = _make_conn(existing_perms=[], role_id=None)
        db = _make_db(conn)

        with patch("shared.database.db_service", db), \
             patch.object(roles_mod, "get_resources_map", return_value={"myplugin": ["view"]}):
            await rbac_mod.sync_superadmin_permissions()

        conn.execute.assert_not_awaited()

    async def test_disconnected_db_is_survivable(self):
        db = MagicMock()
        db.is_connected = False

        with patch("shared.database.db_service", db):
            await rbac_mod.sync_superadmin_permissions()

        db.acquire.assert_not_called()

    async def test_cache_is_invalidated_after_insert(self):
        """Without invalidation the fresh permission would not be visible until TTL."""
        conn = _make_conn(existing_perms=[])
        db = _make_db(conn)

        with patch("shared.database.db_service", db), \
             patch.object(roles_mod, "get_resources_map", return_value={"myplugin": ["view"]}), \
             patch.object(rbac_mod, "invalidate_cache") as inv:
            await rbac_mod.sync_superadmin_permissions()

        inv.assert_called_once()


# ── lifespan call order — the actual regression guard ───────────

class TestLifespanCallOrder:
    """The bug was purely an ordering one, so the order itself is what we pin down.

    Parsed from source rather than executed: lifespan drags in the whole startup
    chain (DB, entitlements, schedulers), and none of that is needed to answer
    the only question that matters — does the sync run after plugins register?
    """

    @staticmethod
    def _main_tree():
        main_py = Path(rbac_mod.__file__).resolve().parents[1] / "main.py"
        return ast.parse(main_py.read_text(encoding="utf-8"))

    @staticmethod
    def _sync_aliases(tree):
        """Local names bound to sync_superadmin_permissions, aliases included."""
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("core.rbac"):
                for alias in node.names:
                    if alias.name == "sync_superadmin_permissions":
                        names.add(alias.asname or alias.name)
        return names

    def test_sync_is_called_after_plugin_register(self):
        tree = self._main_tree()
        aliases = self._sync_aliases(tree)
        assert aliases, "sync_superadmin_permissions is not imported in main.py"

        register_lines = [
            n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "register"
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "plugin_loader"
        ]
        assert register_lines, "plugin_loader.register(app) call not found in main.py"

        sync_lines = [
            n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in aliases
        ]
        assert sync_lines, "sync_superadmin_permissions is never called in main.py"

        first_register = min(register_lines)
        assert any(line > first_register for line in sync_lines), (
            "sync_superadmin_permissions must run after plugin_loader.register(app), "
            "otherwise plugin RBAC resources are not in the map yet and the permission "
            "never reaches the superadmin role (issue #268)"
        )

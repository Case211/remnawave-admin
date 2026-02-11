"""Tests for RBAC — permission checking and AdminUser model."""
import pytest

from web.backend.api.deps import AdminUser, require_permission, require_superadmin
from web.backend.core.rbac import has_permission, invalidate_cache, _permissions_cache

from .conftest import (
    make_admin,
    SUPERADMIN_PERMISSIONS,
    VIEWER_PERMISSIONS,
    OPERATOR_PERMISSIONS,
    MANAGER_PERMISSIONS,
)


class TestAdminUserModel:
    """AdminUser.has_permission method."""

    def test_superadmin_has_all_permissions(self):
        admin = make_admin("superadmin")
        assert admin.has_permission("users", "view")
        assert admin.has_permission("users", "create")
        assert admin.has_permission("users", "edit")
        assert admin.has_permission("users", "delete")
        assert admin.has_permission("admins", "create")
        assert admin.has_permission("settings", "edit")
        assert admin.has_permission("automations", "delete")

    def test_viewer_has_only_view_permissions(self):
        admin = make_admin("viewer")
        assert admin.has_permission("users", "view")
        assert admin.has_permission("nodes", "view")
        assert not admin.has_permission("users", "create")
        assert not admin.has_permission("users", "edit")
        assert not admin.has_permission("users", "delete")
        assert not admin.has_permission("admins", "view")
        assert not admin.has_permission("settings", "edit")

    def test_operator_can_edit_but_not_create(self):
        admin = make_admin("operator")
        assert admin.has_permission("users", "view")
        assert admin.has_permission("users", "edit")
        assert not admin.has_permission("users", "create")
        assert not admin.has_permission("users", "delete")

    def test_manager_can_create_and_delete_users(self):
        admin = make_admin("manager")
        assert admin.has_permission("users", "create")
        assert admin.has_permission("users", "delete")
        assert not admin.has_permission("admins", "create")  # Only superadmin
        assert not admin.has_permission("roles", "edit")

    def test_custom_permissions(self):
        admin = make_admin(
            "custom",
            permissions={("users", "view"), ("nodes", "view")},
        )
        assert admin.has_permission("users", "view")
        assert admin.has_permission("nodes", "view")
        assert not admin.has_permission("users", "create")

    def test_empty_permissions(self):
        admin = make_admin("empty", permissions=set())
        assert not admin.has_permission("users", "view")


class TestRBACMatrix:
    """Test the full RBAC permission matrix — role × resource × action."""

    RESOURCES_ACTIONS = [
        ("users", "view"), ("users", "create"), ("users", "edit"), ("users", "delete"),
        ("nodes", "view"), ("nodes", "create"), ("nodes", "edit"), ("nodes", "delete"),
        ("hosts", "view"), ("hosts", "create"), ("hosts", "edit"), ("hosts", "delete"),
        ("violations", "view"), ("violations", "edit"),
        ("analytics", "view"),
        ("admins", "view"), ("admins", "create"), ("admins", "edit"), ("admins", "delete"),
        ("roles", "view"), ("roles", "create"), ("roles", "edit"), ("roles", "delete"),
        ("audit", "view"),
        ("settings", "view"), ("settings", "edit"),
        ("automations", "view"), ("automations", "create"), ("automations", "edit"), ("automations", "delete"),
        ("fleet", "view"),
        ("logs", "view"),
        ("bulk", "execute"),
    ]

    @pytest.mark.parametrize("resource,action", RESOURCES_ACTIONS)
    def test_superadmin_has_permission(self, resource, action):
        admin = make_admin("superadmin")
        assert admin.has_permission(resource, action), (
            f"Superadmin should have {resource}:{action}"
        )

    @pytest.mark.parametrize("resource,action", [
        ("users", "create"), ("users", "edit"), ("users", "delete"),
        ("nodes", "create"), ("nodes", "edit"), ("nodes", "delete"),
        ("hosts", "create"), ("hosts", "edit"), ("hosts", "delete"),
        ("admins", "view"), ("admins", "create"), ("admins", "edit"), ("admins", "delete"),
        ("roles", "view"), ("roles", "create"), ("roles", "edit"), ("roles", "delete"),
        ("settings", "view"), ("settings", "edit"),
        ("automations", "view"), ("automations", "create"), ("automations", "edit"), ("automations", "delete"),
        ("bulk", "execute"),
    ])
    def test_viewer_lacks_permission(self, resource, action):
        admin = make_admin("viewer")
        assert not admin.has_permission(resource, action), (
            f"Viewer should NOT have {resource}:{action}"
        )

    @pytest.mark.parametrize("resource,action", [
        ("users", "view"), ("nodes", "view"), ("hosts", "view"),
        ("violations", "view"), ("analytics", "view"),
        ("audit", "view"), ("fleet", "view"), ("logs", "view"),
    ])
    def test_viewer_has_view_permissions(self, resource, action):
        admin = make_admin("viewer")
        assert admin.has_permission(resource, action), (
            f"Viewer should have {resource}:{action}"
        )

    @pytest.mark.parametrize("resource,action", [
        ("admins", "create"), ("admins", "delete"),
        ("roles", "create"), ("roles", "edit"), ("roles", "delete"),
        ("settings", "edit"),
        ("automations", "delete"),
    ])
    def test_manager_lacks_admin_permissions(self, resource, action):
        admin = make_admin("manager")
        assert not admin.has_permission(resource, action), (
            f"Manager should NOT have {resource}:{action}"
        )

    @pytest.mark.parametrize("resource,action", [
        ("users", "view"), ("users", "create"), ("users", "edit"), ("users", "delete"),
        ("nodes", "view"), ("nodes", "create"), ("nodes", "edit"), ("nodes", "delete"),
        ("hosts", "view"), ("hosts", "create"), ("hosts", "edit"), ("hosts", "delete"),
        ("bulk", "execute"),
    ])
    def test_manager_has_resource_management(self, resource, action):
        admin = make_admin("manager")
        assert admin.has_permission(resource, action), (
            f"Manager should have {resource}:{action}"
        )


class TestPermissionCacheInvalidation:
    """Cache invalidation for RBAC permissions."""

    def test_invalidate_resets_timestamp(self):
        from web.backend.core.rbac import _cache_ts
        invalidate_cache()
        from web.backend.core import rbac
        assert rbac._cache_ts == 0

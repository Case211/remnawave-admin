"""Role management API endpoints."""
import json
import logging
from fastapi import APIRouter, HTTPException, Depends, Request

from web.backend.api.deps import (
    AdminUser,
    require_permission,
    get_client_ip,
)
from web.backend.core.rbac import (
    list_roles,
    get_role_by_id,
    get_role_by_name,
    create_role,
    update_role,
    delete_role,
    write_audit_log,
)
from web.backend.schemas.admin import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    PermissionItem,
)
from web.backend.schemas.common import SuccessResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# All available resources and their allowed actions
AVAILABLE_RESOURCES = {
    "users": ["view", "create", "edit", "delete"],
    "nodes": ["view", "create", "edit", "delete"],
    "hosts": ["view", "create", "edit", "delete"],
    "violations": ["view", "resolve"],
    "settings": ["view", "edit"],
    "analytics": ["view"],
    "admins": ["view", "create", "edit", "delete"],
    "roles": ["view", "create", "edit", "delete"],
    "audit": ["view"],
}


def _role_to_response(role: dict) -> RoleResponse:
    """Convert DB row to response model."""
    perms = role.get("permissions", [])
    return RoleResponse(
        id=role["id"],
        name=role["name"],
        display_name=role["display_name"],
        description=role.get("description"),
        is_system=role.get("is_system", False),
        permissions=[PermissionItem(**p) for p in perms],
        permissions_count=role.get("permissions_count", len(perms)),
        admins_count=role.get("admins_count"),
        created_at=role.get("created_at"),
    )


@router.get("", response_model=list[RoleResponse])
async def list_all_roles(
    admin: AdminUser = Depends(require_permission("roles", "view")),
):
    """List all roles with permission counts."""
    roles = await list_roles()
    result = []
    for r in roles:
        # Enrich with full permissions for each role
        full = await get_role_by_id(r["id"])
        if full:
            full["permissions_count"] = r.get("permissions_count", 0)
            full["admins_count"] = r.get("admins_count", 0)
            result.append(_role_to_response(full))
    return result


@router.get("/resources")
async def get_available_resources(
    admin: AdminUser = Depends(require_permission("roles", "view")),
):
    """Get all available resources and actions for the permission matrix."""
    return AVAILABLE_RESOURCES


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int,
    admin: AdminUser = Depends(require_permission("roles", "view")),
):
    """Get role with its permissions."""
    role = await get_role_by_id(role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return _role_to_response(role)


@router.post("", response_model=RoleResponse, status_code=201)
async def create_new_role(
    request: Request,
    data: RoleCreate,
    admin: AdminUser = Depends(require_permission("roles", "create")),
):
    """Create a new custom role."""
    # Check name uniqueness
    existing = await get_role_by_name(data.name)
    if existing:
        raise HTTPException(status_code=409, detail="Role name already exists")

    # Validate permissions
    for perm in data.permissions:
        if perm.resource not in AVAILABLE_RESOURCES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown resource: {perm.resource}",
            )
        if perm.action not in AVAILABLE_RESOURCES[perm.resource]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action '{perm.action}' for resource '{perm.resource}'",
            )

    role = await create_role(
        name=data.name,
        display_name=data.display_name,
        description=data.description,
        permissions=[p.model_dump() for p in data.permissions],
    )
    if not role:
        raise HTTPException(status_code=500, detail="Failed to create role")

    # Audit
    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="role.create",
        resource="roles",
        resource_id=str(role["id"]),
        details=json.dumps({"name": data.name}),
        ip_address=get_client_ip(request),
    )

    return _role_to_response(role)


@router.put("/{role_id}", response_model=RoleResponse)
async def update_existing_role(
    role_id: int,
    request: Request,
    data: RoleUpdate,
    admin: AdminUser = Depends(require_permission("roles", "edit")),
):
    """Update an existing role."""
    existing = await get_role_by_id(role_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Role not found")

    # Validate permissions if provided
    if data.permissions is not None:
        for perm in data.permissions:
            if perm.resource not in AVAILABLE_RESOURCES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown resource: {perm.resource}",
                )
            if perm.action not in AVAILABLE_RESOURCES[perm.resource]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid action '{perm.action}' for resource '{perm.resource}'",
                )

    role = await update_role(
        role_id=role_id,
        display_name=data.display_name,
        description=data.description,
        permissions=[p.model_dump() for p in data.permissions] if data.permissions is not None else None,
    )
    if not role:
        raise HTTPException(status_code=500, detail="Failed to update role")

    # Audit
    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="role.update",
        resource="roles",
        resource_id=str(role_id),
        ip_address=get_client_ip(request),
    )

    return _role_to_response(role)


@router.delete("/{role_id}", response_model=SuccessResponse)
async def delete_existing_role(
    role_id: int,
    request: Request,
    admin: AdminUser = Depends(require_permission("roles", "delete")),
):
    """Delete a custom role. System roles cannot be deleted."""
    existing = await get_role_by_id(role_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Role not found")

    if existing.get("is_system"):
        raise HTTPException(status_code=400, detail="Cannot delete system roles")

    success = await delete_role(role_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete role")

    # Audit
    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="role.delete",
        resource="roles",
        resource_id=str(role_id),
        details=json.dumps({"deleted_role": existing["name"]}),
        ip_address=get_client_ip(request),
    )

    return SuccessResponse(message="Role deleted")

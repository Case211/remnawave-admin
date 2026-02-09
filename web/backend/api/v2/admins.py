"""Admin account management API endpoints."""
import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Query

from web.backend.api.deps import (
    AdminUser,
    get_current_admin,
    require_permission,
    require_superadmin,
    get_client_ip,
)
from web.backend.core.rbac import (
    create_admin_account,
    update_admin_account,
    delete_admin_account,
    list_admin_accounts,
    get_admin_account_by_id,
    get_admin_account_by_username,
    get_role_by_id,
    write_audit_log,
    get_audit_logs,
)
from web.backend.core.admin_credentials import hash_password, validate_password_strength
from web.backend.schemas.admin import (
    AdminAccountCreate,
    AdminAccountUpdate,
    AdminAccountResponse,
    AdminAccountListResponse,
    AuditLogEntry,
    AuditLogResponse,
)
from web.backend.schemas.common import SuccessResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _account_to_response(account: dict) -> AdminAccountResponse:
    """Convert DB row to response model."""
    return AdminAccountResponse(
        id=account["id"],
        username=account["username"],
        telegram_id=account.get("telegram_id"),
        role_id=account.get("role_id"),
        role_name=account.get("role_name"),
        role_display_name=account.get("role_display_name"),
        max_users=account.get("max_users"),
        max_traffic_gb=account.get("max_traffic_gb"),
        max_nodes=account.get("max_nodes"),
        max_hosts=account.get("max_hosts"),
        users_created=account.get("users_created", 0),
        traffic_used_bytes=account.get("traffic_used_bytes", 0),
        nodes_created=account.get("nodes_created", 0),
        hosts_created=account.get("hosts_created", 0),
        is_active=account.get("is_active", True),
        is_generated_password=account.get("is_generated_password", False),
        created_by=account.get("created_by"),
        created_at=account.get("created_at"),
        updated_at=account.get("updated_at"),
    )


@router.get("", response_model=AdminAccountListResponse)
async def list_admins(
    admin: AdminUser = Depends(require_permission("admins", "view")),
):
    """List all admin accounts."""
    accounts = await list_admin_accounts()
    return AdminAccountListResponse(
        items=[_account_to_response(a) for a in accounts],
        total=len(accounts),
    )


@router.get("/{admin_id}", response_model=AdminAccountResponse)
async def get_admin(
    admin_id: int,
    admin: AdminUser = Depends(require_permission("admins", "view")),
):
    """Get admin account by ID."""
    account = await get_admin_account_by_id(admin_id)
    if not account:
        raise HTTPException(status_code=404, detail="Admin not found")
    return _account_to_response(account)


@router.post("", response_model=AdminAccountResponse, status_code=201)
async def create_admin(
    request: Request,
    data: AdminAccountCreate,
    admin: AdminUser = Depends(require_permission("admins", "create")),
):
    """Create a new admin account."""
    # Check role exists
    role = await get_role_by_id(data.role_id)
    if not role:
        raise HTTPException(status_code=400, detail="Role not found")

    # Check username uniqueness
    existing = await get_admin_account_by_username(data.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    # Hash password if provided
    pw_hash = None
    if data.password:
        is_strong, error = validate_password_strength(data.password)
        if not is_strong:
            raise HTTPException(status_code=400, detail=error)
        pw_hash = hash_password(data.password)

    account = await create_admin_account(
        username=data.username,
        password_hash=pw_hash,
        telegram_id=data.telegram_id,
        role_id=data.role_id,
        max_users=data.max_users,
        max_traffic_gb=data.max_traffic_gb,
        max_nodes=data.max_nodes,
        max_hosts=data.max_hosts,
        created_by=admin.account_id,
    )
    if not account:
        raise HTTPException(status_code=500, detail="Failed to create admin account")

    # Audit
    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="admin.create",
        resource="admins",
        resource_id=str(account["id"]),
        details=json.dumps({"username": data.username, "role_id": data.role_id}),
        ip_address=get_client_ip(request),
    )

    # Refetch with role join
    account = await get_admin_account_by_id(account["id"])
    return _account_to_response(account)


@router.put("/{admin_id}", response_model=AdminAccountResponse)
async def update_admin(
    admin_id: int,
    request: Request,
    data: AdminAccountUpdate,
    admin: AdminUser = Depends(require_permission("admins", "edit")),
):
    """Update an admin account."""
    existing = await get_admin_account_by_id(admin_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Admin not found")

    # Cannot edit own role / deactivate self
    if admin.account_id == admin_id:
        if data.role_id is not None and data.role_id != existing.get("role_id"):
            raise HTTPException(status_code=400, detail="Cannot change your own role")
        if data.is_active is not None and not data.is_active:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    fields = {}
    if data.username is not None:
        # Check uniqueness
        dup = await get_admin_account_by_username(data.username)
        if dup and dup["id"] != admin_id:
            raise HTTPException(status_code=409, detail="Username already exists")
        fields["username"] = data.username
    if data.telegram_id is not None:
        fields["telegram_id"] = data.telegram_id
    if data.role_id is not None:
        role = await get_role_by_id(data.role_id)
        if not role:
            raise HTTPException(status_code=400, detail="Role not found")
        fields["role_id"] = data.role_id
    if data.max_users is not None:
        fields["max_users"] = data.max_users
    if data.max_traffic_gb is not None:
        fields["max_traffic_gb"] = data.max_traffic_gb
    if data.max_nodes is not None:
        fields["max_nodes"] = data.max_nodes
    if data.max_hosts is not None:
        fields["max_hosts"] = data.max_hosts
    if data.is_active is not None:
        fields["is_active"] = data.is_active
    if data.password is not None:
        is_strong, error = validate_password_strength(data.password)
        if not is_strong:
            raise HTTPException(status_code=400, detail=error)
        fields["password_hash"] = hash_password(data.password)
        fields["is_generated_password"] = False

    updated = await update_admin_account(admin_id, **fields)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update admin account")

    # Audit
    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="admin.update",
        resource="admins",
        resource_id=str(admin_id),
        details=json.dumps({k: str(v) for k, v in fields.items() if k != "password_hash"}),
        ip_address=get_client_ip(request),
    )

    account = await get_admin_account_by_id(admin_id)
    return _account_to_response(account)


@router.delete("/{admin_id}", response_model=SuccessResponse)
async def delete_admin_endpoint(
    admin_id: int,
    request: Request,
    admin: AdminUser = Depends(require_permission("admins", "delete")),
):
    """Delete an admin account."""
    if admin.account_id == admin_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    existing = await get_admin_account_by_id(admin_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Admin not found")

    success = await delete_admin_account(admin_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete admin account")

    # Audit
    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="admin.delete",
        resource="admins",
        resource_id=str(admin_id),
        details=json.dumps({"deleted_username": existing["username"]}),
        ip_address=get_client_ip(request),
    )

    return SuccessResponse(message="Admin account deleted")


@router.get("/audit-log", response_model=AuditLogResponse)
async def get_audit_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    resource: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("audit", "view")),
):
    """Get audit log entries with optional filters."""
    logs, total = await get_audit_logs(
        limit=limit,
        offset=offset,
        admin_id=admin_id,
        action=action,
        resource=resource,
    )
    return AuditLogResponse(
        items=[AuditLogEntry(**log) for log in logs],
        total=total,
    )

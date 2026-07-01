"""Admin account management API endpoints."""
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Request, Query

from web.backend.core.errors import api_error, E
from web.backend.api.deps import (
    AdminUser,
    get_current_admin,
    require_permission,
    require_superadmin,
    get_client_ip,
)
from web.backend.core.admin_accounts import (
    create_admin_account,
    update_admin_account,
    delete_admin_account,
    list_admin_accounts,
    get_admin_account_by_id,
    get_admin_account_by_username,
    reset_admin_counter,
)
from web.backend.core.audit import write_audit_log, get_audit_logs
from web.backend.core.rbac import get_role_by_id
from web.backend.core.admin_credentials import hash_password, validate_password_strength
from web.backend.schemas.admin import (
    AdminAccountCreate,
    AdminAccountUpdate,
    AdminAccountResponse,
    AdminAccountListResponse,
    CounterResetRequest,
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
        email=account.get("email"),
        telegram_id=account.get("telegram_id"),
        role_id=account.get("role_id"),
        role_name=account.get("role_name"),
        role_display_name=account.get("role_display_name"),
        max_users=account.get("max_users"),
        max_traffic_gb=account.get("max_traffic_gb"),
        max_nodes=account.get("max_nodes"),
        max_hosts=account.get("max_hosts"),
        unlimited_traffic_policy=account.get("unlimited_traffic_policy", "allowed"),
        unrestricted_user_access=account.get("unrestricted_user_access", True),
        has_bot_access=account.get("has_bot_access", False),
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
    """List all admin accounts. Also allowed for unrestricted_user_access admins."""
    accounts = await list_admin_accounts()
    return AdminAccountListResponse(
        items=[_account_to_response(a) for a in accounts],
        total=len(accounts),
    )


@router.get("/me", response_model=AdminAccountListResponse)
async def list_admins_for_filter(
    admin: AdminUser = Depends(get_current_admin),
):
    """Lightweight admin list for filter dropdown (allowed for unrestricted_user_access)."""
    if not (admin.role == "superadmin" or getattr(admin, "unrestricted_user_access", False)):
        raise api_error(403, E.FORBIDDEN)
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
        raise api_error(404, E.ADMIN_NOT_FOUND)
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
        raise api_error(400, E.ROLE_NOT_FOUND)

    # Check username uniqueness
    existing = await get_admin_account_by_username(data.username)
    if existing:
        raise api_error(409, E.USERNAME_EXISTS)

    # Hash password if provided
    pw_hash = None
    if data.password:
        is_strong, error = validate_password_strength(data.password)
        if not is_strong:
            raise api_error(400, E.INVALID_PASSWORD, error)
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
        unlimited_traffic_policy=data.unlimited_traffic_policy,
        unrestricted_user_access=data.unrestricted_user_access,
        has_bot_access=data.has_bot_access,
        is_generated_password=bool(pw_hash),
        created_by=admin.account_id,
        email=data.email,
    )
    if not account:
        raise api_error(500, E.ADMIN_CREATE_FAILED)

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
        raise api_error(404, E.ADMIN_NOT_FOUND)

    # Cannot edit own role / deactivate self
    if admin.account_id == admin_id:
        # model_fields_set catches an explicit null too — otherwise a null role_id
        # (e.g. frontend sending NaN→null) would slip past and blank out the role,
        # silently demoting the only superadmin to a roleless "admin".
        if "role_id" in data.model_fields_set and data.role_id != existing.get("role_id"):
            raise api_error(400, E.CANNOT_MODIFY_SELF, "Cannot change your own role")
        if data.is_active is not None and not data.is_active:
            raise api_error(400, E.CANNOT_MODIFY_SELF, "Cannot deactivate yourself")

    fields = {}
    if data.username is not None:
        # Check uniqueness
        dup = await get_admin_account_by_username(data.username)
        if dup and dup["id"] != admin_id:
            raise api_error(409, E.USERNAME_EXISTS)
        fields["username"] = data.username
    if data.telegram_id is not None or "telegram_id" in data.model_fields_set:
        # Use model_fields_set to distinguish "not provided" from "explicitly null"
        # so the frontend can clear an existing value by sending null.
        if data.telegram_id is not None and not (1 <= data.telegram_id <= 9_999_999_999):
            raise api_error(400, E.INVALID_TELEGRAM_ID)
        fields["telegram_id"] = data.telegram_id
    if data.role_id is not None or "role_id" in data.model_fields_set:
        # role_id must never be cleared — an admin without a role loses all RBAC
        # resolution (deps.py falls back to "admin"), which would silently strip a
        # superadmin of their rights. Reject an explicit null outright.
        if data.role_id is None:
            raise api_error(400, E.ROLE_NOT_FOUND, "role_id cannot be cleared")
        role = await get_role_by_id(data.role_id)
        if not role:
            raise api_error(400, E.ROLE_NOT_FOUND)
        fields["role_id"] = data.role_id
    # For numeric quota fields, accept null as "clear" (set to NULL → unlimited).
    if data.max_users is not None or "max_users" in data.model_fields_set:
        if data.max_users is not None and data.max_users < 0:
            raise api_error(400, E.INVALID_INPUT, "max_users must be >= 0")
        fields["max_users"] = data.max_users
    if data.max_traffic_gb is not None or "max_traffic_gb" in data.model_fields_set:
        if data.max_traffic_gb is not None and data.max_traffic_gb < 0:
            raise api_error(400, E.INVALID_INPUT, "max_traffic_gb must be >= 0")
        fields["max_traffic_gb"] = data.max_traffic_gb
    if data.max_nodes is not None or "max_nodes" in data.model_fields_set:
        if data.max_nodes is not None and data.max_nodes < 0:
            raise api_error(400, E.INVALID_INPUT, "max_nodes must be >= 0")
        fields["max_nodes"] = data.max_nodes
    if data.max_hosts is not None or "max_hosts" in data.model_fields_set:
        if data.max_hosts is not None and data.max_hosts < 0:
            raise api_error(400, E.INVALID_INPUT, "max_hosts must be >= 0")
        fields["max_hosts"] = data.max_hosts
    if data.is_active is not None:
        fields["is_active"] = data.is_active
    if data.email is not None or "email" in data.model_fields_set:
        fields["email"] = data.email or None
    if data.unlimited_traffic_policy is not None:
        if data.unlimited_traffic_policy not in ("allowed", "disabled", "enforced"):
            raise api_error(400, E.INVALID_INPUT, "Policy must be one of: allowed, disabled, enforced")
        fields["unlimited_traffic_policy"] = data.unlimited_traffic_policy
    if data.unrestricted_user_access is not None:
        fields["unrestricted_user_access"] = data.unrestricted_user_access
    if data.has_bot_access is not None:
        fields["has_bot_access"] = data.has_bot_access
    if data.password is not None:
        is_strong, error = validate_password_strength(data.password)
        if not is_strong:
            raise api_error(400, E.INVALID_PASSWORD, error)
        fields["password_hash"] = hash_password(data.password)
        fields["is_generated_password"] = False

    updated = await update_admin_account(admin_id, **fields)
    if not updated:
        raise api_error(500, E.ADMIN_UPDATE_FAILED)

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
        raise api_error(400, E.CANNOT_MODIFY_SELF, "Cannot delete yourself")

    existing = await get_admin_account_by_id(admin_id)
    if not existing:
        raise api_error(404, E.ADMIN_NOT_FOUND)

    success = await delete_admin_account(admin_id)
    if not success:
        raise api_error(500, E.ADMIN_DELETE_FAILED)

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


@router.post("/{admin_id}/counters/reset", response_model=AdminAccountResponse)
async def reset_admin_counter_endpoint(
    admin_id: int,
    request: Request,
    data: CounterResetRequest,
    admin: AdminUser = Depends(require_permission("admins", "edit")),
):
    """Reset a specific usage counter for an admin account."""
    valid_counters = ("users_created", "nodes_created", "hosts_created", "traffic_used_bytes")
    if data.counter not in valid_counters:
        raise api_error(400, E.INVALID_INPUT, f"counter must be one of: {', '.join(valid_counters)}")

    existing = await get_admin_account_by_id(admin_id)
    if not existing:
        raise api_error(404, E.ADMIN_NOT_FOUND)

    updated = await reset_admin_counter(admin_id, data.counter)
    if not updated:
        raise api_error(500, E.INVALID_INPUT, "Failed to reset counter")

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="admin.counter_reset",
        resource="admins",
        resource_id=str(admin_id),
        details=json.dumps({"counter": data.counter, "target_username": existing.get("username")}),
        ip_address=get_client_ip(request),
    )

    return _account_to_response(updated)


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

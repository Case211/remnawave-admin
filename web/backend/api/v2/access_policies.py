"""Access policies API — manage scope templates for admin rights.

Policies whitelist specific nodes/hosts/squads (by uuid or tag) with a set
of allowed actions (view/edit/delete). Policies can be attached to roles
(inherited by all admins with that role) or to individual admins.

Resolution: see web/backend/core/rbac.get_scope.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from web.backend.api.deps import AdminUser, require_permission, get_client_ip
from web.backend.core.errors import api_error, E
from web.backend.core.rbac import write_audit_log, invalidate_scope_cache

logger = logging.getLogger(__name__)
router = APIRouter()


VALID_RESOURCE_TYPES = {"node", "host", "squad"}
VALID_SCOPE_TYPES = {"uuid", "tag"}
VALID_ACTIONS = {"view", "edit", "delete"}


class RuleIn(BaseModel):
    resource_type: str = Field(..., description="node | host | squad")
    scope_type: str = Field(..., description="uuid | tag")
    scope_value: str = Field(..., min_length=1, max_length=200)
    actions: List[str] = Field(default_factory=lambda: ["view"])


class RuleOut(RuleIn):
    id: Optional[int] = None


class PolicyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    rules: List[RuleIn] = Field(default_factory=list)


class PolicyUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    rules: Optional[List[RuleIn]] = None


class PolicyListItem(BaseModel):
    id: int
    name: str
    description: Optional[str]
    rules_count: int
    roles_count: int
    admins_count: int


class PolicyDetail(BaseModel):
    id: int
    name: str
    description: Optional[str]
    rules: List[RuleOut]
    role_ids: List[int]
    admin_ids: List[int]


class AttachPoliciesRequest(BaseModel):
    policy_ids: List[int] = Field(default_factory=list)


def _validate_rules(rules: List[RuleIn]) -> None:
    for r in rules:
        if r.resource_type not in VALID_RESOURCE_TYPES:
            raise api_error(400, E.VALIDATION, f"Unknown resource_type: {r.resource_type}")
        if r.scope_type not in VALID_SCOPE_TYPES:
            raise api_error(400, E.VALIDATION, f"Unknown scope_type: {r.scope_type}")
        bad = [a for a in r.actions if a not in VALID_ACTIONS]
        if bad:
            raise api_error(400, E.VALIDATION, f"Unknown actions: {bad}")
        if not r.actions:
            raise api_error(400, E.VALIDATION, "Rule must have at least one action")


@router.get("", response_model=List[PolicyListItem])
async def list_policies(
    admin: AdminUser = Depends(require_permission("access_policies", "view")),
):
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)
    items = await db_service.list_access_policies()
    return [PolicyListItem(**it) for it in items]


@router.post("", response_model=PolicyDetail)
async def create_policy(
    body: PolicyIn,
    request: Request,
    admin: AdminUser = Depends(require_permission("access_policies", "create")),
):
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)
    _validate_rules(body.rules)
    try:
        policy_id = await db_service.create_access_policy(
            name=body.name, description=body.description,
            created_by=admin.account_id,
            rules=[r.model_dump() for r in body.rules],
        )
    except Exception as e:
        if "uq_access_policies_name" in str(e):
            raise api_error(409, E.ALREADY_EXISTS, "Policy with this name already exists")
        raise
    invalidate_scope_cache()
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username or "system",
        action="access_policy.create", resource="access_policies",
        resource_id=str(policy_id), details=f"name={body.name}",
        ip_address=get_client_ip(request),
    )
    return await _detail(policy_id)


@router.get("/{policy_id}", response_model=PolicyDetail)
async def get_policy(
    policy_id: int,
    admin: AdminUser = Depends(require_permission("access_policies", "view")),
):
    return await _detail(policy_id)


@router.patch("/{policy_id}", response_model=PolicyDetail)
async def update_policy(
    policy_id: int,
    body: PolicyUpdate,
    request: Request,
    admin: AdminUser = Depends(require_permission("access_policies", "edit")),
):
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)
    if body.rules is not None:
        _validate_rules(body.rules)
    existing = await db_service.get_access_policy(policy_id)
    if not existing:
        raise api_error(404, E.NOT_FOUND)
    await db_service.update_access_policy(
        policy_id=policy_id, name=body.name, description=body.description,
        rules=[r.model_dump() for r in body.rules] if body.rules is not None else None,
    )
    invalidate_scope_cache()
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username or "system",
        action="access_policy.update", resource="access_policies",
        resource_id=str(policy_id), details=f"name={body.name or existing['name']}",
        ip_address=get_client_ip(request),
    )
    return await _detail(policy_id)


@router.delete("/{policy_id}")
async def delete_policy(
    policy_id: int,
    request: Request,
    admin: AdminUser = Depends(require_permission("access_policies", "delete")),
):
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)
    existing = await db_service.get_access_policy(policy_id)
    if not existing:
        raise api_error(404, E.NOT_FOUND)
    await db_service.delete_access_policy(policy_id)
    invalidate_scope_cache()
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username or "system",
        action="access_policy.delete", resource="access_policies",
        resource_id=str(policy_id), details=f"name={existing['name']}",
        ip_address=get_client_ip(request),
    )
    return {"success": True}


@router.post("/_roles/{role_id}/attach")
async def attach_policies_to_role(
    role_id: int,
    body: AttachPoliciesRequest,
    request: Request,
    admin: AdminUser = Depends(require_permission("access_policies", "edit")),
):
    from shared.database import db_service
    await db_service.set_role_policies(role_id, body.policy_ids)
    invalidate_scope_cache()
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username or "system",
        action="access_policy.attach_role", resource="access_policies",
        resource_id=str(role_id), details=f"policy_ids={body.policy_ids}",
        ip_address=get_client_ip(request),
    )
    return {"success": True}


@router.post("/_admins/{admin_id}/attach")
async def attach_policies_to_admin(
    admin_id: int,
    body: AttachPoliciesRequest,
    request: Request,
    admin: AdminUser = Depends(require_permission("access_policies", "edit")),
):
    from shared.database import db_service
    await db_service.set_admin_policies(admin_id, body.policy_ids)
    invalidate_scope_cache()
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username or "system",
        action="access_policy.attach_admin", resource="access_policies",
        resource_id=str(admin_id), details=f"policy_ids={body.policy_ids}",
        ip_address=get_client_ip(request),
    )
    return {"success": True}


async def _detail(policy_id: int) -> PolicyDetail:
    from shared.database import db_service
    policy = await db_service.get_access_policy(policy_id)
    if not policy:
        raise api_error(404, E.NOT_FOUND)
    return PolicyDetail(
        id=policy["id"], name=policy["name"], description=policy.get("description"),
        rules=[RuleOut(**r) for r in policy.get("rules", [])],
        role_ids=policy.get("role_ids", []),
        admin_ids=policy.get("admin_ids", []),
    )

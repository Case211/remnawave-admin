"""Automation management API endpoints."""
import json
import logging
import math
from typing import Optional, List

from fastapi import APIRouter, Depends, Request, Query

from web.backend.core.errors import api_error, E

from web.backend.api.deps import (
    AdminUser,
    require_permission,
    get_client_ip,
)
from web.backend.core.rbac import write_audit_log
from web.backend.core.automation import (
    list_automation_rules,
    get_automation_rule_by_id,
    get_automation_rules_stats,
    create_automation_rule,
    update_automation_rule,
    toggle_automation_rule,
    delete_automation_rule,
    get_automation_logs,
    AUTOMATION_TEMPLATES,
)
from web.backend.core.automation_engine import engine as automation_engine
from web.backend.schemas.automation import (
    AutomationRuleCreate,
    AutomationRuleUpdate,
    AutomationRuleResponse,
    AutomationRuleListResponse,
    AutomationLogEntry,
    AutomationLogResponse,
    AutomationTemplate,
    AutomationTestResult,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _rule_to_response(rule: dict) -> AutomationRuleResponse:
    """Convert a DB row dict to response model."""
    trigger_config = rule.get("trigger_config", {})
    if isinstance(trigger_config, str):
        trigger_config = json.loads(trigger_config)
    conditions = rule.get("conditions", [])
    if isinstance(conditions, str):
        conditions = json.loads(conditions)
    action_config = rule.get("action_config", {})
    if isinstance(action_config, str):
        action_config = json.loads(action_config)

    return AutomationRuleResponse(
        id=rule["id"],
        name=rule["name"],
        description=rule.get("description"),
        is_enabled=rule["is_enabled"],
        category=rule["category"],
        trigger_type=rule["trigger_type"],
        trigger_config=trigger_config,
        conditions=conditions,
        action_type=rule["action_type"],
        action_config=action_config,
        last_triggered_at=rule.get("last_triggered_at"),
        trigger_count=rule.get("trigger_count", 0),
        created_by=rule.get("created_by"),
        created_at=rule.get("created_at"),
        updated_at=rule.get("updated_at"),
    )


def _log_to_entry(row: dict) -> AutomationLogEntry:
    """Convert a DB row dict to log entry model."""
    details = row.get("details")
    if isinstance(details, str):
        details = json.loads(details)
    return AutomationLogEntry(
        id=row["id"],
        rule_id=row["rule_id"],
        rule_name=row.get("rule_name"),
        triggered_at=row.get("triggered_at"),
        target_type=row.get("target_type"),
        target_id=row.get("target_id"),
        action_taken=row["action_taken"],
        result=row["result"],
        details=details,
    )


# ── List rules ───────────────────────────────────────────────

@router.get("", response_model=AutomationRuleListResponse)
async def list_automations(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    trigger_type: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    admin: AdminUser = Depends(require_permission("automation", "view")),
):
    """List automation rules with pagination and filtering."""
    items, total = await list_automation_rules(
        page=page,
        per_page=per_page,
        category=category,
        trigger_type=trigger_type,
        is_enabled=is_enabled,
    )
    stats = await get_automation_rules_stats()
    pages = max(1, math.ceil(total / per_page))
    return AutomationRuleListResponse(
        items=[_rule_to_response(r) for r in items],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
        total_active=stats["total_active"],
        total_triggers=stats["total_triggers"],
    )


# ── Create rule ──────────────────────────────────────────────

@router.post("", response_model=AutomationRuleResponse, status_code=201)
async def create_automation(
    request: Request,
    data: AutomationRuleCreate,
    admin: AdminUser = Depends(require_permission("automation", "create")),
):
    """Create a new automation rule."""
    rule = await create_automation_rule(
        name=data.name,
        description=data.description,
        is_enabled=data.is_enabled,
        category=data.category,
        trigger_type=data.trigger_type,
        trigger_config=data.trigger_config,
        conditions=data.conditions,
        action_type=data.action_type,
        action_config=data.action_config,
        created_by=admin.account_id,
    )
    if not rule:
        raise api_error(500, E.AUTOMATION_CREATE_FAILED)

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="automation.create",
        resource="automation",
        resource_id=str(rule["id"]),
        details=json.dumps({"name": data.name, "action_type": data.action_type}),
        ip_address=get_client_ip(request),
    )

    return _rule_to_response(rule)


# ── Templates (before /{rule_id} to avoid path conflict) ─────

@router.get("/templates", response_model=List[AutomationTemplate])
async def list_templates(
    admin: AdminUser = Depends(require_permission("automation", "view")),
):
    """List pre-built automation templates."""
    return [AutomationTemplate(**t) for t in AUTOMATION_TEMPLATES]


@router.post("/templates/{template_id}/activate", response_model=AutomationRuleResponse)
async def activate_template(
    template_id: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("automation", "create")),
):
    """Create a new automation rule from a template."""
    template = next((t for t in AUTOMATION_TEMPLATES if t["id"] == template_id), None)
    if not template:
        raise api_error(404, E.TEMPLATE_NOT_FOUND)

    rule = await create_automation_rule(
        name=template["name"],
        description=template["description"],
        is_enabled=True,
        category=template["category"],
        trigger_type=template["trigger_type"],
        trigger_config=template["trigger_config"],
        conditions=template["conditions"],
        action_type=template["action_type"],
        action_config=template["action_config"],
        created_by=admin.account_id,
    )
    if not rule:
        raise api_error(500, E.AUTOMATION_ACTIVATE_FAILED)

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="automation.template_activate",
        resource="automation",
        resource_id=str(rule["id"]),
        details=json.dumps({"template_id": template_id, "name": template["name"]}),
        ip_address=get_client_ip(request),
    )

    return _rule_to_response(rule)


# ── Logs (before /{rule_id} to avoid path conflict) ──────────

@router.get("/log", response_model=AutomationLogResponse)
async def get_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    cursor: Optional[int] = Query(None, description="Cursor (last seen log ID) for efficient pagination"),
    rule_id: Optional[int] = None,
    result: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    admin: AdminUser = Depends(require_permission("automation", "view")),
):
    """Get automation trigger log with filtering.

    Supports cursor-based pagination: ?cursor=123&per_page=50
    """
    items, total = await get_automation_logs(
        page=page,
        per_page=per_page,
        rule_id=rule_id,
        result=result,
        date_from=date_from,
        date_to=date_to,
        cursor=cursor,
    )
    pages = max(1, math.ceil(total / per_page))

    # Compute next_cursor
    next_cursor = None
    if items and len(items) == per_page:
        last_id = items[-1].get("id")
        if last_id is not None:
            next_cursor = last_id

    resp = AutomationLogResponse(
        items=[_log_to_entry(r) for r in items],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )
    # Attach next_cursor to response dict (extend model response)
    result_dict = resp.model_dump()
    result_dict["next_cursor"] = next_cursor
    return result_dict


# ── Get single rule ──────────────────────────────────────────

@router.get("/{rule_id}", response_model=AutomationRuleResponse)
async def get_automation(
    rule_id: int,
    admin: AdminUser = Depends(require_permission("automation", "view")),
):
    """Get automation rule details."""
    rule = await get_automation_rule_by_id(rule_id)
    if not rule:
        raise api_error(404, E.AUTOMATION_NOT_FOUND)
    return _rule_to_response(rule)


# ── Update rule ──────────────────────────────────────────────

@router.put("/{rule_id}", response_model=AutomationRuleResponse)
async def update_automation(
    rule_id: int,
    request: Request,
    data: AutomationRuleUpdate,
    admin: AdminUser = Depends(require_permission("automation", "edit")),
):
    """Update an automation rule."""
    existing = await get_automation_rule_by_id(rule_id)
    if not existing:
        raise api_error(404, E.AUTOMATION_NOT_FOUND)

    fields = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not fields:
        return _rule_to_response(existing)

    rule = await update_automation_rule(rule_id, **fields)
    if not rule:
        raise api_error(500, E.AUTOMATION_UPDATE_FAILED)

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="automation.update",
        resource="automation",
        resource_id=str(rule_id),
        details=json.dumps({"updated_fields": list(fields.keys())}),
        ip_address=get_client_ip(request),
    )

    return _rule_to_response(rule)


# ── Toggle rule ──────────────────────────────────────────────

@router.patch("/{rule_id}/toggle", response_model=AutomationRuleResponse)
async def toggle_automation(
    rule_id: int,
    request: Request,
    admin: AdminUser = Depends(require_permission("automation", "edit")),
):
    """Toggle automation rule enabled/disabled."""
    existing = await get_automation_rule_by_id(rule_id)
    if not existing:
        raise api_error(404, E.AUTOMATION_NOT_FOUND)

    rule = await toggle_automation_rule(rule_id)
    if not rule:
        raise api_error(500, E.AUTOMATION_TOGGLE_FAILED)

    new_state = "enabled" if rule["is_enabled"] else "disabled"
    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="automation.toggle",
        resource="automation",
        resource_id=str(rule_id),
        details=json.dumps({"name": rule["name"], "new_state": new_state}),
        ip_address=get_client_ip(request),
    )

    return _rule_to_response(rule)


# ── Delete rule ──────────────────────────────────────────────

@router.delete("/{rule_id}")
async def delete_automation(
    rule_id: int,
    request: Request,
    admin: AdminUser = Depends(require_permission("automation", "delete")),
):
    """Delete an automation rule."""
    existing = await get_automation_rule_by_id(rule_id)
    if not existing:
        raise api_error(404, E.AUTOMATION_NOT_FOUND)

    success = await delete_automation_rule(rule_id)
    if not success:
        raise api_error(500, E.AUTOMATION_DELETE_FAILED)

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="automation.delete",
        resource="automation",
        resource_id=str(rule_id),
        details=json.dumps({"name": existing["name"]}),
        ip_address=get_client_ip(request),
    )

    return {"status": "ok", "message": "Automation rule deleted"}


# ── Test / Dry-run ───────────────────────────────────────────

@router.post("/{rule_id}/test", response_model=AutomationTestResult)
async def test_automation(
    rule_id: int,
    admin: AdminUser = Depends(require_permission("automation", "run")),
):
    """Run a dry-run test of an automation rule without side effects."""
    existing = await get_automation_rule_by_id(rule_id)
    if not existing:
        raise api_error(404, E.AUTOMATION_NOT_FOUND)

    result = await automation_engine.dry_run(rule_id)
    return AutomationTestResult(**result)

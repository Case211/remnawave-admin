"""Operator API for the delayed-enforcement workflow."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from shared.config_service import config_service
from shared.database import db_service
from web.backend.api.deps import AdminUser, get_client_ip, require_permission
from web.backend.core.audit import write_audit_log
from web.backend.core.enforcement_workflow import (
    ACTIVE_STATUSES,
    _matches_policy,
    pilot_user_uuids,
    process_case,
)


router = APIRouter()


class CaseAction(BaseModel):
    action: str
    confirm: bool = False


def _get(key: str, default):
    return config_service.get(f"enforcement_{key}", default)


async def _find_user(identifier: str) -> dict:
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            "SELECT uuid::text AS uuid, username, email, telegram_id, status, tag FROM users "
            "WHERE uuid::text=$1 OR LOWER(username)=LOWER($1) "
            "OR LOWER(COALESCE(email,''))=LOWER($1) OR telegram_id::text=$1 LIMIT 2",
            identifier.strip(),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="User not found")
    if len(rows) != 1:
        raise HTTPException(status_code=409, detail="User identity is ambiguous")
    return dict(rows[0])


@router.get("/status")
async def status(_: AdminUser = Depends(require_permission("violations", "view"))) -> dict:
    pilot = pilot_user_uuids()
    pilot_values = sorted(pilot or [])
    counts: dict[str, int] = {}
    pilot_users: list[dict] = []
    if db_service.is_connected:
        async with db_service.acquire() as conn:
            rows = await conn.fetch("SELECT status, COUNT(*) count FROM enforcement_cases GROUP BY status")
            counts = {str(row["status"]): int(row["count"]) for row in rows}
            if pilot_values:
                rows = await conn.fetch(
                    "SELECT uuid::text uuid, username, status, tag FROM users "
                    "WHERE uuid=ANY($1::uuid[]) ORDER BY username", pilot_values,
                )
                pilot_users = [dict(row) for row in rows]
    return {
        "enabled": bool(_get("enabled", False)), "mode": str(_get("mode", "dry_run")),
        "scope": str(_get("scope", "trial_only")),
        "grace_hours": int(_get("grace_hours", 12) or 12),
        "min_score": float(_get("min_score", 0) or 0),
        "final_action": str(_get("final_action", "manual_review")),
        "notice_suffix": str(_get("notice_suffix", "") or ""),
        "pause_for_support": bool(_get("pause_for_support", True)),
        "delivery_failure": str(_get("delivery_failure", "manual_review")),
        "delivery_attempts": int(_get("delivery_attempts", 3) or 3),
        "throttle_kbit": int(_get("throttle_kbit", 1024) or 1024),
        "throttle_hours": int(_get("throttle_hours", 0) or 0),
        "pilot_config_valid": pilot is not None, "pilot_user_uuids": pilot_values,
        "pilot_users": pilot_users, "case_counts": counts,
    }


@router.get("/simulate")
async def simulate(
    user: str = Query(..., min_length=1, max_length=320),
    _: AdminUser = Depends(require_permission("violations", "view")),
) -> dict:
    target = await _find_user(user)
    pilot = pilot_user_uuids()
    async with db_service.acquire() as conn:
        violation = await conn.fetchrow(
            "SELECT * FROM violations WHERE user_uuid=$1::uuid AND action_taken IS NULL "
            "ORDER BY detected_at DESC LIMIT 1", target["uuid"],
        )
    reasons = list(violation["reasons"] or []) if violation else []
    raw = dict(violation.get("raw_breakdown") or {}) if violation else {}
    breakdown = raw.get("breakdown") if isinstance(raw.get("breakdown"), dict) else raw
    signals: list[dict] = []
    hwid = breakdown.get("hwid") if isinstance(breakdown, dict) else None
    if isinstance(hwid, dict) and hwid.get("active_trial_abuse_detected"):
        signals.append({"code": "hwid.active_trial_accounts"})
    if isinstance(hwid, dict) and hwid.get("repeated_trial_abuse_detected"):
        signals.append({"code": "hwid.repeated_trial_subscription"})
    matches, signal = _matches_policy(signals, violation.get("recommended_action") if violation else None)
    in_pilot = bool(pilot and target["uuid"].lower() in pilot)
    score_ok = bool(violation and float(violation.get("score") or 0) >= float(_get("min_score", 0) or 0))
    eligible = bool(_get("enabled", False) and violation and matches and score_ok and pilot is not None and (not pilot or in_pilot))
    return {
        "user": target, "violation_id": int(violation["id"]) if violation else None,
        "signal": signal or None, "reasons": reasons[:10], "eligible": eligible,
        "in_pilot": in_pilot, "mode": str(_get("mode", "dry_run")),
        "final_action": str(_get("final_action", "manual_review")),
        "grace_hours": int(_get("grace_hours", 12) or 12),
        "would_send_notice": eligible and str(_get("mode", "dry_run")) != "dry_run",
        "would_apply_action": eligible and str(_get("mode", "dry_run")) == "enforce",
    }


@router.get("/cases")
async def cases(
    limit: int = Query(50, ge=1, le=200),
    _: AdminUser = Depends(require_permission("violations", "view")),
) -> dict:
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            "SELECT c.*, u.username, u.email FROM enforcement_cases c "
            "LEFT JOIN users u ON u.uuid=c.user_uuid ORDER BY c.created_at DESC LIMIT $1", limit,
        )
    return {"items": [dict(row) for row in rows]}


@router.post("/cases/{case_id}/action")
async def case_action(
    case_id: int, body: CaseAction, request: Request,
    admin: AdminUser = Depends(require_permission("violations", "resolve")),
) -> dict:
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Explicit confirmation is required")
    if body.action not in {"run_now", "manual_review", "cancel"}:
        raise HTTPException(status_code=400, detail="Unknown action")
    async with db_service.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM enforcement_cases WHERE id=$1", case_id)
    if not row:
        raise HTTPException(status_code=404, detail="Case not found")
    case = dict(row)
    if body.action == "run_now":
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE enforcement_cases SET status='due', deadline_at=NOW(), updated_at=NOW() "
                "WHERE id=$1 AND status IN ('grace_period','paused_for_support','manual_review') RETURNING *",
                case_id,
            )
        if not row:
            raise HTTPException(status_code=409, detail="Case cannot be run from its current state")
        await process_case(dict(row))
    else:
        status = "manual_review" if body.action == "manual_review" else "cancelled"
        async with db_service.acquire() as conn:
            changed = await conn.fetchval(
                "UPDATE enforcement_cases SET status=$2, resolution=$3, resolved_at=NOW(), "
                "updated_at=NOW() WHERE id=$1 AND status=ANY($4::text[]) RETURNING id",
                case_id, status, f"operator_{body.action}", list(ACTIVE_STATUSES),
            )
        if not changed:
            raise HTTPException(status_code=409, detail="Case is already final")
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action=f"enforcement.{body.action}", resource="violations", resource_id=str(case_id),
        details=json.dumps({"case_id": case_id}), ip_address=get_client_ip(request),
    )
    return {"success": True, "case_id": case_id, "action": body.action}

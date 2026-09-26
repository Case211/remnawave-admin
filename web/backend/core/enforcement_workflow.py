"""Durable warning, grace-period and delayed-enforcement workflow."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from shared.config_service import config_service
from shared.database import db_service


logger = logging.getLogger(__name__)
TRIAL_SIGNALS = {"hwid.active_trial_accounts", "hwid.repeated_trial_subscription"}
ACTIVE_STATUSES = (
    "pending_notice", "notifying", "grace_period", "due",
)


def _setting(key: str, default: Any) -> Any:
    return config_service.get(f"enforcement_{key}", default)


def pilot_user_uuids() -> set[str] | None:
    value = _setting("pilot_user_uuids", []) or []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            logger.error("Invalid JSON in enforcement_pilot_user_uuids; workflow fails closed")
            return None
    if not isinstance(value, list):
        return None
    return {str(item).strip().lower() for item in value if str(item).strip()}


def _matches_policy(signals: list[dict[str, Any]], recommended_action: str | None) -> tuple[bool, str]:
    trial = next((s for s in signals if s.get("code") in TRIAL_SIGNALS), None)
    scope = str(_setting("scope", "trial_only"))
    if trial:
        return True, str(trial["code"])
    if scope == "all_hard_blocks" and recommended_action == "hard_block":
        return True, "violation.hard_block"
    return False, ""


async def create_enforcement_case(
    *,
    violation_id: int,
    user_uuid: str,
    signals: list[dict[str, Any]],
    recommended_action: str | None = None,
    score: float | None = None,
    reasons: list[str] | None = None,
    **_: Any,
) -> bool:
    """Persist a policy snapshot and return whether the immediate action is deferred."""
    if not _setting("enabled", False):
        return False
    matches, signal_code = _matches_policy(signals, recommended_action)
    if not matches:
        return False
    if score is not None and float(score) < float(_setting("min_score", 0) or 0):
        return False

    pilot = pilot_user_uuids()
    if pilot is None or (pilot and user_uuid.lower() not in pilot):
        return False

    mode = str(_setting("mode", "dry_run"))
    if mode not in {"dry_run", "deliver_only", "enforce"}:
        mode = "dry_run"
    action = str(_setting("final_action", "manual_review"))
    if action not in {"manual_review", "disable", "throttle", "none"}:
        action = "manual_review"
    grace_hours = max(1, min(720, int(_setting("grace_hours", 12) or 12)))
    max_attempts = max(1, min(20, int(_setting("delivery_attempts", 3) or 3)))
    pause_for_support = bool(_setting("pause_for_support", True))
    status = "dry_run" if mode == "dry_run" else "pending_notice"
    resolution = "simulated" if mode == "dry_run" else None
    snapshot = {
        "mode": mode,
        "final_action": action,
        "grace_hours": grace_hours,
        "delivery_attempts": max_attempts,
        "delivery_failure": str(_setting("delivery_failure", "manual_review")),
        "pause_for_support": pause_for_support,
        "throttle_kbit": int(_setting("throttle_kbit", 1024) or 1024),
        "throttle_hours": max(0, int(_setting("throttle_hours", 0) or 0)),
    }
    metadata = {"reasons": reasons or [], "recommended_action": recommended_action}

    async with db_service.acquire() as conn:
        await conn.execute(
            "INSERT INTO enforcement_cases "
            "(violation_id, user_uuid, signal_code, status, mode, final_action, deadline_at, "
            "resolution, policy_snapshot, metadata) VALUES "
            "($1, $2::uuid, $3, $4, $5, $6, NOW() + ($7 * INTERVAL '1 hour'), "
            "$8, $9::jsonb, $10::jsonb) "
            "ON CONFLICT (violation_id, user_uuid, signal_code) DO NOTHING",
            violation_id, user_uuid, signal_code, status, mode, action, grace_hours,
            resolution, json.dumps(snapshot), json.dumps(metadata),
        )
    # Even dry-run must suppress the old immediate action; otherwise it is not safe.
    return True


async def _load_violation(conn: Any, case: dict[str, Any]) -> dict[str, Any] | None:
    if not case.get("violation_id"):
        return None
    row = await conn.fetchrow("SELECT * FROM violations WHERE id=$1", case["violation_id"])
    return dict(row) if row else None


async def _send_notice(case: dict[str, Any]) -> None:
    async with db_service.acquire() as conn:
        claimed = await conn.fetchrow(
            "UPDATE enforcement_cases SET status='notifying', attempt_count=attempt_count+1, "
            "updated_at=NOW() WHERE id=$1 AND status='pending_notice' RETURNING *",
            case["id"],
        )
        violation = await _load_violation(conn, case)
    if not claimed:
        return

    snapshot = dict(claimed.get("policy_snapshot") or {})
    try:
        if not violation:
            raise RuntimeError("violation_not_found")
        from web.backend.core.violation_notices import send_notice

        hours = int(snapshot.get("grace_hours") or 12)
        deadline = datetime.now(timezone.utc) + timedelta(hours=hours)
        suffix_template = str(_setting(
            "notice_suffix",
            "У вас есть {hours} ч. до {deadline}, чтобы обратиться в поддержку. "
            "После этого будет применено действие: {action}.",
        ))
        try:
            suffix = suffix_template.format(
                hours=hours,
                deadline=deadline.strftime("%Y-%m-%d %H:%M UTC"),
                action=claimed.get("final_action") or "manual_review",
            )
        except (KeyError, ValueError):
            suffix = suffix_template
        result = await send_notice(
            violation, sent_by="enforcement", auto=True, body_suffix=suffix,
        )
        # A manual warning may win the race after the case was queued.  It is
        # a valid notice for this violation, so start the grace period instead
        # of treating the deduplication result as a delivery failure.
        if not result.get("sent") and result.get("reason") != "already_notified":
            raise RuntimeError(str(result.get("reason") or "notice_not_delivered"))
    except Exception as exc:  # noqa: BLE001 - policy decides the durable outcome
        attempts = int(claimed.get("attempt_count") or 1)
        max_attempts = int(snapshot.get("delivery_attempts") or 3)
        failure = str(snapshot.get("delivery_failure") or "manual_review")
        if attempts < max_attempts:
            next_status, resolution = "pending_notice", None
        elif failure == "continue":
            next_status, resolution = "grace_period", "notice_failed_continued"
        elif failure == "fail":
            next_status, resolution = "failed", "notice_failed"
        else:
            next_status, resolution = "manual_review", "notice_failed"
        async with db_service.acquire() as conn:
            await conn.execute(
                "UPDATE enforcement_cases SET status=$2, resolution=$3, last_error=$4, "
                "deadline_at=CASE WHEN $2='grace_period' THEN NOW() + "
                "(($5::jsonb->>'grace_hours')::int * INTERVAL '1 hour') ELSE deadline_at END, "
                "updated_at=NOW() WHERE id=$1 AND status='notifying'",
                case["id"], next_status, resolution, str(exc)[:1000], json.dumps(snapshot),
            )
        return

    async with db_service.acquire() as conn:
        await conn.execute(
            "UPDATE enforcement_cases SET status='grace_period', notice_sent_at=NOW(), "
            "deadline_at=NOW() + (($2::jsonb->>'grace_hours')::int * INTERVAL '1 hour'), "
            "last_error=NULL, updated_at=NOW() WHERE id=$1 AND status='notifying'",
            case["id"], json.dumps(snapshot),
        )


async def _recheck(case: dict[str, Any]) -> tuple[bool, str | None]:
    async with db_service.acquire() as conn:
        violation = await _load_violation(conn, case)
        user_exists = bool(await conn.fetchval("SELECT 1 FROM users WHERE uuid=$1::uuid", str(case["user_uuid"])))
    if not violation:
        return False, "violation_missing"
    if violation.get("action_taken"):
        return False, "violation_already_resolved"
    if not user_exists:
        return False, "user_missing"
    whitelisted, _ = await db_service.is_user_violation_whitelisted(str(case["user_uuid"]))
    if whitelisted:
        return False, "user_whitelisted"
    return True, None


async def process_case(case: dict[str, Any]) -> None:
    """Advance one case. SQL claims make repeated workers and races harmless."""
    if case["status"] == "pending_notice":
        await _send_notice(case)
        return
    if case["status"] == "grace_period" and case["deadline_at"] <= datetime.now(timezone.utc):
        async with db_service.acquire() as conn:
            claimed = await conn.fetchrow(
                "UPDATE enforcement_cases SET status='due', updated_at=NOW() "
                "WHERE id=$1 AND status='grace_period' RETURNING *", case["id"],
            )
        if not claimed:
            return
        case = dict(claimed)
    if case["status"] != "due":
        return

    valid, reason = await _recheck(case)
    if not valid:
        async with db_service.acquire() as conn:
            await conn.execute(
                "UPDATE enforcement_cases SET status='cancelled', resolution=$2, resolved_at=NOW(), "
                "updated_at=NOW() WHERE id=$1 AND status='due'", case["id"], reason,
            )
        return

    mode = str(case.get("mode") or "dry_run")
    action = str(case.get("final_action") or "manual_review")
    if mode != "enforce":
        status, resolution = "resolved", f"would_{action}"
    elif action in {"manual_review", "none"}:
        status = "manual_review" if action == "manual_review" else "resolved"
        resolution = "deadline_expired" if action == "manual_review" else "no_action"
    else:
        async with db_service.acquire() as conn:
            won = await conn.fetchval(
                "UPDATE enforcement_cases SET status='enforcing', updated_at=NOW() "
                "WHERE id=$1 AND status='due' RETURNING id", case["id"],
            )
        if not won:  # A support event or operator won the race.
            return
        try:
            if action == "disable":
                from shared.api_client import api_client
                from shared.data_access import resolve_panel_user_id

                await api_client.disable_user(await resolve_panel_user_id(str(case["user_uuid"])))
            else:
                from shared.throttle import apply_throttle

                snapshot = dict(case.get("policy_snapshot") or {})
                hours = int(snapshot.get("throttle_hours") or 0)
                ok, error, _ = await apply_throttle(
                    user_uuid=str(case["user_uuid"]),
                    rate_kbit=int(snapshot.get("throttle_kbit") or 1024),
                    reason="Delayed violation enforcement",
                    admin_username="auto",
                    until=datetime.now(timezone.utc) + timedelta(hours=hours) if hours else None,
                )
                if not ok:
                    raise RuntimeError(error or "throttle_failed")
        except Exception as exc:  # noqa: BLE001
            async with db_service.acquire() as conn:
                await conn.execute(
                    "UPDATE enforcement_cases SET status='failed', resolution='action_failed', "
                    "last_error=$2, updated_at=NOW() WHERE id=$1 AND status='enforcing'",
                    case["id"], str(exc)[:1000],
                )
            return
        status, resolution = "enforced", action

    expected = "enforcing" if status == "enforced" else "due"
    async with db_service.acquire() as conn:
        changed = await conn.fetchval(
            "UPDATE enforcement_cases SET status=$2, resolution=$3, resolved_at=NOW(), "
            "last_error=NULL, updated_at=NOW() WHERE id=$1 AND status=$4 RETURNING id",
            case["id"], status, resolution, expected,
        )
    if changed and status == "enforced" and case.get("violation_id"):
        await db_service.update_violation_action(
            violation_id=case["violation_id"], action_taken=resolution,
            admin_telegram_id=None, admin_comment="Delayed enforcement workflow",
        )


async def pause_for_support_identity(
    *, user_uuid: str | None = None, telegram_id: int | None = None,
    email: str | None = None, username: str | None = None,
    support_event: dict[str, Any] | None = None,
) -> tuple[int, list[int]]:
    """Atomically pause active cases when exactly one local user matches."""
    identities = [("uuid::text=$1", user_uuid), ("telegram_id::text=$1", telegram_id),
                  ("LOWER(COALESCE(email,''))=LOWER($1)", email),
                  ("LOWER(username)=LOWER($1)", username)]
    matches: set[str] = set()
    async with db_service.acquire() as conn:
        for condition, value in identities:
            if value is None or str(value).strip() == "":
                continue
            rows = await conn.fetch(f"SELECT uuid::text AS uuid FROM users WHERE {condition}", str(value).strip())
            matches.update(str(row["uuid"]) for row in rows)
        if len(matches) != 1:
            return len(matches), []
        rows = await conn.fetch(
            "UPDATE enforcement_cases SET status='paused_for_support', "
            "resolution='support_contacted', metadata=metadata || jsonb_build_object("
            "'support_event', $2::jsonb), updated_at=NOW() "
            "WHERE user_uuid=$1::uuid AND status=ANY($3::text[]) "
            "AND COALESCE((policy_snapshot->>'pause_for_support')::boolean, true) RETURNING id",
            next(iter(matches)), json.dumps(support_event or {}), list(ACTIVE_STATUSES),
        )
    return 1, [int(row["id"]) for row in rows]


async def enforcement_loop() -> None:
    await asyncio.sleep(30)
    while True:
        try:
            async with db_service.acquire() as conn:
                await conn.execute(
                    "UPDATE enforcement_cases SET status=CASE "
                    "WHEN status='notifying' THEN 'pending_notice' ELSE 'due' END, "
                    "last_error='worker lease expired', updated_at=NOW() "
                    "WHERE status IN ('notifying','enforcing') "
                    "AND updated_at < NOW() - INTERVAL '10 minutes'"
                )
                rows = await conn.fetch(
                    "SELECT * FROM enforcement_cases WHERE status='pending_notice' "
                    "OR (status='grace_period' AND deadline_at<=NOW()) OR status='due' "
                    "ORDER BY deadline_at LIMIT 100"
                )
            for row in rows:
                await process_case(dict(row))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Enforcement workflow loop failed: %s", exc)
        await asyncio.sleep(60)

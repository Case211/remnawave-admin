"""Automation core module — data layer.

Provides CRUD operations for automation rules and logs,
plus in-memory template definitions.
"""
import json
import logging
import math
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


# ── Templates (in-memory constants) ──────────────────────────

AUTOMATION_TEMPLATES = [
    {
        "id": "auto_block_sharing",
        "name": "Auto-block Sharing",
        "description": "Автоматическая блокировка пользователей с score нарушения > 80",
        "category": "violations",
        "trigger_type": "event",
        "trigger_config": {"event": "violation.detected", "min_score": 80},
        "conditions": [{"field": "score", "operator": ">=", "value": 80}],
        "action_type": "block_user",
        "action_config": {"reason": "Sharing detected (auto)"},
    },
    {
        "id": "node_monitoring",
        "name": "Node Monitoring",
        "description": "Telegram-уведомление когда нода офлайн > 5 минут",
        "category": "nodes",
        "trigger_type": "event",
        "trigger_config": {"event": "node.went_offline", "offline_minutes": 5},
        "conditions": [],
        "action_type": "notify",
        "action_config": {"channel": "telegram", "message": "Node {node_name} is offline for over 5 minutes"},
    },
    {
        "id": "cleanup_expired",
        "name": "Cleanup Expired Users",
        "description": "Ежедневная очистка пользователей с истёкшей подпиской > 30 дней",
        "category": "system",
        "trigger_type": "schedule",
        "trigger_config": {"cron": "0 3 * * *"},
        "conditions": [{"field": "expired_days", "operator": ">=", "value": 30}],
        "action_type": "cleanup_expired",
        "action_config": {"older_than_days": 30},
    },
    {
        "id": "traffic_notification",
        "name": "Traffic Notification",
        "description": "Уведомление администратора когда трафик пользователя > 90%",
        "category": "users",
        "trigger_type": "threshold",
        "trigger_config": {"metric": "user_traffic_percent", "operator": ">=", "value": 90},
        "conditions": [],
        "action_type": "notify",
        "action_config": {"channel": "telegram", "message": "User {username} has used {percent}% of traffic limit"},
    },
    {
        "id": "auto_restart_node",
        "name": "Auto-restart Node",
        "description": "Автоматический перезапуск ноды офлайн > 15 минут",
        "category": "nodes",
        "trigger_type": "event",
        "trigger_config": {"event": "node.went_offline", "offline_minutes": 15},
        "conditions": [],
        "action_type": "restart_node",
        "action_config": {},
    },
    {
        "id": "daily_report",
        "name": "Daily Report",
        "description": "Ежедневная Telegram-сводка в 23:00",
        "category": "system",
        "trigger_type": "schedule",
        "trigger_config": {"cron": "0 23 * * *"},
        "conditions": [],
        "action_type": "notify",
        "action_config": {
            "channel": "telegram",
            "message": "Daily report: {users_total} users, {traffic_today} traffic today, {violations_today} violations",
        },
    },
]


# ── CRUD: automation_rules ───────────────────────────────────

async def list_automation_rules(
    page: int = 1,
    per_page: int = 20,
    category: Optional[str] = None,
    trigger_type: Optional[str] = None,
    is_enabled: Optional[bool] = None,
) -> Tuple[List[dict], int]:
    """List automation rules with pagination and filters."""
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            where_parts = []
            params: list = []
            idx = 1

            if category is not None:
                where_parts.append(f"category = ${idx}")
                params.append(category)
                idx += 1
            if trigger_type is not None:
                where_parts.append(f"trigger_type = ${idx}")
                params.append(trigger_type)
                idx += 1
            if is_enabled is not None:
                where_parts.append(f"is_enabled = ${idx}")
                params.append(is_enabled)
                idx += 1

            where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM automation_rules{where_clause}",
                *params,
            )

            offset = (page - 1) * per_page
            rows = await conn.fetch(
                f"SELECT * FROM automation_rules{where_clause} "
                f"ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}",
                *params, per_page, offset,
            )

            return [dict(r) for r in rows], total or 0
    except Exception as e:
        logger.error("Failed to list automation rules: %s", e)
        return [], 0


async def get_automation_rules_stats() -> dict:
    """Get global aggregate stats for automation rules."""
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN is_enabled THEN 1 ELSE 0 END), 0) AS total_active,
                    COALESCE(SUM(trigger_count), 0) AS total_triggers
                FROM automation_rules
                """
            )
            return dict(row) if row else {"total_active": 0, "total_triggers": 0}
    except Exception as e:
        logger.error("Failed to get automation stats: %s", e)
        return {"total_active": 0, "total_triggers": 0}


async def get_automation_rule_by_id(rule_id: int) -> Optional[dict]:
    """Get a single automation rule by ID."""
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM automation_rules WHERE id = $1", rule_id
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to get automation rule %d: %s", rule_id, e)
        return None


async def create_automation_rule(
    name: str,
    description: Optional[str],
    is_enabled: bool,
    category: str,
    trigger_type: str,
    trigger_config: dict,
    conditions: list,
    action_type: str,
    action_config: dict,
    created_by: Optional[int],
) -> Optional[dict]:
    """Create a new automation rule."""
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO automation_rules
                    (name, description, is_enabled, category, trigger_type,
                     trigger_config, conditions, action_type, action_config, created_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING *
                """,
                name, description, is_enabled, category, trigger_type,
                json.dumps(trigger_config), json.dumps(conditions),
                action_type, json.dumps(action_config), created_by,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to create automation rule: %s", e)
        return None


async def update_automation_rule(rule_id: int, **fields) -> Optional[dict]:
    """Update an automation rule. Only provided fields are updated."""
    try:
        from src.services.database import db_service

        # Build SET clause dynamically
        set_parts = []
        params: list = []
        idx = 1

        json_fields = {"trigger_config", "conditions", "action_config"}
        for key, value in fields.items():
            if value is None:
                continue
            if key in json_fields:
                value = json.dumps(value)
            set_parts.append(f"{key} = ${idx}")
            params.append(value)
            idx += 1

        if not set_parts:
            return await get_automation_rule_by_id(rule_id)

        set_parts.append(f"updated_at = NOW()")
        params.append(rule_id)

        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                f"UPDATE automation_rules SET {', '.join(set_parts)} "
                f"WHERE id = ${idx} RETURNING *",
                *params,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to update automation rule %d: %s", rule_id, e)
        return None


async def toggle_automation_rule(rule_id: int) -> Optional[dict]:
    """Toggle is_enabled flag on a rule."""
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE automation_rules
                SET is_enabled = NOT is_enabled, updated_at = NOW()
                WHERE id = $1
                RETURNING *
                """,
                rule_id,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to toggle automation rule %d: %s", rule_id, e)
        return None


async def delete_automation_rule(rule_id: int) -> bool:
    """Delete an automation rule (cascades to logs)."""
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM automation_rules WHERE id = $1", rule_id
            )
            return result == "DELETE 1"
    except Exception as e:
        logger.error("Failed to delete automation rule %d: %s", rule_id, e)
        return False


async def increment_trigger_count(rule_id: int) -> None:
    """Increment trigger_count and update last_triggered_at atomically."""
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            await conn.execute(
                """
                UPDATE automation_rules
                SET trigger_count = trigger_count + 1,
                    last_triggered_at = NOW()
                WHERE id = $1
                """,
                rule_id,
            )
    except Exception as e:
        logger.error("Failed to increment trigger count for rule %d: %s", rule_id, e)


async def try_acquire_trigger(rule_id: int, min_interval_seconds: int = 60) -> bool:
    """Atomically attempt to acquire a trigger lock for a rule.

    Returns True if the rule was successfully claimed (i.e. enough time
    has passed since last_triggered_at). This prevents double-triggering.
    """
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE automation_rules
                SET trigger_count = trigger_count + 1,
                    last_triggered_at = NOW()
                WHERE id = $1
                  AND is_enabled = true
                  AND (last_triggered_at IS NULL
                       OR last_triggered_at < NOW() - INTERVAL '1 second' * $2)
                RETURNING id
                """,
                rule_id, min_interval_seconds,
            )
            return row is not None
    except Exception as e:
        logger.error("Failed to acquire trigger for rule %d: %s", rule_id, e)
        return False


# ── Automation log ───────────────────────────────────────────

async def write_automation_log(
    rule_id: int,
    target_type: Optional[str],
    target_id: Optional[str],
    action_taken: str,
    result: str,
    details: Optional[dict] = None,
) -> None:
    """Write an entry to the automation_log table."""
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO automation_log
                    (rule_id, target_type, target_id, action_taken, result, details)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                rule_id, target_type, target_id, action_taken, result,
                json.dumps(details) if details else None,
            )
    except Exception as e:
        logger.error("Failed to write automation log: %s", e)


async def get_automation_logs(
    page: int = 1,
    per_page: int = 50,
    rule_id: Optional[int] = None,
    result: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    cursor: Optional[int] = None,
) -> Tuple[List[dict], int]:
    """Get automation log entries with pagination and filters.

    Supports cursor-based pagination: pass cursor (last seen log id)
    to efficiently fetch the next page without OFFSET.
    """
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            where_parts = []
            params: list = []
            idx = 1

            if cursor is not None:
                where_parts.append(f"l.id < ${idx}")
                params.append(cursor)
                idx += 1

            if rule_id is not None:
                where_parts.append(f"l.rule_id = ${idx}")
                params.append(rule_id)
                idx += 1
            if result is not None:
                where_parts.append(f"l.result = ${idx}")
                params.append(result)
                idx += 1
            if date_from is not None:
                where_parts.append(f"l.triggered_at >= ${idx}::timestamptz")
                params.append(date_from)
                idx += 1
            if date_to is not None:
                where_parts.append(f"l.triggered_at <= ${idx}::timestamptz")
                params.append(date_to)
                idx += 1

            where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

            # Count without cursor filter for accurate total
            count_where_parts = [p for p in where_parts]
            count_params = list(params)
            if cursor is not None:
                count_where_parts = count_where_parts[1:]
                count_params = count_params[1:]
            count_where = (" WHERE " + " AND ".join(count_where_parts)) if count_where_parts else ""

            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM automation_log l{count_where}",
                *count_params,
            )

            if cursor is not None:
                params.append(per_page)
                rows = await conn.fetch(
                    f"""
                    SELECT l.*, r.name AS rule_name
                    FROM automation_log l
                    LEFT JOIN automation_rules r ON r.id = l.rule_id
                    {where_clause}
                    ORDER BY l.id DESC
                    LIMIT ${idx}
                    """,
                    *params,
                )
            else:
                offset = (page - 1) * per_page
                rows = await conn.fetch(
                    f"""
                    SELECT l.*, r.name AS rule_name
                    FROM automation_log l
                    LEFT JOIN automation_rules r ON r.id = l.rule_id
                    {where_clause}
                    ORDER BY l.triggered_at DESC
                    LIMIT ${idx} OFFSET ${idx + 1}
                    """,
                    *params, per_page, offset,
                )

            return [dict(r) for r in rows], total or 0
    except Exception as e:
        logger.error("Failed to get automation logs: %s", e)
        return [], 0


async def get_enabled_rules_by_trigger_type(trigger_type: str) -> List[dict]:
    """Get all enabled rules with a specific trigger type."""
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM automation_rules
                WHERE is_enabled = true AND trigger_type = $1
                ORDER BY id
                """,
                trigger_type,
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get enabled rules for trigger_type=%s: %s", trigger_type, e)
        return []


async def get_enabled_event_rules(event_type: str) -> List[dict]:
    """Get all enabled event-type rules matching a specific event."""
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM automation_rules
                WHERE is_enabled = true
                  AND trigger_type = 'event'
                  AND trigger_config->>'event' = $1
                ORDER BY id
                """,
                event_type,
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get event rules for %s: %s", event_type, e)
        return []

"""Automation core module — data layer.

Provides CRUD operations for automation rules and logs,
plus in-memory template definitions.
"""
import json
import logging
import math
from typing import Optional, List, Tuple

from shared import timefmt
from shared.db_schema import AUTOMATION_RULES_TABLE, AUTOMATION_LOG_TABLE
from shared.db_query import select_sql, insert_sql, update_sql, delete_sql, left_join_sql

logger = logging.getLogger(__name__)


# ── Templates (in-memory constants) ──────────────────────────

AUTOMATION_TEMPLATES = [
    {
        "id": "auto_block_sharing",
        "name": "Auto-block Sharing",
        "name_key": "automations.templates.auto_block_sharing.name",
        "description": "Автоматическая блокировка пользователей с score нарушения > 80",
        "description_key": "automations.templates.auto_block_sharing.description",
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
        "name_key": "automations.templates.node_monitoring.name",
        "description": "Telegram-уведомление когда нода офлайн > 5 минут",
        "description_key": "automations.templates.node_monitoring.description",
        "category": "nodes",
        "trigger_type": "event",
        "trigger_config": {"event": "node.went_offline", "offline_minutes": 5},
        "conditions": [],
        "action_type": "notify",
        "action_config": {"channel": "telegram", "message": "🔴 Нода <b>{node_name}</b> офлайн более 5 минут"},
    },
    {
        "id": "cleanup_expired",
        "name": "Cleanup Expired Users",
        "name_key": "automations.templates.cleanup_expired.name",
        "description": "Ежедневная очистка пользователей с истёкшей подпиской > 30 дней",
        "description_key": "automations.templates.cleanup_expired.description",
        "category": "system",
        "trigger_type": "schedule",
        "trigger_config": {"cron": "0 3 * * *"},
        "conditions": [],
        "action_type": "cleanup_expired",
        "action_config": {"older_than_days": 30},
    },
    {
        "id": "traffic_notification",
        "name": "Traffic Notification",
        "name_key": "automations.templates.traffic_notification.name",
        "description": "Уведомление администратора когда трафик пользователя > 90%",
        "description_key": "automations.templates.traffic_notification.description",
        "category": "users",
        "trigger_type": "threshold",
        "trigger_config": {"metric": "user_traffic_percent", "operator": ">=", "value": 90},
        "conditions": [],
        "action_type": "notify",
        "action_config": {"channel": "telegram", "message": "⚠️ <b>{username}</b> использовал <b>{percent}%</b> лимита трафика"},
    },
    {
        "id": "auto_restart_node",
        "name": "Auto-restart Node",
        "name_key": "automations.templates.auto_restart_node.name",
        "description": "Автоматический перезапуск ноды офлайн > 15 минут",
        "description_key": "automations.templates.auto_restart_node.description",
        "category": "nodes",
        "trigger_type": "event",
        "trigger_config": {"event": "node.went_offline", "offline_minutes": 15},
        "conditions": [],
        "action_type": "restart_node",
        "action_config": {},
    },
    {
        "id": "node_traffic_alert",
        "name": "Node Traffic Alert",
        "name_key": "automations.templates.node_traffic_alert.name",
        "description": "Telegram-уведомление когда пользователь использует > N ГБ на ноде",
        "description_key": "automations.templates.node_traffic_alert.description",
        "category": "users",
        "trigger_type": "threshold",
        "trigger_config": {"metric": "user_node_traffic_gb", "operator": ">=", "value": 10},
        "conditions": [],
        "action_type": "notify",
        "action_config": {
            "channel": "telegram",
            "message": "📈 <b>{username}</b> использовал <b>{traffic_gb} ГБ</b> на ноде <b>{node_name}</b>",
        },
    },
    {
        "id": "daily_report",
        "name": "Daily Report",
        "name_key": "automations.templates.daily_report.name",
        "description": "Ежедневная Telegram-сводка в полночь по часам панели за прошедшие сутки",
        "description_key": "automations.templates.daily_report.description",
        "category": "system",
        "trigger_type": "schedule",
        "trigger_config": {"cron": "0 0 * * *"},
        "conditions": [],
        "action_type": "notify",
        "action_config": {
            "channel": "telegram",
            "message": (
                "📊 <b>Дневной отчёт за {report_date}</b>\n"
                "\n"
                "👥 Пользователи: <b>{users_total}</b> всего"
                " (+{users_new_yesterday} новых, {users_expired_yesterday} истекло)\n"
                "🟢 Онлайн сейчас: <b>{users_online}</b>\n"
                "🖥 Ноды: <b>{nodes_online}/{nodes_total}</b> онлайн\n"
                "📡 Трафик: <b>{traffic_yesterday}</b>\n"
                "\n"
                "🏆 Топ нод по трафику:\n"
                "{top_nodes_yesterday}\n"
                "\n"
                "⚠️ Нарушений: <b>{violations_yesterday}</b>"
            ),
        },
    },
    {
        "id": "auto_block_torrent",
        "name": "Auto-block Torrent",
        "name_key": "automations.templates.auto_block_torrent.name",
        "description": "Автоматическая блокировка при обнаружении торрент-трафика",
        "description_key": "automations.templates.auto_block_torrent.description",
        "category": "violations",
        "trigger_type": "event",
        "trigger_config": {"event": "torrent.detected"},
        "conditions": [],
        "action_type": "block_user",
        "action_config": {"reason": "Torrent traffic detected (auto)"},
    },
    {
        "id": "node_cpu_high",
        "name": "Node CPU high",
        "name_key": "automations.templates.node_cpu_high.name",
        "description": "CPU ноды выше 90% дольше 5 минут",
        "description_key": "automations.templates.node_cpu_high.description",
        "category": "nodes",
        "trigger_type": "threshold",
        "trigger_config": {"metric": "node_cpu_percent", "operator": ">", "value": 90, "for_minutes": 5,
                           "cooldown_minutes": 30},
        "conditions": [],
        "action_type": "notify",
        "action_config": {"channel": "telegram", "severity": "critical", "channels": ["in_app"],
                          "message": "🔥 CPU на ноде {node_code}: <b>{value}%</b> (порог {threshold}%)"},
    },
    {
        "id": "node_memory_high",
        "name": "Node memory high",
        "name_key": "automations.templates.node_memory_high.name",
        "description": "Память ноды занята больше чем на 90% дольше 5 минут",
        "description_key": "automations.templates.node_memory_high.description",
        "category": "nodes",
        "trigger_type": "threshold",
        "trigger_config": {"metric": "node_memory_percent", "operator": ">", "value": 90, "for_minutes": 5,
                           "cooldown_minutes": 30},
        "conditions": [],
        "action_type": "notify",
        "action_config": {"channel": "telegram", "severity": "critical", "channels": ["in_app"],
                          "message": "🧠 Память на ноде {node_code}: <b>{value}%</b> (порог {threshold}%)"},
    },
    {
        "id": "node_disk_high",
        "name": "Node disk almost full",
        "name_key": "automations.templates.node_disk_high.name",
        "description": "Диск ноды заполнен больше чем на 90%",
        "description_key": "automations.templates.node_disk_high.description",
        "category": "nodes",
        "trigger_type": "threshold",
        "trigger_config": {"metric": "node_disk_percent", "operator": ">", "value": 90, "cooldown_minutes": 360},
        "conditions": [],
        "action_type": "notify",
        "action_config": {"channel": "telegram", "severity": "warning", "channels": ["in_app"],
                          "message": "💾 Диск на ноде {node_code}: <b>{value}%</b> (порог {threshold}%)"},
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
        from shared.database import db_service
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
                select_sql(AUTOMATION_RULES_TABLE, "COUNT(*)", where_clause),
                *params,
            )

            offset = (page - 1) * per_page
            rows = await conn.fetch(
                select_sql(AUTOMATION_RULES_TABLE, "*",
                    f"{where_clause} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"),
                *params, per_page, offset,
            )

            return [dict(r) for r in rows], total or 0
    except Exception as e:
        logger.error("Failed to list automation rules: %s", e)
        return [], 0


async def get_automation_rules_stats() -> dict:
    """Get global aggregate stats for automation rules."""
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(AUTOMATION_RULES_TABLE,
                    "COALESCE(SUM(CASE WHEN is_enabled THEN 1 ELSE 0 END), 0) AS total_active, "
                    "COALESCE(SUM(trigger_count), 0) AS total_triggers, "
                    "MAX(last_triggered_at) AS last_triggered_at")
            )
            return dict(row) if row else {"total_active": 0, "total_triggers": 0, "last_triggered_at": None}
    except Exception as e:
        logger.error("Failed to get automation stats: %s", e)
        return {"total_active": 0, "total_triggers": 0}


async def get_automation_rule_by_id(rule_id: int) -> Optional[dict]:
    """Get a single automation rule by ID."""
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(AUTOMATION_RULES_TABLE, "*", "WHERE id = $1"), rule_id
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
    extra_actions: Optional[list] = None,
) -> Optional[dict]:
    """Create a new automation rule."""
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                insert_sql(AUTOMATION_RULES_TABLE,
                    ["name", "description", "is_enabled", "category", "trigger_type",
                     "trigger_config", "conditions", "action_type", "action_config", "created_by",
                     "extra_actions"],
                    returning="*"),
                name, description, is_enabled, category, trigger_type,
                json.dumps(trigger_config), json.dumps(conditions),
                action_type, json.dumps(action_config), created_by,
                json.dumps(extra_actions or []),
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to create automation rule: %s", e)
        return None


async def update_automation_rule(rule_id: int, **fields) -> Optional[dict]:
    """Update an automation rule. Only provided fields are updated."""
    try:
        from shared.database import db_service

        # Build SET clause dynamically
        set_parts = []
        params: list = []
        idx = 1

        json_fields = {"trigger_config", "conditions", "action_config", "extra_actions"}
        for key, value in fields.items():
            # Описание можно очистить; у остальных полей None — «не менять»
            if value is None and key != "description":
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
                update_sql(AUTOMATION_RULES_TABLE, ', '.join(set_parts), f"id = ${idx}", returning="*"),
                *params,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to update automation rule %d: %s", rule_id, e)
        return None


async def toggle_automation_rule(rule_id: int) -> Optional[dict]:
    """Toggle is_enabled flag on a rule."""
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                update_sql(AUTOMATION_RULES_TABLE,
                    "is_enabled = NOT is_enabled, updated_at = NOW()",
                    "id = $1", returning="*"),
                rule_id,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to toggle automation rule %d: %s", rule_id, e)
        return None


async def delete_automation_rule(rule_id: int) -> bool:
    """Delete an automation rule (cascades to logs)."""
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            result = await conn.execute(
                delete_sql(AUTOMATION_RULES_TABLE, "id = $1"), rule_id
            )
            return result == "DELETE 1"
    except Exception as e:
        logger.error("Failed to delete automation rule %d: %s", rule_id, e)
        return False


async def increment_trigger_count(rule_id: int) -> None:
    """Increment trigger_count and update last_triggered_at atomically."""
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            await conn.execute(
                update_sql(AUTOMATION_RULES_TABLE,
                    "trigger_count = trigger_count + 1, last_triggered_at = NOW()",
                    "id = $1"),
                rule_id,
            )
    except Exception as e:
        logger.error("Failed to increment trigger count for rule %d: %s", rule_id, e)


async def try_acquire_target(rule_id: int, target: str, min_interval_seconds: int) -> bool:
    """Замок срабатывания на пару «правило + цель».

    Замок на правило целиком терял события: два нарушения в пределах
    интервала — второе молча пропадало. Успешный захват сразу засчитывается
    в статистику правила.
    """
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            async with conn.transaction():
                claimed = await conn.fetchval(
                    """
                    INSERT INTO automation_trigger_locks (rule_id, target, last_triggered_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (rule_id, target) DO UPDATE SET last_triggered_at = NOW()
                    WHERE automation_trigger_locks.last_triggered_at
                          < NOW() - INTERVAL '1 second' * $3
                    RETURNING rule_id
                    """,
                    rule_id, target, min_interval_seconds,
                )
                if claimed is None:
                    return False
                updated = await conn.fetchval(
                    update_sql(AUTOMATION_RULES_TABLE,
                        "trigger_count = trigger_count + 1, last_triggered_at = NOW()",
                        "id = $1 AND is_enabled = true", returning="id"),
                    rule_id,
                )
                return updated is not None
    except Exception as e:
        logger.error("Failed to acquire trigger for rule %d / %s: %s", rule_id, target, e)
        return False


async def users_over_traffic(min_percent: float) -> List[dict]:
    """Активные юзеры, израсходовавшие не меньше min_percent лимита — из своей
    базы, а не полным списком из панели каждые пару минут."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT uuid::text AS uuid, username, used_traffic_bytes, traffic_limit_bytes, expire_at,
                   COALESCE(raw_data::jsonb->>'tag', '') AS tag,
                   COALESCE((SELECT string_agg(s->>'name', ',')
                             FROM jsonb_array_elements(COALESCE(raw_data::jsonb->'activeInternalSquads', '[]'::jsonb)) s), '')
                       AS squads
            FROM users
            WHERE traffic_limit_bytes > 0 AND LOWER(status) = 'active'
              AND used_traffic_bytes >= traffic_limit_bytes * ($1::float8 / 100)
            """,
            float(min_percent),
        )
    return [dict(r) for r in rows]


async def expired_users_to_disable(cutoff, squad_uuids: Optional[List[str]] = None,
                                   tag: Optional[str] = None) -> List[str]:
    """uuid юзеров, у которых подписка истекла раньше cutoff и которые ещё не
    отключены. Фильтр по сквадам и тегу — чтобы не задеть служебные аккаунты."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT uuid::text AS uuid FROM users
            WHERE expire_at IS NOT NULL AND expire_at < $1
              AND UPPER(COALESCE(status, '')) <> 'DISABLED'
              AND ($2::text[] IS NULL OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements(COALESCE(raw_data::jsonb->'activeInternalSquads', '[]'::jsonb)) s
                    WHERE s->>'uuid' = ANY($2::text[])))
              AND ($3::text IS NULL OR raw_data::jsonb->>'tag' = $3::text)
            """,
            cutoff, squad_uuids or None, tag or None,
        )
    return [r["uuid"] for r in rows]


async def users_expired_between(since, until) -> List[dict]:
    """Юзеры, у которых подписка истекла в промежутке (since, until]."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT uuid::text AS uuid, username, expire_at,
                   COALESCE(raw_data::jsonb->>'tag', '') AS tag,
                   COALESCE((SELECT string_agg(s->>'name', ', ')
                             FROM jsonb_array_elements(COALESCE(raw_data::jsonb->'activeInternalSquads', '[]'::jsonb)) s), '') AS squads
            FROM users
            WHERE expire_at > $1 AND expire_at <= $2
            ORDER BY expire_at
            LIMIT 1000
            """,
            since, until,
        )
    return [dict(r) for r in rows]


async def user_traffic_today(min_bytes: int) -> List[dict]:
    """Трафик юзера за сегодня (сутки по часам панели) по всем нодам."""
    from shared.database import db_service
    z = timefmt.sql_zone()
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT h.user_uuid::text AS uuid, u.username, SUM(h.delta_bytes) AS traffic_bytes
            FROM user_node_traffic_history h
            JOIN users u ON u.uuid = h.user_uuid
            WHERE h.recorded_at >= (date_trunc('day', NOW() AT TIME ZONE {z}) AT TIME ZONE {z})
              AND UPPER(COALESCE(u.status, '')) NOT IN ('EXPIRED', 'DISABLED', 'LIMITED')
            GROUP BY h.user_uuid, u.username
            HAVING SUM(h.delta_bytes) >= $1
            ORDER BY traffic_bytes DESC
            """,
            int(min_bytes),
        )
    return [dict(r) for r in rows]


async def node_load() -> List[dict]:
    """Нагрузка включённых нод на связи — из метрик Fleet."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            "SELECT uuid::text AS uuid, name, cpu_usage, memory_usage, disk_usage FROM nodes "
            "WHERE NOT is_disabled AND is_connected"
        )
    return [dict(r) for r in rows]


async def count_since(what: str, since) -> int:
    """Всплески: нарушения или новые юзеры с момента since."""
    from shared.database import db_service
    column = {"violations": ("violations", "detected_at"), "users": ("users", "created_at")}[what]
    async with db_service.acquire() as conn:
        return int(await conn.fetchval(
            f"SELECT COUNT(*) FROM {column[0]} WHERE {column[1]} >= $1", since,
        ) or 0)


async def schedule_pending_action(rule_id: int, action: str, target: str, run_at,
                                  payload: Optional[dict] = None) -> bool:
    """Отложенное действие: переживает рестарт, выполнит движок.

    False — такое уже ждёт своего часа (один отложенный шаг правила на клиента,
    см. миграцию 0125), второе не ставится.
    """
    from shared.database import db_service
    async with db_service.acquire() as conn:
        inserted = await conn.fetchval(
            "INSERT INTO automation_pending_actions (rule_id, action, target, run_at, payload) "
            "VALUES ($1, $2, $3, $4, $5::jsonb) ON CONFLICT DO NOTHING RETURNING id",
            rule_id, action, target, run_at,
            json.dumps(payload, default=str) if payload is not None else None,
        )
    return inserted is not None


async def support_contact_since(telegram_id: Optional[int], since, user_uuid: Optional[str] = None) -> bool:
    """Писал ли клиент в Bedolaga или внешнюю поддержку начиная с since."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        return bool(await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM support_tickets t
                 WHERE t.telegram_id = $1
                   AND (t.created_at >= $2
                        OR (t.last_message_from = 'user' AND t.last_message_at >= $2)
                        OR EXISTS (SELECT 1 FROM support_ticket_messages m
                                    WHERE m.ticket_id = t.id AND NOT m.is_from_admin
                                      AND m.created_at >= $2))
            ) OR EXISTS (
                SELECT 1 FROM external_support_events e
                 WHERE e.occurred_at >= $2
                   AND (e.user_uuid = $3::uuid OR ($1::bigint IS NOT NULL AND e.telegram_id = $1))
            )
            """,
            telegram_id, since, user_uuid,
        ))


async def claim_due_actions(limit: int = 50) -> List[dict]:
    """Наступившие отложенные действия — забрать атомарно (без двойного исполнения)."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            """
            UPDATE automation_pending_actions SET done_at = NOW()
            WHERE id IN (
                SELECT id FROM automation_pending_actions
                WHERE done_at IS NULL AND run_at <= NOW()
                ORDER BY run_at LIMIT $1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, rule_id, action, target, payload
            """,
            limit,
        )
    return [dict(r) for r in rows]


async def finish_pending_action(action_id: int, result: str) -> None:
    from shared.database import db_service
    async with db_service.acquire() as conn:
        await conn.execute("UPDATE automation_pending_actions SET result = $2 WHERE id = $1", action_id, result)


async def count_recent_successes(rule_id: int, target_id: str, action: str, minutes: int) -> int:
    """Сколько раз правило успешно сделало action с целью за последние minutes."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        return int(await conn.fetchval(
            f"SELECT COUNT(*) FROM {AUTOMATION_LOG_TABLE} WHERE rule_id = $1 AND target_id = $2 "
            "AND action_taken = $3 AND result = 'success' AND triggered_at > NOW() - INTERVAL '1 minute' * $4",
            rule_id, target_id, action, minutes,
        ) or 0)


async def cleanup_automation_history(keep_days: int = 90) -> int:
    """Журнал и замки старше keep_days — прочь: иначе растут без предела."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        result = await conn.execute(
            f"DELETE FROM {AUTOMATION_LOG_TABLE} WHERE triggered_at < NOW() - INTERVAL '1 day' * $1",
            keep_days,
        )
        await conn.execute(
            "DELETE FROM automation_trigger_locks WHERE last_triggered_at < NOW() - INTERVAL '1 day' * $1",
            keep_days,
        )
        await conn.execute(
            "DELETE FROM automation_pending_actions WHERE done_at < NOW() - INTERVAL '1 day' * $1",
            keep_days,
        )
        await conn.execute(
            "DELETE FROM external_support_events WHERE occurred_at < NOW() - INTERVAL '1 day' * $1",
            keep_days,
        )
    return int(result.split()[-1]) if result else 0


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
        from shared.database import db_service
        async with db_service.acquire() as conn:
            await conn.execute(
                insert_sql(AUTOMATION_LOG_TABLE,
                    ["rule_id", "target_type", "target_id", "action_taken", "result", "details"]),
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
        from shared.database import db_service
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
            # asyncpg не принимает строку для timestamptz; голая дата — сутки
            # в часовом поясе панели, конец диапазона — весь выбранный день
            since, until = timefmt.filter_bounds(date_from, date_to)
            if since:
                where_parts.append(f"l.triggered_at >= ${idx}")
                params.append(since)
                idx += 1
            if until:
                where_parts.append(f"l.triggered_at < ${idx}")
                params.append(until)
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
                select_sql(AUTOMATION_LOG_TABLE, "COUNT(*)", f"l{count_where}"),
                *count_params,
            )

            if cursor is not None:
                params.append(per_page)
                join = f"l {left_join_sql(AUTOMATION_RULES_TABLE, 'r', 'r.id = l.rule_id')}"
                rows = await conn.fetch(
                    select_sql(AUTOMATION_LOG_TABLE, "l.*, r.name AS rule_name",
                        f"{join} {where_clause} ORDER BY l.id DESC LIMIT ${idx}"),
                    *params,
                )
            else:
                offset = (page - 1) * per_page
                join = f"l {left_join_sql(AUTOMATION_RULES_TABLE, 'r', 'r.id = l.rule_id')}"
                rows = await conn.fetch(
                    select_sql(AUTOMATION_LOG_TABLE, "l.*, r.name AS rule_name",
                        f"{join} {where_clause} ORDER BY l.triggered_at DESC LIMIT ${idx} OFFSET ${idx + 1}"),
                    *params, per_page, offset,
                )

            return [dict(r) for r in rows], total or 0
    except Exception as e:
        logger.error("Failed to get automation logs: %s", e)
        return [], 0


async def get_enabled_rules_by_trigger_type(trigger_type: str) -> List[dict]:
    """Get all enabled rules with a specific trigger type."""
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(AUTOMATION_RULES_TABLE, "*",
                    "WHERE is_enabled = true AND trigger_type = $1 ORDER BY id"),
                trigger_type,
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get enabled rules for trigger_type=%s: %s", trigger_type, e)
        return []


async def get_enabled_event_rules(event_type: str) -> List[dict]:
    """Get all enabled event-type rules matching a specific event."""
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(AUTOMATION_RULES_TABLE, "*",
                    "WHERE is_enabled = true AND trigger_type = 'event'"
                    " AND trigger_config->>'event' = $1 ORDER BY id"),
                event_type,
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get event rules for %s: %s", event_type, e)
        return []

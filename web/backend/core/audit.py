"""Audit log database operations — extracted from rbac.py."""
import re
from typing import Optional, List, Tuple

import logging
logger = logging.getLogger(__name__)

from shared import timefmt
from shared.db_schema import AUDIT_TABLE
from shared.db_query import select_sql, insert_sql


async def write_audit_log(
    admin_id: Optional[int],
    admin_username: str,
    action: str,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            await conn.execute(
                insert_sql(
                    AUDIT_TABLE,
                    ["admin_id", "admin_username", "action", "resource", "resource_id", "details", "ip_address"],
                ),
                admin_id, admin_username, action, resource, resource_id, details, ip_address,
            )
    except Exception as e:
        logger.warning("write_audit_log failed: %s", e)


async def get_audit_logs(
    limit: int = 50,
    offset: int = 0,
    admin_id: Optional[int] = None,
    action: Optional[str] = None,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    cursor: Optional[int] = None,
) -> Tuple[List[dict], int]:
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return [], 0

        where_parts = []
        params = []
        idx = 1

        if cursor is not None:
            where_parts.append(f"id < ${idx}")
            params.append(cursor)
            idx += 1

        if admin_id is not None:
            where_parts.append(f"admin_id = ${idx}")
            params.append(admin_id)
            idx += 1
        if action:
            where_parts.append(f"action ILIKE ${idx}")
            params.append(f"%{action}%")
            idx += 1
        if resource:
            where_parts.append(f"resource = ${idx}")
            params.append(resource)
            idx += 1
        if resource_id:
            where_parts.append(f"resource_id = ${idx}")
            params.append(resource_id)
            idx += 1
        # asyncpg не принимает строку для timestamptz; голая дата — сутки
        # в часовом поясе панели, конец диапазона — весь выбранный день
        since, until = timefmt.filter_bounds(date_from, date_to)
        if since:
            where_parts.append(f"created_at >= ${idx}")
            params.append(since)
            idx += 1
        if until:
            where_parts.append(f"created_at < ${idx}")
            params.append(until)
            idx += 1
        if search:
            where_parts.append(
                f"(admin_username ILIKE ${idx} OR action ILIKE ${idx} OR "
                f"resource_id ILIKE ${idx} OR details ILIKE ${idx})"
            )
            params.append(f"%{search}%")
            idx += 1

        where_clause = ""
        if where_parts:
            where_clause = "WHERE " + " AND ".join(where_parts)

        async with db_service.acquire() as conn:
            count_where_parts = [p for p in where_parts]
            count_params = list(params)
            if cursor is not None:
                count_where_parts = count_where_parts[1:]
                count_params = count_params[1:]
            count_where = ""
            if count_where_parts:
                if cursor is not None:
                    renumbered = []
                    for part in count_where_parts:
                        renumbered.append(re.sub(r'\$(\d+)', lambda m: f"${int(m.group(1)) - 1}", part))
                    count_where = "WHERE " + " AND ".join(renumbered)
                else:
                    count_where = "WHERE " + " AND ".join(count_where_parts)

            count_row = await conn.fetchrow(
                select_sql(
                    AUDIT_TABLE,
                    "COUNT(*)",
                    count_where,
                ),
                *count_params,
            )
            total = count_row[0] if count_row else 0

            if cursor is not None:
                params.append(limit)
                rows = await conn.fetch(
                    select_sql(
                        AUDIT_TABLE,
                        "*",
                        f"{where_clause} ORDER BY id DESC LIMIT ${idx}",
                    ),
                    *params,
                )
            else:
                params.append(limit)
                params.append(offset)
                rows = await conn.fetch(
                    select_sql(
                        AUDIT_TABLE,
                        "*",
                        f"{where_clause} ORDER BY id DESC LIMIT ${idx} OFFSET ${idx + 1}",
                    ),
                    *params,
                )
            return [dict(r) for r in rows], total
    except Exception as e:
        logger.error("get_audit_logs failed: %s", e)
        return [], 0


async def get_audit_logs_for_resource(
    resource: str,
    resource_id: str,
    limit: int = 50,
) -> List[dict]:
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return []

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    AUDIT_TABLE,
                    "*",
                    "WHERE resource = $1 AND resource_id = $2 ORDER BY created_at DESC LIMIT $3",
                ),
                resource, resource_id, limit,
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("get_audit_logs_for_resource failed: %s", e)
        return []


async def get_audit_distinct_actions() -> List[str]:
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return []

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    AUDIT_TABLE,
                    "DISTINCT action",
                    "ORDER BY action",
                ),
            )
            return [r["action"] for r in rows]
    except Exception as e:
        logger.error("get_audit_distinct_actions failed: %s", e)
        return []

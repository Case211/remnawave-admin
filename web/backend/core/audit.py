"""Audit log database operations — extracted from rbac.py."""
import re
from contextvars import ContextVar
from typing import Optional, List, Tuple

import logging
logger = logging.getLogger(__name__)

from shared import timefmt
from shared.db_schema import AUDIT_TABLE
from shared.db_query import select_sql, insert_sql


# Мидлварь кладёт сюда словарь на время запроса; запись аудита из обработчика
# ставит в нём флаг, и мидлварь не пишет вторую запись о той же операции.
# Словарь, а не bool: обработчик работает в копии контекста, и новое значение
# переменной до мидлвари не дошло бы, а изменение общего объекта доходит.
request_audit_state: ContextVar[Optional[dict]] = ContextVar("request_audit_state", default=None)


_SECRET_PARTS = ("password", "secret", "token", "api_key", "private", "credential")


def _camel(key: str) -> str:
    head, *rest = key.split("_")
    return head + "".join(part.title() for part in rest)


def audit_changes(before: Optional[dict], after: dict) -> dict:
    """«Было → стало» для журнала: {поле: [старое, новое]} по изменённым полям.

    Старое ищется и в snake_case, и в camelCase — данные панели в базе лежат
    в camelCase. Если старого состояния нет, пишутся все поля со старым None.
    Секреты маскируются.
    """
    changes = {}
    for key, new in after.items():
        old = None
        if before:
            old = before.get(key, before.get(_camel(key)))
        if before is not None and str(old) == str(new):
            continue
        if any(part in key.lower() for part in _SECRET_PARTS):
            old, new = ("***" if old is not None else None), "***"
        changes[key] = [old, new]
    return changes


async def write_audit_log(
    admin_id: Optional[int],
    admin_username: str,
    action: str,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    state = request_audit_state.get()
    if state is not None:
        state["written"] = True
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


def _like(value: str) -> str:
    """Экранировать % и _ для LIKE: поиск «reset_traffic» не должен ловить любой символ на месте «_»."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
    admin_username: Optional[str] = None,
    ip_address: Optional[str] = None,
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
        if admin_username:
            where_parts.append(f"admin_username = ${idx}")
            params.append(admin_username)
            idx += 1
        if ip_address:
            where_parts.append(f"ip_address = ${idx}")
            params.append(ip_address)
            idx += 1
        if action:
            # «.create» — точное действие у любого раздела; иначе — вхождение
            where_parts.append(f"action ILIKE ${idx}")
            params.append(f"%{_like(action)}" if action.startswith(".") else f"%{_like(action)}%")
            idx += 1
        if resource:
            # Фильтр страницы строится по префиксу действия («user»), а в колонке
            # resource лежит «users»: сравнение только с колонкой давало пустоту
            variants = {resource, f"{resource}s", resource[:-1] if resource.endswith("s") else resource}
            where_parts.append(
                f"(resource = ANY(${idx}::text[]) OR split_part(action, '.', 1) = ANY(${idx}::text[]))"
            )
            params.append(sorted(variants))
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
            params.append(f"%{_like(search)}%")
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

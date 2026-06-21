"""Admin account database operations — extracted from rbac.py.

These functions manage the admin_accounts table (CRUD + usage counters).
"""
import time
from typing import Optional, Dict, List

import logging
logger = logging.getLogger(__name__)

from shared.db_schema import (
    ADMIN_INSERT_COLUMNS,
    ADMIN_UPDATE_COLUMNS_SET,
    ADMIN_COUNTER_COLUMNS,
    ADMIN_TABLE,
    ADMIN_ROLES_TABLE,
)
from shared.db_query import select_sql, insert_sql, update_sql, delete_sql, left_join_sql


# ── Cache ────────────────────────────────────────────────────────

_admin_account_cache: Dict[int, Optional[dict]] = {}
_admin_cache_ts: Dict[int, float] = {}
# Short TTL — admin counters change frequently (create/delete user, reset
# traffic, etc.) and the frontend polls /auth/me after every mutation to
# show the current quota. A long TTL means the user sees stale numbers for
# up to a minute, which is misleading. 10s is enough to absorb a burst of
# requests from the same render while still feeling responsive.
_ADMIN_CACHE_TTL = 10


def invalidate_admin_cache(admin_id: Optional[int] = None) -> None:
    """Invalidate the admin cache.

    Pass an admin_id to drop just that entry (preferred — minimizes cache
    stampede on other admins). Pass None to drop the entire cache.
    """
    if admin_id is None:
        _admin_account_cache.clear()
        _admin_cache_ts.clear()
        return
    _admin_account_cache.pop(admin_id, None)
    _admin_cache_ts.pop(admin_id, None)


def _cache_get(admin_id: int) -> Optional[dict]:
    """Return the cached entry for admin_id if it's still fresh."""
    ts = _admin_cache_ts.get(admin_id)
    if ts is None:
        return None
    if time.time() - ts >= _ADMIN_CACHE_TTL:
        # Expired — drop it so we don't leak memory.
        _admin_account_cache.pop(admin_id, None)
        _admin_cache_ts.pop(admin_id, None)
        return None
    return _admin_account_cache.get(admin_id)


def _cache_put(admin_id: int, value: Optional[dict]) -> None:
    _admin_account_cache[admin_id] = value
    _admin_cache_ts[admin_id] = time.time()


# ── Helpers ──────────────────────────────────────────────────────

async def _fetch_one(query: str, *args) -> Optional[dict]:
    from shared.database import db_service
    if not db_service.is_connected:
        return None
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def _fetch_all(query: str, *args) -> List[dict]:
    from shared.database import db_service
    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]


# ── SQL fragments for admin SELECT with roles JOIN ──────────────

_ADMIN_SELECT_COLS = "a.*, r.name as role_name, r.display_name as role_display_name"
_ADMIN_SELECT_FROM = (
    f"a {left_join_sql(ADMIN_ROLES_TABLE, 'r', 'r.id = a.role_id')}"
)


# ── Read ─────────────────────────────────────────────────────────

async def get_admin_account_by_username(username: str) -> Optional[dict]:
    try:
        return await _fetch_one(
            select_sql(
                ADMIN_TABLE,
                _ADMIN_SELECT_COLS,
                f"{_ADMIN_SELECT_FROM} WHERE LOWER(a.username) = LOWER($1)",
            ),
            username,
        )
    except Exception as e:
        logger.error("get_admin_account_by_username failed: %s", e)
        return None


async def get_admin_account_by_email(email: str) -> Optional[dict]:
    try:
        return await _fetch_one(
            select_sql(
                ADMIN_TABLE,
                _ADMIN_SELECT_COLS,
                f"{_ADMIN_SELECT_FROM} WHERE LOWER(a.email) = LOWER($1)",
            ),
            email,
        )
    except Exception as e:
        logger.error("get_admin_account_by_email failed: %s", e)
        return None


async def get_admin_account_by_id(admin_id: int) -> Optional[dict]:
    cached = _cache_get(admin_id)
    if cached is not None:
        return cached
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            _cache_put(admin_id, None)
            return None
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(
                    ADMIN_TABLE,
                    _ADMIN_SELECT_COLS,
                    f"{_ADMIN_SELECT_FROM} WHERE a.id = $1",
                ),
                admin_id,
            )
            result = dict(row) if row else None
            _cache_put(admin_id, result)
            return result
    except Exception as e:
        logger.error("get_admin_account_by_id failed: %s", e)
        _cache_put(admin_id, None)
        return None


async def list_admin_accounts() -> List[dict]:
    try:
        return await _fetch_all(
            select_sql(
                ADMIN_TABLE,
                _ADMIN_SELECT_COLS,
                f"{_ADMIN_SELECT_FROM} ORDER BY a.created_at ASC",
            )
        )
    except Exception as e:
        logger.error("list_admin_accounts failed: %s", e)
        return []


# ── Write ────────────────────────────────────────────────────────

async def create_admin_account(
    username: str,
    password_hash: Optional[str],
    telegram_id: Optional[int],
    role_id: int,
    max_users: Optional[int] = None,
    max_traffic_gb: Optional[int] = None,
    max_nodes: Optional[int] = None,
    max_hosts: Optional[int] = None,
    unlimited_traffic_policy: str = "allowed",
    unrestricted_user_access: bool = False,  # scoping ON по умолчанию для новых админов
    has_bot_access: bool = False,
    is_generated_password: bool = False,
    created_by: Optional[int] = None,
    email: Optional[str] = None,
) -> Optional[dict]:
    try:
        values = [
            username, password_hash, telegram_id, role_id,
            max_users, max_traffic_gb, max_nodes, max_hosts,
            unlimited_traffic_policy, unrestricted_user_access,
            has_bot_access, is_generated_password, created_by, email,
        ]
        return await _fetch_one(
            insert_sql(
                ADMIN_TABLE,
                ADMIN_INSERT_COLUMNS,
                returning="*",
            ),
            *values,
        )
    except Exception as e:
        logger.error("create_admin_account failed: %s", e)
        return None


async def update_admin_account(
    admin_id: int,
    **fields,
) -> Optional[dict]:
    if not fields:
        return await get_admin_account_by_id(admin_id)

    filtered = {k: v for k, v in fields.items() if k in ADMIN_UPDATE_COLUMNS_SET}
    if not filtered:
        return await get_admin_account_by_id(admin_id)

    set_parts = []
    values = []
    idx = 1
    for key, val in filtered.items():
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    set_parts.append("updated_at = NOW()")

    values.append(admin_id)
    query = update_sql(
        ADMIN_TABLE,
        ', '.join(set_parts),
        f"id = ${idx}",
        returning="*",
    )

    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(query, *values)
            if row is not None:
                # Drop the cache so the next /auth/me reflects the new
                # values (e.g. max_traffic_gb, max_users, role, etc.).
                invalidate_admin_cache(admin_id)
            return dict(row) if row else None
    except Exception as e:
        logger.error("update_admin_account failed: %s", e)
        return None


async def delete_admin_account(admin_id: int) -> bool:
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return False
        async with db_service.acquire() as conn:
            result = await conn.execute(
                delete_sql(
                    ADMIN_TABLE,
                    "id = $1",
                ),
                admin_id,
            )
            deleted = "DELETE 1" in result
            if deleted:
                # Admin is gone — drop the cache so a stale row can't be
                # served to a future admin with the same id (id reuse).
                invalidate_admin_cache(admin_id)
            return deleted
    except Exception as e:
        logger.error("delete_admin_account failed: %s", e)
        return False


# ── Counters ─────────────────────────────────────────────────────

_COUNTER_QUERIES = {
    "users_created": update_sql(
        ADMIN_TABLE,
        "users_created = users_created + $1",
        "id = $2",
    ),
    "traffic_used_bytes": update_sql(
        ADMIN_TABLE,
        "traffic_used_bytes = traffic_used_bytes + $1",
        "id = $2",
    ),
    "nodes_created": update_sql(
        ADMIN_TABLE,
        "nodes_created = nodes_created + $1",
        "id = $2",
    ),
    "hosts_created": update_sql(
        ADMIN_TABLE,
        "hosts_created = hosts_created + $1",
        "id = $2",
    ),
}

# Counters that should be floored at 0 on decrement. `users_created` is a
# lifetime event count and must NOT be floored. The others track allocated
# quota (traffic/nodes/hosts) and going negative is always wrong.
_COUNTERS_WITH_FLOOR = frozenset({
    "traffic_used_bytes",
    "nodes_created",
    "hosts_created",
    # `users_created` is intentionally excluded
})


async def increment_usage_counter(admin_id: int, counter: str, amount: int = 1) -> bool:
    query = _COUNTER_QUERIES.get(counter)
    if not query:
        return False
    if amount > 0 and counter in ADMIN_COUNTER_COLUMNS:
        limit_col = ADMIN_COUNTER_COLUMNS[counter]
        query = update_sql(
            ADMIN_TABLE,
            f"{counter} = {counter} + $1",
            f"id = $2 AND ({limit_col} IS NULL OR {counter} + $1 <= {limit_col})"
        )
    elif amount < 0 and counter in _COUNTERS_WITH_FLOOR:
        # Safety floor: prevent the counter from going negative. The
        # `traffic_used_bytes` counter represents the admin's currently
        # allocated quota and must never drop below zero — going negative
        # breaks the UI (shows "-202.0 GB of 1024 GB") and makes the quota
        # limit check in users.py pass when it shouldn't. The GREATEST()
        # clamps the result to >= 0.
        query = update_sql(
            ADMIN_TABLE,
            f"{counter} = GREATEST(0, {counter} + $1)",
            f"id = $2",
        )
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return False
        async with db_service.acquire() as conn:
            result = await conn.execute(query, amount, admin_id)
            updated = "UPDATE 0" not in (result or "")
            if updated:
                # Drop the cached row so the next /auth/me (or any other
                # reader) sees the new counter value. Without this the
                # frontend would see stale numbers for up to the cache TTL
                # even though the mutation just succeeded.
                invalidate_admin_cache(admin_id)
            return updated
    except Exception as e:
        logger.error("increment_usage_counter failed: %s", e)
        return False


async def recompute_admin_traffic_counter(admin_id: int) -> Optional[int]:
    """Recompute an admin's `traffic_used_bytes` counter from scratch.

    The counter should equal `SUM(traffic_limit_bytes - used_traffic_bytes)`
    for all users currently owned by the admin. This is the safety net
    for when the counter has drifted from reality (e.g. due to historic
    bugs, partial failures, policy changes, etc.).

    Returns the new counter value, or None if the DB is unavailable.

    The new value is also clamped to >= 0 in the SQL so any pre-existing
    negative drift is cleaned up.
    """
    from shared.db_schema import USERS_TABLE
    from shared.db_query import select_sql, update_sql
    from shared.database import db_service

    if not db_service.is_connected:
        return None
    try:
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(
                    USERS_TABLE,
                    "COALESCE(SUM(GREATEST(0, traffic_limit_bytes - used_traffic_bytes)), 0) AS total",
                    "WHERE created_by_admin_id = $1 AND traffic_limit_bytes IS NOT NULL",
                ),
                admin_id,
            )
            new_value = int(row["total"] or 0) if row else 0
            await conn.execute(
                update_sql(
                    ADMIN_TABLE,
                    "traffic_used_bytes = $1",
                    "id = $2",
                ),
                new_value,
                admin_id,
            )
            invalidate_admin_cache(admin_id)
            return new_value
    except Exception as e:
        logger.error("recompute_admin_traffic_counter failed for %s: %s", admin_id, e)
        return None


async def reset_admin_counter(admin_id: int, counter: str) -> Optional[dict]:
    """Reset a specific usage counter for an admin to 0.

    Valid counters: users_created, nodes_created, hosts_created, traffic_used_bytes
    """
    if counter not in _COUNTER_QUERIES:
        logger.error("reset_admin_counter: unknown counter %s", counter)
        return None
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return None
        query = update_sql(
            ADMIN_TABLE,
            f"{counter} = 0",
            "id = $1",
            returning="*",
        )
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(query, admin_id)
            invalidate_admin_cache()
            return dict(row) if row else None
    except Exception as e:
        logger.error("reset_admin_counter failed: %s", e)
        return None


# ── Existence ────────────────────────────────────────────────────

async def admin_account_exists() -> bool:
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return False
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(
                    ADMIN_TABLE,
                    "1",
                    "LIMIT 1",
                ),
            )
            return row is not None
    except Exception as e:
        logger.error("admin_account_exists failed: %s", e)
        return False


# ── Batch helpers ────────────────────────────────────────────────

async def get_admin_usernames(admin_ids: List[int]) -> Dict[int, str]:
    if not admin_ids:
        return {}
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {}
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    ADMIN_TABLE,
                    "id, username",
                    "WHERE id = ANY($1)",
                ),
                admin_ids,
            )
            return {r["id"]: r["username"] for r in rows}
    except Exception as e:
        logger.warning("get_admin_usernames failed: %s", e)
        return {}

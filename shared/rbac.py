"""RBAC — Role-Based Access Control core module (shared).

Provides permission resolution and scope checking for both
the Telegram bot and web backend from a single codebase.

Designed to be imported directly by the bot process, and
re-exported/extended by web/backend/core/rbac.py for the web API.
"""
import json
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from shared.database import db_service
from shared.logger import logger
from shared.db_schema import ADMIN_COUNTER_COLUMNS, ADMIN_TABLE, ADMIN_ROLES_TABLE, ADMIN_PERMISSIONS_TABLE, USERS_TABLE, USER_NODE_TRAFFIC_TABLE
from shared.db_query import select_sql, update_sql, left_join_sql

# ── In-memory permission cache ──────────────────────────────────
# role_id -> {("resource", "action"), ...}
_permissions_cache: Dict[int, Set[Tuple[str, str]]] = {}
_cache_ts: float = 0
_CACHE_TTL = 60  # seconds


async def _ensure_cache() -> None:
    """Reload permission cache if stale."""
    global _permissions_cache, _cache_ts

    if time.time() - _cache_ts < _CACHE_TTL and _permissions_cache:
        return

    if not db_service.is_connected:
        return
    try:
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    ADMIN_PERMISSIONS_TABLE,
                    "role_id, resource, action",
                )
            )
            new_cache: Dict[int, Set[Tuple[str, str]]] = {}
            for row in rows:
                rid = row["role_id"]
                new_cache.setdefault(rid, set()).add((row["resource"], row["action"]))
            _permissions_cache = new_cache
            _cache_ts = time.time()
    except Exception as e:
        logger.warning("Failed to reload permissions cache: %s", e)


def invalidate_cache() -> None:
    """Force cache invalidation (call after role/permission changes)."""
    global _cache_ts
    _cache_ts = 0


# ── Permission checking ─────────────────────────────────────────

async def has_permission(role_id: Optional[int], resource: str, action: str) -> bool:
    """Check whether a role has a specific permission."""
    if role_id is None:
        return False
    await _ensure_cache()
    perms = _permissions_cache.get(role_id, set())
    return (resource, action) in perms


async def get_role_permissions(role_id: int) -> List[dict]:
    """Return all permissions for a role as list of {resource, action}."""
    await _ensure_cache()
    perms = _permissions_cache.get(role_id, set())
    return [{"resource": r, "action": a} for r, a in sorted(perms)]


async def get_all_permissions_for_role_id(role_id: int) -> Set[Tuple[str, str]]:
    """Return set of (resource, action) for a role."""
    await _ensure_cache()
    return _permissions_cache.get(role_id, set())


async def get_role_permission_set(role_id: int) -> Set[Tuple[str, str]]:
    """Alias for get_all_permissions_for_role_id — convenience."""
    return await get_all_permissions_for_role_id(role_id)


# ── SQL fragments for admin SELECT with roles JOIN ──────────────

_ADMIN_SELECT_COLS = "a.*, r.name as role_name, r.display_name as role_display_name"
_ADMIN_SELECT_FROM = (
    f"a {left_join_sql(ADMIN_ROLES_TABLE, 'r', 'r.id = a.role_id')}"
)


# ── Admin account lookup ────────────────────────────────────────

async def get_admin_account_by_telegram_id(telegram_id: int) -> Optional[dict]:
    """Fetch admin account by Telegram ID with role info."""
    if not db_service.is_connected:
        return None
    try:
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(
                    ADMIN_TABLE,
                    _ADMIN_SELECT_COLS,
                    f"{_ADMIN_SELECT_FROM} WHERE a.telegram_id = $1",
                ),
                telegram_id,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("get_admin_account_by_telegram_id failed: %s", e)
        return None


async def get_admin_account_by_id(admin_id: int) -> Optional[dict]:
    """Fetch admin account by ID with role info."""
    if not db_service.is_connected:
        return None
    try:
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(
                    ADMIN_TABLE,
                    _ADMIN_SELECT_COLS,
                    f"{_ADMIN_SELECT_FROM} WHERE a.id = $1",
                ),
                admin_id,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("get_admin_account_by_id failed: %s", e)
        return None


# ── Access policies — scope resolver ─────────────────────────────

# Cache: (account_id, role_id) -> {(resource_type, action): allowed_uuids_or_None}
# None means "full access" (no policies attached), set[uuid] means whitelist.
_scope_cache: Dict[Tuple[Optional[int], Optional[int]], Dict[Tuple[str, str], Optional[Set[str]]]] = {}
_scope_cache_ts: float = 0
_SCOPE_CACHE_TTL = 30  # seconds


def invalidate_scope_cache() -> None:
    """Force scope cache reset (call after policy changes)."""
    global _scope_cache_ts, _scope_cache
    _scope_cache.clear()
    _scope_cache_ts = 0


async def get_scope(
    account_id: Optional[int],
    role_id: Optional[int],
    role: Optional[str],
    resource_type: str,
    action: str = "view",
) -> Optional[Set[str]]:
    """Resolve allowed resource UUIDs for an admin on (resource_type, action).

    Args:
        account_id: admin_accounts.id (None for legacy/env admins)
        role_id: admin_roles.id (None for legacy/env admins)
        role: role name (e.g. "superadmin")
        resource_type: 'node', 'host', 'squad'
        action: 'view', 'edit', 'delete'

    Returns:
        None — no restriction for this resource type (superadmin, legacy admin,
               no policies attached, or existing policies don't target this type)
        set[str] — whitelist of UUIDs (may be empty — no access)
    """
    if role == "superadmin" or account_id is None:
        return None

    global _scope_cache_ts, _scope_cache
    if time.time() - _scope_cache_ts > _SCOPE_CACHE_TTL:
        _scope_cache_ts = time.time()
        _scope_cache.clear()

    cache_key = (account_id, role_id)
    per_admin = _scope_cache.get(cache_key)
    if per_admin is not None:
        cached = per_admin.get((resource_type, action), "MISS")
        if cached != "MISS":
            return cached

    if not db_service.is_connected:
        return set()  # fail-closed: при недоступной БД не выдаём полный доступ (как get_visible_user_uuids)
    try:
        rules = await db_service.get_effective_policy_rules(account_id, role_id)
        if not rules:
            _scope_cache.setdefault(cache_key, {})[(resource_type, action)] = None
            return None

        relevant = [r for r in rules if r["resource_type"] == resource_type]
        if not relevant:
            _scope_cache.setdefault(cache_key, {})[(resource_type, action)] = None
            return None

        def _rule_covers(rule_actions: List[str]) -> bool:
            if action == "view":
                return bool(rule_actions)
            return action in rule_actions

        allowed: Set[str] = set()
        for r in relevant:
            if not _rule_covers(r.get("actions") or []):
                continue
            scope_type = r.get("scope_type")
            scope_value = r.get("scope_value", "")
            if scope_type == "uuid":
                allowed.add(scope_value.lower())
            elif scope_type == "tag":
                uuids = await db_service.get_uuids_by_tag(resource_type, scope_value)
                allowed.update(u.lower() for u in uuids)

        _scope_cache.setdefault(cache_key, {})[(resource_type, action)] = allowed
        return allowed.copy()
    except Exception as e:
        logger.warning("get_scope failed for admin=%s rt=%s: %s", account_id, resource_type, e)
        return set()  # fail-closed: при ошибке резолва scope не выдаём полный доступ


def filter_by_scope(items: List[dict], scope: Optional[Set[str]], uuid_key: str = "uuid") -> List[dict]:
    """Filter a list of dicts by an allowed-UUID scope.

    If scope is None -> return items unchanged (full access).
    """
    if scope is None:
        return items
    return [it for it in items if (val := it.get(uuid_key)) and str(val).lower() in scope]


async def get_visible_user_uuids(
    account_id: Optional[int],
    role: Optional[str],
) -> Optional[Set[str]]:
    """Resolve which user UUIDs an admin can see.

    Superadmins / unknown admins see all users (return None).
    Creator scope is always applied when unrestricted_user_access = False.
    Access policies further restrict (intersect with) creator scope.

    Returns:
        None — no restrictions (superadmin, or unrestricted + no policies)
        set[str] — whitelist of user UUIDs (lowercase, possibly empty)
    """
    if role == "superadmin" or account_id is None:
        return None

    if not db_service.is_connected:
        return set()
    try:
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(
                    ADMIN_TABLE,
                    "unrestricted_user_access, role_id",
                    "WHERE id = $1",
                ),
                account_id,
            )
            if not row:
                return None
            unrestricted = row.get("unrestricted_user_access", True)
            role_id = row["role_id"]

        creator_uuids: Optional[Set[str]] = None
        if not unrestricted:
            async with db_service.acquire() as conn:
                rows = await conn.fetch(
                    select_sql(USERS_TABLE, "uuid", "WHERE created_by_admin_id = $1"),
                    account_id,
                )
                creator_uuids = {str(row["uuid"]).lower() for row in rows}

        node_scope = await get_scope(account_id, role_id, role, "node", "view")
        squad_scope = await get_scope(account_id, role_id, role, "squad", "view")

        if node_scope is None and squad_scope is None:
            return None if unrestricted else creator_uuids

        policy_uuids: Set[str] = set()

        if node_scope is not None and node_scope:
            async with db_service.acquire() as conn:
                rows = await conn.fetch(
                    select_sql(USER_NODE_TRAFFIC_TABLE, "DISTINCT user_uuid", "WHERE node_uuid = ANY($1::uuid[])"),
                    list(node_scope),
                )
                policy_uuids.update(str(r["user_uuid"]).lower() for r in rows)

        if squad_scope is not None and squad_scope:
            squad_list = list(squad_scope)
            async with db_service.acquire() as conn:
                rows = await conn.fetch(
                    select_sql(USERS_TABLE, "uuid", "WHERE external_squad_uuid = ANY($1::uuid[])"),
                    squad_list,
                )
                policy_uuids.update(str(r["uuid"]).lower() for r in rows)

                internal_rows = await conn.fetch(
                    select_sql(USERS_TABLE, "uuid::text AS uuid, raw_data", "WHERE raw_data IS NOT NULL")
                )
                squad_lower = {s.lower() for s in squad_list}
                for r in internal_rows:
                    raw = r["raw_data"]
                    if isinstance(raw, str):
                        try:
                            raw = json.loads(raw)
                        except (ValueError, TypeError):
                            continue
                    if not isinstance(raw, dict):
                        continue
                    sqs = raw.get("activeInternalSquads") or []
                    if not isinstance(sqs, list):
                        continue
                    for sq in sqs:
                        sq_uuid = None
                        if isinstance(sq, str):
                            sq_uuid = sq
                        elif isinstance(sq, dict):
                            sq_uuid = sq.get("uuid") or sq.get("squadUuid")
                        if sq_uuid and str(sq_uuid).lower() in squad_lower:
                            policy_uuids.add(str(r["uuid"]).lower())
                            break

        if unrestricted:
            return policy_uuids if policy_uuids else set()

        if creator_uuids is None:
            return policy_uuids if policy_uuids else set()

        result = creator_uuids & policy_uuids
        return result if result else set()

    except Exception as e:
        logger.warning("get_visible_user_uuids failed: %s", e)
        return set()


# ── Quota checking ──────────────────────────────────────────────

async def check_quota(admin_id: int, resource: str) -> Tuple[bool, str]:
    """Check if admin is within their resource quota.

    Returns (allowed, error_message).
    """
    account = await get_admin_account_by_id(admin_id)
    if not account:
        return False, "Admin account not found"
    if not account.get("is_active", True):
        return False, "Admin account is disabled"

    limit_field = f"max_{resource}"
    counter_field = f"{resource}_created"

    limit_val = account.get(limit_field)
    if limit_val is None:
        return True, ""

    current = account.get(counter_field, 0)
    if current >= limit_val:
        return False, f"Quota exceeded: {resource} ({current}/{limit_val})"

    return True, ""

# Query templates for each counter
_COUNTER_QUERIES = {
    "users_created": update_sql(
        ADMIN_TABLE,
        "users_created = users_created + $1",
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
    "traffic_used_bytes": update_sql(
        ADMIN_TABLE,
        "traffic_used_bytes = traffic_used_bytes + $1",
        "id = $2",
    ),
}


async def increment_usage_counter(admin_id: int, counter: str, amount: int = 1) -> bool:
    """Increment an admin's usage counter.

    Args:
        admin_id: Admin account ID
        counter: Counter name (users_created, nodes_created, hosts_created, traffic_used_bytes)
        amount: Amount to increment (can be negative for rollback)

    Returns:
        True if increment succeeded, False if limit exceeded or error

    All counters except `users_created` are clamped to a floor of 0 so a
    decrement that would otherwise go negative (e.g. caused by a stale
    local DB or a logic bug in the caller) is silently floored rather
    than corrupting the UI with nonsense negative values. This is a
    safety net — the real fix is to keep the math correct upstream.
    """
    query = _COUNTER_QUERIES.get(counter)
    if not query:
        logger.warning("Unknown counter: %s", counter)
        return False

    if amount > 0 and counter in ADMIN_COUNTER_COLUMNS:
        limit_col = ADMIN_COUNTER_COLUMNS[counter]
        query = update_sql(
            ADMIN_TABLE,
            f"{counter} = {counter} + $1",
            f"id = $2 AND ({limit_col} IS NULL OR {counter} + $1 <= {limit_col})"
        )
    elif amount < 0 and counter != "users_created":
        # Floor at 0 to prevent negative values (e.g. traffic_used_bytes).
        # `users_created` is intentionally not floored — it's a lifetime
        # event count that should never go below the current value.
        query = update_sql(
            ADMIN_TABLE,
            f"{counter} = GREATEST(0, {counter} + $1)",
            f"id = $2",
        )

    try:
        if not db_service.is_connected:
            return False
        async with db_service.acquire() as conn:
            result = await conn.execute(query, amount, admin_id)
            return "UPDATE 0" not in (result or "")
    except Exception as e:
        logger.error("increment_usage_counter failed: %s", e)
        return False


async def write_audit_log(
    admin_id: Optional[int],
    admin_username: str,
    action: str,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Write an audit log entry to the database."""
    from shared.db_schema import AUDIT_TABLE
    from shared.db_query import insert_sql

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

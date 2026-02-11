"""RBAC — Role-Based Access Control core module.

Provides:
- Database operations for roles, permissions, and admin accounts
- Permission checking helpers
- Caching layer for frequently-accessed permission data
"""
import logging
import time
from typing import Optional, Dict, List, Set, Tuple

logger = logging.getLogger(__name__)

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

    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                "SELECT role_id, resource, action FROM admin_permissions"
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


# ── Admin account database operations ───────────────────────────

async def get_admin_account_by_username(username: str) -> Optional[dict]:
    """Fetch admin account by username (case-insensitive)."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT a.*, r.name as role_name, r.display_name as role_display_name
                FROM admin_accounts a
                LEFT JOIN admin_roles r ON r.id = a.role_id
                WHERE LOWER(a.username) = LOWER($1)
                """,
                username,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("get_admin_account_by_username failed: %s", e)
        return None


async def get_admin_account_by_telegram_id(telegram_id: int) -> Optional[dict]:
    """Fetch admin account by Telegram ID."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT a.*, r.name as role_name, r.display_name as role_display_name
                FROM admin_accounts a
                LEFT JOIN admin_roles r ON r.id = a.role_id
                WHERE a.telegram_id = $1
                """,
                telegram_id,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("get_admin_account_by_telegram_id failed: %s", e)
        return None


async def get_admin_account_by_id(admin_id: int) -> Optional[dict]:
    """Fetch admin account by ID."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT a.*, r.name as role_name, r.display_name as role_display_name
                FROM admin_accounts a
                LEFT JOIN admin_roles r ON r.id = a.role_id
                WHERE a.id = $1
                """,
                admin_id,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("get_admin_account_by_id failed: %s", e)
        return None


async def list_admin_accounts() -> List[dict]:
    """List all admin accounts with role info."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return []
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT a.*, r.name as role_name, r.display_name as role_display_name
                FROM admin_accounts a
                LEFT JOIN admin_roles r ON r.id = a.role_id
                ORDER BY a.created_at ASC
                """
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("list_admin_accounts failed: %s", e)
        return []


async def create_admin_account(
    username: str,
    password_hash: Optional[str],
    telegram_id: Optional[int],
    role_id: int,
    max_users: Optional[int] = None,
    max_traffic_gb: Optional[int] = None,
    max_nodes: Optional[int] = None,
    max_hosts: Optional[int] = None,
    is_generated_password: bool = False,
    created_by: Optional[int] = None,
) -> Optional[dict]:
    """Create a new admin account. Returns the created record."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO admin_accounts
                    (username, password_hash, telegram_id, role_id,
                     max_users, max_traffic_gb, max_nodes, max_hosts,
                     is_generated_password, created_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING *
                """,
                username, password_hash, telegram_id, role_id,
                max_users, max_traffic_gb, max_nodes, max_hosts,
                is_generated_password, created_by,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("create_admin_account failed: %s", e)
        return None


async def update_admin_account(
    admin_id: int,
    **fields,
) -> Optional[dict]:
    """Update admin account fields. Returns updated record."""
    if not fields:
        return await get_admin_account_by_id(admin_id)

    allowed = {
        "username", "password_hash", "telegram_id", "role_id",
        "max_users", "max_traffic_gb", "max_nodes", "max_hosts",
        "is_active", "is_generated_password",
    }
    filtered = {k: v for k, v in fields.items() if k in allowed}
    if not filtered:
        return await get_admin_account_by_id(admin_id)

    set_parts = []
    values = []
    idx = 1
    for key, val in filtered.items():
        set_parts.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    set_parts.append(f"updated_at = NOW()")

    values.append(admin_id)
    query = (
        f"UPDATE admin_accounts SET {', '.join(set_parts)} "
        f"WHERE id = ${idx} RETURNING *"
    )

    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(query, *values)
            return dict(row) if row else None
    except Exception as e:
        logger.error("update_admin_account failed: %s", e)
        return None


async def delete_admin_account(admin_id: int) -> bool:
    """Delete admin account by ID."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return False
        async with db_service.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM admin_accounts WHERE id = $1", admin_id
            )
            return "DELETE 1" in result
    except Exception as e:
        logger.error("delete_admin_account failed: %s", e)
        return False


async def increment_usage_counter(admin_id: int, counter: str, amount: int = 1) -> bool:
    """Increment a usage counter (users_created, nodes_created, etc.)."""
    _COUNTER_QUERIES = {
        "users_created": "UPDATE admin_accounts SET users_created = users_created + $1 WHERE id = $2",
        "traffic_used_bytes": "UPDATE admin_accounts SET traffic_used_bytes = traffic_used_bytes + $1 WHERE id = $2",
        "nodes_created": "UPDATE admin_accounts SET nodes_created = nodes_created + $1 WHERE id = $2",
        "hosts_created": "UPDATE admin_accounts SET hosts_created = hosts_created + $1 WHERE id = $2",
    }
    query = _COUNTER_QUERIES.get(counter)
    if not query:
        return False
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return False
        async with db_service.acquire() as conn:
            await conn.execute(query, amount, admin_id)
            return True
    except Exception as e:
        logger.error("increment_usage_counter failed: %s", e)
        return False


async def admin_account_exists() -> bool:
    """Check if any admin account exists."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return False
        async with db_service.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM admin_accounts LIMIT 1")
            return row is not None
    except Exception as e:
        logger.error("admin_account_exists failed: %s", e)
        return False


# ── Role database operations ────────────────────────────────────

async def list_roles() -> List[dict]:
    """List all roles with permission counts."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return []
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT r.*,
                       COUNT(p.id) as permissions_count,
                       COUNT(DISTINCT a.id) as admins_count
                FROM admin_roles r
                LEFT JOIN admin_permissions p ON p.role_id = r.id
                LEFT JOIN admin_accounts a ON a.role_id = r.id
                GROUP BY r.id
                ORDER BY r.id ASC
                """
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("list_roles failed: %s", e)
        return []


async def get_role_by_id(role_id: int) -> Optional[dict]:
    """Fetch role with its permissions."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            role = await conn.fetchrow(
                "SELECT * FROM admin_roles WHERE id = $1", role_id
            )
            if not role:
                return None
            perms = await conn.fetch(
                "SELECT resource, action FROM admin_permissions WHERE role_id = $1",
                role_id,
            )
            result = dict(role)
            result["permissions"] = [dict(p) for p in perms]
            return result
    except Exception as e:
        logger.error("get_role_by_id failed: %s", e)
        return None


async def get_role_by_name(name: str) -> Optional[dict]:
    """Fetch role by name."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM admin_roles WHERE name = $1", name
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("get_role_by_name failed: %s", e)
        return None


async def create_role(
    name: str,
    display_name: str,
    description: Optional[str] = None,
    permissions: Optional[List[dict]] = None,
) -> Optional[dict]:
    """Create role with permissions. permissions = [{resource, action}, ...]"""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO admin_roles (name, display_name, description, is_system)
                    VALUES ($1, $2, $3, false)
                    RETURNING *
                    """,
                    name, display_name, description,
                )
                role = dict(row)
                if permissions:
                    for p in permissions:
                        await conn.execute(
                            """
                            INSERT INTO admin_permissions (role_id, resource, action)
                            VALUES ($1, $2, $3)
                            ON CONFLICT DO NOTHING
                            """,
                            role["id"], p["resource"], p["action"],
                        )
                invalidate_cache()
                role["permissions"] = permissions or []
                return role
    except Exception as e:
        logger.error("create_role failed: %s", e)
        return None


async def update_role(
    role_id: int,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    permissions: Optional[List[dict]] = None,
) -> Optional[dict]:
    """Update role and optionally replace all permissions."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            async with conn.transaction():
                # Update role fields
                if display_name is not None or description is not None:
                    sets = []
                    vals = []
                    idx = 1
                    if display_name is not None:
                        sets.append(f"display_name = ${idx}")
                        vals.append(display_name)
                        idx += 1
                    if description is not None:
                        sets.append(f"description = ${idx}")
                        vals.append(description)
                        idx += 1
                    vals.append(role_id)
                    await conn.execute(
                        f"UPDATE admin_roles SET {', '.join(sets)} WHERE id = ${idx}",
                        *vals,
                    )

                # Replace permissions if provided
                if permissions is not None:
                    await conn.execute(
                        "DELETE FROM admin_permissions WHERE role_id = $1", role_id
                    )
                    for p in permissions:
                        await conn.execute(
                            """
                            INSERT INTO admin_permissions (role_id, resource, action)
                            VALUES ($1, $2, $3)
                            """,
                            role_id, p["resource"], p["action"],
                        )
                    invalidate_cache()

                return await get_role_by_id(role_id)
    except Exception as e:
        logger.error("update_role failed: %s", e)
        return None


async def delete_role(role_id: int) -> bool:
    """Delete a custom role (system roles cannot be deleted)."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return False
        async with db_service.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM admin_roles WHERE id = $1 AND is_system = false", role_id
            )
            if "DELETE 1" in result:
                invalidate_cache()
                return True
            return False
    except Exception as e:
        logger.error("delete_role failed: %s", e)
        return False


# ── Audit log ───────────────────────────────────────────────────

async def write_audit_log(
    admin_id: Optional[int],
    admin_username: str,
    action: str,
    resource: Optional[str] = None,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Write an entry to the audit log."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO admin_audit_log
                    (admin_id, admin_username, action, resource, resource_id, details, ip_address)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
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
) -> Tuple[List[dict], int]:
    """Fetch audit logs with optional filters. Returns (logs, total_count)."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return [], 0

        where_parts = []
        params = []
        idx = 1
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
        if date_from:
            where_parts.append(f"created_at >= ${idx}::timestamptz")
            params.append(date_from)
            idx += 1
        if date_to:
            where_parts.append(f"created_at <= ${idx}::timestamptz")
            params.append(date_to)
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
            count_row = await conn.fetchrow(
                f"SELECT COUNT(*) FROM admin_audit_log {where_clause}", *params
            )
            total = count_row[0] if count_row else 0

            params.append(limit)
            params.append(offset)
            rows = await conn.fetch(
                f"""
                SELECT * FROM admin_audit_log
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}
                """,
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
    """Fetch audit logs for a specific resource (e.g., user history)."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return []

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM admin_audit_log
                WHERE resource = $1 AND resource_id = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                resource, resource_id, limit,
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("get_audit_logs_for_resource failed: %s", e)
        return []


async def get_audit_distinct_actions() -> List[str]:
    """Get distinct action names for filter dropdowns."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return []

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT action FROM admin_audit_log ORDER BY action"
            )
            return [r["action"] for r in rows]
    except Exception as e:
        logger.error("get_audit_distinct_actions failed: %s", e)
        return []


# ── Quota checking ──────────────────────────────────────────────

async def check_quota(admin_id: int, resource: str) -> Tuple[bool, str]:
    """Check if admin is within their resource quota.

    Returns (allowed, error_message).
    """
    account = await get_admin_account_by_id(admin_id)
    if not account:
        return False, "Admin account not found"
    if not account["is_active"]:
        return False, "Admin account is disabled"

    limit_field = f"max_{resource}"
    counter_field = f"{resource}_created"

    limit_val = account.get(limit_field)
    if limit_val is None:
        return True, ""  # Unlimited

    current = account.get(counter_field, 0)
    if current >= limit_val:
        return False, f"Quota exceeded: {resource} ({current}/{limit_val})"

    return True, ""


# ── First-run RBAC setup ───────────────────────────────────────

async def ensure_rbac_tables() -> None:
    """Ensure RBAC tables exist (for use when Alembic hasn't run yet).

    This is a safety net — in production, use Alembic migrations.
    """
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            # Just check if the table exists
            row = await conn.fetchrow(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'admin_accounts'"
            )
            if not row:
                logger.warning(
                    "RBAC tables not found. Run Alembic migrations: "
                    "alembic upgrade head"
                )
    except Exception as e:
        logger.warning("ensure_rbac_tables check failed: %s", e)

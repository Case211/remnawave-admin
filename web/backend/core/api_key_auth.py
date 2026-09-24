"""API key authentication for public API (v3).

Keys are stored as SHA-256 hashes. The raw key is shown only at creation time.
"""
import hashlib
import ipaddress
import logging
import secrets
from datetime import datetime, timezone
from typing import Optional, List

logger = logging.getLogger(__name__)

API_KEY_PREFIX = "rwa_"


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (raw_key, key_hash, key_prefix)
    """
    random_part = secrets.token_urlsafe(32)
    raw_key = f"{API_KEY_PREFIX}{random_part}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]
    return raw_key, key_hash, key_prefix


def hash_api_key(raw_key: str) -> str:
    """Hash a raw API key for lookup."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def ip_allowed(client_ip: Optional[str], allowed: Optional[List[str]]) -> bool:
    """Адрес клиента входит в список ключа; пустой список — любой адрес."""
    if not allowed:
        return True
    if not client_ip:
        return False
    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allowed:
        try:
            if addr in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


async def validate_api_key(raw_key: str, client_ip: Optional[str] = None) -> Optional[dict]:
    """Validate an API key and return its metadata.

    Returns dict with id, name, scopes, user limits — or None if invalid.
    Прошлый ключ после ротации принимается до prev_valid_until.
    """
    key_hash = hash_api_key(raw_key)

    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return None

        async with db_service.acquire() as conn:
            # Ключ отключённого или удалённого админа не работает: иначе
            # доступ уволенного переживал его отключение
            row = await conn.fetchrow(
                "SELECT k.id, k.name, k.scopes, k.is_active, k.expires_at, k.created_by_admin_id, "
                "k.allowed_ips, k.user_squads, k.user_tag, "
                "a.id AS owner_id, a.is_active AS owner_active "
                "FROM api_keys k LEFT JOIN admin_accounts a ON a.id = k.created_by_admin_id "
                "WHERE k.key_hash = $1 OR (k.prev_key_hash = $1 AND k.prev_valid_until > NOW())",
                key_hash,
            )
            if not row:
                return None

            if not row["is_active"]:
                return None
            if row["created_by_admin_id"] is not None and not (row["owner_id"] and row["owner_active"]):
                return None

            if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
                return None

            if not ip_allowed(client_ip, row.get("allowed_ips")):
                logger.warning("API key %s used from a non-allowed address %s", row["id"], client_ip)
                return None

            # Buffered last_used_at update — avoids row-lock on every request.
            try:
                from web.backend.core.api_key_usage import mark_used
                await mark_used(row["id"])
            except Exception:
                pass

            return {
                "id": row["id"],
                "name": row["name"],
                "scopes": list(row["scopes"]) if row["scopes"] else [],
                "user_squads": list(row.get("user_squads") or []),
                "user_tag": row.get("user_tag") or None,
            }
    except Exception as e:
        logger.error("API key validation error: %s", e)
        return None


async def create_api_key_record(
    name: str,
    scopes: List[str],
    admin_id: Optional[int],
    admin_username: str,
    expires_at: Optional[datetime] = None,
    description: Optional[str] = None,
    allowed_ips: Optional[List[str]] = None,
    user_squads: Optional[List[str]] = None,
    user_tag: Optional[str] = None,
) -> tuple[str, dict]:
    """Create a new API key and store it.

    Returns:
        (raw_key, record_dict)
    """
    raw_key, key_hash, key_prefix = generate_api_key()

    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO api_keys (name, key_hash, key_prefix, scopes, expires_at, "
            "created_by_admin_id, created_by_username, description, allowed_ips, user_squads, user_tag) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING *",
            name, key_hash, key_prefix, scopes, expires_at,
            admin_id, admin_username, description, allowed_ips, user_squads, user_tag,
        )

    return raw_key, dict(row)

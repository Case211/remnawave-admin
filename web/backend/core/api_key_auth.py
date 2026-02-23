"""API key authentication for public API (v3).

Keys are stored as SHA-256 hashes. The raw key is shown only at creation time.
"""
import hashlib
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


async def validate_api_key(raw_key: str) -> Optional[dict]:
    """Validate an API key and return its metadata.

    Returns dict with id, name, scopes, or None if invalid.
    """
    key_hash = hash_api_key(raw_key)

    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return None

        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name, scopes, is_active, expires_at "
                "FROM api_keys WHERE key_hash = $1",
                key_hash,
            )
            if not row:
                return None

            if not row["is_active"]:
                return None

            if row["expires_at"] and row["expires_at"] < datetime.now(timezone.utc):
                return None

            # Update last_used_at
            await conn.execute(
                "UPDATE api_keys SET last_used_at = NOW() WHERE id = $1",
                row["id"],
            )

            return {
                "id": row["id"],
                "name": row["name"],
                "scopes": list(row["scopes"]) if row["scopes"] else [],
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
            "created_by_admin_id, created_by_username) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
            name, key_hash, key_prefix, scopes, expires_at,
            admin_id, admin_username,
        )

    record = dict(row)
    for dt in ("created_at", "updated_at", "expires_at", "last_used_at"):
        if record.get(dt):
            record[dt] = record[dt].isoformat()
    return raw_key, record

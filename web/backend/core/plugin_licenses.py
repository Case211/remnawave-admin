"""License-token storage for installed plugins.

Plugins read their JWT through :func:`get_token` rather than the env var
directly so that a single panel can host several licensed plugins without
polluting the process environment.

Lookup order on the plugin side:

1. ``RWA_LICENSE_KEY`` env (legacy single-plugin installs, dev mode)
2. ``plugin_licenses`` row for the plugin id (the UI installer)

Either source is enough; the env wins to keep development workflows
deterministic.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def get_token(plugin_id: str) -> Optional[str]:
    """Return the stored JWT for ``plugin_id`` or ``None`` if not set."""
    from shared.database import db_service

    if not db_service.is_connected:
        return None
    try:
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT jwt_token FROM plugin_licenses WHERE plugin_id = $1",
                plugin_id,
            )
    except Exception:
        # Table missing on a freshly upgraded panel before migrations
        # land. Don't crash plugin discovery — the env-var path still works.
        logger.warning("plugin_licenses.read_failed", exc_info=True)
        return None
    if not row:
        return None
    token = row["jwt_token"]
    return str(token).strip() if token else None


async def list_all() -> List[Dict[str, Any]]:
    from shared.database import db_service

    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT plugin_id, wheel_name, version, installed_at, updated_at
            FROM plugin_licenses
            ORDER BY plugin_id
            """
        )
    return [dict(r) for r in rows]


async def upsert(
    *,
    plugin_id: str,
    jwt_token: str,
    wheel_name: Optional[str] = None,
    version: Optional[str] = None,
) -> None:
    from shared.database import db_service

    if not db_service.is_connected:
        raise RuntimeError("plugin_licenses: database not connected")
    async with db_service.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO plugin_licenses (plugin_id, jwt_token, wheel_name, version, installed_at, updated_at)
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            ON CONFLICT (plugin_id) DO UPDATE SET
                jwt_token = EXCLUDED.jwt_token,
                wheel_name = COALESCE(EXCLUDED.wheel_name, plugin_licenses.wheel_name),
                version = COALESCE(EXCLUDED.version, plugin_licenses.version),
                updated_at = NOW()
            """,
            plugin_id,
            jwt_token,
            wheel_name,
            version,
        )


async def delete(plugin_id: str) -> bool:
    from shared.database import db_service

    if not db_service.is_connected:
        return False
    async with db_service.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM plugin_licenses WHERE plugin_id = $1",
            plugin_id,
        )
    # asyncpg returns "DELETE n" — n>0 means a row was removed.
    return result.endswith("0") is False


# Sync wrapper for use during plugin manifest construction (which runs
# during `create_app`, before the event loop is running). The lifespan
# pre-populates a process-wide cache so plugin manifests can resolve
# their token synchronously.
_token_cache: Dict[str, str] = {}


def get_token_sync(plugin_id: str) -> Optional[str]:
    """Synchronous lookup against the in-process cache primed at startup."""
    return _token_cache.get(plugin_id)


async def prime_cache() -> None:
    """Refresh the synchronous cache from the database.

    Called from lifespan after the DB pool is up but before plugins are
    registered, so ``manifest()`` can read tokens without awaiting.
    """
    from shared.database import db_service

    _token_cache.clear()
    if not db_service.is_connected:
        return
    try:
        async with db_service.acquire() as conn:
            rows = await conn.fetch("SELECT plugin_id, jwt_token FROM plugin_licenses")
    except Exception:
        logger.warning("plugin_licenses.prime_failed", exc_info=True)
        return
    for r in rows:
        token = r.get("jwt_token")
        if token:
            _token_cache[r["plugin_id"]] = str(token).strip()


def _bust_cache_entry(plugin_id: str) -> None:
    _token_cache.pop(plugin_id, None)

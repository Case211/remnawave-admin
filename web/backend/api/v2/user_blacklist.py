"""User Blacklist API — manage Telegram user ID blacklisting."""
import logging
import re

import httpx
from fastapi import APIRouter, Depends, Query, Request

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core.errors import E, api_error
from web.backend.core.rate_limit import limiter, RATE_READ, RATE_MUTATIONS
from shared.config_service import config_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_blacklist_text(text: str, source: str) -> list[tuple[int, str, str]]:
    """Parse a blacklist file into (telegram_id, reason, source) tuples.

    Supports formats:
    - 123456789 #reason text
    - 123456789 # reason text
    - 123456789
    """
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(\d{5,15})\s*(?:#\s*(.*))?$", line)
        if match:
            tid = int(match.group(1))
            reason = (match.group(2) or "").strip() or None
            entries.append((tid, reason, source))
    return entries


@router.get("")
@limiter.limit(RATE_READ)
async def list_blacklist(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    source: str = Query(None),
    admin: AdminUser = Depends(require_permission("blocked_ips", "view")),
):
    """List blacklisted Telegram user IDs."""
    from shared.database import db_service
    items = await db_service.get_user_blacklist(limit=limit, offset=offset, source=source)
    total = await db_service.get_user_blacklist_count(source=source)
    return {"items": items, "total": total}


@router.get("/sources")
@limiter.limit(RATE_READ)
async def list_sources(
    request: Request,
    admin: AdminUser = Depends(require_permission("blocked_ips", "view")),
):
    """Get blacklist sources with entry counts."""
    from shared.database import db_service
    sources = await db_service.get_user_blacklist_sources()
    return {"sources": sources}


@router.get("/check/{telegram_id}")
@limiter.limit(RATE_READ)
async def check_blacklist(
    request: Request,
    telegram_id: int,
    admin: AdminUser = Depends(require_permission("blocked_ips", "view")),
):
    """Check if a Telegram ID is blacklisted."""
    from shared.database import db_service
    entry = await db_service.is_telegram_id_blacklisted(telegram_id)
    return {"blacklisted": entry is not None, "entry": entry}


@router.post("")
@limiter.limit(RATE_MUTATIONS)
async def add_to_blacklist(
    request: Request,
    admin: AdminUser = Depends(require_permission("blocked_ips", "create")),
):
    """Add a Telegram ID to the blacklist manually."""
    body = await request.json()
    telegram_id = body.get("telegram_id")
    reason = body.get("reason", "")

    if not telegram_id or not isinstance(telegram_id, int):
        raise api_error(400, E.INVALID_INPUT, "telegram_id (int) is required")

    from shared.database import db_service
    ok = await db_service.add_to_user_blacklist(
        telegram_id=telegram_id,
        reason=reason,
        source="manual",
        added_by=admin.username,
    )

    if config_service.get("user_blacklist_auto_block", False):
        await _auto_block_user(telegram_id)

    return {"success": ok}


@router.post("/bulk")
@limiter.limit(RATE_MUTATIONS)
async def bulk_add(
    request: Request,
    admin: AdminUser = Depends(require_permission("blocked_ips", "create")),
):
    """Bulk add Telegram IDs. Body: {telegram_ids: [int], reason: str}"""
    body = await request.json()
    telegram_ids = body.get("telegram_ids", [])
    reason = body.get("reason", "")

    if not telegram_ids or len(telegram_ids) > 1000:
        raise api_error(400, E.INVALID_INPUT, "1-1000 telegram_ids required")

    entries = [(int(tid), reason, "manual") for tid in telegram_ids]

    from shared.database import db_service
    count = await db_service.bulk_add_to_user_blacklist(entries)
    return {"added": count}


@router.delete("/{telegram_id}")
@limiter.limit(RATE_MUTATIONS)
async def remove_from_blacklist(
    request: Request,
    telegram_id: int,
    admin: AdminUser = Depends(require_permission("blocked_ips", "delete")),
):
    """Remove a Telegram ID from the blacklist."""
    from shared.database import db_service
    ok = await db_service.remove_from_user_blacklist(telegram_id)
    if not ok:
        raise api_error(404, E.NOT_FOUND, "Telegram ID not found in blacklist")
    return {"success": True}


@router.post("/sync")
@limiter.limit("5/minute")
async def sync_blacklists(
    request: Request,
    admin: AdminUser = Depends(require_permission("blocked_ips", "create")),
):
    """Manually trigger blacklist sync from configured URLs."""
    result = await sync_external_blacklists()
    return result


async def sync_external_blacklists() -> dict:
    """Fetch and sync all configured external blacklist URLs."""
    urls_raw = config_service.get("user_blacklist_urls", "")
    if not urls_raw:
        return {"synced": 0, "sources": []}

    urls = [u.strip() for u in urls_raw.replace(",", "\n").split("\n") if u.strip()]
    if not urls:
        return {"synced": 0, "sources": []}

    from shared.database import db_service
    results = []
    total_synced = 0

    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=30) as hc:
                resp = await hc.get(url)
            if resp.status_code != 200:
                logger.warning("Blacklist fetch failed for %s: HTTP %d", url, resp.status_code)
                results.append({"url": url, "status": "error", "error": f"HTTP {resp.status_code}"})
                continue

            entries = _parse_blacklist_text(resp.text, source=url)
            if entries:
                await db_service.bulk_add_to_user_blacklist(entries)
                total_synced += len(entries)
                logger.info("Blacklist synced: %d entries from %s", len(entries), url)
                results.append({"url": url, "status": "ok", "count": len(entries)})
            else:
                results.append({"url": url, "status": "ok", "count": 0})

        except Exception as e:
            logger.error("Blacklist sync failed for %s: %s", url, e)
            results.append({"url": url, "status": "error", "error": str(e)})

    # Auto-block if enabled
    if config_service.get("user_blacklist_auto_block", False) and total_synced > 0:
        await _auto_block_blacklisted_users()

    return {"synced": total_synced, "sources": results}


async def _auto_block_user(telegram_id: int):
    """Block a single user by Telegram ID via Panel API."""
    try:
        from shared.database import db_service
        user = await db_service.get_user_by_telegram_id(telegram_id)
        if not user or user.get("status") == "DISABLED":
            return
        from shared.api_client import api_client
        await api_client.disable_user(user["uuid"])
        logger.info("Auto-blocked blacklisted user: tg_id=%d uuid=%s", telegram_id, user["uuid"])
    except Exception as e:
        logger.error("Auto-block failed for tg_id=%d: %s", telegram_id, e)


async def _auto_block_blacklisted_users():
    """Check all blacklisted Telegram IDs against local users and block matches."""
    try:
        from shared.database import db_service
        blacklist = await db_service.get_user_blacklist(limit=10000)
        tg_ids = [e["telegram_id"] for e in blacklist]
        if not tg_ids:
            return

        from shared.api_client import api_client
        blocked = 0
        for tg_id in tg_ids:
            user = await db_service.get_user_by_telegram_id(tg_id)
            if user and user.get("status") != "DISABLED":
                try:
                    await api_client.disable_user(user["uuid"])
                    blocked += 1
                    logger.info("Auto-blocked blacklisted user: tg_id=%d", tg_id)
                except Exception:
                    pass
        if blocked:
            logger.info("Auto-blocked %d blacklisted users", blocked)
    except Exception as e:
        logger.error("Auto-block scan failed: %s", e)

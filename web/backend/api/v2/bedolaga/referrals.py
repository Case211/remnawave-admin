"""Bedolaga referrals — table view backed by /partners/referrers + cached user list."""
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query

from web.backend.api.deps import AdminUser, require_permission
from shared.bedolaga_client import bedolaga_client

from web.backend.api.v2.bedolaga import proxy_request

logger = logging.getLogger(__name__)
router = APIRouter()

# Cache for the (heavy) full user list. Used to resolve referrer → referrals
# without pounding Bedolaga every time a row is expanded.
_users_cache: list[dict] = []
_users_cache_ts: float = 0.0
_USERS_CACHE_TTL = 300  # 5 minutes


async def _load_all_users(force: bool = False) -> list[dict]:
    """Fetch (and cache) every Bedolaga user, paginated."""
    global _users_cache, _users_cache_ts

    now = time.time()
    if not force and _users_cache and (now - _users_cache_ts) < _USERS_CACHE_TTL:
        return _users_cache

    all_users: list[dict] = []
    offset = 0
    limit = 200
    while True:
        data = await proxy_request(lambda o=offset: bedolaga_client.get_all_users(limit=limit, offset=o))
        items = data.get("items") or []
        all_users.extend(items)
        total = data.get("total") or 0
        if len(items) < limit or (total and len(all_users) >= total):
            break
        offset += limit

    _users_cache = all_users
    _users_cache_ts = now
    return all_users


@router.get("/referrers")
async def list_referrers(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
    search: Optional[str] = Query(None, description="Filter by username/first_name/referral_code (substring)."),
    min_refs: int = Query(0, ge=0, description="Hide referrers with fewer invitees than this."),
    top_only: bool = Query(False, description="Only return referrers with ≥10 invitees."),
    sort: str = Query(
        "invited_desc",
        description="Sort order: invited_desc | invited_asc | earned_desc | earned_asc | activity_desc | created_desc",
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List referrers with their aggregates (uses Bedolaga partners endpoint)."""
    # Pull a generous page from Bedolaga so we can filter/sort server-side.
    fetch_limit = max(limit + offset, 200)
    data = await proxy_request(lambda: bedolaga_client.list_partners(limit=fetch_limit, offset=0))
    partners = data.get("items") or []
    total_from_api = int(data.get("total") or len(partners))

    if search:
        needle = search.strip().lower()
        partners = [
            p for p in partners
            if needle in (p.get("username") or "").lower()
            or needle in (p.get("first_name") or "").lower()
            or needle in (p.get("referral_code") or "").lower()
        ]

    threshold = 10 if top_only else min_refs
    if threshold > 0:
        partners = [p for p in partners if int(p.get("invited_count") or 0) >= threshold]

    sort_keys = {
        "invited_desc": (lambda p: int(p.get("invited_count") or 0), True),
        "invited_asc": (lambda p: int(p.get("invited_count") or 0), False),
        "earned_desc": (lambda p: int(p.get("total_earned_kopeks") or 0), True),
        "earned_asc": (lambda p: int(p.get("total_earned_kopeks") or 0), False),
        "activity_desc": (lambda p: p.get("last_activity") or "", True),
        "created_desc": (lambda p: p.get("created_at") or "", True),
    }
    key_fn, reverse = sort_keys.get(sort, sort_keys["invited_desc"])
    partners.sort(key=key_fn, reverse=reverse)

    total_filtered = len(partners)
    page = partners[offset:offset + limit]

    return {
        "items": page,
        "total": total_filtered,
        "total_unfiltered": total_from_api,
        "limit": limit,
        "offset": offset,
    }


@router.get("/referrers/{user_id}/refs")
async def list_referrer_refs(
    user_id: int = Path(..., ge=1),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
    refresh: bool = Query(False, description="Force-refresh the cached user list."),
):
    """List users invited by the given referrer (from cached full user dump)."""
    users = await _load_all_users(force=refresh)
    refs: list[dict] = []

    for u in users:
        if u.get("referred_by_id") != user_id:
            continue
        sub = u.get("subscription") or {}
        refs.append({
            "id": u.get("id"),
            "telegram_id": u.get("telegram_id"),
            "username": u.get("username"),
            "first_name": u.get("first_name"),
            "display_name": u.get("username") or u.get("first_name") or f"#{u.get('id')}",
            "status": u.get("status"),
            "balance_rubles": u.get("balance_rubles"),
            "subscription_status": sub.get("status"),
            "is_trial": bool(sub.get("is_trial")),
            "subscription_end": sub.get("end_date"),
            "created_at": u.get("created_at"),
            "last_activity": u.get("last_activity"),
        })

    refs.sort(key=lambda r: r.get("created_at") or "", reverse=True)

    return {
        "items": refs,
        "total": len(refs),
        "cached_at": _users_cache_ts,
    }


@router.get("/stats")
async def referrer_stats(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Aggregate counters for the referrals page header."""
    return await proxy_request(bedolaga_client.get_partner_global_stats)

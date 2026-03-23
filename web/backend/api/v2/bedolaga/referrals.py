"""Bedolaga referrals — build network from users data with caching."""
import logging
import time
from collections import defaultdict

from fastapi import APIRouter, Depends

from web.backend.api.deps import AdminUser, require_permission
from shared.bedolaga_client import bedolaga_client

from web.backend.api.v2.bedolaga import proxy_request

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory cache for referral network (heavy endpoint)
_network_cache: dict = {}
_network_cache_ts: float = 0
_NETWORK_CACHE_TTL = 300  # 5 minutes


@router.get("/network")
async def get_referral_network(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Build referral network graph from all users (cached 5 min)."""
    global _network_cache, _network_cache_ts

    now = time.time()
    if _network_cache and (now - _network_cache_ts) < _NETWORK_CACHE_TTL:
        return _network_cache

    # Fetch all users (paginated)
    all_users = []
    offset = 0
    limit = 200
    while True:
        data = await proxy_request(lambda o=offset: bedolaga_client.get_all_users(limit=limit, offset=o))
        items = data.get("items", [])
        all_users.extend(items)
        if len(items) < limit or len(all_users) >= data.get("total", 0):
            break
        offset += limit

    # Build referral counts
    referral_counts = defaultdict(int)
    for u in all_users:
        ref_by = u.get("referred_by_id")
        if ref_by:
            referral_counts[ref_by] += 1

    # Build nodes (only users who are referrers or were referred)
    users_with_refs = []
    edges = []
    involved_ids = set()

    for u in all_users:
        uid = u.get("id")
        ref_by = u.get("referred_by_id")
        if ref_by or uid in referral_counts:
            involved_ids.add(uid)
            if ref_by:
                involved_ids.add(ref_by)

    for u in all_users:
        uid = u.get("id")
        if uid not in involved_ids:
            continue

        sub = u.get("subscription")
        users_with_refs.append({
            "id": uid,
            "username": u.get("username"),
            "first_name": u.get("first_name"),
            "display_name": u.get("username") or u.get("first_name") or f"#{uid}",
            "status": u.get("status"),
            "referral_code": u.get("referral_code"),
            "referrer_id": u.get("referred_by_id"),
            "direct_referrals": referral_counts.get(uid, 0),
            "balance_rubles": u.get("balance_rubles", 0),
            "subscription_status": sub.get("status") if sub else None,
            "subscription_name": None,
            "subscription_end": sub.get("end_date") if sub else None,
            "is_trial": sub.get("is_trial", False) if sub else False,
        })

        ref_by = u.get("referred_by_id")
        if ref_by:
            edges.append({
                "source": f"user-{ref_by}",
                "target": f"user-{uid}",
                "type": "referral",
            })

    total_referrers = sum(1 for u in users_with_refs if u["direct_referrals"] > 0)

    result = {
        "users": users_with_refs,
        "edges": edges,
        "total_users": len(all_users),
        "total_referrers": total_referrers,
        "total_campaigns": 0,
        "total_earnings_kopeks": 0,
    }

    _network_cache = result
    _network_cache_ts = now
    return result

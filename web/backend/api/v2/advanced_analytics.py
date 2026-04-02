"""Advanced Analytics API — geo map, top users, trends, node metrics history."""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any

from fastapi import APIRouter, Depends, Query, Request

from web.backend.api.deps import require_permission, AdminUser
from web.backend.core.cache import cached, CACHE_TTL_LONG
from web.backend.core.rate_limit import limiter, RATE_ANALYTICS

logger = logging.getLogger(__name__)
router = APIRouter()


_city_aliases: Optional[Dict[str, str]] = None


def _get_city_aliases() -> Dict[str, str]:
    """Lazy-load city name aliases from GeoAnalyzer."""
    global _city_aliases
    if _city_aliases is None:
        from shared.violation_detector import GeoAnalyzer
        _city_aliases = GeoAnalyzer.CITY_NAME_ALIASES
    return _city_aliases


def _normalize_city_name(city: str) -> str:
    """Normalize city name for deduplication (e.g. 'Москва' -> 'moscow')."""
    if not city:
        return ""
    normalized = city.lower().strip()
    for suffix in [' city', ' gorod', ' oblast', ' region']:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].strip()
    return _get_city_aliases().get(normalized, normalized)


@router.get("/geo")
@limiter.limit(RATE_ANALYTICS)
async def get_geo_connections(
    request: Request,
    period: str = Query("7d", description="Period: 24h, 7d, 30d"),
    date_from: Optional[str] = Query(None, description="Custom start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="Custom end date (ISO 8601)"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get geographical distribution of user connections from violations/IP metadata."""
    return await _compute_geo(period=period, date_from=date_from, date_to=date_to)


@cached("analytics:geo", ttl=CACHE_TTL_LONG, key_args=("period", "date_from", "date_to"))
async def _compute_geo(period: str = "7d", date_from: Optional[str] = None, date_to: Optional[str] = None):
    """Compute geo connections (cacheable)."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"countries": [], "cities": []}

        now = datetime.now(timezone.utc)
        if date_from:
            since = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
        else:
            delta_map = {"24h": 1, "7d": 7, "30d": 30, "all": 3650}
            days = delta_map.get(period, 7)
            since = now - timedelta(days=days)

        async with db_service.acquire() as conn:
            # Get country distribution from ip_metadata table
            country_rows = await conn.fetch(
                """
                SELECT country_name, country_code, COUNT(*) as count
                FROM ip_metadata
                WHERE created_at >= $1 AND country_name IS NOT NULL
                GROUP BY country_name, country_code
                ORDER BY count DESC
                LIMIT 50
                """,
                since,
            )

            countries = [
                {
                    "country": r["country_name"],
                    "country_code": r["country_code"],
                    "count": r["count"],
                }
                for r in country_rows
            ]

            # Get city distribution (AVG coords to merge same city with different lat/lon)
            city_rows = await conn.fetch(
                """
                SELECT city, country_name,
                       AVG(latitude) as latitude,
                       AVG(longitude) as longitude,
                       COUNT(*) as count
                FROM ip_metadata
                WHERE created_at >= $1 AND city IS NOT NULL AND latitude IS NOT NULL
                GROUP BY city, country_name
                ORDER BY count DESC
                LIMIT 100
                """,
                since,
            )

            cities = []

            # Fetch all users grouped by city in a single query (avoids N+1)
            city_users_map: dict = {}
            try:
                # Join user_connections (INET) with ip_metadata (VARCHAR)
                # Use host() to strip CIDR mask from INET, with text fallback
                user_city_rows = await conn.fetch(
                    """
                    SELECT im.city, im.country_name,
                           u.username, u.uuid::text as uuid, u.status,
                           COUNT(uc.id) as connections,
                           array_agg(DISTINCT SPLIT_PART(uc.ip_address::text, '/', 1)) as ips
                    FROM user_connections uc
                    JOIN ip_metadata im
                        ON SPLIT_PART(uc.ip_address::text, '/', 1) = TRIM(im.ip_address)
                    JOIN users u ON uc.user_uuid = u.uuid
                    WHERE im.city IS NOT NULL AND im.country_name IS NOT NULL
                          AND im.created_at >= $1
                    GROUP BY im.city, im.country_name, u.uuid, u.username, u.status
                    ORDER BY im.city, connections DESC
                    """,
                    since,
                )
                for ur in user_city_rows:
                    key = (ur["city"], ur["country_name"])
                    if key not in city_users_map:
                        city_users_map[key] = []
                    city_users_map[key].append({
                        "username": ur["username"],
                        "uuid": ur["uuid"],
                        "status": ur["status"],
                        "connections": ur["connections"],
                        "ips": [str(ip) for ip in (ur["ips"] or [])],
                    })
                logger.info(
                    "Geo users: found %d user-city pairs across %d cities",
                    len(user_city_rows),
                    len(city_users_map),
                )
            except Exception as exc:
                logger.warning("Failed to fetch users by city: %s", exc)

            # Merge city_users_map by normalized city name first
            merged_users_map: Dict[tuple, list] = {}
            for (city_name, country), users_list in city_users_map.items():
                norm_key = (_normalize_city_name(city_name), country)
                if norm_key not in merged_users_map:
                    merged_users_map[norm_key] = []
                # Deduplicate users by uuid
                existing_uuids = {u["uuid"] for u in merged_users_map[norm_key]}
                for u in users_list:
                    if u["uuid"] not in existing_uuids:
                        merged_users_map[norm_key].append(u)
                        existing_uuids.add(u["uuid"])

            # Merge city rows by normalized name
            merged_cities: Dict[tuple, Dict[str, Any]] = {}
            for r in city_rows:
                if r["latitude"] is None or r["longitude"] is None:
                    continue
                norm_name = _normalize_city_name(r["city"])
                merge_key = (norm_name, r["country_name"])
                if merge_key in merged_cities:
                    entry = merged_cities[merge_key]
                    old_count = entry["count"]
                    new_count = r["count"]
                    total = old_count + new_count
                    # Weighted average of coordinates
                    entry["lat"] = (entry["lat"] * old_count + float(r["latitude"]) * new_count) / total
                    entry["lon"] = (entry["lon"] * old_count + float(r["longitude"]) * new_count) / total
                    entry["count"] = total
                else:
                    merged_cities[merge_key] = {
                        "city": r["city"],
                        "country": r["country_name"],
                        "lat": float(r["latitude"]),
                        "lon": float(r["longitude"]),
                        "count": r["count"],
                    }

            for merge_key, entry in merged_cities.items():
                users = merged_users_map.get(merge_key, [])
                cities.append({
                    **entry,
                    "unique_users": len(users),
                    "users": users,
                })

            # Sort by count descending (merging may have changed order)
            cities.sort(key=lambda c: c["count"], reverse=True)

            return {"countries": countries, "cities": cities}

    except Exception as e:
        logger.error("get_geo_connections failed: %s", e)
        return {"countries": [], "cities": []}


@router.get("/top-users")
@limiter.limit(RATE_ANALYTICS)
async def get_top_users_by_traffic(
    request: Request,
    limit: int = Query(20, ge=5, le=100),
    date_from: Optional[str] = Query(None, description="Start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="End date (ISO 8601)"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get top users by traffic consumption, optionally for a date range."""
    if date_from and date_to:
        # Panel API expects YYYY-MM-DD, not full ISO 8601
        date_from = date_from[:10]
        date_to = date_to[:10]
        return await _compute_top_users_range(date_from, date_to, limit)
    return await _compute_top_users(limit=limit)


@cached("analytics:top-users", ttl=CACHE_TTL_LONG, key_args=("limit",))
async def _compute_top_users(limit: int = 20):
    """Compute top users by traffic (cacheable, cumulative)."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"items": []}

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT uuid, username, status,
                       used_traffic_bytes,
                       traffic_limit_bytes,
                       COALESCE(
                           raw_data->'userTraffic'->>'onlineAt',
                           raw_data->>'onlineAt'
                       ) as online_at
                FROM users
                WHERE used_traffic_bytes > 0
                ORDER BY used_traffic_bytes DESC
                LIMIT $1
                """,
                limit,
            )

            items = []
            for r in rows:
                used = r["used_traffic_bytes"] or 0
                limit_bytes = r["traffic_limit_bytes"]
                usage_pct = None
                if limit_bytes and limit_bytes > 0:
                    usage_pct = round((used / limit_bytes) * 100, 1)

                items.append({
                    "uuid": str(r["uuid"]),
                    "username": r["username"],
                    "status": r["status"],
                    "used_traffic_bytes": used,
                    "traffic_limit_bytes": limit_bytes,
                    "usage_percent": usage_pct,
                    "online_at": r["online_at"],
                })

            return {"items": items}

    except Exception as e:
        logger.error("get_top_users_by_traffic failed: %s", e)
        return {"items": []}


async def _compute_top_users_range(date_from: str, date_to: str, limit: int = 20):
    """Get top users by traffic for a specific date range via Panel API."""
    try:
        from web.backend.core.api_helper import fetch_nodes_usage_by_range
        resp = await fetch_nodes_usage_by_range(date_from, date_to, top_nodes_limit=100)
        logger.debug("top-users-range response keys: %s, topNodes count: %s",
                     list(resp.keys()) if isinstance(resp, dict) else type(resp),
                     len(resp.get("topNodes", [])) if isinstance(resp, dict) else "N/A")
        if not resp:
            return {"items": [], "period": {"from": date_from, "to": date_to}}

        # Aggregate user traffic across all nodes for the period
        from shared.api_client import api_client
        from shared.database import db_service

        # Get per-node user usage and aggregate
        nodes_data = resp.get("topNodes") or resp.get("nodes") or []
        user_traffic: Dict[str, int] = {}

        for node in nodes_data[:20]:  # Limit to top 20 nodes to avoid too many API calls
            node_uuid = node.get("uuid")
            if not node_uuid:
                continue
            try:
                node_users = await api_client.get_node_users_usage(
                    node_uuid, date_from, date_to, top_users_limit=limit
                )
                payload = node_users.get("response", node_users) if isinstance(node_users, dict) else {}
                users_list = payload.get("topUsers") or payload.get("users") or []
                if isinstance(payload, list):
                    users_list = payload
                for u in users_list:
                    # Panel returns {username, total, color} — no UUID
                    uname = u.get("username") or ""
                    traffic = int(u.get("total") or u.get("totalBytes") or 0)
                    if uname and traffic > 0:
                        user_traffic[uname] = user_traffic.get(uname, 0) + traffic
            except Exception as e:
                logger.debug("Failed to get node %s users usage: %s", node_uuid[:8], e)

        # Sort by traffic and enrich with user info from DB (keyed by username)
        sorted_users = sorted(user_traffic.items(), key=lambda x: x[1], reverse=True)[:limit]
        items = []

        if db_service.is_connected and sorted_users:
            usernames = [u[0] for u in sorted_users]
            async with db_service.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT uuid, username, status, traffic_limit_bytes FROM users WHERE username = ANY($1)",
                    usernames,
                )
                user_map = {r["username"]: r for r in rows}

            for uname, traffic in sorted_users:
                info = user_map.get(uname, {})
                limit_bytes = info.get("traffic_limit_bytes")
                usage_pct = round((traffic / limit_bytes) * 100, 1) if limit_bytes and limit_bytes > 0 else None
                items.append({
                    "uuid": str(info["uuid"]) if info.get("uuid") else "",
                    "username": uname,
                    "status": info.get("status", "unknown"),
                    "used_traffic_bytes": traffic,
                    "traffic_limit_bytes": limit_bytes,
                    "usage_percent": usage_pct,
                    "online_at": None,
                })
        else:
            for uname, traffic in sorted_users:
                items.append({
                    "uuid": "", "username": uname, "status": "unknown",
                    "used_traffic_bytes": traffic, "traffic_limit_bytes": None,
                    "usage_percent": None, "online_at": None,
                })

        return {"items": items, "period": {"from": date_from, "to": date_to}}
    except Exception as e:
        logger.error("_compute_top_users_range failed: %s", e)
        return {"items": [], "period": {"from": date_from, "to": date_to}}


@router.get("/nodes-traffic")
@limiter.limit(RATE_ANALYTICS)
async def get_nodes_traffic(
    request: Request,
    date_from: str = Query(..., description="Start date (ISO 8601)"),
    date_to: str = Query(..., description="End date (ISO 8601)"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Per-node traffic breakdown for a date range."""
    # Panel API expects YYYY-MM-DD, not full ISO 8601
    date_from = date_from[:10]
    date_to = date_to[:10]
    try:
        from web.backend.core.api_helper import fetch_nodes_usage_by_range
        resp = await fetch_nodes_usage_by_range(date_from, date_to, top_nodes_limit=100)
        logger.debug("nodes-traffic response keys: %s", list(resp.keys()) if isinstance(resp, dict) else type(resp))
        if not resp:
            return {"items": [], "total_bytes": 0, "period": {"from": date_from, "to": date_to}}

        nodes_data = resp.get("topNodes") or resp.get("nodes") or []
        if not nodes_data and isinstance(resp, dict):
            logger.debug("nodes-traffic full resp sample: %s", str(resp)[:500])

        # Enrich with node names from DB
        from shared.database import db_service
        node_names = {}
        if db_service.is_connected:
            try:
                async with db_service.acquire() as conn:
                    rows = await conn.fetch("SELECT uuid, name FROM nodes")
                    node_names = {str(r["uuid"]): r["name"] for r in rows}
            except Exception:
                pass

        items = []
        total = 0
        for n in nodes_data:
            uid = n.get("uuid", "")
            traffic = int(n.get("total", 0) or 0)
            total += traffic
            items.append({
                "uuid": uid,
                "name": node_names.get(uid, uid[:8]),
                "traffic_bytes": traffic,
            })

        # Add percentage
        for item in items:
            item["percent"] = round((item["traffic_bytes"] / total) * 100, 1) if total > 0 else 0

        return {"items": items, "total_bytes": total, "period": {"from": date_from, "to": date_to}}
    except Exception as e:
        logger.error("get_nodes_traffic failed: %s", e)
        return {"items": [], "total_bytes": 0, "period": {"from": date_from, "to": date_to}}


@router.get("/trends")
@limiter.limit(RATE_ANALYTICS)
async def get_trends(
    request: Request,
    metric: str = Query("users", description="Metric: users, traffic, violations"),
    period: str = Query("30d", description="Period: 7d, 30d, 90d"),
    date_from: Optional[str] = Query(None, description="Custom start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="Custom end date (ISO 8601)"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get trend data — growth of users, traffic, violations over time."""
    return await _compute_trends(metric=metric, period=period, date_from=date_from, date_to=date_to)


@cached("analytics:trends", ttl=CACHE_TTL_LONG, key_args=("metric", "period", "date_from", "date_to"))
async def _compute_trends(metric: str = "users", period: str = "30d", date_from: Optional[str] = None, date_to: Optional[str] = None):
    """Compute trends (cacheable)."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"series": [], "total_growth": 0}

        now = datetime.now(timezone.utc)
        if date_from:
            since = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
        else:
            delta_map = {"7d": 7, "30d": 30, "90d": 90, "all": 3650}
            days = delta_map.get(period, 30)
            since = now - timedelta(days=days)

        async with db_service.acquire() as conn:
            if metric == "users":
                rows = await conn.fetch(
                    """
                    SELECT DATE(created_at) as day, COUNT(*) as count
                    FROM users
                    WHERE created_at >= $1
                    GROUP BY DATE(created_at)
                    ORDER BY day
                    """,
                    since,
                )
                series = [{"date": str(r["day"]), "value": r["count"]} for r in rows]

                # Total growth
                total_before = await conn.fetchval(
                    "SELECT COUNT(*) FROM users WHERE created_at < $1", since
                )
                total_now = await conn.fetchval("SELECT COUNT(*) FROM users")
                growth = total_now - (total_before or 0)

            elif metric == "violations":
                rows = await conn.fetch(
                    """
                    SELECT DATE(detected_at) as day, COUNT(*) as count
                    FROM violations
                    WHERE detected_at >= $1
                    GROUP BY DATE(detected_at)
                    ORDER BY day
                    """,
                    since,
                )
                series = [{"date": str(r["day"]), "value": r["count"]} for r in rows]
                growth = sum(s["value"] for s in series)

            elif metric == "traffic":
                # Approximate: sum of used_traffic_bytes from users created in each day
                rows = await conn.fetch(
                    """
                    SELECT DATE(created_at) as day,
                           SUM(used_traffic_bytes) as total_bytes
                    FROM users
                    WHERE created_at >= $1
                    GROUP BY DATE(created_at)
                    ORDER BY day
                    """,
                    since,
                )
                series = [
                    {"date": str(r["day"]), "value": int(r["total_bytes"] or 0)}
                    for r in rows
                ]
                growth = sum(s["value"] for s in series)

            else:
                series = []
                growth = 0

            return {
                "series": series,
                "metric": metric,
                "period": period,
                "total_growth": growth,
            }

    except Exception as e:
        logger.error("get_trends failed: %s", e)
        return {"series": [], "total_growth": 0}


@router.get("/shared-hwids")
@limiter.limit(RATE_ANALYTICS)
async def get_shared_hwids(
    request: Request,
    min_users: int = Query(2, ge=2, le=10),
    limit: int = Query(50, ge=5, le=200),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get HWIDs shared across multiple user accounts."""
    return await _compute_shared_hwids(min_users=min_users, limit=limit)


@cached("analytics:shared-hwids", ttl=CACHE_TTL_LONG, key_args=("min_users", "limit"))
async def _compute_shared_hwids(min_users: int = 2, limit: int = 50):
    """Compute shared HWIDs (cacheable)."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"items": [], "total_shared_hwids": 0}

        items = await db_service.get_shared_hwids(min_users=min_users, limit=limit)
        return {"items": items, "total_shared_hwids": len(items)}

    except Exception as e:
        logger.error("get_shared_hwids failed: %s", e)
        return {"items": [], "total_shared_hwids": 0}


@router.get("/providers")
@limiter.limit(RATE_ANALYTICS)
async def get_providers(
    request: Request,
    period: str = Query("7d", description="Period: 24h, 7d, 30d"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get provider/ASN analytics from ip_metadata."""
    return await _compute_providers(period=period)


@cached("analytics:providers", ttl=CACHE_TTL_LONG, key_args=("period",))
async def _compute_providers(period: str = "7d"):
    """Compute provider analytics (cacheable)."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"connection_types": [], "top_asn": [], "flags": {}}

        now = datetime.now(timezone.utc)
        delta_map = {"24h": 1, "7d": 7, "30d": 30, "all": 3650}
        days = delta_map.get(period, 7)
        since = now - timedelta(days=days)

        async with db_service.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM ip_metadata WHERE created_at >= $1",
                since,
            ) or 1

            # Connection types distribution
            type_rows = await conn.fetch(
                """
                SELECT COALESCE(connection_type, 'unknown') as type,
                       COUNT(*) as count
                FROM ip_metadata
                WHERE created_at >= $1
                GROUP BY connection_type
                ORDER BY count DESC
                """,
                since,
            )
            connection_types = [
                {"type": r["type"], "count": r["count"],
                 "percent": round(r["count"] / total * 100, 1)}
                for r in type_rows
            ]

            # Top ASN organizations
            asn_rows = await conn.fetch(
                """
                SELECT asn, asn_org, COUNT(*) as count
                FROM ip_metadata
                WHERE created_at >= $1 AND asn IS NOT NULL
                GROUP BY asn, asn_org
                ORDER BY count DESC
                LIMIT 10
                """,
                since,
            )
            top_asn = [
                {"asn": r["asn"], "org": r["asn_org"] or f"AS{r['asn']}",
                 "count": r["count"],
                 "percent": round(r["count"] / total * 100, 1)}
                for r in asn_rows
            ]

            # Flags: VPN/Proxy/Tor/Hosting percentages
            flag_row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE is_vpn = true) as vpn,
                    COUNT(*) FILTER (WHERE is_proxy = true) as proxy,
                    COUNT(*) FILTER (WHERE is_tor = true) as tor,
                    COUNT(*) FILTER (WHERE is_hosting = true) as hosting
                FROM ip_metadata
                WHERE created_at >= $1
                """,
                since,
            )
            flags = {
                "vpn": {"count": flag_row["vpn"], "percent": round(flag_row["vpn"] / total * 100, 1)},
                "proxy": {"count": flag_row["proxy"], "percent": round(flag_row["proxy"] / total * 100, 1)},
                "tor": {"count": flag_row["tor"], "percent": round(flag_row["tor"] / total * 100, 1)},
                "hosting": {"count": flag_row["hosting"], "percent": round(flag_row["hosting"] / total * 100, 1)},
            }

            return {"connection_types": connection_types, "top_asn": top_asn, "flags": flags, "total": total}

    except Exception as e:
        logger.error("get_providers failed: %s", e)
        return {"connection_types": [], "top_asn": [], "flags": {}}


@router.get("/retention")
@limiter.limit(RATE_ANALYTICS)
async def get_retention(
    request: Request,
    weeks: int = Query(12, ge=4, le=52, description="Number of weeks to analyze"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get cohort retention analysis."""
    return await _compute_retention(weeks=weeks)


@cached("analytics:retention", ttl=CACHE_TTL_LONG, key_args=("weeks",))
async def _compute_retention(weeks: int = 12):
    """Compute retention cohorts (cacheable)."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"cohorts": [], "overall_retention": 0}

        now = datetime.now(timezone.utc)
        since = now - timedelta(weeks=weeks)

        async with db_service.acquire() as conn:
            # Get cohorts by registration week
            rows = await conn.fetch(
                """
                WITH cohorts AS (
                    SELECT
                        DATE_TRUNC('week', created_at)::date as cohort_week,
                        uuid,
                        status,
                        used_traffic_bytes,
                        expire_at
                    FROM users
                    WHERE created_at >= $1
                )
                SELECT
                    cohort_week,
                    COUNT(*) as total_users,
                    COUNT(*) FILTER (WHERE status = 'ACTIVE') as active_users,
                    COUNT(*) FILTER (WHERE used_traffic_bytes > 0) as with_traffic,
                    COUNT(*) FILTER (WHERE expire_at IS NOT NULL AND expire_at > NOW()) as with_active_sub
                FROM cohorts
                GROUP BY cohort_week
                ORDER BY cohort_week
                """,
                since,
            )

            cohorts = []
            total_registered = 0
            total_retained = 0

            for r in rows:
                total = r["total_users"]
                active = r["active_users"]
                retention_pct = round(active / total * 100, 1) if total > 0 else 0
                traffic_pct = round(r["with_traffic"] / total * 100, 1) if total > 0 else 0
                sub_pct = round(r["with_active_sub"] / total * 100, 1) if total > 0 else 0

                total_registered += total
                total_retained += active

                cohorts.append({
                    "week": str(r["cohort_week"]),
                    "total_users": total,
                    "active_users": active,
                    "retention_percent": retention_pct,
                    "with_traffic_percent": traffic_pct,
                    "with_active_sub_percent": sub_pct,
                })

            overall = round(total_retained / total_registered * 100, 1) if total_registered > 0 else 0

            return {
                "cohorts": cohorts,
                "overall_retention": overall,
                "total_registered": total_registered,
                "total_retained": total_retained,
            }

    except Exception as e:
        logger.error("get_retention failed: %s", e)
        return {"cohorts": [], "overall_retention": 0}


# ── Node Metrics History ────────────────────────────────────────

@router.get("/node-metrics-history")
@limiter.limit(RATE_ANALYTICS)
async def get_node_metrics_history(
    request: Request,
    period: str = Query("24h", description="Period: 24h, 7d, 30d"),
    node_uuid: Optional[str] = Query(None, description="Filter by node UUID"),
    admin: AdminUser = Depends(require_permission("fleet", "view")),
):
    """Get historical node metrics averages for the given period."""
    return await _compute_node_metrics_history(period=period, node_uuid=node_uuid)


@cached("analytics:node-metrics-history", ttl=300, key_args=("period", "node_uuid"))
async def _compute_node_metrics_history(period: str = "24h", node_uuid: Optional[str] = None):
    from shared.database import db_service

    try:
        if not db_service.is_connected:
            return {"nodes": [], "timeseries": []}

        nodes = await db_service.get_node_metrics_history(period=period, node_uuid=node_uuid)
        timeseries = await db_service.get_node_metrics_timeseries(period=period, node_uuid=node_uuid)

        # Group timeseries by bucket
        buckets: dict = defaultdict(dict)
        node_names: dict = {}
        for row in timeseries:
            b = row.get("bucket")
            bucket_str = b.isoformat() if hasattr(b, "isoformat") else str(b)
            uid = str(row["node_uuid"])
            node_names[uid] = row.get("node_name", uid[:8])
            buckets[bucket_str][uid] = {
                "cpu": float(row["avg_cpu"]) if row.get("avg_cpu") is not None else None,
                "memory": float(row["avg_memory"]) if row.get("avg_memory") is not None else None,
                "disk": float(row["avg_disk"]) if row.get("avg_disk") is not None else None,
            }

        ts_data = [{"timestamp": k, "nodes": v} for k, v in sorted(buckets.items())]

        return {
            "nodes": [
                {
                    "node_uuid": str(n["node_uuid"]),
                    "node_name": n.get("node_name", ""),
                    "avg_cpu": float(n["avg_cpu"]) if n.get("avg_cpu") is not None else None,
                    "avg_memory": float(n["avg_memory"]) if n.get("avg_memory") is not None else None,
                    "avg_disk": float(n["avg_disk"]) if n.get("avg_disk") is not None else None,
                    "max_cpu": float(n["max_cpu"]) if n.get("max_cpu") is not None else None,
                    "max_memory": float(n["max_memory"]) if n.get("max_memory") is not None else None,
                    "max_disk": float(n["max_disk"]) if n.get("max_disk") is not None else None,
                    "samples_count": n.get("samples_count", 0),
                }
                for n in nodes
            ],
            "timeseries": ts_data,
            "node_names": node_names,
        }
    except Exception as e:
        logger.error("get_node_metrics_history failed: %s", e)
        return {"nodes": [], "timeseries": []}


# ── Torrent / P2P Analytics ────────────────────────────────────────

@router.get("/torrent-stats")
@limiter.limit(RATE_ANALYTICS)
async def get_torrent_stats(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="Days to look back"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get torrent/P2P event statistics and timeseries."""
    return await _compute_torrent_stats(days=days)


@cached("analytics:torrent-stats", ttl=300, key_args=("days",))
async def _compute_torrent_stats(days: int = 7):
    from shared.database import db_service

    empty = {"summary": {}, "timeseries": [], "top_users": [], "top_destinations": []}

    # 1. Try Panel API (torrent-blocker plugin) — primary source
    panel_data = await _fetch_panel_torrent_stats()

    # 2. Local DB (node-agent torrent events) — secondary source
    local_data = None
    try:
        if db_service.is_connected:
            stats = await db_service.get_torrent_stats(days=days)
            timeseries = await db_service.get_torrent_timeseries(days=days)
            top_destinations = await db_service.get_torrent_top_destinations(days=days)
            local_data = {
                "summary": {
                    "total_events": stats.get("total_events", 0),
                    "unique_users": stats.get("unique_users", 0),
                    "unique_destinations": stats.get("unique_destinations", 0),
                    "affected_nodes": stats.get("affected_nodes", 0),
                },
                "timeseries": timeseries,
                "top_users": stats.get("top_users", []),
                "top_destinations": top_destinations,
            }
    except Exception as e:
        logger.debug("Local torrent stats failed: %s", e)

    # 3. Merge: Panel API summary + local timeseries/destinations
    if panel_data and local_data:
        # Sum up totals from both sources
        ps = panel_data["summary"]
        ls = local_data["summary"]
        return {
            "summary": {
                "total_events": ps.get("total_events", 0) + ls.get("total_events", 0),
                "unique_users": ps.get("unique_users", 0) + ls.get("unique_users", 0),
                "unique_destinations": ls.get("unique_destinations", 0),
                "affected_nodes": ps.get("affected_nodes", 0) + ls.get("affected_nodes", 0),
            },
            "timeseries": local_data["timeseries"],
            "top_users": panel_data["top_users"] + local_data["top_users"],
            "top_destinations": local_data["top_destinations"],
        }
    if panel_data:
        return panel_data
    if local_data:
        return local_data
    return empty


async def _fetch_panel_torrent_stats():
    """Fetch torrent blocker stats from Panel API."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_torrent_blocker_stats()
        resp = result.get("response", {})
        stats = resp.get("stats", {})
        top_users_raw = resp.get("topUsers", [])
        top_nodes_raw = resp.get("topNodes", [])

        top_users = [
            {"user_uuid": u.get("uuid", ""), "username": u.get("username", ""), "event_count": u.get("total", 0)}
            for u in top_users_raw
        ]

        return {
            "summary": {
                "total_events": stats.get("totalReports", 0),
                "unique_users": stats.get("distinctUsers", 0),
                "unique_destinations": 0,  # Panel API doesn't track destinations
                "affected_nodes": stats.get("distinctNodes", 0),
                "reports_last_24h": stats.get("reportsLast24Hours", 0),
            },
            "timeseries": [],  # Panel API doesn't provide timeseries
            "top_users": top_users,
            "top_destinations": [],
            "top_nodes": [
                {"name": n.get("name", ""), "uuid": n.get("uuid", ""), "country_code": n.get("countryCode", ""), "total": n.get("total", 0)}
                for n in top_nodes_raw
            ],
        }
    except Exception as e:
        logger.debug("Panel torrent-blocker stats unavailable: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════
# Cohort Analysis — Retention Matrix & Churn
# ══════════════════════════════════════════════════════════════════


@router.get("/cohort-matrix")
@limiter.limit(RATE_ANALYTICS)
async def get_cohort_matrix(
    request: Request,
    granularity: str = Query("week", regex="^(week|month)$"),
    months: int = Query(3, ge=1, le=12),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get cohort retention matrix — shows activity by cohort over time."""
    return await _compute_cohort_matrix(granularity=granularity, months=months)


@cached("analytics:cohort-matrix", ttl=CACHE_TTL_LONG, key_args=("granularity", "months"))
async def _compute_cohort_matrix(granularity: str = "week", months: int = 3):
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"cohorts": [], "periods": []}

        trunc = "week" if granularity == "week" else "month"
        since = datetime.now(timezone.utc) - timedelta(days=months * 30)

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                f"""
                WITH cohorts AS (
                    SELECT uuid, DATE_TRUNC('{trunc}', created_at)::date AS cohort
                    FROM users
                    WHERE created_at >= $1
                ),
                activity AS (
                    SELECT
                        c.cohort,
                        DATE_TRUNC('{trunc}', uc.connected_at)::date AS activity_period,
                        COUNT(DISTINCT c.uuid) AS active_users
                    FROM cohorts c
                    JOIN user_connections uc ON uc.user_uuid = c.uuid
                    WHERE uc.connected_at >= $1
                    GROUP BY c.cohort, activity_period
                ),
                cohort_sizes AS (
                    SELECT cohort, COUNT(*) AS total_users FROM cohorts GROUP BY cohort
                )
                SELECT
                    cs.cohort,
                    cs.total_users,
                    a.activity_period,
                    COALESCE(a.active_users, 0) AS active_users
                FROM cohort_sizes cs
                LEFT JOIN activity a ON a.cohort = cs.cohort
                ORDER BY cs.cohort, a.activity_period
                """,
                since,
            )

        # Build matrix: {cohort: {period: active_users, ...}, ...}
        cohort_data: Dict[str, Dict[str, Any]] = {}
        periods_set = set()

        for r in rows:
            cohort = str(r["cohort"])
            total = r["total_users"]
            period = str(r["activity_period"]) if r["activity_period"] else None
            active = r["active_users"]

            if cohort not in cohort_data:
                cohort_data[cohort] = {"cohort": cohort, "total_users": total, "periods": {}}

            if period:
                periods_set.add(period)
                retention_pct = round(active / total * 100, 1) if total > 0 else 0
                cohort_data[cohort]["periods"][period] = {
                    "active_users": active,
                    "retention_percent": retention_pct,
                }

        periods = sorted(periods_set)
        cohorts = sorted(cohort_data.values(), key=lambda x: x["cohort"])

        return {"cohorts": cohorts, "periods": periods, "granularity": granularity}
    except Exception as e:
        logger.error("Cohort matrix failed: %s", e)
        return {"cohorts": [], "periods": [], "granularity": granularity}


@router.get("/churn")
@limiter.limit(RATE_ANALYTICS)
async def get_churn_rate(
    request: Request,
    period: str = Query("month", regex="^(week|month)$"),
    months: int = Query(6, ge=1, le=24),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get churn rate over time — users who stopped being active."""
    return await _compute_churn(period=period, months=months)


@cached("analytics:churn", ttl=CACHE_TTL_LONG, key_args=("period", "months"))
async def _compute_churn(period: str = "month", months: int = 6):
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"series": [], "avg_churn": 0}

        trunc = "week" if period == "week" else "month"
        since = datetime.now(timezone.utc) - timedelta(days=months * 30)

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                f"""
                WITH periods AS (
                    SELECT
                        DATE_TRUNC('{trunc}', connected_at)::date AS p,
                        COUNT(DISTINCT user_uuid) AS active_users
                    FROM user_connections
                    WHERE connected_at >= $1
                    GROUP BY p
                    ORDER BY p
                ),
                total_by_period AS (
                    SELECT
                        DATE_TRUNC('{trunc}', created_at)::date AS p,
                        COUNT(*) AS new_users
                    FROM users
                    WHERE created_at >= $1
                    GROUP BY p
                )
                SELECT
                    p.p AS period,
                    p.active_users,
                    COALESCE(t.new_users, 0) AS new_users,
                    LAG(p.active_users) OVER (ORDER BY p.p) AS prev_active
                FROM periods p
                LEFT JOIN total_by_period t ON t.p = p.p
                ORDER BY p.p
                """,
                since,
            )

        series = []
        total_churn = 0
        churn_count = 0

        for r in rows:
            active = r["active_users"]
            prev = r["prev_active"]
            new = r["new_users"]

            churn_rate = 0
            churned = 0
            if prev and prev > 0:
                # Churned = previous active + new - current active
                churned = max(0, prev + new - active)
                churn_rate = round(churned / prev * 100, 1)
                total_churn += churn_rate
                churn_count += 1

            series.append({
                "period": str(r["period"]),
                "active_users": active,
                "new_users": new,
                "churned_users": churned,
                "churn_rate": churn_rate,
            })

        avg_churn = round(total_churn / churn_count, 1) if churn_count > 0 else 0

        return {"series": series, "avg_churn": avg_churn, "period": period}
    except Exception as e:
        logger.error("Churn rate failed: %s", e)
        return {"series": [], "avg_churn": 0, "period": period}


@router.get("/ltv")
@limiter.limit(RATE_ANALYTICS)
async def get_ltv_estimate(
    request: Request,
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Estimate user Lifetime Value based on activity duration and billing data."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"avg_lifetime_days": 0, "estimated_ltv": 0}

        async with db_service.acquire() as conn:
            # Average user lifetime (days between created_at and last activity)
            lifetime_row = await conn.fetchrow(
                """
                SELECT
                    AVG(EXTRACT(EPOCH FROM (last_seen - created_at)) / 86400) AS avg_lifetime_days,
                    COUNT(*) AS sample_size
                FROM (
                    SELECT
                        u.created_at,
                        MAX(uc.connected_at) AS last_seen
                    FROM users u
                    JOIN user_connections uc ON uc.user_uuid = u.uuid
                    WHERE u.created_at >= NOW() - INTERVAL '6 months'
                    GROUP BY u.uuid, u.created_at
                    HAVING MAX(uc.connected_at) > u.created_at
                ) sub
                """
            )

        avg_days = float(lifetime_row["avg_lifetime_days"] or 0)
        sample_size = lifetime_row["sample_size"] or 0

        # Get cost per user from billing
        ltv = 0
        try:
            from shared.api_client import api_client
            nodes_result = await api_client.get_infra_billing_nodes()
            nodes_resp = nodes_result.get("response", {})
            stats = nodes_resp.get("stats", {}) if isinstance(nodes_resp, dict) else {}
            monthly_cost = float(stats.get("currentMonthPayments", 0) or 0)

            active_count = (await db_service.get_users_count_by_status()).get("active", 1) or 1
            cost_per_user_month = monthly_cost / active_count if active_count > 0 else 0
            avg_months = avg_days / 30
            ltv = round(cost_per_user_month * avg_months, 2)
        except Exception:
            pass

        return {
            "avg_lifetime_days": round(avg_days, 1),
            "sample_size": sample_size,
            "estimated_ltv": ltv,
        }
    except Exception as e:
        logger.error("LTV estimate failed: %s", e)
        return {"avg_lifetime_days": 0, "sample_size": 0, "estimated_ltv": 0}


# ══════════════════════════════════════════════════════════════════
# Geo-Balancing Recommendations
# ══════════════════════════════════════════════════════════════════


@router.get("/geo-balance")
@limiter.limit(RATE_ANALYTICS)
async def get_geo_balance(
    request: Request,
    days: int = Query(7, ge=1, le=90),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Geo-balancing analysis: node load distribution and recommendations."""
    return await _compute_geo_balance(days=days)


@cached("analytics:geo-balance", ttl=900, key_args=("days",))
async def _compute_geo_balance(days: int = 7):
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"nodes": [], "recommendations": [], "regions": []}

        since = datetime.now(timezone.utc) - timedelta(days=days)

        async with db_service.acquire() as conn:
            # Node load + metrics (users_online is in raw_data, not a column)
            node_rows = await conn.fetch(
                """
                SELECT uuid::text, name, is_connected, is_disabled,
                       cpu_usage, memory_usage, disk_usage,
                       COALESCE((raw_data->>'usersOnline')::int, 0) AS users_online,
                       traffic_used_bytes
                FROM nodes ORDER BY name
                """
            )

            # User distribution by country per node (from connections + ip_metadata)
            geo_rows = await conn.fetch(
                """
                SELECT
                    uc.node_uuid::text AS node_uuid,
                    COALESCE(im.country_code, '??') AS country_code,
                    COALESCE(im.country_name, 'Unknown') AS country_name,
                    COUNT(DISTINCT uc.user_uuid) AS user_count,
                    COUNT(*) AS connection_count
                FROM user_connections uc
                LEFT JOIN ip_metadata im
                    ON SPLIT_PART(uc.ip_address::text, '/', 1) = TRIM(im.ip_address)
                WHERE uc.connected_at >= $1
                GROUP BY uc.node_uuid, im.country_code, im.country_name
                ORDER BY user_count DESC
                """,
                since,
            )

            # Total users per country (for unserved region detection)
            country_totals = await conn.fetch(
                """
                SELECT
                    COALESCE(im.country_code, '??') AS country_code,
                    COALESCE(im.country_name, 'Unknown') AS country_name,
                    COUNT(DISTINCT uc.user_uuid) AS user_count
                FROM user_connections uc
                LEFT JOIN ip_metadata im
                    ON SPLIT_PART(uc.ip_address::text, '/', 1) = TRIM(im.ip_address)
                WHERE uc.connected_at >= $1
                GROUP BY im.country_code, im.country_name
                ORDER BY user_count DESC
                LIMIT 30
                """,
                since,
            )

        # Build node data with geo breakdown
        node_geo: Dict[str, List] = defaultdict(list)
        for r in geo_rows:
            node_geo[r["node_uuid"]].append({
                "country_code": r["country_code"],
                "country_name": r["country_name"],
                "user_count": r["user_count"],
                "connection_count": r["connection_count"],
            })

        nodes = []
        overloaded = []
        for n in node_rows:
            uuid = n["uuid"]
            cpu = n["cpu_usage"] or 0
            mem = n["memory_usage"] or 0
            disk = n["disk_usage"] or 0
            online = n["users_online"] or 0

            is_overloaded = cpu > 80 or mem > 85 or disk > 90
            node_data = {
                "uuid": uuid,
                "name": n["name"],
                "is_connected": n["is_connected"],
                "is_disabled": n["is_disabled"],
                "cpu_usage": round(cpu, 1),
                "memory_usage": round(mem, 1),
                "disk_usage": round(disk, 1),
                "users_online": online,
                "is_overloaded": is_overloaded,
                "top_countries": node_geo.get(uuid, [])[:5],
            }
            nodes.append(node_data)
            if is_overloaded and n["is_connected"]:
                overloaded.append(node_data)

        # Compute median users_online for comparison
        online_values = [n["users_online"] for n in nodes if n["is_connected"] and not n["is_disabled"]]
        median_online = sorted(online_values)[len(online_values) // 2] if online_values else 0

        # Generate recommendations
        recommendations = []

        for n in overloaded:
            reasons = []
            if n["cpu_usage"] > 80:
                reasons.append(f"CPU {n['cpu_usage']}%")
            if n["memory_usage"] > 85:
                reasons.append(f"RAM {n['memory_usage']}%")
            if n["disk_usage"] > 90:
                reasons.append(f"Disk {n['disk_usage']}%")
            recommendations.append({
                "type": "overloaded",
                "severity": "critical" if n["cpu_usage"] > 90 or n["memory_usage"] > 90 else "warning",
                "node": n["name"],
                "node_uuid": n["uuid"],
                "message": f"Нода {n['name']} перегружена: {', '.join(reasons)}",
            })

        # Detect nodes with way more users than median
        for n in nodes:
            if n["is_connected"] and not n["is_disabled"] and median_online > 0:
                if n["users_online"] > median_online * 2.5 and n["users_online"] > 50:
                    recommendations.append({
                        "type": "unbalanced",
                        "severity": "warning",
                        "node": n["name"],
                        "node_uuid": n["uuid"],
                        "message": f"Нода {n['name']}: {n['users_online']} юзеров (медиана {median_online}). Рассмотрите перераспределение.",
                    })

        # Regions summary
        regions = [
            {"country_code": r["country_code"], "country_name": r["country_name"], "user_count": r["user_count"]}
            for r in country_totals
        ]

        return {
            "nodes": nodes,
            "recommendations": recommendations,
            "regions": regions,
            "median_users_online": median_online,
            "overloaded_count": len(overloaded),
        }
    except Exception as e:
        logger.error("Geo-balance failed: %s", e)
        return {"nodes": [], "recommendations": [], "regions": []}

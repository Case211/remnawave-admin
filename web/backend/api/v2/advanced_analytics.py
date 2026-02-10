"""Advanced Analytics API — geo map, top users, trends."""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query

from web.backend.api.deps import require_permission, AdminUser

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/geo")
async def get_geo_connections(
    period: str = Query("7d", description="Period: 24h, 7d, 30d"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get geographical distribution of user connections from violations/IP metadata."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return {"countries": [], "cities": []}

        now = datetime.now(timezone.utc)
        delta_map = {"24h": 1, "7d": 7, "30d": 30}
        days = delta_map.get(period, 7)
        since = now - timedelta(days=days)

        async with db_service.acquire() as conn:
            # Get country distribution from ip_metadata table
            country_rows = await conn.fetch(
                """
                SELECT country, country_code, COUNT(*) as count
                FROM ip_metadata
                WHERE lookup_time >= $1 AND country IS NOT NULL
                GROUP BY country, country_code
                ORDER BY count DESC
                LIMIT 50
                """,
                since,
            )

            countries = [
                {
                    "country": r["country"],
                    "country_code": r["country_code"],
                    "count": r["count"],
                }
                for r in country_rows
            ]

            # Get city distribution
            city_rows = await conn.fetch(
                """
                SELECT city, country, lat, lon, COUNT(*) as count
                FROM ip_metadata
                WHERE lookup_time >= $1 AND city IS NOT NULL AND lat IS NOT NULL
                GROUP BY city, country, lat, lon
                ORDER BY count DESC
                LIMIT 100
                """,
                since,
            )

            cities = [
                {
                    "city": r["city"],
                    "country": r["country"],
                    "lat": float(r["lat"]) if r["lat"] else None,
                    "lon": float(r["lon"]) if r["lon"] else None,
                    "count": r["count"],
                }
                for r in city_rows
                if r["lat"] is not None and r["lon"] is not None
            ]

            return {"countries": countries, "cities": cities}

    except Exception as e:
        logger.error("get_geo_connections failed: %s", e)
        return {"countries": [], "cities": []}


@router.get("/top-users")
async def get_top_users_by_traffic(
    limit: int = Query(20, ge=5, le=100),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get top users by traffic consumption."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return {"items": []}

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT uuid, username, status,
                       used_traffic_bytes, lifetime_used_traffic_bytes,
                       traffic_limit_bytes, online_at
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
                    "uuid": r["uuid"],
                    "username": r["username"],
                    "status": r["status"],
                    "used_traffic_bytes": used,
                    "lifetime_used_traffic_bytes": r["lifetime_used_traffic_bytes"] or 0,
                    "traffic_limit_bytes": limit_bytes,
                    "usage_percent": usage_pct,
                    "online_at": str(r["online_at"]) if r["online_at"] else None,
                })

            return {"items": items}

    except Exception as e:
        logger.error("get_top_users_by_traffic failed: %s", e)
        return {"items": []}


@router.get("/trends")
async def get_trends(
    metric: str = Query("users", description="Metric: users, traffic, violations"),
    period: str = Query("30d", description="Period: 7d, 30d, 90d"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get trend data — growth of users, traffic, violations over time."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return {"series": [], "total_growth": 0}

        now = datetime.now(timezone.utc)
        delta_map = {"7d": 7, "30d": 30, "90d": 90}
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

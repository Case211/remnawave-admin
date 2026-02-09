"""Analytics API endpoints."""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, Query

from web.backend.api.deps import get_current_admin, AdminUser, require_permission
from web.backend.core.api_helper import (
    fetch_users_from_api, fetch_nodes_from_api, fetch_hosts_from_api,
    fetch_bandwidth_stats, fetch_nodes_realtime_usage,
    fetch_nodes_usage_by_range, _normalize,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class OverviewStats(BaseModel):
    """Overview statistics."""

    total_users: int = 0
    active_users: int = 0
    disabled_users: int = 0
    expired_users: int = 0
    total_nodes: int = 0
    online_nodes: int = 0
    offline_nodes: int = 0
    disabled_nodes: int = 0
    total_hosts: int = 0
    violations_today: int = 0
    violations_week: int = 0
    total_traffic_bytes: int = 0
    users_online: int = 0


class TrafficStats(BaseModel):
    """Traffic statistics."""

    total_bytes: int = 0
    today_bytes: int = 0
    week_bytes: int = 0
    month_bytes: int = 0


async def _get_users_data() -> List[Dict[str, Any]]:
    """Get users from DB (normalized), fall back to API if DB is empty/unavailable."""
    try:
        from src.services.database import db_service
        if db_service.is_connected:
            users = await db_service.get_all_users(limit=50000)
            if users:
                # Normalize: flatten nested userTraffic, add snake_case aliases
                return [_normalize(u) for u in users]
    except Exception as e:
        logger.debug("DB users fetch failed: %s", e)

    # Fall back to Remnawave API (already normalized)
    return await fetch_users_from_api()


async def _get_nodes_data() -> List[Dict[str, Any]]:
    """Get nodes from DB (normalized), fall back to API if DB is empty/unavailable."""
    try:
        from src.services.database import db_service
        if db_service.is_connected:
            nodes = await db_service.get_all_nodes()
            if nodes:
                return [_normalize(n) for n in nodes]
    except Exception as e:
        logger.debug("DB nodes fetch failed: %s", e)

    # Fall back to Remnawave API (already normalized)
    return await fetch_nodes_from_api()


async def _get_hosts_data() -> List[Dict[str, Any]]:
    """Get hosts from DB, fall back to API if DB is empty/unavailable."""
    try:
        from src.services.database import db_service
        if db_service.is_connected:
            hosts = await db_service.get_all_hosts()
            if hosts:
                return hosts
    except Exception as e:
        logger.debug("DB hosts fetch failed: %s", e)

    # Fall back to Remnawave API
    return await fetch_hosts_from_api()


async def _get_violation_counts() -> Dict[str, int]:
    """Get violation counts for today and this week from DB."""
    try:
        from src.services.database import db_service
        if db_service.is_connected:
            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=7)

            today_stats = await db_service.get_violations_stats_for_period(
                start_date=today_start,
                end_date=now,
            )
            week_stats = await db_service.get_violations_stats_for_period(
                start_date=week_start,
                end_date=now,
            )
            return {
                'today': today_stats.get('total', 0),
                'week': week_stats.get('total', 0),
            }
    except Exception as e:
        logger.debug("DB violation counts fetch failed: %s", e)
    return {'today': 0, 'week': 0}


def _get_user_status(user: Dict[str, Any]) -> str:
    """Extract user status from user data (handles both DB and API formats).
    Always returns lowercase for consistent comparison.
    """
    status = user.get('status') or user.get('Status') or ''
    return status.lower().strip()


def _is_node_connected(node: Dict[str, Any]) -> bool:
    """Check if node is connected (handles both DB and API formats)."""
    return bool(node.get('is_connected') or node.get('isConnected'))


def _is_node_disabled(node: Dict[str, Any]) -> bool:
    """Check if node is disabled (handles both DB and API formats)."""
    return bool(node.get('is_disabled') or node.get('isDisabled'))


def _get_traffic_bytes(user: Dict[str, Any]) -> int:
    """Extract used traffic bytes from user data (handles all formats)."""
    # Direct fields (snake_case or camelCase)
    val = user.get('used_traffic_bytes') or user.get('usedTrafficBytes')
    # Nested userTraffic object (raw API response from DB)
    if not val:
        user_traffic = user.get('userTraffic')
        if isinstance(user_traffic, dict):
            val = user_traffic.get('usedTrafficBytes') or user_traffic.get('used_traffic_bytes')
    # Lifetime traffic as fallback
    if not val:
        val = user.get('lifetimeUsedTrafficBytes')
        if not val:
            user_traffic = user.get('userTraffic')
            if isinstance(user_traffic, dict):
                val = user_traffic.get('lifetimeUsedTrafficBytes')
    if not val:
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def _get_node_traffic(node: Dict[str, Any]) -> int:
    """Extract traffic bytes from node data."""
    val = (
        node.get('traffic_used_bytes')
        or node.get('trafficUsedBytes')
        or node.get('traffic_total_bytes')
        or node.get('trafficTotalBytes')
        or 0
    )
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def _get_users_online(node: Dict[str, Any]) -> int:
    """Extract users online from node data."""
    val = node.get('users_online') or node.get('usersOnline') or 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


@router.get("/overview", response_model=OverviewStats)
async def get_overview(
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get overview statistics for dashboard."""
    try:
        users = await _get_users_data()
        nodes = await _get_nodes_data()
        hosts = await _get_hosts_data()
        violations = await _get_violation_counts()

        # Calculate user stats (case-insensitive status comparison)
        total_users = len(users)
        active_users = sum(1 for u in users if _get_user_status(u) == 'active')
        disabled_users = sum(1 for u in users if _get_user_status(u) == 'disabled')
        expired_users = sum(1 for u in users if _get_user_status(u) == 'expired')

        # Calculate node stats
        total_nodes = len(nodes)
        disabled_nodes = sum(1 for n in nodes if _is_node_disabled(n))
        online_nodes = sum(1 for n in nodes if _is_node_connected(n) and not _is_node_disabled(n))
        offline_nodes = total_nodes - online_nodes - disabled_nodes

        # Calculate host stats
        total_hosts = len(hosts)

        # Get total traffic from Remnawave bandwidth stats API
        total_traffic_bytes = 0
        bw_stats = await fetch_bandwidth_stats()
        if bw_stats:
            current_year = bw_stats.get('bandwidthCurrentYear', {})
            try:
                total_traffic_bytes = int(current_year.get('current') or 0)
            except (ValueError, TypeError):
                pass
        # Fallback to user/node traffic sums if bandwidth API unavailable
        if not total_traffic_bytes:
            user_traffic = sum(_get_traffic_bytes(u) for u in users)
            node_traffic = sum(_get_node_traffic(n) for n in nodes)
            total_traffic_bytes = max(user_traffic, node_traffic)
        users_online = sum(_get_users_online(n) for n in nodes)

        return OverviewStats(
            total_users=total_users,
            active_users=active_users,
            disabled_users=disabled_users,
            expired_users=expired_users,
            total_nodes=total_nodes,
            online_nodes=online_nodes,
            offline_nodes=offline_nodes,
            disabled_nodes=disabled_nodes,
            total_hosts=total_hosts,
            violations_today=violations['today'],
            violations_week=violations['week'],
            total_traffic_bytes=total_traffic_bytes,
            users_online=users_online,
        )

    except Exception as e:
        logger.error("Error getting overview stats: %s", e)
        return OverviewStats()


def _parse_bandwidth_bytes(val: Any) -> int:
    """Parse a bandwidth value (string, float, or number) to int bytes."""
    if val is None:
        return 0
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def _sum_top_nodes_total(response: Dict[str, Any]) -> int:
    """Sum the 'total' field across all topNodes in a nodes-usage response."""
    top_nodes = response.get('topNodes', [])
    if not isinstance(top_nodes, list):
        return 0
    total = 0
    for node in top_nodes:
        try:
            total += int(node.get('total', 0) or 0)
        except (ValueError, TypeError):
            pass
    return total


@router.get("/traffic", response_model=TrafficStats)
async def get_traffic_stats(
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get traffic statistics with time breakdowns.

    Primary source for period traffic (today/week/month):
        /api/bandwidth-stats/nodes with date ranges — queries persistent DB data,
        survives service restarts.
    Fallback for period traffic:
        /api/system/stats/bandwidth — in-memory counters that reset on restart.
    Total traffic:
        /api/system/stats/bandwidth → bandwidthCurrentYear (persistent).
    """
    try:
        now = datetime.utcnow()
        today_bytes = 0
        week_bytes = 0
        month_bytes = 0
        total_bytes = 0

        # --- Period traffic from date-range queries (primary, persistent) ---
        # API expects date format YYYY-MM-DD (not full ISO datetime)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_date = (now + timedelta(days=1)).strftime('%Y-%m-%d')

        try:
            resp = await fetch_nodes_usage_by_range(
                start=today_start.strftime('%Y-%m-%d'),
                end=end_date,
            )
            if resp:
                today_bytes = _sum_top_nodes_total(resp)
        except Exception as e:
            logger.debug("Failed to fetch today's traffic by range: %s", e)

        try:
            resp = await fetch_nodes_usage_by_range(
                start=week_start.strftime('%Y-%m-%d'),
                end=end_date,
            )
            if resp:
                week_bytes = _sum_top_nodes_total(resp)
        except Exception as e:
            logger.debug("Failed to fetch weekly traffic by range: %s", e)

        try:
            resp = await fetch_nodes_usage_by_range(
                start=month_start.strftime('%Y-%m-%d'),
                end=end_date,
            )
            if resp:
                month_bytes = _sum_top_nodes_total(resp)
        except Exception as e:
            logger.debug("Failed to fetch monthly traffic by range: %s", e)

        # --- Total traffic + fallback for periods from bandwidth stats ---
        bw_stats = await fetch_bandwidth_stats()
        if bw_stats:
            logger.debug(
                "Bandwidth stats response keys: %s",
                list(bw_stats.keys()) if isinstance(bw_stats, dict) else type(bw_stats),
            )

            current_year = bw_stats.get('bandwidthCurrentYear', {})
            total_bytes = _parse_bandwidth_bytes(current_year.get('current'))

            # Use bandwidth stats as fallback if date-range queries returned 0
            if not week_bytes:
                last_seven = bw_stats.get('bandwidthLastSevenDays', {})
                week_bytes = _parse_bandwidth_bytes(last_seven.get('current'))

            if not month_bytes:
                calendar_month = bw_stats.get('bandwidthCalendarMonth', {})
                month_bytes = _parse_bandwidth_bytes(calendar_month.get('current'))
                if not month_bytes:
                    last_30 = bw_stats.get('bandwidthLast30Days', {})
                    month_bytes = _parse_bandwidth_bytes(last_30.get('current'))

            if not today_bytes:
                last_two_days = bw_stats.get('bandwidthLastTwoDays', {})
                today_bytes = _parse_bandwidth_bytes(last_two_days.get('current'))

        # Fallback for today: realtime node stats (only if still 0)
        if not today_bytes:
            realtime = await fetch_nodes_realtime_usage()
            if realtime:
                realtime_total = 0
                for node_rt in realtime:
                    realtime_total += _parse_bandwidth_bytes(node_rt.get('totalBytes'))
                if realtime_total > 0:
                    today_bytes = realtime_total

        # Fallback for total: sum user/node traffic
        if not total_bytes:
            users = await _get_users_data()
            nodes = await _get_nodes_data()
            user_traffic = sum(_get_traffic_bytes(u) for u in users)
            node_traffic = sum(_get_node_traffic(n) for n in nodes)
            total_bytes = max(user_traffic, node_traffic)

        return TrafficStats(
            total_bytes=total_bytes,
            today_bytes=today_bytes,
            week_bytes=week_bytes,
            month_bytes=month_bytes,
        )

    except Exception as e:
        logger.error("Error getting traffic stats: %s", e)
        return TrafficStats()


@router.get("/users")
async def get_user_stats(
    period: str = Query("week", regex="^(day|week|month)$"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get user statistics for charts."""
    return {
        "period": period,
        "data": [],
    }


@router.get("/connections")
async def get_connection_stats(
    period: str = Query("day", regex="^(hour|day|week)$"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get connection statistics for charts."""
    return {
        "period": period,
        "data": [],
    }

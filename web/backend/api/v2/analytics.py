"""Analytics API endpoints."""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, Query, Request

from web.backend.api.deps import get_current_admin, AdminUser, require_permission
from web.backend.core.cache import cached, CACHE_TTL_SHORT, CACHE_TTL_MEDIUM, CACHE_TTL_LONG
from web.backend.core.rate_limit import limiter, RATE_ANALYTICS
from web.backend.core.update_checker import get_latest_version
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


class TimeseriesPoint(BaseModel):
    """Single point in a timeseries."""
    timestamp: str
    value: int = 0


class NodeTimeseriesPoint(BaseModel):
    """Single point in per-node timeseries."""
    timestamp: str
    total: int = 0
    nodes: Dict[str, int] = {}


class TimeseriesResponse(BaseModel):
    """Response for timeseries endpoint."""
    period: str
    metric: str
    points: List[TimeseriesPoint] = []
    node_points: List[NodeTimeseriesPoint] = []
    node_names: Dict[str, str] = {}


class DeltaStats(BaseModel):
    """Delta indicators for stat cards."""
    users_delta: Optional[float] = None         # % change in total users (24h)
    users_online_delta: Optional[int] = None    # change in online users
    traffic_delta: Optional[float] = None       # % change in traffic (vs yesterday)
    violations_delta: Optional[int] = None      # change in violations (today vs yesterday)
    nodes_delta: Optional[int] = None           # change in online nodes


class NodeFleetItem(BaseModel):
    """Compact node info for dashboard fleet view."""
    uuid: str
    name: str = ''
    address: str = ''
    port: int = 443
    is_connected: bool = False
    is_disabled: bool = False
    is_xray_running: bool = False
    xray_version: Optional[str] = None
    users_online: int = 0
    traffic_today_bytes: int = 0
    traffic_total_bytes: int = 0
    uptime_seconds: Optional[int] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    memory_total_bytes: Optional[int] = None
    memory_used_bytes: Optional[int] = None
    disk_usage: Optional[float] = None
    disk_total_bytes: Optional[int] = None
    disk_used_bytes: Optional[int] = None
    last_seen_at: Optional[str] = None
    download_speed_bps: int = 0
    upload_speed_bps: int = 0
    metrics_updated_at: Optional[str] = None


class NodeFleetResponse(BaseModel):
    """Response for node fleet endpoint."""
    nodes: List[NodeFleetItem] = []
    total: int = 0
    online: int = 0
    offline: int = 0
    disabled: int = 0


class SystemComponentStatus(BaseModel):
    """Status of a system component."""
    name: str
    status: str  # "online", "offline", "degraded", "unknown"
    details: Dict[str, Any] = {}


class SystemComponentsResponse(BaseModel):
    """Response for system components endpoint."""
    components: List[SystemComponentStatus] = []
    uptime_seconds: Optional[int] = None
    version: str = ""


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


@cached("analytics:overview", ttl=CACHE_TTL_SHORT)
async def _compute_overview() -> OverviewStats:
    """Compute overview stats (cacheable)."""
    users = await _get_users_data()
    nodes = await _get_nodes_data()
    hosts = await _get_hosts_data()
    violations = await _get_violation_counts()

    total_users = len(users)
    active_users = sum(1 for u in users if _get_user_status(u) == 'active')
    disabled_users = sum(1 for u in users if _get_user_status(u) == 'disabled')
    expired_users = sum(1 for u in users if _get_user_status(u) == 'expired')

    total_nodes = len(nodes)
    disabled_nodes = sum(1 for n in nodes if _is_node_disabled(n))
    online_nodes = sum(1 for n in nodes if _is_node_connected(n) and not _is_node_disabled(n))
    offline_nodes = total_nodes - online_nodes - disabled_nodes
    total_hosts = len(hosts)

    total_traffic_bytes = 0
    bw_stats = await fetch_bandwidth_stats()
    if bw_stats:
        current_year = bw_stats.get('bandwidthCurrentYear', {})
        try:
            total_traffic_bytes = int(current_year.get('current') or 0)
        except (ValueError, TypeError):
            pass
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


@router.get("/overview", response_model=OverviewStats)
@limiter.limit(RATE_ANALYTICS)
async def get_overview(
    request: Request,
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get overview statistics for dashboard."""
    try:
        return await _compute_overview()

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


@cached("analytics:traffic", ttl=CACHE_TTL_MEDIUM)
async def _compute_traffic() -> TrafficStats:
    """Compute traffic stats (cacheable)."""
    now = datetime.utcnow()
    today_bytes = 0
    week_bytes = 0
    month_bytes = 0
    total_bytes = 0

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_date = (now + timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        resp = await fetch_nodes_usage_by_range(start=today_start.strftime('%Y-%m-%d'), end=end_date)
        if resp:
            today_bytes = _sum_top_nodes_total(resp)
    except Exception as e:
        logger.debug("Failed to fetch today's traffic by range: %s", e)

    try:
        resp = await fetch_nodes_usage_by_range(start=week_start.strftime('%Y-%m-%d'), end=end_date)
        if resp:
            week_bytes = _sum_top_nodes_total(resp)
    except Exception as e:
        logger.debug("Failed to fetch weekly traffic by range: %s", e)

    try:
        resp = await fetch_nodes_usage_by_range(start=month_start.strftime('%Y-%m-%d'), end=end_date)
        if resp:
            month_bytes = _sum_top_nodes_total(resp)
    except Exception as e:
        logger.debug("Failed to fetch monthly traffic by range: %s", e)

    bw_stats = await fetch_bandwidth_stats()
    if bw_stats:
        current_year = bw_stats.get('bandwidthCurrentYear', {})
        total_bytes = _parse_bandwidth_bytes(current_year.get('current'))

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

    if not today_bytes:
        realtime = await fetch_nodes_realtime_usage()
        if realtime:
            realtime_total = sum(_parse_bandwidth_bytes(r.get('totalBytes')) for r in realtime)
            if realtime_total > 0:
                today_bytes = realtime_total

    if not total_bytes:
        users = await _get_users_data()
        nodes = await _get_nodes_data()
        user_traffic = sum(_get_traffic_bytes(u) for u in users)
        node_traffic = sum(_get_node_traffic(n) for n in nodes)
        total_bytes = max(user_traffic, node_traffic)

    return TrafficStats(
        total_bytes=total_bytes, today_bytes=today_bytes,
        week_bytes=week_bytes, month_bytes=month_bytes,
    )


@router.get("/traffic", response_model=TrafficStats)
@limiter.limit(RATE_ANALYTICS)
async def get_traffic_stats(
    request: Request,
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get traffic statistics with time breakdowns."""
    try:
        return await _compute_traffic()
    except Exception as e:
        logger.error("Error getting traffic stats: %s", e)
        return TrafficStats()


@router.get("/timeseries", response_model=TimeseriesResponse)
@limiter.limit(RATE_ANALYTICS)
async def get_timeseries(
    request: Request,
    period: str = Query("24h", regex="^(24h|7d|30d)$"),
    metric: str = Query("traffic", regex="^(traffic|connections)$"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get timeseries data for traffic or connections charts.

    For traffic: returns bytes per time bucket from the upstream bandwidth-stats API.
    For connections: returns users_online snapshots per node.
    """
    try:
        now = datetime.utcnow()
        node_names: Dict[str, str] = {}

        if metric == "traffic":
            # Determine date range based on period
            if period == "24h":
                start_dt = now - timedelta(hours=24)
            elif period == "7d":
                start_dt = now - timedelta(days=7)
            else:  # 30d
                start_dt = now - timedelta(days=30)

            start_str = start_dt.strftime('%Y-%m-%d')
            end_str = (now + timedelta(days=1)).strftime('%Y-%m-%d')

            resp = await fetch_nodes_usage_by_range(
                start=start_str, end=end_str, top_nodes_limit=50,
            )

            points: List[TimeseriesPoint] = []
            node_points: List[NodeTimeseriesPoint] = []

            if resp:
                logger.debug(
                    "Timeseries raw response keys: %s",
                    list(resp.keys()) if isinstance(resp, dict) else type(resp),
                )

                # Extract node names from topNodes
                top_nodes = resp.get('topNodes', [])
                for tn in top_nodes:
                    uid = tn.get('uuid', '')
                    name = tn.get('nodeName') or tn.get('name') or uid[:8]
                    if uid:
                        node_names[uid] = name

                # Extract series data
                series = resp.get('series', [])
                logger.debug(
                    "Timeseries series: type=%s, len=%s, sample=%s",
                    type(series).__name__,
                    len(series) if isinstance(series, list) else 'N/A',
                    series[:2] if isinstance(series, list) and series else 'empty',
                )

                if isinstance(series, list) and series:
                    for entry in series:
                        if not isinstance(entry, dict):
                            continue
                        ts = entry.get('date') or entry.get('timestamp') or ''
                        total = 0
                        per_node: Dict[str, int] = {}
                        for key, val in entry.items():
                            if key in ('date', 'timestamp'):
                                continue
                            try:
                                v = int(float(val))
                            except (ValueError, TypeError):
                                continue
                            per_node[key] = v
                            total += v
                        if ts:
                            points.append(TimeseriesPoint(timestamp=ts, value=total))
                            node_points.append(NodeTimeseriesPoint(
                                timestamp=ts, total=total, nodes=per_node,
                            ))

                # Fallback: if series is empty but topNodes has data,
                # build daily points by querying each day individually
                if not points and top_nodes:
                    points, node_points = await _build_daily_points(
                        start_dt, now, node_names, period,
                    )

            return TimeseriesResponse(
                period=period,
                metric=metric,
                points=points,
                node_points=node_points,
                node_names=node_names,
            )

        else:  # connections
            # Get current node data with users_online
            nodes = await _get_nodes_data()
            node_points_list: List[NodeTimeseriesPoint] = []
            total_online = 0
            per_node: Dict[str, int] = {}

            for n in nodes:
                uid = n.get('uuid', '')
                name = n.get('name') or uid[:8]
                online = 0
                try:
                    online = int(n.get('users_online') or n.get('usersOnline') or 0)
                except (ValueError, TypeError):
                    pass
                if uid:
                    node_names[uid] = name
                    per_node[uid] = online
                    total_online += online

            # Current snapshot as a single point
            ts = now.strftime('%Y-%m-%dT%H:%M')
            node_points_list.append(NodeTimeseriesPoint(
                timestamp=ts, total=total_online, nodes=per_node,
            ))

            return TimeseriesResponse(
                period=period,
                metric=metric,
                points=[TimeseriesPoint(timestamp=ts, value=total_online)],
                node_points=node_points_list,
                node_names=node_names,
            )

    except Exception as e:
        logger.error("Error getting timeseries: %s", e)
        return TimeseriesResponse(period=period, metric=metric)


async def _build_daily_points(
    start_dt: datetime,
    end_dt: datetime,
    node_names: Dict[str, str],
    period: str,
) -> tuple:
    """Build per-day timeseries by querying each day individually.

    Used as fallback when the upstream API's series field is empty
    but topNodes data is available.
    """
    from datetime import timedelta

    points: List[TimeseriesPoint] = []
    node_points: List[NodeTimeseriesPoint] = []

    # Determine days to query
    if period == "24h":
        # For 24h, just show today and yesterday
        days = [end_dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1),
                end_dt.replace(hour=0, minute=0, second=0, microsecond=0)]
    else:
        num_days = 7 if period == "7d" else 30
        days = []
        for i in range(num_days):
            d = end_dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=num_days - 1 - i)
            days.append(d)

    for day in days:
        day_str = day.strftime('%Y-%m-%d')
        next_day_str = (day + timedelta(days=1)).strftime('%Y-%m-%d')
        try:
            resp = await fetch_nodes_usage_by_range(
                start=day_str, end=next_day_str, top_nodes_limit=50,
            )
            if resp:
                total = 0
                per_node: Dict[str, int] = {}
                for tn in resp.get('topNodes', []):
                    uid = tn.get('uuid', '')
                    try:
                        val = int(tn.get('total', 0) or 0)
                    except (ValueError, TypeError):
                        val = 0
                    if uid:
                        per_node[uid] = val
                        total += val
                        # Ensure node name is captured
                        if uid not in node_names:
                            node_names[uid] = tn.get('nodeName') or tn.get('name') or uid[:8]
                points.append(TimeseriesPoint(timestamp=day_str, value=total))
                node_points.append(NodeTimeseriesPoint(
                    timestamp=day_str, total=total, nodes=per_node,
                ))
            else:
                points.append(TimeseriesPoint(timestamp=day_str, value=0))
                node_points.append(NodeTimeseriesPoint(timestamp=day_str, total=0, nodes={}))
        except Exception as e:
            logger.debug("Failed to fetch day %s traffic: %s", day_str, e)
            points.append(TimeseriesPoint(timestamp=day_str, value=0))
            node_points.append(NodeTimeseriesPoint(timestamp=day_str, total=0, nodes={}))

    return points, node_points


def _generate_synthetic_traffic_points(period: str, now: datetime) -> List[TimeseriesPoint]:
    """Generate empty timeseries points as placeholders when no upstream data is available."""
    points = []
    if period == "24h":
        for i in range(24):
            ts = (now - timedelta(hours=23 - i)).strftime('%Y-%m-%dT%H:00')
            points.append(TimeseriesPoint(timestamp=ts, value=0))
    elif period == "7d":
        for i in range(7):
            ts = (now - timedelta(days=6 - i)).strftime('%Y-%m-%d')
            points.append(TimeseriesPoint(timestamp=ts, value=0))
    else:  # 30d
        for i in range(30):
            ts = (now - timedelta(days=29 - i)).strftime('%Y-%m-%d')
            points.append(TimeseriesPoint(timestamp=ts, value=0))
    return points


@cached("analytics:deltas", ttl=CACHE_TTL_MEDIUM)
async def _compute_deltas() -> DeltaStats:
    """Compute delta stats (cacheable)."""
    now = datetime.utcnow()
    result = DeltaStats()

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    end_str = (now + timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        today_resp = await fetch_nodes_usage_by_range(
            start=today_start.strftime('%Y-%m-%d'), end=end_str,
        )
        yesterday_resp = await fetch_nodes_usage_by_range(
            start=yesterday_start.strftime('%Y-%m-%d'),
            end=today_start.strftime('%Y-%m-%d'),
        )
        today_traffic = _sum_top_nodes_total(today_resp) if today_resp else 0
        yesterday_traffic = _sum_top_nodes_total(yesterday_resp) if yesterday_resp else 0
        if yesterday_traffic > 0:
            result.traffic_delta = round(
                ((today_traffic - yesterday_traffic) / yesterday_traffic) * 100, 1
            )
        elif today_traffic > 0:
            result.traffic_delta = 100.0
    except Exception as e:
        logger.debug("Failed to compute traffic delta: %s", e)

    try:
        from src.services.database import db_service
        if db_service.is_connected:
            today_stats = await db_service.get_violations_stats_for_period(
                start_date=today_start, end_date=now,
            )
            yesterday_stats = await db_service.get_violations_stats_for_period(
                start_date=yesterday_start, end_date=today_start,
            )
            today_v = today_stats.get('total', 0)
            yesterday_v = yesterday_stats.get('total', 0)
            result.violations_delta = today_v - yesterday_v
    except Exception as e:
        logger.debug("Failed to compute violations delta: %s", e)

    return result


@router.get("/deltas", response_model=DeltaStats)
@limiter.limit(RATE_ANALYTICS)
async def get_delta_stats(
    request: Request,
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get delta indicators for dashboard stat cards."""
    try:
        return await _compute_deltas()
    except Exception as e:
        logger.error("Error getting delta stats: %s", e)
        return DeltaStats()


@router.get("/node-fleet", response_model=NodeFleetResponse)
@limiter.limit(RATE_ANALYTICS)
async def get_node_fleet(
    request: Request,
    admin: AdminUser = Depends(require_permission("fleet", "view")),
):
    """Get compact node fleet data for dashboard cards.

    Returns all nodes with enriched metrics (traffic today, speed, uptime).
    """
    try:
        from web.backend.api.v2.nodes import _get_nodes_list, _ensure_node_snake_case

        nodes = await _get_nodes_list()
        nodes = [_ensure_node_snake_case(n) for n in nodes]

        # Enrich with today's traffic
        now = datetime.utcnow()
        today_str = now.strftime('%Y-%m-%d')
        tomorrow_str = (now + timedelta(days=1)).strftime('%Y-%m-%d')

        try:
            resp = await fetch_nodes_usage_by_range(start=today_str, end=tomorrow_str)
            if resp:
                for tn in resp.get('topNodes', []):
                    uid = tn.get('uuid')
                    if uid:
                        try:
                            today_val = int(tn.get('total', 0) or 0)
                        except (ValueError, TypeError):
                            today_val = 0
                        for n in nodes:
                            if n.get('uuid') == uid:
                                n['traffic_today_bytes'] = today_val
                                break
        except Exception as e:
            logger.debug("Fleet: date-range traffic failed: %s", e)

        # Enrich with realtime speed data
        try:
            realtime = await fetch_nodes_realtime_usage()
            rt_map = {r.get('nodeUuid'): r for r in realtime}
            for n in nodes:
                rt = rt_map.get(n.get('uuid'))
                if rt:
                    n['download_speed_bps'] = int(rt.get('downloadSpeedBps') or 0)
                    n['upload_speed_bps'] = int(rt.get('uploadSpeedBps') or 0)
                    if not n.get('traffic_today_bytes'):
                        try:
                            n['traffic_today_bytes'] = int(rt.get('totalBytes') or 0)
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            logger.debug("Fleet: realtime fetch failed: %s", e)

        # Enrich with system metrics from DB (collected by Node Agent)
        try:
            from src.services.database import db_service
            if db_service.is_connected:
                db_nodes = await db_service.get_all_nodes()
                metrics_map = {}
                for dn in db_nodes:
                    raw = dn.get('raw_data') or dn
                    uid = dn.get('uuid') or (raw.get('uuid') if isinstance(raw, dict) else None)
                    if uid:
                        metrics_map[str(uid)] = dn
                for n in nodes:
                    db_node = metrics_map.get(n.get('uuid'))
                    if db_node:
                        if db_node.get('cpu_usage') is not None:
                            n['cpu_usage'] = db_node['cpu_usage']
                        if db_node.get('memory_usage') is not None:
                            n['memory_usage'] = db_node['memory_usage']
                        if db_node.get('memory_total_bytes') is not None:
                            n['memory_total_bytes'] = db_node['memory_total_bytes']
                        if db_node.get('memory_used_bytes') is not None:
                            n['memory_used_bytes'] = db_node['memory_used_bytes']
                        if db_node.get('disk_usage') is not None:
                            n['disk_usage'] = db_node['disk_usage']
                        if db_node.get('disk_total_bytes') is not None:
                            n['disk_total_bytes'] = db_node['disk_total_bytes']
                        if db_node.get('disk_used_bytes') is not None:
                            n['disk_used_bytes'] = db_node['disk_used_bytes']
                        if db_node.get('uptime_seconds') is not None:
                            n['uptime_seconds'] = db_node['uptime_seconds']
                        if db_node.get('metrics_updated_at') is not None:
                            mua = db_node['metrics_updated_at']
                            n['metrics_updated_at'] = mua.isoformat() if hasattr(mua, 'isoformat') else str(mua)
        except Exception as e:
            logger.debug("Fleet: DB metrics enrichment failed: %s", e)

        # Build response items
        fleet_items = []
        online = 0
        offline = 0
        disabled = 0

        for n in nodes:
            is_disabled = bool(n.get('is_disabled'))
            is_connected = bool(n.get('is_connected'))

            if is_disabled:
                disabled += 1
            elif is_connected:
                online += 1
            else:
                offline += 1

            last_seen = n.get('last_seen_at')
            if last_seen and not isinstance(last_seen, str):
                try:
                    last_seen = last_seen.isoformat()
                except Exception:
                    last_seen = str(last_seen)

            metrics_updated = n.get('metrics_updated_at')
            if metrics_updated and not isinstance(metrics_updated, str):
                try:
                    metrics_updated = metrics_updated.isoformat()
                except Exception:
                    metrics_updated = str(metrics_updated)

            fleet_items.append(NodeFleetItem(
                uuid=n.get('uuid', ''),
                name=n.get('name', ''),
                address=n.get('address', ''),
                port=int(n.get('port') or 443),
                is_connected=is_connected,
                is_disabled=is_disabled,
                is_xray_running=bool(n.get('is_xray_running')),
                xray_version=n.get('xray_version'),
                users_online=int(n.get('users_online') or 0),
                traffic_today_bytes=int(n.get('traffic_today_bytes') or 0),
                traffic_total_bytes=int(n.get('traffic_total_bytes') or 0),
                uptime_seconds=n.get('uptime_seconds'),
                cpu_usage=n.get('cpu_usage'),
                memory_usage=n.get('memory_usage'),
                memory_total_bytes=n.get('memory_total_bytes'),
                memory_used_bytes=n.get('memory_used_bytes'),
                disk_usage=n.get('disk_usage'),
                disk_total_bytes=n.get('disk_total_bytes'),
                disk_used_bytes=n.get('disk_used_bytes'),
                last_seen_at=last_seen,
                download_speed_bps=int(n.get('download_speed_bps') or 0),
                upload_speed_bps=int(n.get('upload_speed_bps') or 0),
                metrics_updated_at=metrics_updated,
            ))

        # Sort: offline first (problematic), then online, then disabled
        def sort_key(item: NodeFleetItem):
            if not item.is_disabled and not item.is_connected:
                return (0, item.name)  # offline first
            elif item.is_connected and not item.is_disabled:
                return (1, item.name)  # online second
            else:
                return (2, item.name)  # disabled last

        fleet_items.sort(key=sort_key)

        return NodeFleetResponse(
            nodes=fleet_items,
            total=len(fleet_items),
            online=online,
            offline=offline,
            disabled=disabled,
        )

    except Exception as e:
        logger.error("Error getting node fleet: %s", e)
        return NodeFleetResponse()


@router.get("/system/components", response_model=SystemComponentsResponse)
@limiter.limit(RATE_ANALYTICS)
async def get_system_components(
    request: Request,
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get status of all system components for dashboard."""
    import time

    components: List[SystemComponentStatus] = []

    # 1. Check Remnawave API
    try:
        from web.backend.core.api_helper import api_get
        start_time = time.monotonic()
        health = await api_get("/api/system/health")
        elapsed_ms = round((time.monotonic() - start_time) * 1000)
        if health is not None:
            components.append(SystemComponentStatus(
                name="Remnawave API",
                status="online",
                details={"response_time_ms": elapsed_ms},
            ))
        else:
            components.append(SystemComponentStatus(
                name="Remnawave API",
                status="offline",
                details={"error": "No response"},
            ))
    except Exception as e:
        components.append(SystemComponentStatus(
            name="Remnawave API",
            status="offline",
            details={"error": str(e)},
        ))

    # 2. Check Database
    try:
        from src.services.database import db_service
        if db_service.is_connected:
            # Quick query to verify
            users_count = 0
            try:
                users = await db_service.get_all_users(limit=1)
                users_count = len(users) if users else 0
            except Exception:
                pass
            pool_info = {}
            try:
                pool = db_service._pool
                if pool:
                    pool_info = {
                        "size": pool.get_size(),
                        "free_size": pool.get_idle_size(),
                        "min_size": pool.get_min_size(),
                        "max_size": pool.get_max_size(),
                    }
            except Exception:
                pass
            components.append(SystemComponentStatus(
                name="PostgreSQL",
                status="online",
                details={**pool_info, "has_data": users_count > 0},
            ))
        else:
            components.append(SystemComponentStatus(
                name="PostgreSQL",
                status="offline",
                details={"error": "Not connected"},
            ))
    except Exception as e:
        components.append(SystemComponentStatus(
            name="PostgreSQL",
            status="offline",
            details={"error": str(e)},
        ))

    # 3. Check Nodes
    try:
        nodes = await _get_nodes_data()
        total = len(nodes)
        connected = sum(1 for n in nodes if _is_node_connected(n) and not _is_node_disabled(n))
        components.append(SystemComponentStatus(
            name="Nodes",
            status="online" if connected > 0 else ("degraded" if total > 0 else "offline"),
            details={"total": total, "online": connected},
        ))
    except Exception as e:
        components.append(SystemComponentStatus(
            name="Nodes",
            status="unknown",
            details={"error": str(e)},
        ))

    # 4. Check WebSocket
    try:
        from web.backend.api.v2.websocket import manager
        ws_count = len(manager.active_connections) if manager else 0
        components.append(SystemComponentStatus(
            name="WebSocket",
            status="online",
            details={"active_connections": ws_count},
        ))
    except Exception:
        components.append(SystemComponentStatus(
            name="WebSocket",
            status="unknown",
            details={},
        ))

    # Calculate uptime (approximate via process start time)
    uptime = None
    try:
        import psutil
        p = psutil.Process()
        uptime = int(time.time() - p.create_time())
    except Exception:
        pass

    version = await get_latest_version()

    return SystemComponentsResponse(
        components=components,
        uptime_seconds=uptime,
        version=version,
    )


# ── Update Checker ─────────────────────────────────────────────

@router.get("/updates")
async def check_updates(
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Check for available updates from GitHub Releases."""
    from web.backend.core.update_checker import check_for_updates
    return await check_for_updates()


@router.get("/dependencies")
async def get_dependencies(
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get versions of key system dependencies."""
    from web.backend.core.update_checker import get_dependency_versions
    return await get_dependency_versions()

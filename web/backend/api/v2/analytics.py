"""Analytics API endpoints."""
import logging
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, Query

from web.backend.api.deps import get_current_admin, AdminUser
from web.backend.core.api_helper import fetch_users_from_api, fetch_nodes_from_api, fetch_hosts_from_api
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
    total_hosts: int = 0
    violations_today: int = 0
    violations_week: int = 0


class TrafficStats(BaseModel):
    """Traffic statistics."""

    total_bytes: int = 0
    today_bytes: int = 0
    week_bytes: int = 0
    month_bytes: int = 0


async def _get_users_data() -> List[Dict[str, Any]]:
    """Get users from DB, fall back to API if DB is empty/unavailable."""
    try:
        from src.services.database import db_service
        if db_service.is_connected:
            users = await db_service.get_all_users()
            if users:
                return users
    except Exception as e:
        logger.debug("DB users fetch failed: %s", e)

    # Fall back to Remnawave API
    return await fetch_users_from_api()


async def _get_nodes_data() -> List[Dict[str, Any]]:
    """Get nodes from DB, fall back to API if DB is empty/unavailable."""
    try:
        from src.services.database import db_service
        if db_service.is_connected:
            nodes = await db_service.get_all_nodes()
            if nodes:
                return nodes
    except Exception as e:
        logger.debug("DB nodes fetch failed: %s", e)

    # Fall back to Remnawave API
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


def _get_user_status(user: Dict[str, Any]) -> str:
    """Extract user status from user data (handles both DB and API formats)."""
    return user.get('status') or user.get('Status') or ''


def _is_node_connected(node: Dict[str, Any]) -> bool:
    """Check if node is connected (handles both DB and API formats)."""
    return bool(node.get('is_connected') or node.get('isConnected'))


def _get_traffic_bytes(user: Dict[str, Any]) -> int:
    """Extract used traffic bytes from user data (handles both DB and API formats)."""
    val = user.get('used_traffic_bytes') or user.get('usedTrafficBytes') or 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


@router.get("/overview", response_model=OverviewStats)
async def get_overview(
    admin: AdminUser = Depends(get_current_admin),
):
    """Get overview statistics for dashboard."""
    try:
        users = await _get_users_data()
        nodes = await _get_nodes_data()
        hosts = await _get_hosts_data()

        # Calculate user stats
        total_users = len(users)
        active_users = sum(1 for u in users if _get_user_status(u) == 'active')
        disabled_users = sum(1 for u in users if _get_user_status(u) == 'disabled')
        expired_users = sum(1 for u in users if _get_user_status(u) == 'expired')

        # Calculate node stats
        total_nodes = len(nodes)
        online_nodes = sum(1 for n in nodes if _is_node_connected(n))
        offline_nodes = total_nodes - online_nodes

        # Calculate host stats
        total_hosts = len(hosts)

        return OverviewStats(
            total_users=total_users,
            active_users=active_users,
            disabled_users=disabled_users,
            expired_users=expired_users,
            total_nodes=total_nodes,
            online_nodes=online_nodes,
            offline_nodes=offline_nodes,
            total_hosts=total_hosts,
            violations_today=0,
            violations_week=0,
        )

    except Exception as e:
        logger.error("Error getting overview stats: %s", e)
        return OverviewStats()


@router.get("/traffic", response_model=TrafficStats)
async def get_traffic_stats(
    admin: AdminUser = Depends(get_current_admin),
):
    """Get traffic statistics."""
    try:
        users = await _get_users_data()

        # Calculate total traffic
        total_bytes = sum(_get_traffic_bytes(u) for u in users)

        return TrafficStats(
            total_bytes=total_bytes,
            today_bytes=0,
            week_bytes=0,
            month_bytes=0,
        )

    except Exception as e:
        logger.error("Error getting traffic stats: %s", e)
        return TrafficStats()


@router.get("/users")
async def get_user_stats(
    period: str = Query("week", regex="^(day|week|month)$"),
    admin: AdminUser = Depends(get_current_admin),
):
    """Get user statistics for charts."""
    return {
        "period": period,
        "data": [],
    }


@router.get("/connections")
async def get_connection_stats(
    period: str = Query("day", regex="^(hour|day|week)$"),
    admin: AdminUser = Depends(get_current_admin),
):
    """Get connection statistics for charts."""
    return {
        "period": period,
        "data": [],
    }

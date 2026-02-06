"""Analytics API endpoints."""
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

# Add src to path for importing bot services
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from web.backend.api.deps import get_current_admin, AdminUser
from pydantic import BaseModel

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


@router.get("/overview", response_model=OverviewStats)
async def get_overview(
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Get overview statistics for dashboard.
    """
    try:
        from src.services.database import db_service

        # Get all data
        users = await db_service.get_all_users()
        nodes = await db_service.get_all_nodes()
        hosts = await db_service.get_all_hosts()

        # Calculate user stats
        total_users = len(users)
        active_users = sum(1 for u in users if u.get('status') == 'active')
        disabled_users = sum(1 for u in users if u.get('status') == 'disabled')
        expired_users = sum(1 for u in users if u.get('status') == 'expired')

        # Calculate node stats
        total_nodes = len(nodes)
        online_nodes = sum(1 for n in nodes if n.get('is_connected'))
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
            violations_today=0,  # TODO: implement
            violations_week=0,  # TODO: implement
        )

    except ImportError:
        return OverviewStats()


@router.get("/traffic", response_model=TrafficStats)
async def get_traffic_stats(
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Get traffic statistics.
    """
    try:
        from src.services.database import db_service

        users = await db_service.get_all_users()

        # Calculate total traffic
        total_bytes = sum(u.get('used_traffic_bytes', 0) for u in users)

        return TrafficStats(
            total_bytes=total_bytes,
            today_bytes=0,  # TODO: implement daily tracking
            week_bytes=0,
            month_bytes=0,
        )

    except ImportError:
        return TrafficStats()


@router.get("/users")
async def get_user_stats(
    period: str = Query("week", regex="^(day|week|month)$"),
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Get user statistics for charts.
    """
    # TODO: Implement time-series data for charts
    return {
        "period": period,
        "data": [],
    }


@router.get("/connections")
async def get_connection_stats(
    period: str = Query("day", regex="^(hour|day|week)$"),
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Get connection statistics for charts.
    """
    # TODO: Implement connection time-series
    return {
        "period": period,
        "data": [],
    }

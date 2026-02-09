"""Users API endpoints."""
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException

# Add src to path for importing bot services
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from web.backend.api.deps import get_current_admin, AdminUser
from web.backend.core.api_helper import fetch_users_from_api
from web.backend.schemas.user import UserListItem, UserDetail, UserCreate, UserUpdate, HwidDevice
from web.backend.schemas.common import PaginatedResponse, SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _ensure_snake_case(user: dict) -> dict:
    """Ensure user dict has snake_case keys for pydantic schemas."""
    result = dict(user)
    # Flatten nested userTraffic fields to root level
    # Remnawave API returns usedTrafficBytes, onlineAt etc. inside userTraffic object
    user_traffic = result.get('userTraffic')
    if isinstance(user_traffic, dict):
        for key in ('usedTrafficBytes', 'lifetimeUsedTrafficBytes', 'onlineAt',
                     'firstConnectedAt', 'lastConnectedNodeUuid'):
            if key in user_traffic and key not in result:
                result[key] = user_traffic[key]
    mappings = {
        'shortUuid': 'short_uuid',
        'subscriptionUuid': 'subscription_uuid',
        'subscriptionUrl': 'subscription_url',
        'telegramId': 'telegram_id',
        'expireAt': 'expire_at',
        'trafficLimitBytes': 'traffic_limit_bytes',
        'usedTrafficBytes': 'used_traffic_bytes',
        'lifetimeUsedTrafficBytes': 'lifetime_used_traffic_bytes',
        'hwidDeviceLimit': 'hwid_device_limit',
        'hwidDeviceCount': 'hwid_device_count',
        'activeDeviceCount': 'hwid_device_count',
        'createdAt': 'created_at',
        'updatedAt': 'updated_at',
        'onlineAt': 'online_at',
        'subLastUserAgent': 'sub_last_user_agent',
    }
    for camel, snake in mappings.items():
        if camel in result and snake not in result:
            result[snake] = result[camel]
    # Normalize status to lowercase (Remnawave API returns ACTIVE, DISABLED, etc.)
    if isinstance(result.get('status'), str):
        result['status'] = result['status'].lower()
    return result


async def _get_users_list():
    """Get users from DB, fall back to API."""
    try:
        from src.services.database import db_service
        if db_service.is_connected:
            users = await db_service.get_all_users(limit=50000)
            if users:
                logger.debug("Loaded %d users from database", len(users))
                return users
            else:
                logger.info("Database connected but no users found, trying API")
    except Exception as e:
        logger.warning("DB users fetch failed: %s", e)

    try:
        users = await fetch_users_from_api()
        logger.debug("Loaded %d users from API", len(users))
        return users
    except Exception as e:
        logger.warning("API users fetch failed: %s", e)
        return []


def _parse_dt(val) -> Optional[datetime]:
    """Parse a datetime value from various formats."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            # Try ISO format
            return datetime.fromisoformat(val.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None
    return None


@router.get("", response_model=PaginatedResponse[UserListItem])
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by username, email, or UUID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    traffic_type: Optional[str] = Query(None, description="Filter by traffic type: unlimited, limited"),
    expire_filter: Optional[str] = Query(None, description="Filter by expiration: expiring_7d, expiring_30d, expired, no_expiry"),
    online_filter: Optional[str] = Query(None, description="Filter by online status: online_24h, online_7d, online_30d, never"),
    traffic_usage: Optional[str] = Query(None, description="Filter by traffic usage: above_90, above_70, above_50, zero"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    admin: AdminUser = Depends(get_current_admin),
):
    """List users with pagination and filtering."""
    try:
        users = await _get_users_list()
        # Normalize all users to have snake_case keys
        users = [_ensure_snake_case(u) for u in users]

        # Enrich with HWID device counts from local DB (single query, no API calls)
        try:
            from src.services.database import db_service
            if db_service.is_connected:
                device_counts = await db_service.get_hwid_device_counts_bulk()
                if device_counts:
                    for u in users:
                        uid = u.get('uuid')
                        if uid and uid in device_counts:
                            u['hwid_device_count'] = device_counts[uid]
        except Exception as e:
            logger.debug("Failed to enrich hwid device counts: %s", e)

        now = datetime.now(timezone.utc)

        def _get(u, *keys, default=''):
            for k in keys:
                v = u.get(k)
                if v is not None:
                    return v
            return default

        # Filter: search
        if search:
            search_lower = search.lower()
            users = [
                u for u in users
                if search_lower in str(_get(u, 'username')).lower()
                or search_lower in str(_get(u, 'email')).lower()
                or search_lower in str(_get(u, 'uuid')).lower()
                or search_lower in str(_get(u, 'short_uuid')).lower()
                or search_lower in str(_get(u, 'telegram_id')).lower()
                or search_lower in str(_get(u, 'description')).lower()
            ]

        # Filter: status
        if status:
            status_lower = status.lower()
            users = [u for u in users if str(_get(u, 'status')).lower() == status_lower]

        # Filter: traffic type
        if traffic_type:
            if traffic_type == 'unlimited':
                users = [u for u in users if u.get('traffic_limit_bytes') is None or u.get('traffic_limit_bytes') == 0]
            elif traffic_type == 'limited':
                users = [u for u in users if u.get('traffic_limit_bytes') is not None and u.get('traffic_limit_bytes') > 0]

        # Filter: expiration
        if expire_filter:
            def _expire_match(u):
                expire = _parse_dt(u.get('expire_at'))
                if expire_filter == 'no_expiry':
                    return expire is None
                if expire is None:
                    return False
                # Ensure timezone-aware comparison
                if expire.tzinfo is None:
                    expire = expire.replace(tzinfo=timezone.utc)
                if expire_filter == 'expired':
                    return expire < now
                if expire_filter == 'expiring_7d':
                    return now <= expire <= now + timedelta(days=7)
                if expire_filter == 'expiring_30d':
                    return now <= expire <= now + timedelta(days=30)
                return True
            users = [u for u in users if _expire_match(u)]

        # Filter: online status
        if online_filter:
            def _online_match(u):
                online = _parse_dt(u.get('online_at'))
                if online_filter == 'never':
                    return online is None
                if online is None:
                    return False
                if online.tzinfo is None:
                    online = online.replace(tzinfo=timezone.utc)
                if online_filter == 'online_24h':
                    return online >= now - timedelta(hours=24)
                if online_filter == 'online_7d':
                    return online >= now - timedelta(days=7)
                if online_filter == 'online_30d':
                    return online >= now - timedelta(days=30)
                return True
            users = [u for u in users if _online_match(u)]

        # Filter: traffic usage percentage
        if traffic_usage:
            def _traffic_usage_match(u):
                used = u.get('used_traffic_bytes', 0) or 0
                limit = u.get('traffic_limit_bytes')
                if traffic_usage == 'zero':
                    return used == 0
                # Percentage-based filters only apply to limited users
                if not limit or limit == 0:
                    return False
                pct = (used / limit) * 100
                if traffic_usage == 'above_90':
                    return pct >= 90
                if traffic_usage == 'above_70':
                    return pct >= 70
                if traffic_usage == 'above_50':
                    return pct >= 50
                return True
            users = [u for u in users if _traffic_usage_match(u)]

        # Sort
        reverse = sort_order == "desc"
        sort_key_map = {
            'created_at': ('created_at',),
            'username': ('username',),
            'status': ('status',),
            'expire_at': ('expire_at',),
            'online_at': ('online_at',),
        }

        if sort_by == 'used_traffic_bytes':
            users.sort(key=lambda x: x.get('used_traffic_bytes', 0) or 0, reverse=reverse)
        elif sort_by == 'lifetime_used_traffic_bytes':
            users.sort(key=lambda x: x.get('lifetime_used_traffic_bytes', 0) or 0, reverse=reverse)
        elif sort_by == 'traffic_limit_bytes':
            def _traffic_limit_key(u):
                val = u.get('traffic_limit_bytes')
                if val is None or val == 0:
                    return float('inf') if not reverse else -1
                return val
            users.sort(key=_traffic_limit_key, reverse=reverse)
        elif sort_by == 'hwid_device_limit':
            users.sort(key=lambda x: x.get('hwid_device_limit', 0) or 0, reverse=reverse)
        elif sort_by in ('online_at', 'expire_at'):
            # Date fields: None values go to end
            def _date_sort_key(u):
                val = _parse_dt(u.get(sort_by))
                if val is None:
                    return '' if not reverse else 'zzzz'
                return val.isoformat()
            users.sort(key=_date_sort_key, reverse=reverse)
        else:
            sort_keys = sort_key_map.get(sort_by, (sort_by,))
            users.sort(key=lambda x: _get(x, *sort_keys) or '', reverse=reverse)

        # Paginate
        total = len(users)
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        items = users[start_idx:end_idx]

        # Convert to schema
        user_items = []
        parse_errors = 0
        for u in items:
            try:
                user_items.append(UserListItem(**u))
            except Exception as e:
                parse_errors += 1
                if parse_errors <= 3:
                    logger.warning("Failed to parse user %s: %s (keys: %s)",
                                   u.get('uuid', '?'), e, list(u.keys())[:10])

        if parse_errors > 0:
            logger.warning("Failed to parse %d/%d users on page %d", parse_errors, len(items), page)

        return PaginatedResponse(
            items=user_items,
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page if total > 0 else 1,
        )

    except Exception as e:
        logger.error("Error listing users: %s", e, exc_info=True)
        return PaginatedResponse(
            items=[],
            total=0,
            page=page,
            per_page=per_page,
            pages=1,
        )


@router.get("/{user_uuid}", response_model=UserDetail)
async def get_user(
    user_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Get detailed user information with anti-abuse data from DB."""
    try:
        # Try to get user from DB first, then API
        user_data = None
        try:
            from src.services.database import db_service
            if db_service.is_connected:
                user_data = await db_service.get_user_by_uuid(user_uuid)
        except Exception:
            pass

        if not user_data:
            try:
                from src.services.api_client import api_client
                resp = await api_client.get_user_by_uuid(user_uuid)
                user_data = resp.get('response', resp) if isinstance(resp, dict) else resp
            except ImportError:
                raise HTTPException(status_code=503, detail="API service not available")

        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        # Normalize to snake_case
        user_data = _ensure_snake_case(user_data)

        # Enrich with anti-abuse data from DB
        try:
            from src.services.database import db_service
            if db_service.is_connected:
                # Violation count for last 30 days
                violations = await db_service.get_user_violations(
                    user_uuid=user_uuid, days=30, limit=1000
                )
                user_data['violation_count_30d'] = len(violations)

                # Active connections
                active_conns = await db_service.get_user_active_connections(user_uuid)
                user_data['active_connections'] = len(active_conns)

                # Unique IPs in last 24 hours
                unique_ips = await db_service.get_user_unique_ips_count(user_uuid, since_hours=24)
                user_data['unique_ips_24h'] = unique_ips

                # Trust score: 100 minus avg violation score (if any recent violations)
                if violations:
                    avg_score = sum(v.get('score', 0) for v in violations) / len(violations)
                    user_data['trust_score'] = max(0, int(100 - avg_score))
                else:
                    user_data['trust_score'] = 100
        except Exception as e:
            logger.debug("Failed to enrich user with anti-abuse data: %s", e)

        return UserDetail(**user_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting user %s: %s", user_uuid, e)
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("", response_model=UserDetail)
async def create_user(
    data: UserCreate,
    admin: AdminUser = Depends(get_current_admin),
):
    """Create a new user."""
    try:
        from src.services.api_client import api_client

        user = await api_client.create_user(
            username=data.username,
            traffic_limit=data.traffic_limit_bytes,
            expire_days=data.expire_days,
            hwid_device_limit=data.hwid_device_limit,
        )

        return UserDetail(**_ensure_snake_case(user))

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{user_uuid}", response_model=UserDetail)
async def update_user(
    user_uuid: str,
    data: UserUpdate,
    admin: AdminUser = Depends(get_current_admin),
):
    """Update user fields."""
    try:
        from src.services.api_client import api_client

        update_data = data.model_dump(exclude_unset=True, mode='json')
        resp = await api_client.update_user(user_uuid, **update_data)
        user = resp.get('response', resp) if isinstance(resp, dict) else resp

        return UserDetail(**_ensure_snake_case(user))

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{user_uuid}", response_model=SuccessResponse)
async def delete_user(
    user_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Delete a user."""
    try:
        from src.services.api_client import api_client

        await api_client.delete_user(user_uuid)

        # Also remove from local DB so UI updates immediately
        try:
            from src.services.database import db_service
            if db_service.is_connected:
                await db_service.delete_user(user_uuid)
        except Exception:
            pass  # non-critical, sync will reconcile

        return SuccessResponse(message="User deleted")

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_uuid}/enable", response_model=SuccessResponse)
async def enable_user(
    user_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Enable a disabled user."""
    try:
        from src.services.api_client import api_client

        await api_client.enable_user(user_uuid)
        return SuccessResponse(message="User enabled")

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_uuid}/disable", response_model=SuccessResponse)
async def disable_user(
    user_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Disable a user."""
    try:
        from src.services.api_client import api_client

        await api_client.disable_user(user_uuid)
        return SuccessResponse(message="User disabled")

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_uuid}/reset-traffic", response_model=SuccessResponse)
async def reset_user_traffic(
    user_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Reset user's traffic usage."""
    try:
        from src.services.api_client import api_client

        await api_client.reset_user_traffic(user_uuid)
        return SuccessResponse(message="Traffic reset")

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_uuid}/revoke", response_model=SuccessResponse)
async def revoke_user_subscription(
    user_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Revoke user's subscription (regenerate subscription UUID)."""
    try:
        from src.services.api_client import api_client

        await api_client.revoke_user_subscription(user_uuid)
        return SuccessResponse(message="Subscription revoked")

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hwid-device-counts")
async def get_hwid_device_counts(
    user_uuids: List[str],
    admin: AdminUser = Depends(get_current_admin),
):
    """Get HWID device counts for multiple users in one call."""
    import asyncio

    async def _get_count(uuid: str) -> tuple:
        try:
            from src.services.api_client import api_client
            result = await api_client.get_user_hwid_devices(uuid)
            response = result.get("response", result) if isinstance(result, dict) else result
            devices = response if isinstance(response, list) else response.get("devices", []) if isinstance(response, dict) else []
            return (uuid, len(devices))
        except Exception:
            return (uuid, 0)

    # Limit concurrent requests
    semaphore = asyncio.Semaphore(10)

    async def _limited_get_count(uuid: str) -> tuple:
        async with semaphore:
            return await _get_count(uuid)

    results = await asyncio.gather(*[_limited_get_count(uid) for uid in user_uuids[:100]])
    return {uuid: count for uuid, count in results}


@router.get("/{user_uuid}/traffic-stats")
async def get_user_traffic_stats(
    user_uuid: str,
    period: str = Query("today", description="Period: today, week, month, 3month, 6month, year"),
    admin: AdminUser = Depends(get_current_admin),
):
    """Get per-user traffic statistics with per-node breakdown from Remnawave API.

    Uses /api/bandwidth-stats/users/{uuid} which returns actual per-user
    traffic data broken down by node for any date range.
    """
    from datetime import datetime, timedelta, timezone

    try:
        # Get user data for current/lifetime traffic
        user_data = None
        try:
            from src.services.database import db_service
            if db_service.is_connected:
                user_data = await db_service.get_user_by_uuid(user_uuid)
        except Exception:
            pass

        if not user_data:
            try:
                from src.services.api_client import api_client as _api
                resp = await _api.get_user_by_uuid(user_uuid)
                user_data = resp.get('response', resp) if isinstance(resp, dict) else resp
            except ImportError:
                raise HTTPException(status_code=503, detail="API service not available")

        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")

        user_data = _ensure_snake_case(user_data)

        used_bytes = user_data.get('used_traffic_bytes', 0) or 0
        lifetime_bytes = user_data.get('lifetime_used_traffic_bytes', 0) or 0
        traffic_limit = user_data.get('traffic_limit_bytes')

        # Calculate date range for the requested period
        # API expects YYYY-MM-DD format; end = tomorrow to include full current day
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_map = {
            'today': timedelta(days=1),
            'week': timedelta(days=7),
            'month': timedelta(days=30),
            '3month': timedelta(days=90),
            '6month': timedelta(days=180),
            'year': timedelta(days=365),
        }
        delta = period_map.get(period, timedelta(days=1))
        start_dt = today_start - delta if period != 'today' else today_start
        end_dt = today_start + timedelta(days=1)
        start_str = start_dt.strftime('%Y-%m-%d')
        end_str = end_dt.strftime('%Y-%m-%d')

        # Fetch per-user traffic from Remnawave bandwidth-stats API
        period_bytes = 0
        nodes_traffic = []
        try:
            from src.services.api_client import api_client
            result = await api_client.get_user_traffic_stats(
                user_uuid, start=start_str, end=end_str, top_nodes_limit=50
            )
            # Parse response - API returns { response: { topNodes: [...], series: [...], ... } }
            response = result.get('response', result) if isinstance(result, dict) else result

            if isinstance(response, dict):
                # Per-node breakdown from topNodes array
                # Fields: uuid, name, countryCode, color, total (bytes as number)
                top_nodes = response.get('topNodes', [])
                if isinstance(top_nodes, list):
                    for node in top_nodes:
                        total = int(node.get('total', 0) or 0)
                        period_bytes += total
                        nodes_traffic.append({
                            'node_name': node.get('name', 'Unknown'),
                            'node_uuid': node.get('uuid', ''),
                            'total_bytes': total,
                        })
        except Exception as e:
            logger.warning("Failed to fetch per-user bandwidth stats for %s: %s", user_uuid, e)

        return {
            'used_bytes': used_bytes,
            'lifetime_bytes': lifetime_bytes,
            'traffic_limit_bytes': traffic_limit,
            'period': period,
            'period_bytes': period_bytes,
            'nodes_traffic': nodes_traffic,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting traffic stats for %s: %s", user_uuid, e)
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/{user_uuid}/sync-hwid-devices")
async def sync_user_hwid_devices(
    user_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Force re-sync HWID devices for a user from Remnawave API to local DB."""
    try:
        from src.services.sync import sync_service
        synced = await sync_service.sync_user_hwid_devices(user_uuid)
        return {"success": True, "synced": synced}
    except Exception as e:
        logger.error("Error syncing HWID devices for %s: %s", user_uuid, e)
        raise HTTPException(status_code=500, detail="Sync failed")


@router.get("/{user_uuid}/hwid-devices", response_model=List[HwidDevice])
async def get_user_hwid_devices(
    user_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Get HWID devices for a user. Reads from local DB (synced via webhooks), API as fallback."""
    def _parse_devices(devices: list) -> List[HwidDevice]:
        items = []
        for d in devices:
            items.append(HwidDevice(
                hwid=d.get("hwid", ""),
                platform=d.get("platform"),
                os_version=d.get("osVersion") or d.get("os_version"),
                device_model=d.get("deviceModel") or d.get("device_model"),
                app_version=d.get("appVersion") or d.get("app_version"),
                user_agent=d.get("userAgent") or d.get("user_agent"),
                created_at=d.get("createdAt") or d.get("created_at"),
                updated_at=d.get("updatedAt") or d.get("updated_at"),
            ))
        return items

    # Read from local DB first (kept up-to-date via sync + webhooks)
    try:
        from src.services.database import db_service
        if db_service.is_connected:
            db_devices = await db_service.get_user_hwid_devices(user_uuid)
            if db_devices:
                return _parse_devices(db_devices)
    except Exception as e:
        logger.debug("DB HWID fetch failed for %s, trying API: %s", user_uuid, e)

    # Fall back to API if local DB has no data
    try:
        from src.services.api_client import api_client

        result = await api_client.get_user_hwid_devices(user_uuid)
        response = result.get("response", result) if isinstance(result, dict) else result
        devices = response if isinstance(response, list) else response.get("devices", []) if isinstance(response, dict) else []

        return _parse_devices(devices)

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        logger.error("API HWID fetch also failed for %s: %s", user_uuid, e)

    return []

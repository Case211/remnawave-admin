"""Users API endpoints."""
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException, Request

from web.backend.core.errors import api_error, E

# Add src to path for importing bot services
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from web.backend.api.deps import get_current_admin, require_permission, require_quota, AdminUser, get_client_ip
from web.backend.core.api_helper import fetch_users_from_api
from web.backend.core.rbac import write_audit_log
from web.backend.schemas.user import UserListItem, UserDetail, UserCreate, UserUpdate, HwidDevice
from web.backend.schemas.common import PaginatedResponse, SuccessResponse
from web.backend.schemas.bulk import BulkUserRequest, BulkOperationResult, BulkOperationError
from web.backend.core.rate_limit import limiter, RATE_BULK

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
        'trafficLimitStrategy': 'traffic_limit_strategy',
        'usedTrafficBytes': 'used_traffic_bytes',
        'lifetimeUsedTrafficBytes': 'lifetime_used_traffic_bytes',
        'hwidDeviceLimit': 'hwid_device_limit',
        'hwidDeviceCount': 'hwid_device_count',
        'activeDeviceCount': 'hwid_device_count',
        'externalSquadUuid': 'external_squad_uuid',
        'activeInternalSquads': 'active_internal_squads',
        'createdAt': 'created_at',
        'updatedAt': 'updated_at',
        'onlineAt': 'online_at',
        'subLastUserAgent': 'sub_last_user_agent',
        'subLastOpenedAt': 'sub_last_opened_at',
        'subRevokedAt': 'sub_revoked_at',
        'lastTrafficResetAt': 'last_traffic_reset_at',
        'trojanPassword': 'trojan_password',
        'vlessUuid': 'vless_uuid',
        'ssPassword': 'ss_password',
        'lastTriggeredThreshold': 'last_triggered_threshold',
        'firstConnectedAt': 'first_connected_at',
        'lastConnectedNodeUuid': 'last_connected_node_uuid',
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
        from shared.database import db_service
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
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """List users with pagination and filtering."""
    try:
        users = await _get_users_list()
        # Normalize all users to have snake_case keys
        users = [_ensure_snake_case(u) for u in users]

        # Enrich with HWID device counts from local DB (single query, no API calls)
        try:
            from shared.database import db_service
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


# ── Squad endpoints (must be before /{user_uuid} routes) ──────


def _normalize_squad(sq: dict) -> dict:
    """Ensure squad dict has squadTag/squadName fields for frontend compatibility.

    Remnawave API returns 'name' / 'tag', but frontend expects 'squadName' / 'squadTag'.
    """
    result = dict(sq)
    if "squadName" not in result:
        result["squadName"] = sq.get("name") or sq.get("tag") or sq.get("squadTag") or ""
    if "squadTag" not in result:
        result["squadTag"] = sq.get("tag") or sq.get("name") or sq.get("squadName") or ""
    return result


@router.get("/meta/internal-squads")
async def get_internal_squads(
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get available internal squads — reads from DB (synced), falls back to API."""
    squads = []
    try:
        from shared.data_access import get_all_internal_squads
        squads = await get_all_internal_squads()
    except ImportError:
        # Fallback: direct API call if data_access module is unavailable
        try:
            from shared.api_client import api_client
            result = await api_client.get_internal_squads()
            payload = result.get("response", result) if isinstance(result, dict) else result
            if isinstance(payload, dict):
                squads = payload.get("internalSquads", [])
            elif isinstance(payload, list):
                squads = payload
        except ImportError:
            raise api_error(503, E.API_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.error("Error fetching internal squads: %s", e)
            return []

    return [_normalize_squad(sq) for sq in squads if isinstance(sq, dict)]


@router.get("/meta/external-squads")
async def get_external_squads(
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get available external squads — reads from DB (synced), falls back to API."""
    squads = []
    try:
        from shared.data_access import get_all_external_squads
        squads = await get_all_external_squads()
    except ImportError:
        # Fallback: direct API call if data_access module is unavailable
        try:
            from shared.api_client import api_client
            result = await api_client.get_external_squads()
            payload = result.get("response", result) if isinstance(result, dict) else result
            if isinstance(payload, dict):
                squads = payload.get("externalSquads", [])
            elif isinstance(payload, list):
                squads = payload
        except ImportError:
            raise api_error(503, E.API_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.error("Error fetching external squads: %s", e)
            return []

    return [_normalize_squad(sq) for sq in squads if isinstance(sq, dict)]


@router.get("/{user_uuid}", response_model=UserDetail)
async def get_user(
    user_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get detailed user information with anti-abuse data from DB."""
    try:
        # Try to get user from DB first, then API
        user_data = None
        try:
            from shared.database import db_service
            if db_service.is_connected:
                user_data = await db_service.get_user_by_uuid(user_uuid)
        except Exception:
            pass

        if not user_data:
            try:
                from shared.api_client import api_client
                resp = await api_client.get_user_by_uuid(user_uuid)
                user_data = resp.get('response', resp) if isinstance(resp, dict) else resp
            except ImportError:
                raise api_error(503, E.API_SERVICE_UNAVAILABLE)

        if not user_data:
            raise api_error(404, E.USER_NOT_FOUND)

        # Normalize to snake_case
        user_data = _ensure_snake_case(user_data)

        # Enrich with anti-abuse data from DB
        try:
            from shared.database import db_service
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
        raise api_error(500, E.INTERNAL_ERROR)


@router.post("", response_model=UserDetail)
async def create_user(
    request: Request,
    data: UserCreate,
    admin: AdminUser = Depends(require_permission("users", "create")),
    _quota: None = Depends(require_quota("users")),
):
    """Create a new user."""
    try:
        from shared.api_client import api_client

        # Compute expire_at ISO string
        if data.expire_at:
            expire_at_str = data.expire_at.isoformat()
        else:
            # Default: 30 days from now
            expire_at_str = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        result = await api_client.create_user(
            username=data.username,
            expire_at=expire_at_str,
            traffic_limit_bytes=data.traffic_limit_bytes,
            hwid_device_limit=data.hwid_device_limit,
            telegram_id=data.telegram_id,
            description=data.description,
            traffic_limit_strategy=data.traffic_limit_strategy,
            external_squad_uuid=data.external_squad_uuid,
            active_internal_squads=data.active_internal_squads,
            status=data.status,
            tag=data.tag,
            email=data.email,
            short_uuid=data.short_uuid,
            trojan_password=data.trojan_password,
            vless_uuid=data.vless_uuid,
            ss_password=data.ss_password,
            uuid=data.uuid,
            created_at=data.created_at.isoformat() if data.created_at else None,
            last_traffic_reset_at=data.last_traffic_reset_at.isoformat() if data.last_traffic_reset_at else None,
        )

        user = result.get('response', result) if isinstance(result, dict) else result

        # Increment quota usage counter
        if admin.account_id is not None:
            from web.backend.core.rbac import increment_usage_counter
            await increment_usage_counter(admin.account_id, "users_created")

        # Audit
        user_uuid = user.get('uuid', '') if isinstance(user, dict) else ''
        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="user.create",
            resource="users",
            resource_id=str(user_uuid),
            details=json.dumps({"username": data.username}),
            ip_address=get_client_ip(request),
        )

        return UserDetail(**_ensure_snake_case(user))

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{user_uuid}", response_model=UserDetail)
async def update_user(
    user_uuid: str,
    request: Request,
    data: UserUpdate,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Update user fields."""
    try:
        from shared.api_client import api_client

        update_data = data.model_dump(exclude_unset=True, mode='json')
        # Convert snake_case keys to camelCase for Remnawave API
        snake_to_camel = {
            'traffic_limit_bytes': 'trafficLimitBytes',
            'traffic_limit_strategy': 'trafficLimitStrategy',
            'expire_at': 'expireAt',
            'hwid_device_limit': 'hwidDeviceLimit',
            'telegram_id': 'telegramId',
            'active_internal_squads': 'activeInternalSquads',
            'external_squad_uuid': 'externalSquadUuid',
        }
        camel_data = {}
        for k, v in update_data.items():
            camel_data[snake_to_camel.get(k, k)] = v
        resp = await api_client.update_user(user_uuid, **camel_data)
        user = resp.get('response', resp) if isinstance(resp, dict) else resp

        # Audit
        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="user.update",
            resource="users",
            resource_id=user_uuid,
            details=json.dumps({k: str(v) for k, v in update_data.items()}),
            ip_address=get_client_ip(request),
        )

        return UserDetail(**_ensure_snake_case(user))

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{user_uuid}", response_model=SuccessResponse)
async def delete_user(
    user_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("users", "delete")),
):
    """Delete a user."""
    try:
        from shared.api_client import api_client

        await api_client.delete_user(user_uuid)

        # Also remove from local DB so UI updates immediately
        try:
            from shared.database import db_service
            if db_service.is_connected:
                await db_service.delete_user(user_uuid)
        except Exception as e:
            logger.debug("Non-critical: failed to delete user from local DB: %s", e)

        # Audit
        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="user.delete",
            resource="users",
            resource_id=user_uuid,
            details=json.dumps({"user_uuid": user_uuid}),
            ip_address=get_client_ip(request),
        )

        return SuccessResponse(message="User deleted")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_uuid}/enable", response_model=SuccessResponse)
async def enable_user(
    user_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Enable a disabled user."""
    try:
        from shared.api_client import api_client

        await api_client.enable_user(user_uuid)

        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="user.enable", resource="users", resource_id=user_uuid,
            details=json.dumps({"user_uuid": user_uuid}),
            ip_address=get_client_ip(request),
        )
        return SuccessResponse(message="User enabled")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_uuid}/disable", response_model=SuccessResponse)
async def disable_user(
    user_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Disable a user."""
    try:
        from shared.api_client import api_client

        await api_client.disable_user(user_uuid)

        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="user.disable", resource="users", resource_id=user_uuid,
            details=json.dumps({"user_uuid": user_uuid}),
            ip_address=get_client_ip(request),
        )
        return SuccessResponse(message="User disabled")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_uuid}/reset-traffic", response_model=SuccessResponse)
async def reset_user_traffic(
    user_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Reset user's traffic usage."""
    try:
        from shared.api_client import api_client

        await api_client.reset_user_traffic(user_uuid)

        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="user.reset_traffic", resource="users", resource_id=user_uuid,
            details=json.dumps({"user_uuid": user_uuid}),
            ip_address=get_client_ip(request),
        )
        return SuccessResponse(message="Traffic reset")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{user_uuid}/revoke", response_model=SuccessResponse)
async def revoke_user_subscription(
    user_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Revoke user's subscription (regenerate subscription UUID)."""
    try:
        from shared.api_client import api_client

        await api_client.revoke_user_subscription(user_uuid)

        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="user.revoke", resource="users", resource_id=user_uuid,
            details=json.dumps({"user_uuid": user_uuid}),
            ip_address=get_client_ip(request),
        )
        return SuccessResponse(message="Subscription revoked")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/hwid-device-counts")
async def get_hwid_device_counts(
    user_uuids: List[str],
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get HWID device counts for multiple users in one call."""
    import asyncio

    async def _get_count(uuid: str) -> tuple:
        try:
            from shared.api_client import api_client
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
    admin: AdminUser = Depends(require_permission("users", "view")),
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
            from shared.database import db_service
            if db_service.is_connected:
                user_data = await db_service.get_user_by_uuid(user_uuid)
        except Exception:
            pass

        if not user_data:
            try:
                from shared.api_client import api_client as _api
                resp = await _api.get_user_by_uuid(user_uuid)
                user_data = resp.get('response', resp) if isinstance(resp, dict) else resp
            except ImportError:
                raise api_error(503, E.API_SERVICE_UNAVAILABLE)

        if not user_data:
            raise api_error(404, E.USER_NOT_FOUND)

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
            from shared.api_client import api_client
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
        raise api_error(500, E.INTERNAL_ERROR)


@router.get("/{user_uuid}/ip-history")
async def get_user_ip_history(
    user_uuid: str,
    period: str = Query("24h", description="Period: 24h, 7d, 30d"),
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get unique IP addresses for a user with geo enrichment."""
    period_days = {"24h": 1, "7d": 7, "30d": 30}.get(period, 1)
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"items": [], "total": 0}

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    SPLIT_PART(uc.ip_address::text, '/', 1) as ip,
                    im.country_name as country,
                    im.city,
                    im.asn_org,
                    COUNT(uc.id) as connections,
                    MAX(uc.connected_at) as last_seen
                FROM user_connections uc
                LEFT JOIN ip_metadata im
                    ON SPLIT_PART(uc.ip_address::text, '/', 1) = TRIM(im.ip_address)
                WHERE uc.user_uuid = $1
                  AND uc.connected_at > NOW() - make_interval(days => $2)
                GROUP BY SPLIT_PART(uc.ip_address::text, '/', 1),
                         im.country_name, im.city, im.asn_org
                ORDER BY last_seen DESC
                """,
                user_uuid,
                period_days,
            )
            items = [
                {
                    "ip": r["ip"],
                    "country": r["country"] or "",
                    "city": r["city"] or "",
                    "asn_org": r["asn_org"] or "",
                    "connections": r["connections"],
                    "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
                }
                for r in rows
            ]
            return {"items": items, "total": len(items)}
    except Exception as e:
        logger.error("Error getting IP history for %s: %s", user_uuid, e)
        raise api_error(500, E.INTERNAL_ERROR)


@router.post("/{user_uuid}/sync-hwid-devices")
async def sync_user_hwid_devices(
    user_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Force re-sync HWID devices for a user from Remnawave API to local DB."""
    try:
        from shared.sync import sync_service
        synced = await sync_service.sync_user_hwid_devices(user_uuid)
        return {"success": True, "synced": synced}
    except Exception as e:
        logger.error("Error syncing HWID devices for %s: %s", user_uuid, e)
        raise api_error(500, E.SYNC_FAILED)


@router.get("/{user_uuid}/hwid-devices", response_model=List[HwidDevice])
async def get_user_hwid_devices(
    user_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "view")),
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
        from shared.database import db_service
        if db_service.is_connected:
            db_devices = await db_service.get_user_hwid_devices(user_uuid)
            if db_devices:
                return _parse_devices(db_devices)
    except Exception as e:
        logger.debug("DB HWID fetch failed for %s, trying API: %s", user_uuid, e)

    # DB empty — trigger sync from Panel API (uses same logic as manual sync button)
    try:
        from shared.sync import sync_service
        synced = await sync_service.sync_user_hwid_devices(user_uuid)
        if synced:
            from shared.database import db_service
            if db_service.is_connected:
                db_devices = await db_service.get_user_hwid_devices(user_uuid)
                if db_devices:
                    return _parse_devices(db_devices)
    except Exception as e:
        logger.debug("Sync HWID failed for %s: %s", user_uuid, e)

    return []


@router.delete("/{user_uuid}/hwid-devices/{device_id}")
async def delete_user_hwid_device(
    user_uuid: str,
    device_id: str,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Delete a specific HWID device for a user."""
    try:
        from shared.database import db_service
        from shared.api_client import api_client

        # Delete from local DB (parameter is hwid, not device_id)
        if db_service.is_connected:
            await db_service.delete_hwid_device(user_uuid=user_uuid, hwid=device_id)

        # Also delete from main API
        try:
            await api_client.delete_user_hwid_device(user_uuid, device_id)
        except Exception as e:
            logger.warning("Failed to delete HWID device %s from API for %s: %s", device_id, user_uuid, e)

        return {"success": True, "message": "Device deleted"}
    except Exception as e:
        logger.error("Error deleting HWID device %s for %s: %s", device_id, user_uuid, e)
        raise HTTPException(status_code=500, detail=f"Failed to delete device: {str(e)}")


@router.delete("/{user_uuid}/hwid-devices")
async def delete_all_user_hwid_devices(
    user_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Delete all HWID devices for a user."""
    try:
        from shared.database import db_service
        from shared.api_client import api_client

        # Delete from local DB
        if db_service.is_connected:
            await db_service.delete_all_user_hwid_devices(user_uuid=user_uuid)

        # Also delete from main API
        try:
            await api_client.delete_all_user_hwid_devices(user_uuid)
        except Exception as e:
            logger.warning("Failed to delete all HWID devices from API for %s: %s", user_uuid, e)

        return {"success": True, "message": "All devices deleted"}
    except Exception as e:
        logger.error("Error deleting all HWID devices for %s: %s", user_uuid, e)
        raise HTTPException(status_code=500, detail=f"Failed to delete all devices: {str(e)}")


# ── Bulk operations ──────────────────────────────────────────────


@router.post("/bulk/enable", response_model=BulkOperationResult)
@limiter.limit(RATE_BULK)
async def bulk_enable_users(
    request: Request,
    body: BulkUserRequest,
    admin: AdminUser = Depends(require_permission("users", "bulk_operations")),
):
    """Enable multiple users at once (max 100)."""
    try:
        from shared.api_client import api_client
    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)

    success, failed, errors = 0, 0, []
    for uuid in body.uuids:
        try:
            await api_client.enable_user(uuid)
            success += 1
        except Exception as e:
            failed += 1
            errors.append(BulkOperationError(uuid=uuid, error=str(e)))

    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="user.bulk_enable", resource="users", resource_id="bulk",
        details=json.dumps({"count": len(body.uuids), "success": success, "failed": failed}),
        ip_address=get_client_ip(request),
    )
    return BulkOperationResult(success=success, failed=failed, errors=errors)


@router.post("/bulk/disable", response_model=BulkOperationResult)
@limiter.limit(RATE_BULK)
async def bulk_disable_users(
    request: Request,
    body: BulkUserRequest,
    admin: AdminUser = Depends(require_permission("users", "bulk_operations")),
):
    """Disable multiple users at once (max 100)."""
    try:
        from shared.api_client import api_client
    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)

    success, failed, errors = 0, 0, []
    for uuid in body.uuids:
        try:
            await api_client.disable_user(uuid)
            success += 1
        except Exception as e:
            failed += 1
            errors.append(BulkOperationError(uuid=uuid, error=str(e)))

    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="user.bulk_disable", resource="users", resource_id="bulk",
        details=json.dumps({"count": len(body.uuids), "success": success, "failed": failed}),
        ip_address=get_client_ip(request),
    )
    return BulkOperationResult(success=success, failed=failed, errors=errors)


@router.post("/bulk/delete", response_model=BulkOperationResult)
@limiter.limit(RATE_BULK)
async def bulk_delete_users(
    request: Request,
    body: BulkUserRequest,
    admin: AdminUser = Depends(require_permission("users", "bulk_operations")),
):
    """Delete multiple users at once (max 100)."""
    try:
        from shared.api_client import api_client
    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)

    success, failed, errors = 0, 0, []
    for uuid in body.uuids:
        try:
            await api_client.delete_user(uuid)
            try:
                from shared.database import db_service
                if db_service.is_connected:
                    await db_service.delete_user(uuid)
            except Exception as e:
                logger.debug("Non-critical: failed to delete user from local DB: %s", e)
            success += 1
        except Exception as e:
            failed += 1
            errors.append(BulkOperationError(uuid=uuid, error=str(e)))

    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="user.bulk_delete", resource="users", resource_id="bulk",
        details=json.dumps({"count": len(body.uuids), "success": success, "failed": failed}),
        ip_address=get_client_ip(request),
    )
    return BulkOperationResult(success=success, failed=failed, errors=errors)


@router.post("/bulk/reset-traffic", response_model=BulkOperationResult)
@limiter.limit(RATE_BULK)
async def bulk_reset_traffic(
    request: Request,
    body: BulkUserRequest,
    admin: AdminUser = Depends(require_permission("users", "bulk_operations")),
):
    """Reset traffic for multiple users at once (max 100)."""
    try:
        from shared.api_client import api_client
    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)

    success, failed, errors = 0, 0, []
    for uuid in body.uuids:
        try:
            await api_client.reset_user_traffic(uuid)
            success += 1
        except Exception as e:
            failed += 1
            errors.append(BulkOperationError(uuid=uuid, error=str(e)))

    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="user.bulk_reset_traffic", resource="users", resource_id="bulk",
        details=json.dumps({"count": len(body.uuids), "success": success, "failed": failed}),
        ip_address=get_client_ip(request),
    )
    return BulkOperationResult(success=success, failed=failed, errors=errors)



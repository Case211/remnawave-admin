"""Users API endpoints."""
import logging
import sys
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException

# Add src to path for importing bot services
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from web.backend.api.deps import get_current_admin, AdminUser
from web.backend.core.api_helper import fetch_users_from_api
from web.backend.schemas.user import UserListItem, UserDetail, UserCreate, UserUpdate
from web.backend.schemas.common import PaginatedResponse, SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _ensure_snake_case(user: dict) -> dict:
    """Ensure user dict has snake_case keys for pydantic schemas."""
    result = dict(user)
    mappings = {
        'shortUuid': 'short_uuid',
        'subscriptionUuid': 'subscription_uuid',
        'telegramId': 'telegram_id',
        'expireAt': 'expire_at',
        'trafficLimitBytes': 'traffic_limit_bytes',
        'usedTrafficBytes': 'used_traffic_bytes',
        'hwidDeviceLimit': 'hwid_device_limit',
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


@router.get("/", response_model=PaginatedResponse[UserListItem])
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by username, email, or UUID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    admin: AdminUser = Depends(get_current_admin),
):
    """List users with pagination and filtering."""
    try:
        users = await _get_users_list()
        # Normalize all users to have snake_case keys
        users = [_ensure_snake_case(u) for u in users]

        def _get(u, *keys, default=''):
            for k in keys:
                v = u.get(k)
                if v is not None:
                    return v
            return default

        # Filter
        if search:
            search_lower = search.lower()
            users = [
                u for u in users
                if search_lower in str(_get(u, 'username')).lower()
                or search_lower in str(_get(u, 'email')).lower()
                or search_lower in str(_get(u, 'uuid')).lower()
                or search_lower in str(_get(u, 'short_uuid')).lower()
                or search_lower in str(_get(u, 'telegram_id')).lower()
            ]

        if status:
            status_lower = status.lower()
            users = [u for u in users if str(_get(u, 'status')).lower() == status_lower]

        # Sort
        reverse = sort_order == "desc"
        sort_key_map = {
            'created_at': ('created_at',),
            'username': ('username',),
            'status': ('status',),
            'expire_at': ('expire_at',),
        }
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
                user_data = await api_client.get_user(user_uuid)
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


@router.post("/", response_model=UserDetail)
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

        update_data = data.model_dump(exclude_unset=True)
        user = await api_client.update_user(user_uuid, **update_data)

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

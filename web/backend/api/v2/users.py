"""Users API endpoints."""
import sys
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException

# Add src to path for importing bot services
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from web.backend.api.deps import get_current_admin, AdminUser
from web.backend.schemas.user import UserListItem, UserDetail, UserCreate, UserUpdate
from web.backend.schemas.common import PaginatedResponse, SuccessResponse

router = APIRouter()


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
    """
    List users with pagination and filtering.
    """
    try:
        from src.services.database import db_service

        # Get all users from cache
        users = await db_service.get_all_users()

        # Filter
        if search:
            search_lower = search.lower()
            users = [
                u for u in users
                if search_lower in (u.get('username') or '').lower()
                or search_lower in (u.get('email') or '').lower()
                or search_lower in (u.get('uuid') or '').lower()
                or search_lower in (u.get('short_uuid') or '').lower()
            ]

        if status:
            users = [u for u in users if u.get('status') == status]

        # Sort
        reverse = sort_order == "desc"
        users.sort(key=lambda x: x.get(sort_by) or '', reverse=reverse)

        # Paginate
        total = len(users)
        start = (page - 1) * per_page
        end = start + per_page
        items = users[start:end]

        # Convert to schema
        user_items = [UserListItem(**u) for u in items]

        return PaginatedResponse(
            items=user_items,
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page if total > 0 else 1,
        )

    except ImportError:
        # Database service not available
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
    """
    Get detailed user information.
    """
    try:
        from src.services.api_client import api_client

        user = await api_client.get_user(user_uuid)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return UserDetail(**user)

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")


@router.post("/", response_model=UserDetail)
async def create_user(
    data: UserCreate,
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Create a new user.
    """
    try:
        from src.services.api_client import api_client

        user = await api_client.create_user(
            username=data.username,
            traffic_limit=data.traffic_limit_bytes,
            expire_days=data.expire_days,
            hwid_device_limit=data.hwid_device_limit,
        )

        return UserDetail(**user)

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
    """
    Update user fields.
    """
    try:
        from src.services.api_client import api_client

        update_data = data.model_dump(exclude_unset=True)
        user = await api_client.update_user(user_uuid, **update_data)

        return UserDetail(**user)

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{user_uuid}", response_model=SuccessResponse)
async def delete_user(
    user_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Delete a user.
    """
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
    """
    Enable a disabled user.
    """
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
    """
    Disable a user.
    """
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
    """
    Reset user's traffic usage.
    """
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
    """
    Revoke user's subscription (regenerate subscription UUID).
    """
    try:
        from src.services.api_client import api_client

        await api_client.revoke_user_subscription(user_uuid)
        return SuccessResponse(message="Subscription revoked")

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

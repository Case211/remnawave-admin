"""Auth API endpoints."""
from fastapi import APIRouter, HTTPException, Depends

from web.backend.api.deps import get_current_admin, AdminUser
from web.backend.core.config import get_web_settings
from web.backend.core.security import (
    verify_telegram_auth,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from web.backend.schemas.auth import (
    TelegramAuthData,
    TokenResponse,
    RefreshRequest,
    AdminInfo,
)
from web.backend.schemas.common import SuccessResponse

router = APIRouter()


@router.post("/telegram", response_model=TokenResponse)
async def telegram_login(data: TelegramAuthData):
    """
    Authenticate via Telegram Login Widget.

    Verifies the data signature and creates JWT tokens.
    """
    # Convert to dict for verification
    auth_dict = data.model_dump()

    # Verify Telegram signature
    if not verify_telegram_auth(auth_dict.copy()):
        raise HTTPException(status_code=401, detail="Invalid Telegram auth data")

    # Check if user is in admins list
    settings = get_web_settings()
    if data.id not in settings.admins:
        raise HTTPException(status_code=403, detail="Not an admin")

    # Create tokens
    username = data.username or data.first_name
    access_token = create_access_token(data.id, username)
    refresh_token = create_refresh_token(data.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(data: RefreshRequest):
    """
    Refresh access token using refresh token.
    """
    payload = decode_token(data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    telegram_id = int(payload["sub"])

    # Verify still an admin
    settings = get_web_settings()
    if telegram_id not in settings.admins:
        raise HTTPException(status_code=403, detail="Not an admin")

    # Create new tokens
    access_token = create_access_token(telegram_id, "admin")
    refresh_token = create_refresh_token(telegram_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.get("/me", response_model=AdminInfo)
async def get_current_user(admin: AdminUser = Depends(get_current_admin)):
    """
    Get current authenticated admin info.
    """
    return AdminInfo(
        telegram_id=admin.telegram_id,
        username=admin.username,
        role=admin.role,
    )


@router.post("/logout", response_model=SuccessResponse)
async def logout(admin: AdminUser = Depends(get_current_admin)):
    """
    Logout (client should delete tokens).

    Note: In a more complete implementation, we would add
    the token to a blacklist.
    """
    return SuccessResponse(message="Logged out successfully")

"""Auth API endpoints."""
import logging
from fastapi import APIRouter, HTTPException, Depends, Request

from web.backend.api.deps import get_current_admin, AdminUser
from web.backend.core.config import get_web_settings
from web.backend.core.rate_limit import limiter
from web.backend.core.security import (
    verify_telegram_auth,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from web.backend.core.token_blacklist import token_blacklist
from web.backend.schemas.auth import (
    TelegramAuthData,
    TokenResponse,
    RefreshRequest,
    AdminInfo,
)
from web.backend.schemas.common import SuccessResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/telegram", response_model=TokenResponse)
@limiter.limit("5/minute")
async def telegram_login(request: Request, data: TelegramAuthData):
    """
    Authenticate via Telegram Login Widget.

    Verifies the data signature and creates JWT tokens.
    """
    settings = get_web_settings()

    # Convert to dict for verification
    auth_dict = data.model_dump()

    logger.info("Login attempt from Telegram user (id=%d)", data.id)

    # Verify Telegram signature
    is_valid, error_message = verify_telegram_auth(auth_dict)
    if not is_valid:
        logger.warning("Auth verification failed for user id=%d: %s", data.id, error_message)
        raise HTTPException(
            status_code=401,
            detail=f"Invalid Telegram auth data: {error_message}"
        )

    # Check if user is in admins list
    if data.id not in settings.admins:
        logger.warning(f"User {data.id} is not in admins list: {settings.admins}")
        raise HTTPException(
            status_code=403,
            detail="Access denied"
        )

    # Create tokens
    username = data.username or data.first_name
    access_token = create_access_token(data.id, username)
    refresh_token = create_refresh_token(data.id)

    logger.info("Login successful for user id=%d", data.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh_tokens(request: Request, data: RefreshRequest):
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
async def logout(
    request: Request,
    admin: AdminUser = Depends(get_current_admin),
):
    """Logout and invalidate the current access token."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_token(token)
        if payload and "exp" in payload:
            token_blacklist.add(token, float(payload["exp"]))
            logger.info("Token blacklisted for user id=%d", admin.telegram_id)
    return SuccessResponse(message="Logged out successfully")

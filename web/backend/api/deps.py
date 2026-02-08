"""API dependencies for web panel."""
import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status, Query, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from web.backend.core.config import get_web_settings
from web.backend.core.security import decode_token
from web.backend.core.token_blacklist import token_blacklist

logger = logging.getLogger(__name__)
security = HTTPBearer()


@dataclass
class AdminUser:
    """Authenticated admin user."""

    telegram_id: Optional[int] = None
    username: str = "admin"
    role: str = "admin"
    auth_method: str = "telegram"


def _validate_token_payload(payload: dict) -> AdminUser:
    """Validate token payload and return AdminUser.

    Handles both Telegram-based (sub = telegram_id) and
    password-based (sub = "pwd:<username>") authentication.
    """
    subject = payload.get("sub", "")
    settings = get_web_settings()

    if subject.startswith("pwd:"):
        # Password-based auth
        username = subject[4:]
        if not settings.admin_login or username.lower() != settings.admin_login.lower():
            logger.warning("Access denied for password user '%s': account not configured", username)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin account disabled",
            )
        return AdminUser(
            telegram_id=None,
            username=username,
            auth_method="password",
        )
    else:
        # Telegram-based auth
        try:
            telegram_id = int(subject)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if telegram_id not in settings.admins:
            logger.warning("Access denied: telegram_id=%d", telegram_id)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not an admin",
            )
        return AdminUser(
            telegram_id=telegram_id,
            username=payload.get("username", "admin"),
            auth_method="telegram",
        )


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AdminUser:
    """
    Dependency for verifying admin authentication.

    Args:
        credentials: HTTP Bearer credentials

    Returns:
        AdminUser if authenticated

    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials

    # Check if token has been blacklisted (logout)
    if token_blacklist.is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _validate_token_payload(payload)


async def get_current_admin_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
) -> AdminUser:
    """
    Dependency for verifying admin authentication in WebSocket.

    Args:
        websocket: WebSocket connection
        token: JWT token from query parameter

    Returns:
        AdminUser if authenticated

    Raises:
        WebSocketException: If authentication fails
    """
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        raise HTTPException(status_code=401, detail="Missing token")

    if token_blacklist.is_blacklisted(token):
        await websocket.close(code=4001, reason="Token revoked")
        raise HTTPException(status_code=401, detail="Token revoked")

    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        await websocket.close(code=4001, reason="Invalid token")
        raise HTTPException(status_code=401, detail="Invalid token")

    try:
        admin = _validate_token_payload(payload)
    except HTTPException:
        await websocket.close(code=4003, reason="Access denied")
        raise

    return admin


async def get_optional_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    )
) -> Optional[AdminUser]:
    """
    Optional admin authentication (doesn't fail if not authenticated).

    Args:
        credentials: Optional HTTP Bearer credentials

    Returns:
        AdminUser if authenticated, None otherwise
    """
    if not credentials:
        return None

    try:
        return await get_current_admin(credentials)
    except HTTPException:
        return None


async def get_db():
    """
    Dependency for database access.

    Returns:
        DatabaseService instance
    """
    from src.services.database import db_service
    return db_service


async def get_api_client():
    """
    Dependency for API client access.

    Returns:
        RemnavaveAPIClient instance
    """
    from src.services.api_client import api_client
    return api_client

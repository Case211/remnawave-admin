"""API dependencies for web panel."""
import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status, Query, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from web.backend.core.config import get_web_settings
from web.backend.core.security import decode_token

logger = logging.getLogger(__name__)
security = HTTPBearer()


@dataclass
class AdminUser:
    """Authenticated admin user."""

    telegram_id: int
    username: str
    role: str = "admin"


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
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    telegram_id = int(payload["sub"])

    # Verify admin is in admins list
    settings = get_web_settings()
    admins_list = settings.admins
    logger.info(
        f"Admin check: telegram_id={telegram_id}, "
        f"admins_raw={repr(settings.admins_raw)}, "
        f"admins_list={admins_list}"
    )
    if telegram_id not in admins_list:
        logger.warning(
            f"Admin check FAILED: {telegram_id} not in {admins_list}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not an admin",
        )

    return AdminUser(
        telegram_id=telegram_id,
        username=payload.get("username", "admin"),
    )


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

    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        await websocket.close(code=4001, reason="Invalid token")
        raise HTTPException(status_code=401, detail="Invalid token")

    telegram_id = int(payload["sub"])

    settings = get_web_settings()
    if telegram_id not in settings.admins:
        await websocket.close(code=4003, reason="Not an admin")
        raise HTTPException(status_code=403, detail="Not an admin")

    return AdminUser(
        telegram_id=telegram_id,
        username=payload.get("username", "admin"),
    )


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

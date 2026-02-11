"""API dependencies for web panel."""
import functools
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Set

from fastapi import Depends, HTTPException, Request, status, Query, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from web.backend.core.config import get_web_settings
from web.backend.core.security import decode_token
from web.backend.core.token_blacklist import token_blacklist

logger = logging.getLogger(__name__)
security = HTTPBearer()


@dataclass
class AdminUser:
    """Authenticated admin user with RBAC info."""

    telegram_id: Optional[int] = None
    username: str = "admin"
    role: str = "admin"
    role_id: Optional[int] = None
    auth_method: str = "telegram"
    account_id: Optional[int] = None
    permissions: Set[Tuple[str, str]] = field(default_factory=set)

    def has_permission(self, resource: str, action: str) -> bool:
        """Check if this admin has a specific permission."""
        return (resource, action) in self.permissions


async def _validate_token_payload(payload: dict) -> AdminUser:
    """Validate token payload and return AdminUser.

    Resolves admin account from admin_accounts (RBAC) table,
    falling back to .env for backwards compat.
    """
    subject = payload.get("sub", "")
    settings = get_web_settings()

    if subject.startswith("pwd:"):
        username = subject[4:]
        return await _resolve_password_admin(username, settings)
    else:
        return await _resolve_telegram_admin(subject, payload, settings)


async def _resolve_password_admin(username: str, settings) -> AdminUser:
    """Resolve a password-authenticated admin."""
    # 1. Try admin_accounts table (RBAC)
    try:
        from web.backend.core.rbac import (
            get_admin_account_by_username,
            get_all_permissions_for_role_id,
        )
        account = await get_admin_account_by_username(username)
        if account:
            if not account["is_active"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin account disabled",
                )
            perms = set()
            if account["role_id"]:
                perms = await get_all_permissions_for_role_id(account["role_id"])
            return AdminUser(
                telegram_id=account.get("telegram_id"),
                username=account["username"],
                role=account.get("role_name", "admin"),
                role_id=account.get("role_id"),
                auth_method="password",
                account_id=account["id"],
                permissions=perms,
            )
    except HTTPException:
        raise
    except Exception:
        pass

    # 2. Fallback: .env
    if settings.admin_login and username.lower() == settings.admin_login.lower():
        return AdminUser(
            username=username,
            role="superadmin",
            auth_method="password",
        )

    logger.warning("Access denied for password user '%s': account not configured", username)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin account disabled",
    )


async def _resolve_telegram_admin(subject: str, payload: dict, settings) -> AdminUser:
    """Resolve a Telegram-authenticated admin."""
    try:
        telegram_id = int(subject)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Try RBAC admin_accounts table
    try:
        from web.backend.core.rbac import (
            get_admin_account_by_telegram_id,
            get_all_permissions_for_role_id,
        )
        account = await get_admin_account_by_telegram_id(telegram_id)
        if account:
            if not account["is_active"]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin account disabled",
                )
            perms = set()
            if account["role_id"]:
                perms = await get_all_permissions_for_role_id(account["role_id"])
            return AdminUser(
                telegram_id=telegram_id,
                username=account["username"],
                role=account.get("role_name", "admin"),
                role_id=account.get("role_id"),
                auth_method="telegram",
                account_id=account["id"],
                permissions=perms,
            )
    except HTTPException:
        raise
    except Exception:
        pass

    # 2. Fallback: ADMINS env var (legacy — treat as superadmin)
    if telegram_id in settings.admins:
        return AdminUser(
            telegram_id=telegram_id,
            username=payload.get("username", "admin"),
            role="superadmin",
            auth_method="telegram",
        )

    logger.warning("Access denied: telegram_id=%d", telegram_id)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Not an admin",
    )


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AdminUser:
    """Dependency for verifying admin authentication."""
    token = credentials.credentials

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

    return await _validate_token_payload(payload)


async def get_current_admin_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
) -> AdminUser:
    """Dependency for verifying admin authentication in WebSocket."""
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
        admin = await _validate_token_payload(payload)
    except HTTPException:
        await websocket.close(code=4003, reason="Access denied")
        raise

    return admin


async def get_optional_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> Optional[AdminUser]:
    """Optional admin authentication (doesn't fail if not authenticated)."""
    if not credentials:
        return None
    try:
        return await get_current_admin(credentials)
    except HTTPException:
        return None


# ── Permission-checking dependency factory ──────────────────────

def require_permission(resource: str, action: str):
    """Create a dependency that checks for a specific permission.

    Usage in endpoint:
        @router.post("/users")
        async def create_user(admin: AdminUser = Depends(require_permission("users", "create"))):
            ...

    Admins with role "superadmin" (or from legacy ADMINS env) bypass checks.
    """
    async def _check(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
        # Legacy fallback: admins without account_id (from ADMINS env or .env creds)
        # are treated as superadmin with full access
        if admin.account_id is None:
            return admin

        # Superadmin role bypasses all checks
        if admin.role == "superadmin":
            return admin

        if not admin.has_permission(resource, action):
            logger.warning(
                "Permission denied: %s (%s) -> %s:%s",
                admin.username, admin.role, resource, action,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {resource}:{action}",
            )
        return admin

    return _check


def require_superadmin():
    """Dependency that requires the superadmin role."""
    async def _check(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
        if admin.account_id is None:
            # Legacy admin from ADMINS env — treated as superadmin
            return admin
        if admin.role != "superadmin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Superadmin access required",
            )
        return admin
    return _check


# ── Quota-checking dependency factory ───────────────────────

def require_quota(resource: str):
    """Create a dependency that checks admin quota before resource creation.

    Usage in endpoint:
        @router.post("/users")
        async def create_user(
            admin: AdminUser = Depends(require_permission("users", "create")),
            _: None = Depends(require_quota("users")),
        ):
            ...

    Admins without account_id (legacy) or with superadmin role bypass quota.
    Null limits mean unlimited — no check needed.
    """
    async def _check(admin: AdminUser = Depends(get_current_admin)) -> None:
        # Legacy admins and superadmins bypass quota
        if admin.account_id is None or admin.role == "superadmin":
            return

        from web.backend.core.rbac import check_quota
        allowed, error_msg = await check_quota(admin.account_id, resource)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=error_msg,
            )

    return _check


# ── Utility helpers ─────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_db():
    """Dependency for database access."""
    from src.services.database import db_service
    return db_service


async def get_api_client():
    """Dependency for API client access."""
    from src.services.api_client import api_client
    return api_client

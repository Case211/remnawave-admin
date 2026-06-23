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
from shared.db_schema import ADMIN_TABLE
from shared.db_query import insert_sql

logger = logging.getLogger(__name__)
# auto_error=False: при отсутствии Authorization пробуем cookie-аутентификацию
security = HTTPBearer(auto_error=False)


@dataclass
class AdminUser:
    """Authenticated admin user with RBAC info."""

    telegram_id: Optional[int] = None
    username: str = "admin"
    role: str = "admin"
    role_id: Optional[int] = None
    auth_method: str = "telegram"
    account_id: Optional[int] = None
    unrestricted_user_access: bool = False
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
                role=account.get("role_name") or "admin",
                role_id=account.get("role_id"),
                auth_method="password",
                account_id=account["id"],
                unrestricted_user_access=account.get("unrestricted_user_access", False) or False,
                permissions=perms,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("RBAC lookup failed: %s", e)

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
                role=account.get("role_name") or "admin",
                role_id=account.get("role_id"),
                auth_method="telegram",
                account_id=account["id"],
                unrestricted_user_access=account.get("unrestricted_user_access", False) or False,
                permissions=perms,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("RBAC lookup failed: %s", e)

    # 2. Fallback: ADMINS env var — auto-provision RBAC account
    if telegram_id in settings.admins:
        try:
            from web.backend.core.rbac import get_role_by_name, get_all_permissions_for_role_id
            from shared.database import db_service

            role = await get_role_by_name("superadmin")
            if role and db_service.is_connected:
                username = payload.get("username", f"admin_{telegram_id}")
                async with db_service.acquire() as conn:
                    account = await conn.fetchrow(
                        insert_sql(
                            ADMIN_TABLE,
                            ["username", "telegram_id", "role_id", "is_active"],
                            values="$1, $2, $3, true",
                            suffix="ON CONFLICT (telegram_id) DO UPDATE SET username = EXCLUDED.username",
                            returning="*",
                        ),
                        username, telegram_id, role["id"],
                    )
                if account:
                    actual_role_id = account["role_id"]
                    perms = await get_all_permissions_for_role_id(actual_role_id)
                    # Determine actual role name (may have been changed by superadmin)
                    role_name = "superadmin"
                    if actual_role_id != role["id"]:
                        from web.backend.core.rbac import get_role_by_id
                        actual_role = await get_role_by_id(actual_role_id)
                        role_name = actual_role["name"] if actual_role else "admin"
                    logger.info(
                        "RBAC account for ADMINS env admin: tg_id=%d, account_id=%d, role=%s",
                        telegram_id, account["id"], role_name,
                    )
                    return AdminUser(
                        telegram_id=telegram_id,
                        username=account["username"],
                        role=role_name,
                        role_id=actual_role_id,
                        auth_method="telegram",
                        account_id=account["id"],
                        unrestricted_user_access=account.get("unrestricted_user_access", False) or False,
                        permissions=perms,
                    )
        except Exception as e:
            logger.warning("Failed to auto-provision admin account for tg_id=%d: %s", telegram_id, e)

        # Final fallback: legacy mode (no RBAC account — DB unavailable)
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
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AdminUser:
    """Dependency for verifying admin authentication.

    Источники токена (по приоритету):
    1. Authorization: Bearer — API-клиенты, мобильное приложение
    2. HttpOnly cookie rw_access — веб-фронт; мутирующие методы требуют
       X-CSRF-Token (double-submit, см. core/auth_cookies.py)
    """
    from web.backend.core.auth_cookies import ACCESS_COOKIE, csrf_check_passed

    token: Optional[str] = credentials.credentials if credentials else None

    if token is None:
        token = request.cookies.get(ACCESS_COOKIE)
        if token and not csrf_check_passed(request):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing or invalid",
            )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if token_blacklist.is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token, token_type="access")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await _validate_token_payload(payload)


async def get_2fa_temp_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> AdminUser:
    """Dependency for endpoints that accept a 2FA temp token.

    Temp-токен короткоживущий (5 мин) и передаётся только через
    Authorization header — cookie-механизм к нему не применяется.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials

    if token_blacklist.is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token, token_type="2fa_temp")
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired 2FA token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await _validate_token_payload(payload)


# Маркер-подпротокол для передачи JWT в WebSocket-handshake:
# клиент шлёт Sec-WebSocket-Protocol: "access-token, <jwt>".
WS_AUTH_SUBPROTOCOL = "access-token"


def extract_ws_token(websocket: WebSocket) -> Tuple[Optional[str], Optional[str]]:
    """Extract JWT from a WebSocket handshake.

    Источники (по приоритету):
    1. Sec-WebSocket-Protocol ("access-token, <jwt>") — токен не попадает
       в access-логи прокси/сервера в отличие от query string.
    2. HttpOnly cookie rw_access — веб-фронт на cookie-аутентификации
       (браузер шлёт cookie при handshake автоматически; CSRF-риска нет —
       сервер только пушит события, мутаций по WS не делает).
    3. ?token= query param — deprecated, для старых клиентов
       (мобильное приложение обновляется отдельно).

    Returns (token, subprotocol): subprotocol нужно передать в
    websocket.accept(subprotocol=...) — браузер разрывает соединение,
    если сервер не подтвердил запрошенный подпротокол.
    """
    from web.backend.core.auth_cookies import ACCESS_COOKIE

    proto_header = websocket.headers.get("sec-websocket-protocol", "")
    if proto_header:
        parts = [p.strip() for p in proto_header.split(",")]
        if len(parts) >= 2 and parts[0] == WS_AUTH_SUBPROTOCOL and parts[1]:
            return parts[1], WS_AUTH_SUBPROTOCOL

    cookie_token = websocket.cookies.get(ACCESS_COOKIE)
    if cookie_token:
        return cookie_token, None

    return websocket.query_params.get("token"), None


async def get_current_admin_ws(
    websocket: WebSocket,
    token: Optional[str] = None,
) -> AdminUser:
    """Dependency for verifying admin authentication in WebSocket.

    Если token не передан явно, извлекается из handshake (см. extract_ws_token).
    Сохраняет websocket.state.auth_subprotocol — эндпоинт ОБЯЗАН передать его
    в websocket.accept(subprotocol=...).
    """
    if token is None:
        token, subprotocol = extract_ws_token(websocket)
        websocket.state.auth_subprotocol = subprotocol
    else:
        websocket.state.auth_subprotocol = None

    if not token:
        await websocket.close(code=4001, reason="Missing token")
        raise HTTPException(status_code=401, detail="Missing token")

    if token_blacklist.is_blacklisted(token):
        await websocket.close(code=4001, reason="Token revoked")
        raise HTTPException(status_code=401, detail="Token revoked")

    payload = decode_token(token, token_type="access")
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        raise HTTPException(status_code=401, detail="Invalid token")

    try:
        admin = await _validate_token_payload(payload)
    except HTTPException:
        await websocket.close(code=4003, reason="Access denied")
        raise

    return admin


async def get_optional_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> Optional[AdminUser]:
    """Optional admin authentication (doesn't fail if not authenticated)."""
    try:
        return await get_current_admin(request, credentials)
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
            logger.warning(
                "Legacy admin bypass for '%s' — consider migrating to RBAC account",
                admin.username,
            )
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
            logger.warning(
                "Legacy admin bypass for '%s' — consider migrating to RBAC account",
                admin.username,
            )
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
        from web.backend.core.errors import api_error, E
        allowed, error_msg = await check_quota(admin.account_id, resource)
        if not allowed:
            # Map resource name to a specific quota error code so the
            # frontend can show a contextual message.
            code = {
                "users": E.USERS_QUOTA_EXCEEDED,
                "nodes": E.NODES_QUOTA_EXCEEDED,
                "hosts": E.HOSTS_QUOTA_EXCEEDED,
            }.get(resource, E.QUOTA_EXCEEDED)
            raise api_error(status.HTTP_403_FORBIDDEN, code, error_msg)

    return _check


# ── Utility helpers ─────────────────────────────────────────────

def get_client_ip(request: Request) -> str:
    """Extract client IP from trusted proxy headers.

    Priority:
    1. X-Real-IP (set by nginx, most reliable)
    2. X-Forwarded-For first entry (set by upstream reverse proxy)
    3. request.client.host (direct connection fallback)
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_db():
    """Dependency for database access."""
    from shared.database import db_service
    return db_service


async def get_api_client():
    """Dependency for API client access."""
    from shared.api_client import api_client
    return api_client


INTERNAL_API_SECRET_HEADER = "X-Internal-Api-Secret"


async def verify_internal_api_secret(request: Request) -> None:
    """Dependency to verify internal API secret for bot→backend communication.

    Reads the X-Internal-Api-Secret header and compares it with the
    INTERNAL_API_SECRET environment variable. Both bot and backend
    share the same .env file, so this works without a chicken-egg problem.
    """
    import os
    expected = os.environ.get("INTERNAL_API_SECRET", "")
    if not expected:
        logger.warning("INTERNAL_API_SECRET not set, rejecting internal request")
        raise HTTPException(status_code=500, detail="INTERNAL_API_SECRET not configured")
    received = request.headers.get(INTERNAL_API_SECRET_HEADER, "")
    if not received or received != expected:
        logger.warning("Invalid INTERNAL_API_SECRET from %s", request.client.host if request.client else "unknown")
        raise HTTPException(status_code=401, detail="Invalid internal API secret")
    logger.debug("Internal API request verified from %s", request.client.host if request.client else "unknown")

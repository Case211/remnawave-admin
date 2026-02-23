"""Auth API endpoints."""
import logging
from fastapi import APIRouter, HTTPException, Depends, Request

from web.backend.api.deps import get_current_admin, AdminUser
from web.backend.core.errors import api_error, E
from web.backend.core.config import get_web_settings
from web.backend.core.login_guard import login_guard
from web.backend.core.notifier import (
    notify_login_failed,
    notify_login_success,
    notify_ip_blocked,
)
from web.backend.core.rate_limit import limiter
from web.backend.core.security import (
    verify_telegram_auth,
    verify_admin_password_async,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from web.backend.core.token_blacklist import token_blacklist
from web.backend.schemas.auth import (
    TelegramAuthData,
    LoginRequest,
    RegisterRequest,
    SetupStatusResponse,
    ChangePasswordRequest,
    TokenResponse,
    RefreshRequest,
    AdminInfo,
    PermissionEntry,
)
from web.backend.schemas.common import SuccessResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First IP in the chain is the original client
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.get("/setup-status", response_model=SetupStatusResponse)
async def get_setup_status(request: Request):
    """
    Check whether initial admin setup is needed.

    Returns needs_setup=true when no admin account exists in the DB
    and no .env credentials are configured.
    """
    settings = get_web_settings()
    has_env_auth = bool(settings.admin_login and settings.admin_password)

    has_db_auth = False
    try:
        from web.backend.core.admin_credentials import admin_exists
        has_db_auth = await admin_exists()
    except Exception as e:
        logger.debug("Non-critical: %s", e)

    # Also check RBAC admin_accounts table
    has_rbac_accounts = False
    try:
        from web.backend.core.rbac import admin_account_exists
        has_rbac_accounts = await admin_account_exists()
    except Exception as e:
        logger.debug("Non-critical: %s", e)

    needs_setup = not has_env_auth and not has_db_auth and not has_rbac_accounts
    return SetupStatusResponse(needs_setup=needs_setup)


@router.post("/register", response_model=TokenResponse)
@limiter.limit("3/minute")
async def register_admin(request: Request, data: RegisterRequest):
    """
    Register the first admin account. Only works when no admin exists.

    This endpoint is only available during initial setup.
    """
    settings = get_web_settings()
    client_ip = _get_client_ip(request)

    # Check that no admin exists yet (guard against abuse)
    has_env_auth = bool(settings.admin_login and settings.admin_password)
    has_db_auth = False
    try:
        from web.backend.core.admin_credentials import admin_exists
        has_db_auth = await admin_exists()
    except Exception as e:
        logger.debug("Non-critical: %s", e)

    has_rbac_accounts = False
    try:
        from web.backend.core.rbac import admin_account_exists
        has_rbac_accounts = await admin_account_exists()
    except Exception as e:
        logger.debug("Non-critical: %s", e)

    if has_env_auth or has_db_auth or has_rbac_accounts:
        raise api_error(403, E.FORBIDDEN, "Admin account already exists. Registration is disabled.")

    # Validate password strength
    from web.backend.core.admin_credentials import (
        validate_password_strength,
        create_admin,
        ensure_table,
    )

    is_strong, strength_error = validate_password_strength(data.password)
    if not is_strong:
        raise api_error(400, E.INVALID_PASSWORD, strength_error)

    # Validate username
    if len(data.username.strip()) < 3:
        raise api_error(400, E.INVALID_USERNAME, "Username must be at least 3 characters")

    # Create the admin account
    await ensure_table()
    success = await create_admin(data.username.strip(), data.password, is_generated=False)
    if not success:
        raise api_error(500, E.ADMIN_CREATE_FAILED)

    logger.info("First admin registered: '%s' from %s", data.username, client_ip)

    # Auto-login after registration
    subject = f"pwd:{data.username.strip()}"
    access_token = create_access_token(subject, data.username.strip(), auth_method="password")
    refresh_token = create_refresh_token(subject)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.post("/telegram", response_model=TokenResponse)
@limiter.limit("5/minute")
async def telegram_login(request: Request, data: TelegramAuthData):
    """
    Authenticate via Telegram Login Widget.

    Verifies the data signature and creates JWT tokens.
    """
    settings = get_web_settings()
    client_ip = _get_client_ip(request)

    # Check brute-force lockout
    if login_guard.is_locked(client_ip):
        remaining = login_guard.remaining_seconds(client_ip)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {remaining}s",
        )

    # Convert to dict for verification
    auth_dict = data.model_dump()

    logger.info("Login attempt from Telegram user (id=%d) from %s", data.id, client_ip)

    # Verify Telegram signature
    is_valid, error_message = verify_telegram_auth(auth_dict)
    if not is_valid:
        logger.warning("Auth verification failed for user id=%d: %s", data.id, error_message)
        locked = login_guard.record_failure(client_ip)
        await notify_login_failed(
            ip=client_ip,
            username=f"tg:{data.id}",
            auth_method="telegram",
            reason=error_message,
        )
        if locked:
            await notify_ip_blocked(client_ip, 900, 5)
        raise api_error(401, E.INVALID_TOKEN, f"Invalid Telegram auth data: {error_message}")

    # Check if user is in admins list
    if data.id not in settings.admins:
        logger.warning(f"User {data.id} is not in admins list: {settings.admins}")
        locked = login_guard.record_failure(client_ip)
        await notify_login_failed(
            ip=client_ip,
            username=f"tg:{data.id} ({data.username or data.first_name})",
            auth_method="telegram",
            reason="Not in admins list",
        )
        if locked:
            await notify_ip_blocked(client_ip, 900, 5)
        raise api_error(403, E.NOT_AN_ADMIN)

    # Success
    login_guard.record_success(client_ip)

    # Create tokens
    username = data.username or data.first_name
    subject = str(data.id)
    access_token = create_access_token(subject, username, auth_method="telegram")
    refresh_token = create_refresh_token(subject)

    logger.info("Login successful for user id=%d from %s", data.id, client_ip)
    await notify_login_success(ip=client_ip, username=username, auth_method="telegram")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def password_login(request: Request, data: LoginRequest):
    """
    Authenticate with username and password.

    WEB_ADMIN_LOGIN / WEB_ADMIN_PASSWORD must be configured in .env.
    """
    settings = get_web_settings()
    client_ip = _get_client_ip(request)

    # Check brute-force lockout
    if login_guard.is_locked(client_ip):
        remaining = login_guard.remaining_seconds(client_ip)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {remaining}s",
        )

    # Check that password auth is configured (DB or .env)
    has_env_auth = settings.admin_login and settings.admin_password
    has_db_auth = False
    try:
        from web.backend.core.rbac import admin_account_exists
        has_db_auth = await admin_account_exists()
    except Exception as e:
        logger.debug("Non-critical: %s", e)

    if not has_env_auth and not has_db_auth:
        raise api_error(403, E.FORBIDDEN, "Password authentication is not configured")

    logger.info("Password login attempt for user '%s' from %s", data.username, client_ip)

    # Verify credentials (DB first, then .env fallback)
    if not await verify_admin_password_async(data.username, data.password):
        locked = login_guard.record_failure(client_ip)
        logger.warning("Password login failed for user '%s' from %s", data.username, client_ip)
        await notify_login_failed(
            ip=client_ip,
            username=data.username,
            auth_method="password",
            reason="Invalid credentials",
        )
        if locked:
            await notify_ip_blocked(client_ip, 900, 5)
        raise api_error(401, E.INVALID_PASSWORD, "Invalid username or password")

    # Success
    login_guard.record_success(client_ip)

    subject = f"pwd:{data.username}"
    access_token = create_access_token(subject, data.username, auth_method="password")
    refresh_token = create_refresh_token(subject)

    logger.info("Password login successful for user '%s' from %s", data.username, client_ip)
    await notify_login_success(ip=client_ip, username=data.username, auth_method="password")

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

    The old refresh token is blacklisted after successful rotation
    to prevent reuse (one-time use refresh tokens).
    """
    # Check if this refresh token has already been used (blacklisted)
    if token_blacklist.is_blacklisted(data.refresh_token):
        raise api_error(401, E.TOKEN_ALREADY_USED)

    payload = decode_token(data.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise api_error(401, E.INVALID_REFRESH_TOKEN)

    subject = payload["sub"]
    settings = get_web_settings()

    # Determine auth method from subject format
    if subject.startswith("pwd:"):
        # Password-based auth — verify account still exists and is active
        username = subject[4:]
        is_valid = False
        try:
            from web.backend.core.rbac import get_admin_account_by_username
            account = await get_admin_account_by_username(username)
            if account:
                # DB account exists — it is the source of truth
                if not account.get("is_active", True):
                    raise api_error(403, E.ACCOUNT_DISABLED)
                is_valid = True
        except HTTPException:
            raise
        except Exception as e:
            logger.debug("Non-critical: %s", e)
        # Fallback to .env only when no DB account was found
        if not is_valid:
            if not settings.admin_login or username.lower() != settings.admin_login.lower():
                raise api_error(403, E.ADMIN_NOT_FOUND)
        access_token = create_access_token(subject, username, auth_method="password")
    else:
        # Telegram-based auth — verify still in admins list
        telegram_id = int(subject)
        if telegram_id not in settings.admins:
            raise api_error(403, E.NOT_AN_ADMIN)
        access_token = create_access_token(subject, payload.get("username", "admin"), auth_method="telegram")

    refresh_token = create_refresh_token(subject)

    # Blacklist the old refresh token to prevent reuse
    if "exp" in payload:
        token_blacklist.add(data.refresh_token, float(payload["exp"]))

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.get("/me", response_model=AdminInfo)
async def get_current_user(admin: AdminUser = Depends(get_current_admin)):
    """
    Get current authenticated admin info with RBAC permissions.
    """
    # Check if password is auto-generated (needs changing)
    password_is_generated = False
    if admin.auth_method == "password" and admin.account_id:
        try:
            from web.backend.core.rbac import get_admin_account_by_id
            account = await get_admin_account_by_id(admin.account_id)
            if account and account.get("is_generated_password"):
                password_is_generated = True
        except Exception as e:
            logger.debug("Non-critical: %s", e)

    # Build permissions list
    permissions = [
        PermissionEntry(resource=r, action=a)
        for r, a in sorted(admin.permissions)
    ]

    return AdminInfo(
        telegram_id=admin.telegram_id,
        username=admin.username,
        role=admin.role,
        role_id=admin.role_id,
        auth_method=admin.auth_method,
        password_is_generated=password_is_generated,
        permissions=permissions,
    )


@router.post("/change-password", response_model=SuccessResponse)
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Change admin password. Requires current password for verification.
    Only available for password-based accounts stored in DB.
    """
    from web.backend.core.admin_credentials import (
        verify_password,
        hash_password,
        validate_password_strength,
    )
    from web.backend.core.rbac import (
        get_admin_account_by_id,
        get_admin_account_by_username,
        update_admin_account,
    )

    # Validate new password strength
    is_strong, strength_error = validate_password_strength(data.new_password)
    if not is_strong:
        raise api_error(400, E.INVALID_PASSWORD, strength_error)

    # Look up admin in admin_accounts
    account = None
    if admin.account_id:
        account = await get_admin_account_by_id(admin.account_id)
    if not account:
        account = await get_admin_account_by_username(admin.username)

    if not account or not account.get("password_hash"):
        raise api_error(400, E.INVALID_PASSWORD, "Password change is only available for DB-managed accounts")

    # Verify current password
    if not verify_password(data.current_password, account["password_hash"]):
        raise api_error(401, E.INVALID_PASSWORD, "Current password is incorrect")

    # Update password
    new_hash = hash_password(data.new_password)
    updated = await update_admin_account(
        account["id"],
        password_hash=new_hash,
        is_generated_password=False,
    )
    if not updated:
        raise api_error(500, E.PASSWORD_UPDATE_FAILED)

    logger.info("Password changed for user '%s'", admin.username)
    return SuccessResponse(message="Password changed successfully")


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
            logger.info("Token blacklisted for user '%s'", admin.username)
    return SuccessResponse(message="Logged out successfully")

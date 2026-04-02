"""Auth API endpoints."""
import json
import logging
import time
import urllib.parse

import httpx
from jose import jwt as _jwt
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

# Track states initiated by our admin oauth2/authorize.
# Maps state -> expiry timestamp. Used to distinguish admin-initiated
# Telegram OAuth2 flows from main-panel-initiated flows.
_admin_oauth_states: dict[str, float] = {}
_OAUTH_STATE_TTL = 600  # seconds, matches panel's cache TTL


def _register_admin_state(authorization_url: str) -> None:
    """Extract state from authorizationUrl and register it as admin-owned."""
    now = time.time()
    # Purge expired states first
    expired = [s for s, exp in _admin_oauth_states.items() if exp < now]
    for s in expired:
        del _admin_oauth_states[s]
    try:
        qs = urllib.parse.urlparse(authorization_url).query
        state = urllib.parse.parse_qs(qs).get("state", [None])[0]
        if state:
            _admin_oauth_states[state] = now + _OAUTH_STATE_TTL
    except Exception:
        pass


def _is_admin_state(state: str) -> bool:
    """Return True if this state was initiated by the admin panel."""
    exp = _admin_oauth_states.get(state)
    if exp is None:
        return False
    if time.time() > exp:
        del _admin_oauth_states[state]
        return False
    return True

from web.backend.api.deps import get_current_admin, get_2fa_temp_admin, get_client_ip, AdminUser
from web.backend.core.errors import api_error, E
from web.backend.core.config import get_web_settings
from web.backend.core.login_guard import login_guard
from web.backend.core.fail2ban_logger import log_auth_failure
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
    create_temp_2fa_token,
    create_password_reset_token,
    decode_token,
)
from web.backend.core.token_blacklist import token_blacklist
from web.backend.core.totp import (
    generate_totp_secret,
    encrypt_totp_secret,
    decrypt_totp_secret,
    encrypt_backup_codes,
    get_provisioning_uri,
    generate_qr_base64,
    verify_totp_code,
    generate_backup_codes,
    verify_backup_code,
)
from web.backend.schemas.auth import (
    TelegramAuthData,
    LoginRequest,
    RegisterRequest,
    SetupStatusResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    TokenResponse,
    LoginResponse,
    TotpSetupResponse,
    TotpVerifyRequest,
    RefreshRequest,
    AdminInfo,
    PermissionEntry,
)
from web.backend.schemas.common import SuccessResponse
from shared.config_service import config_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/methods")
async def get_auth_methods():
    """Public endpoint — returns enabled auth methods for login page."""
    return {
        "telegram": config_service.get("auth_telegram_enabled", True),
        "password": config_service.get("auth_password_enabled", True),
        "totp_required": config_service.get("auth_totp_required", False),
    }


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
    client_ip = get_client_ip(request)

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


async def _get_rbac_account(subject: str):
    """Look up RBAC admin_account by login subject. Returns dict or None."""
    try:
        from web.backend.core.rbac import (
            get_admin_account_by_username,
            get_admin_account_by_telegram_id,
        )
        if subject.startswith("pwd:"):
            return await get_admin_account_by_username(subject[4:])
        elif subject.startswith("oauth:"):
            # OAuth2 subject — no RBAC account lookup by telegram_id
            return None
        else:
            return await get_admin_account_by_telegram_id(int(subject))
    except Exception as e:
        logger.debug("RBAC account lookup: %s", e)
    return None


@router.post("/telegram", response_model=LoginResponse)
@limiter.limit("5/minute")
async def telegram_login(request: Request, data: TelegramAuthData):
    """
    Authenticate via Telegram Login Widget.

    Verifies the data signature and creates JWT tokens (or temp 2FA token).
    """
    settings = get_web_settings()
    client_ip = get_client_ip(request)

    # Check if Telegram auth is enabled
    if not config_service.get("auth_telegram_enabled", True):
        raise api_error(403, E.FORBIDDEN, "Telegram authentication is disabled")

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
        log_auth_failure(client_ip, f"tg:{data.id}", "telegram", error_message)
        if config_service.get("auth_notify_on_failure", True):
            await notify_login_failed(
                ip=client_ip,
                username=f"tg:{data.id}",
                auth_method="telegram",
                reason=error_message,
            )
        if locked:
            if config_service.get("auth_notify_on_block", True):
                await notify_ip_blocked(
                    client_ip,
                    config_service.get("auth_lockout_minutes", 15) * 60,
                    config_service.get("auth_max_attempts", 5),
                )
        raise api_error(401, E.INVALID_TOKEN, f"Invalid Telegram auth data: {error_message}")

    # Check if user is in admins list
    if data.id not in settings.admins:
        logger.warning(f"User {data.id} is not in admins list: {settings.admins}")
        locked = login_guard.record_failure(client_ip)
        log_auth_failure(client_ip, f"tg:{data.id}", "telegram", "Not in admins list")
        if config_service.get("auth_notify_on_failure", True):
            await notify_login_failed(
                ip=client_ip,
                username=f"tg:{data.id} ({data.username or data.first_name})",
                auth_method="telegram",
                reason="Not in admins list",
            )
        if locked:
            if config_service.get("auth_notify_on_block", True):
                await notify_ip_blocked(
                    client_ip,
                    config_service.get("auth_lockout_minutes", 15) * 60,
                    config_service.get("auth_max_attempts", 5),
                )
        raise api_error(403, E.NOT_AN_ADMIN)

    # Success — credentials valid
    login_guard.record_success(client_ip)

    username = data.username or data.first_name
    subject = str(data.id)

    logger.info("Login successful for user id=%d from %s", data.id, client_ip)

    # Check 2FA requirement (global toggle)
    totp_required = config_service.get("auth_totp_required", False)
    account = await _get_rbac_account(subject)

    if totp_required and account:
        # Don't notify login success yet — wait for 2FA completion
        temp_token = create_temp_2fa_token(subject, auth_method="telegram")
        return LoginResponse(
            requires_2fa=True,
            totp_enabled=bool(account.get("totp_enabled")),
            temp_token=temp_token,
        )

    if totp_required and not account:
        raise api_error(403, E.FORBIDDEN, "2FA is required. Please contact administrator to set up your account.")

    # 2FA disabled or no RBAC account — issue full tokens directly
    await notify_login_success(ip=client_ip, username=username, auth_method="telegram")
    access_token = create_access_token(subject, username, auth_method="telegram")
    refresh_token = create_refresh_token(subject)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def password_login(request: Request, data: LoginRequest):
    """
    Authenticate with username and password.

    Returns full tokens or a temp 2FA token depending on account state.
    """
    settings = get_web_settings()
    client_ip = get_client_ip(request)

    # Check if password auth is enabled
    if not config_service.get("auth_password_enabled", True):
        raise api_error(403, E.FORBIDDEN, "Password authentication is disabled")

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
        log_auth_failure(client_ip, data.username, "password", "Invalid credentials")
        if config_service.get("auth_notify_on_failure", True):
            await notify_login_failed(
                ip=client_ip,
                username=data.username,
                auth_method="password",
                reason="Invalid credentials",
            )
        if locked:
            if config_service.get("auth_notify_on_block", True):
                await notify_ip_blocked(
                    client_ip,
                    config_service.get("auth_lockout_minutes", 15) * 60,
                    config_service.get("auth_max_attempts", 5),
                )
        raise api_error(401, E.INVALID_PASSWORD, "Invalid username or password")

    # Success — credentials valid
    login_guard.record_success(client_ip)

    subject = f"pwd:{data.username}"

    logger.info("Password login successful for user '%s' from %s", data.username, client_ip)

    # Check 2FA requirement (global toggle)
    totp_required = config_service.get("auth_totp_required", False)
    account = await _get_rbac_account(subject)

    if totp_required and account:
        # Don't notify login success yet — wait for 2FA completion
        temp_token = create_temp_2fa_token(subject, auth_method="password")
        return LoginResponse(
            requires_2fa=True,
            totp_enabled=bool(account.get("totp_enabled")),
            temp_token=temp_token,
        )

    if totp_required and not account:
        raise api_error(403, E.FORBIDDEN, "2FA is required. Please contact administrator to set up your account.")

    # 2FA disabled or no RBAC account — issue full tokens directly
    await notify_login_success(ip=client_ip, username=data.username, auth_method="password")
    access_token = create_access_token(subject, data.username, auth_method="password")
    refresh_token = create_refresh_token(subject)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


def _blacklist_temp_token(request: Request) -> None:
    """Blacklist the 2FA temp token from current request to prevent reuse."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_token(token, token_type=None)
        if payload and "exp" in payload:
            token_blacklist.add(token, float(payload["exp"]))
        else:
            logger.warning("Failed to blacklist temp token: decode returned %s", payload)


def _get_subject(admin: AdminUser) -> str:
    """Build JWT subject string from AdminUser."""
    if admin.auth_method == "password":
        return f"pwd:{admin.username}"
    return str(admin.telegram_id)


@router.post("/totp/setup", response_model=TotpSetupResponse)
@limiter.limit("5/minute")
async def totp_setup(request: Request, admin: AdminUser = Depends(get_2fa_temp_admin)):
    """Generate TOTP secret, QR code, and backup codes for first-time setup."""
    subject = _get_subject(admin)
    account = await _get_rbac_account(subject)
    if not account:
        raise api_error(404, E.ADMIN_NOT_FOUND)
    if account.get("totp_enabled"):
        raise api_error(400, E.FORBIDDEN, "TOTP is already enabled")

    # Reuse existing secret if already generated (prevents race condition on re-call)
    existing_secret = account.get("totp_secret")
    if existing_secret:
        try:
            secret = decrypt_totp_secret(existing_secret)
        except ValueError:
            secret = None
        if secret:
            # Regenerate QR and codes from existing secret
            uri = get_provisioning_uri(secret, admin.username)
            qr = generate_qr_base64(uri)
            # Decrypt existing backup codes
            existing_codes = account.get("backup_codes")
            if existing_codes:
                from web.backend.core.totp import decrypt_backup_codes
                codes = decrypt_backup_codes(existing_codes) or generate_backup_codes()
            else:
                codes = generate_backup_codes()
                from web.backend.core.rbac import update_admin_account
                await update_admin_account(account["id"], backup_codes=encrypt_backup_codes(codes))
            return TotpSetupResponse(
                secret=secret,
                qr_code=qr,
                provisioning_uri=uri,
                backup_codes=codes,
            )

    # Generate new secret and backup codes
    secret = generate_totp_secret()
    uri = get_provisioning_uri(secret, admin.username)
    qr = generate_qr_base64(uri)
    codes = generate_backup_codes()

    # Persist encrypted secret and backup codes (not yet enabled — confirm-setup activates)
    from web.backend.core.rbac import update_admin_account
    await update_admin_account(
        account["id"],
        totp_secret=encrypt_totp_secret(secret),
        backup_codes=encrypt_backup_codes(codes),
    )

    return TotpSetupResponse(
        secret=secret,
        qr_code=qr,
        provisioning_uri=uri,
        backup_codes=codes,
    )


@router.post("/totp/confirm-setup", response_model=TokenResponse)
@limiter.limit("5/minute")
async def totp_confirm_setup(
    request: Request,
    data: TotpVerifyRequest,
    admin: AdminUser = Depends(get_2fa_temp_admin),
):
    """Confirm TOTP setup by verifying the first code, then issue full tokens."""
    subject = _get_subject(admin)
    account = await _get_rbac_account(subject)
    if not account or not account.get("totp_secret"):
        raise api_error(400, E.FORBIDDEN, "Call /totp/setup first")

    # Decrypt TOTP secret
    try:
        secret = decrypt_totp_secret(account["totp_secret"])
    except ValueError:
        raise api_error(500, E.FORBIDDEN, "Failed to decrypt TOTP secret")

    client_ip = get_client_ip(request)
    if not verify_totp_code(secret, data.code, account_id=account["id"]):
        locked = login_guard.record_failure(client_ip)
        log_auth_failure(client_ip, admin.username, "totp_setup", "Invalid TOTP code")
        if locked:
            if config_service.get("auth_notify_on_block", True):
                await notify_ip_blocked(
                    client_ip,
                    config_service.get("auth_lockout_minutes", 15) * 60,
                    config_service.get("auth_max_attempts", 5),
                )
        raise api_error(401, E.INVALID_TOKEN, "Invalid TOTP code")

    # Enable 2FA
    login_guard.record_success(client_ip)
    from web.backend.core.rbac import update_admin_account
    await update_admin_account(account["id"], totp_enabled=True)

    # Blacklist temp token to prevent reuse
    _blacklist_temp_token(request)

    settings = get_web_settings()
    access_token = create_access_token(subject, admin.username, auth_method=admin.auth_method)
    refresh_token = create_refresh_token(subject)

    logger.info("TOTP enabled for user '%s'", admin.username)
    await notify_login_success(ip=client_ip, username=admin.username, auth_method=admin.auth_method)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.post("/totp/verify", response_model=TokenResponse)
@limiter.limit("10/minute")
async def totp_verify(
    request: Request,
    data: TotpVerifyRequest,
    admin: AdminUser = Depends(get_2fa_temp_admin),
):
    """Verify TOTP code (or backup code) and issue full tokens."""
    subject = _get_subject(admin)
    account = await _get_rbac_account(subject)
    if not account or not account.get("totp_enabled") or not account.get("totp_secret"):
        raise api_error(400, E.FORBIDDEN, "TOTP is not set up")

    client_ip = get_client_ip(request)
    code = data.code.strip()

    # Decrypt TOTP secret
    try:
        secret = decrypt_totp_secret(account["totp_secret"])
    except ValueError:
        raise api_error(500, E.FORBIDDEN, "Failed to decrypt TOTP secret")

    # Try TOTP code first
    if verify_totp_code(secret, code, account_id=account["id"]):
        login_guard.record_success(client_ip)
        _blacklist_temp_token(request)

        settings = get_web_settings()
        access_token = create_access_token(subject, admin.username, auth_method=admin.auth_method)
        refresh_token = create_refresh_token(subject)
        await notify_login_success(ip=client_ip, username=admin.username, auth_method=admin.auth_method)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_expire_minutes * 60,
        )

    # Try backup code (already encrypted in DB)
    is_valid, updated_codes = verify_backup_code(account.get("backup_codes"), code)
    if is_valid:
        from web.backend.core.rbac import update_admin_account
        await update_admin_account(account["id"], backup_codes=updated_codes)
        logger.info("Backup code used by '%s'", admin.username)

        login_guard.record_success(client_ip)
        _blacklist_temp_token(request)

        settings = get_web_settings()
        access_token = create_access_token(subject, admin.username, auth_method=admin.auth_method)
        refresh_token = create_refresh_token(subject)
        await notify_login_success(ip=client_ip, username=admin.username, auth_method=admin.auth_method)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_expire_minutes * 60,
        )

    # Both TOTP and backup failed
    locked = login_guard.record_failure(client_ip)
    log_auth_failure(client_ip, admin.username, "totp", "Invalid TOTP/backup code")
    if locked:
        if config_service.get("auth_notify_on_block", True):
            await notify_ip_blocked(
                client_ip,
                config_service.get("auth_lockout_minutes", 15) * 60,
                config_service.get("auth_max_attempts", 5),
            )
    raise api_error(401, E.INVALID_TOKEN, "Invalid code")


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

    payload = decode_token(data.refresh_token, token_type="refresh")

    if not payload:
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
    elif subject.startswith("oauth:"):
        # OAuth2 (Telegram OIDC) — panel already validated, just reissue
        username = payload.get("username") or f"oauth:{subject[6:14]}"
        access_token = create_access_token(subject, username, auth_method="telegram")
    else:
        # Legacy numeric telegram_id subject
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
    admin_email = None
    if admin.auth_method == "password" and admin.account_id:
        try:
            from web.backend.core.rbac import get_admin_account_by_id
            account = await get_admin_account_by_id(admin.account_id)
            if account:
                if account.get("is_generated_password"):
                    password_is_generated = True
                admin_email = account.get("email")
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
        email=admin_email,
        role=admin.role,
        role_id=admin.role_id,
        auth_method=admin.auth_method,
        password_is_generated=password_is_generated,
        permissions=permissions,
    )


@router.post("/change-password", response_model=SuccessResponse)
@limiter.limit("5/minute")
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


@router.post("/forgot-password", response_model=SuccessResponse)
@limiter.limit("3/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest):
    """
    Request password reset. Sends an email with a reset link if:
    - The email matches an admin account
    - Email sending is configured (SMTP relay or built-in mail server)

    Always returns success to prevent email enumeration.
    """
    client_ip = get_client_ip(request)
    logger.info("Password reset requested for email '%s' from %s", data.email, client_ip)

    # Always return success — do actual work in background
    try:
        from web.backend.core.rbac import get_admin_account_by_email
        account = await get_admin_account_by_email(data.email)

        if account and account.get("is_active", True) and account.get("password_hash"):
            # Generate reset token
            token = create_password_reset_token(account["id"], account["username"])

            # Build reset URL
            settings = get_web_settings()
            secret_path = config_service.get("secret_path", "")
            prefix = f"/{secret_path}" if secret_path else ""
            # Use configured public URL (never trust Origin/Referer headers)
            import os
            public_url = os.getenv("APP_PUBLIC_URL", "").rstrip("/")
            if not public_url:
                # Fallback: construct from CORS origins if available
                cors = os.getenv("WEB_CORS_ORIGINS", "")
                if cors:
                    public_url = cors.split(",")[0].strip().rstrip("/")
            base_url = f"{public_url}{prefix}" if public_url else prefix

            reset_url = f"{base_url}/reset-password?token={token}"

            # Send email
            from web.backend.core.notification_service import send_email
            await send_email(
                to_email=data.email,
                title="Password Reset",
                body=(
                    f"A password reset was requested for your account '{account['username']}'.\n\n"
                    f"Click the link below to reset your password:\n{reset_url}\n\n"
                    f"This link expires in 30 minutes.\n"
                    f"If you did not request this, ignore this email."
                ),
                severity="warning",
                link=reset_url,
            )
            logger.info("Password reset email sent to '%s' for user '%s'", data.email, account["username"])
        else:
            logger.info("Password reset: no matching account for email '%s'", data.email)
    except Exception as e:
        logger.error("Password reset email failed: %s", e)

    return SuccessResponse(message="If this email is associated with an account, a reset link has been sent.")


@router.post("/reset-password", response_model=SuccessResponse)
@limiter.limit("5/minute")
async def reset_password(request: Request, data: ResetPasswordRequest):
    """
    Reset password using a token from the reset email.
    Validates the token, checks it hasn't been used, and sets the new password.
    """
    # Decode and validate token
    payload = decode_token(data.token, token_type="password_reset")
    if not payload:
        raise api_error(400, E.RESET_TOKEN_INVALID, "Invalid or expired reset token")

    # Check token hasn't been used
    if token_blacklist.is_blacklisted(data.token):
        raise api_error(400, E.RESET_TOKEN_INVALID, "This reset link has already been used")

    admin_id = int(payload["sub"])

    # Validate new password
    from web.backend.core.admin_credentials import validate_password_strength, hash_password
    is_strong, strength_error = validate_password_strength(data.new_password)
    if not is_strong:
        raise api_error(400, E.INVALID_PASSWORD, strength_error)

    # Find admin account
    from web.backend.core.rbac import get_admin_account_by_id, update_admin_account
    account = await get_admin_account_by_id(admin_id)
    if not account:
        raise api_error(400, E.RESET_TOKEN_INVALID, "Invalid reset token")

    if not account.get("is_active", True):
        raise api_error(403, E.ACCOUNT_DISABLED, "Account is disabled")

    # Update password
    new_hash = hash_password(data.new_password)
    updated = await update_admin_account(
        admin_id,
        password_hash=new_hash,
        is_generated_password=False,
    )
    if not updated:
        raise api_error(500, E.PASSWORD_UPDATE_FAILED)

    # Blacklist the token to prevent reuse
    token_blacklist.add(data.token, float(payload["exp"]))

    client_ip = get_client_ip(request)
    logger.info("Password reset completed for user '%s' (id=%d) from %s", account["username"], admin_id, client_ip)

    return SuccessResponse(message="Password has been reset successfully. You can now log in.")


@router.post("/oauth2/authorize")
@limiter.limit("10/minute")
async def oauth2_authorize(request: Request):
    """Get Telegram OAuth2 authorization URL from the Remnawave panel."""
    settings = get_web_settings()
    client_ip = get_client_ip(request)

    if not config_service.get("auth_telegram_enabled", True):
        raise api_error(403, E.FORBIDDEN, "Telegram authentication is disabled")

    if login_guard.is_locked(client_ip):
        remaining = login_guard.remaining_seconds(client_ip)
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {remaining}s")

    try:
        headers = {"Authorization": f"Bearer {settings.api_token}", "X-Forwarded-Proto": "https", "X-Forwarded-For": get_client_ip(request)}
        async with httpx.AsyncClient(timeout=10) as hc:
            resp = await hc.post(
                f"{settings.api_base_url}/api/auth/oauth2/authorize",
                json={"provider": "telegram"},
                headers=headers,
            )
        if resp.status_code != 200:
            logger.error("Panel oauth2/authorize returned %d: %s", resp.status_code, resp.text[:200])
            raise api_error(502, E.INTERNAL_ERROR, "Failed to get authorization URL from panel")
        data = resp.json()
        authorization_url = data.get("response", {}).get("authorizationUrl")
        if not authorization_url:
            raise api_error(502, E.INTERNAL_ERROR, "Panel returned no authorizationUrl")
        # Remember this state so the callback handler knows it belongs to admin
        _register_admin_state(authorization_url)
        return {"authorizationUrl": authorization_url}
    except httpx.RequestError as exc:
        logger.error("Panel oauth2/authorize request failed: %s", exc)
        raise api_error(502, E.INTERNAL_ERROR, "Cannot reach panel API")


@router.post("/oauth2/callback")
@limiter.limit("10/minute")
async def oauth2_callback(request: Request):
    """Exchange OAuth2 code+state for an admin session token."""
    settings = get_web_settings()
    client_ip = get_client_ip(request)

    if not config_service.get("auth_telegram_enabled", True):
        raise api_error(403, E.FORBIDDEN, "Telegram authentication is disabled")

    if login_guard.is_locked(client_ip):
        remaining = login_guard.remaining_seconds(client_ip)
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {remaining}s")

    body = await request.json()
    code = body.get("code")
    state = body.get("state")

    if not code or not state:
        raise api_error(400, E.INVALID_TOKEN, "Missing code or state")

    try:
        headers = {"Authorization": f"Bearer {settings.api_token}", "X-Forwarded-Proto": "https", "X-Forwarded-For": get_client_ip(request)}
        async with httpx.AsyncClient(timeout=10) as hc:
            resp = await hc.post(
                f"{settings.api_base_url}/api/auth/oauth2/callback",
                json={"provider": "telegram", "code": code, "state": state},
                headers=headers,
            )
        if resp.status_code != 200:
            logger.warning("Panel oauth2/callback returned %d: %s", resp.status_code, resp.text[:200])
            login_guard.record_failure(client_ip)
            log_auth_failure(client_ip, "oauth2:telegram", "telegram", f"panel returned {resp.status_code}")
            raise api_error(401, E.INVALID_TOKEN, "Telegram authentication failed")

        panel_token = resp.json().get("response", {}).get("accessToken")
        if not panel_token:
            raise api_error(502, E.INTERNAL_ERROR, "Panel returned no accessToken")

        # Decode panel JWT to extract username and uuid.
        # Panel JWT contains { username, uuid, role } - no telegram_id.
        # The panel already verified the Telegram ID against its own allowedIds list.
        try:
            payload = _jwt.decode(panel_token, key="", options={"verify_signature": False})
            panel_username = payload.get("username", "")
            panel_uuid = payload.get("uuid", "")
            logger.debug("Panel JWT payload: username=%s uuid=%s", panel_username, panel_uuid)
        except Exception as exc:
            logger.error("Failed to decode panel JWT: %s", exc)
            raise api_error(502, E.INTERNAL_ERROR, "Failed to parse panel token")

        if not panel_uuid:
            raise api_error(502, E.INTERNAL_ERROR, "Panel token missing uuid")

    except httpx.RequestError as exc:
        logger.error("Panel oauth2/callback request failed: %s", exc)
        raise api_error(502, E.INTERNAL_ERROR, "Cannot reach panel API")

    login_guard.record_success(client_ip)
    username = panel_username or f"oauth:{panel_uuid[:8]}"
    # Use panel UUID as subject so RBAC lookups work consistently
    subject = f"oauth:{panel_uuid}"
    logger.info("OAuth2 login successful for username=%s from %s", username, client_ip)

    totp_required = config_service.get("auth_totp_required", False)
    account = await _get_rbac_account(subject)

    if totp_required and account:
        temp_token = create_temp_2fa_token(subject, auth_method="telegram")
        return LoginResponse(
            requires_2fa=True,
            totp_enabled=bool(account.get("totp_enabled")),
            temp_token=temp_token,
        )

    if totp_required and not account:
        raise api_error(403, E.FORBIDDEN, "2FA is required. Please contact administrator.")

    await notify_login_success(ip=client_ip, username=username, auth_method="telegram")
    access_token = create_access_token(subject, username, auth_method="telegram")
    refresh_token = create_refresh_token(subject)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_expire_minutes * 60,
    )

@router.get("/oauth2/callback/telegram")
async def oauth2_callback_redirect(request: Request, code: str = None, state: str = None):
    """
    Receive Telegram OAuth2 redirect, exchange code+state for tokens,
    then redirect browser to /admin/ with tokens in URL fragment.
    """
    settings = get_web_settings()
    client_ip = get_client_ip(request)

    if not code or not state:
        return RedirectResponse("/admin/?tg_error=missing_params", status_code=302)

    # If state was not initiated by our admin oauth2/authorize, this callback
    # belongs to the main panel. Proxy its index.html so the main-panel SPA
    # can read code+state from the URL and call its own /api/auth/oauth2/callback.
    if not _is_admin_state(state):
        settings = get_web_settings()
        try:
            async with httpx.AsyncClient(timeout=5) as hc:
                # Fetch main panel index.html so its SPA can read code+state
                r = await hc.get(
                    f"{settings.api_base_url.rstrip('/')}/",
                    headers={"X-Forwarded-Proto": "https", "X-Forwarded-For": client_ip},
                    follow_redirects=True,
                )
            return HTMLResponse(content=r.text, status_code=200, headers={"Cache-Control": "no-store"})
        except Exception as exc:
            logger.error("Failed to proxy main panel index: %s", exc)
            return RedirectResponse("/", status_code=302)

    if login_guard.is_locked(client_ip):
        return RedirectResponse("/admin/?tg_error=locked", status_code=302)

    try:
        headers = {
            "Authorization": f"Bearer {settings.api_token}",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-For": client_ip,
        }
        async with httpx.AsyncClient(timeout=10) as hc:
            resp = await hc.post(
                f"{settings.api_base_url}/api/auth/oauth2/callback",
                json={"provider": "telegram", "code": code, "state": state},
                headers=headers,
            )
        if resp.status_code != 200:
            logger.warning("Panel oauth2/callback returned %d", resp.status_code)
            login_guard.record_failure(client_ip)
            log_auth_failure(client_ip, "oauth2:telegram", "telegram", f"panel returned {resp.status_code}")
            return RedirectResponse("/admin/?tg_error=auth_failed", status_code=302)

        panel_token = resp.json().get("response", {}).get("accessToken")
        if not panel_token:
            return RedirectResponse("/admin/?tg_error=no_token", status_code=302)

        # Panel JWT contains { username, uuid, role } - no telegram_id.
        # Panel already verified the Telegram ID against its allowedIds list.
        try:
            payload = _jwt.decode(panel_token, key="", options={"verify_signature": False})
            panel_username = payload.get("username", "")
            panel_uuid = payload.get("uuid", "")
            logger.debug("Panel JWT payload: username=%s uuid=%s", panel_username, panel_uuid)
        except Exception as exc:
            logger.error("Failed to decode panel JWT: %s", exc)
            return RedirectResponse("/admin/?tg_error=token_parse", status_code=302)

        if not panel_uuid:
            return RedirectResponse("/admin/?tg_error=no_uuid", status_code=302)

    except httpx.RequestError as exc:
        logger.error("Panel oauth2/callback request failed: %s", exc)
        return RedirectResponse("/admin/?tg_error=panel_unreachable", status_code=302)

    login_guard.record_success(client_ip)
    username = panel_username or f"oauth:{panel_uuid[:8]}"
    subject = f"oauth:{panel_uuid}"

    totp_required = config_service.get("auth_totp_required", False)
    account = await _get_rbac_account(subject)

    if totp_required and account:
        temp_token = create_temp_2fa_token(subject, auth_method="telegram")
        return RedirectResponse(f"/admin/login?requires_2fa=1&temp_token={temp_token}", status_code=302)

    if totp_required and not account:
        return RedirectResponse("/admin/?tg_error=2fa_required", status_code=302)

    await notify_login_success(ip=client_ip, username=username, auth_method="telegram")
    access_token = create_access_token(subject, username, auth_method="telegram")
    refresh_token = create_refresh_token(subject)

    logger.info("OAuth2 login successful for username=%s from %s", username, client_ip)

    # Pass tokens via URL fragment - never hits server, handled by SPA
    import urllib.parse
    fragment = urllib.parse.urlencode({
        "access_token": access_token,
        "refresh_token": refresh_token,
    })
    return RedirectResponse(f"/admin/auth/callback/telegram#{fragment}", status_code=302)

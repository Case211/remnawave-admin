"""Auth API endpoints."""
import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from pydantic import BaseModel

from web.backend.api.deps import get_current_admin, get_2fa_temp_admin, get_client_ip, AdminUser, require_permission
from web.backend.core.auth_cookies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    set_auth_cookies,
    clear_auth_cookies,
)
from web.backend.core.errors import api_error, E
from web.backend.core.audit import write_audit_log
from web.backend.core.config import get_web_settings
from web.backend.core.login_guard import login_guard
from web.backend.core.fail2ban_logger import log_auth_failure
from web.backend.core.notification_service import (
    notify_login_failed,
    notify_login_success,
    notify_ip_blocked,
)
from web.backend.core.rate_limit import limiter
from web.backend.core.security import (
    verify_telegram_auth,
    verify_telegram_webapp_init_data,
    verify_admin_password_async,
    create_access_token,
    create_refresh_token,
    create_temp_2fa_token,
    create_password_reset_token,
    decode_token,
    get_access_ttl_minutes,
)
from web.backend.core.token_blacklist import token_blacklist
from web.backend.core import sessions as _sessions
from web.backend.core.auth_policy import method_allowed
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
    TelegramWebAppAuthData,
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
    telegram_enabled = config_service.get("auth_telegram_enabled", True)
    return {
        "telegram": telegram_enabled,
        "telegram_webapp": telegram_enabled and config_service.get(
            "auth_telegram_webapp_enabled", True),
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
async def register_admin(request: Request, response: Response, data: RegisterRequest):
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
    access_token, refresh_token = await _issue_login(
        request, response, subject, data.username.strip(), "password")
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=get_access_ttl_minutes() * 60,
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
        else:
            return await get_admin_account_by_telegram_id(int(subject))
    except Exception as e:
        logger.debug("RBAC account lookup: %s", e)
    return None


@router.post("/telegram", response_model=LoginResponse)
@limiter.limit("5/minute")
async def telegram_login(request: Request, response: Response, data: TelegramAuthData):
    """
    Authenticate via Telegram Login Widget.

    Verifies the data signature and creates JWT tokens (or temp 2FA token).
    """
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
        await _record_telegram_failure(client_ip, f"tg:{data.id}", error_message)
        raise api_error(401, E.INVALID_TOKEN, f"Invalid Telegram auth data: {error_message}")

    return await _finish_telegram_login(
        request, response, data.id, data.username or data.first_name, client_ip)


@router.post("/telegram/webapp", response_model=LoginResponse)
@limiter.limit("10/minute")
async def telegram_webapp_login(request: Request, response: Response, data: TelegramWebAppAuthData):
    """
    Authenticate via Telegram Mini App (Web App) initData.

    Тот же способ входа, что и Login Widget — отличается только источником
    подписанных данных, поэтому auth_method в токене остаётся "telegram"
    (политики allowed_auth_methods, уведомления и список сессий не меняются).
    """
    client_ip = get_client_ip(request)

    if not config_service.get("auth_telegram_enabled", True):
        raise api_error(403, E.FORBIDDEN, "Telegram authentication is disabled")
    if not config_service.get("auth_telegram_webapp_enabled", True):
        raise api_error(403, E.FORBIDDEN, "Telegram Mini App authentication is disabled")

    if login_guard.is_locked(client_ip):
        remaining = login_guard.remaining_seconds(client_ip)
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed attempts. Try again in {remaining}s",
        )

    # initData целиком не логируем — это подписанный секрет на время сессии
    is_valid, error_message, tg_user = verify_telegram_webapp_init_data(data.init_data)
    if not is_valid:
        logger.warning("Mini App auth verification failed from %s: %s", client_ip, error_message)
        await _record_telegram_failure(client_ip, "tg:webapp", error_message)
        raise api_error(401, E.INVALID_TOKEN, f"Invalid Telegram init data: {error_message}")

    tg_id = int(tg_user["id"])
    display_name = tg_user.get("username") or tg_user.get("first_name") or str(tg_id)
    logger.info("Mini App login attempt from Telegram user (id=%d) from %s", tg_id, client_ip)

    return await _finish_telegram_login(request, response, tg_id, display_name, client_ip)


async def _record_telegram_failure(client_ip: str, username_label: str, reason: str) -> None:
    """Неудачная попытка Telegram-входа: guard, fail2ban, уведомления."""
    locked = login_guard.record_failure(client_ip)
    log_auth_failure(client_ip, username_label, "telegram", reason)
    if config_service.get("auth_notify_on_failure", True):
        await notify_login_failed(
            ip=client_ip,
            username=username_label,
            auth_method="telegram",
            reason=reason,
        )
    if locked and config_service.get("auth_notify_on_block", True):
        await notify_ip_blocked(
            client_ip,
            config_service.get("auth_lockout_minutes", 15) * 60,
            config_service.get("auth_max_attempts", 5),
        )


async def _finish_telegram_login(
    request: Request,
    response: Response,
    tg_id: int,
    username: str,
    client_ip: str,
) -> LoginResponse:
    """Общий хвост Telegram-входа для Login Widget и Mini App.

    Подпись к этому моменту уже проверена вызывающей стороной; здесь —
    список админов, политика метода, 2FA и выдача токенов.
    """
    settings = get_web_settings()

    # Check if user is in admins list
    if tg_id not in settings.admins:
        logger.warning(f"User {tg_id} is not in admins list: {settings.admins}")
        await _record_telegram_failure(
            client_ip, f"tg:{tg_id} ({username})", "Not in admins list")
        raise api_error(403, E.NOT_AN_ADMIN)

    # Success — credentials valid
    login_guard.record_success(client_ip)

    subject = str(tg_id)

    logger.info("Login successful for user id=%d from %s", tg_id, client_ip)

    # Check 2FA requirement (global toggle)
    totp_required = config_service.get("auth_totp_required", False)
    account = await _get_rbac_account(subject)
    _check_method_policy(account, "telegram", client_ip, username)

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
    access_token, refresh_token = await _issue_login(
        request, response, subject, username, "telegram", account=account)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=get_access_ttl_minutes() * 60,
    )


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/minute")
async def password_login(request: Request, response: Response, data: LoginRequest):
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
    _check_method_policy(account, "password", client_ip, data.username)

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
    access_token, refresh_token = await _issue_login(
        request, response, subject, data.username, "password", account=account)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=get_access_ttl_minutes() * 60,
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


def _check_method_policy(account: Optional[dict], method: str, client_ip: str, username: str) -> None:
    """403, если способ входа запрещён политикой аккаунта (см. auth_policy)."""
    if account and not method_allowed(account, method):
        log_auth_failure(client_ip, username, method, "Method disallowed by admin policy")
        logger.warning("Login method '%s' blocked by policy for '%s'", method, username)
        raise api_error(403, E.FORBIDDEN, "Этот способ входа запрещён политикой для вашего аккаунта")


async def _issue_login(
    request: Request,
    response: Response,
    subject: str,
    username: str,
    auth_method: str,
    account: Optional[dict] = None,
) -> tuple:
    """Завести сессию (если account-backed) и выдать access+refresh с sid.

    Единая точка выдачи токенов для всех способов входа: создаёт строку
    admin_sessions, зашивает sid в оба токена и ставит cookie.
    Возвращает (access_token, refresh_token).
    """
    account_id = account.get("id") if account else None
    if account_id is None:
        acc = await _get_rbac_account(subject)
        account_id = acc.get("id") if acc else None
    sid = await _sessions.create_session(request, subject, account_id, auth_method, username)
    access_token = create_access_token(subject, username, auth_method=auth_method, sid=sid)
    refresh_token = create_refresh_token(subject, sid=sid)
    set_auth_cookies(response, request, access_token, refresh_token)
    return access_token, refresh_token


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
    response: Response,
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

    logger.info("TOTP enabled for user '%s'", admin.username)
    await notify_login_success(ip=client_ip, username=admin.username, auth_method=admin.auth_method)
    access_token, refresh_token = await _issue_login(
        request, response, subject, admin.username, admin.auth_method, account=account)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=get_access_ttl_minutes() * 60,
    )


@router.post("/totp/verify", response_model=TokenResponse)
@limiter.limit("10/minute")
async def totp_verify(
    request: Request,
    response: Response,
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

        await notify_login_success(ip=client_ip, username=admin.username, auth_method=admin.auth_method)
        access_token, refresh_token = await _issue_login(
            request, response, subject, admin.username, admin.auth_method, account=account)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=get_access_ttl_minutes() * 60,
        )

    # Try backup code (already encrypted in DB)
    is_valid, updated_codes = verify_backup_code(account.get("backup_codes"), code)
    if is_valid:
        from web.backend.core.rbac import update_admin_account
        await update_admin_account(account["id"], backup_codes=updated_codes)
        logger.info("Backup code used by '%s'", admin.username)

        login_guard.record_success(client_ip)
        _blacklist_temp_token(request)

        await notify_login_success(ip=client_ip, username=admin.username, auth_method=admin.auth_method)
        access_token, refresh_token = await _issue_login(
            request, response, subject, admin.username, admin.auth_method, account=account)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=get_access_ttl_minutes() * 60,
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
async def refresh_tokens(
    request: Request,
    response: Response,
    data: Optional[RefreshRequest] = None,
):
    """
    Refresh access token using refresh token.

    Источник refresh-токена: тело запроса (Bearer-клиенты) или
    HttpOnly cookie rw_refresh (веб-фронт). CSRF-проверка не нужна:
    refresh-cookie имеет SameSite=Strict и кросс-сайтово не уходит.

    The old refresh token is blacklisted after successful rotation
    to prevent reuse (one-time use refresh tokens).
    """
    refresh_token_in = (
        data.refresh_token if data and data.refresh_token else None
    ) or request.cookies.get(REFRESH_COOKIE)
    if not refresh_token_in:
        raise api_error(401, E.INVALID_REFRESH_TOKEN)

    # Check if this refresh token has already been used (blacklisted)
    if token_blacklist.is_blacklisted(refresh_token_in):
        raise api_error(401, E.TOKEN_ALREADY_USED)

    payload = decode_token(refresh_token_in, token_type="refresh")

    if not payload:
        raise api_error(401, E.INVALID_REFRESH_TOKEN)

    subject = payload["sub"]
    settings = get_web_settings()

    # Session tracking: если токен помечен sid, сессия — источник истины
    sid = payload.get("sid")
    if sid is not None and not await _sessions.validate_for_refresh(sid):
        raise api_error(401, E.INVALID_REFRESH_TOKEN)

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
        access_token = create_access_token(subject, username, auth_method="password", sid=sid)
    else:
        # Telegram-based auth — verify still in admins list
        telegram_id = int(subject)
        if telegram_id not in settings.admins:
            raise api_error(403, E.NOT_AN_ADMIN)
        access_token = create_access_token(subject, payload.get("username", "admin"), auth_method="telegram", sid=sid)

    refresh_token = create_refresh_token(subject, sid=sid)

    # Blacklist the old refresh token to prevent reuse
    if "exp" in payload:
        token_blacklist.add(refresh_token_in, float(payload["exp"]))

    if sid is not None:
        await _sessions.touch_session(sid, request)

    set_auth_cookies(response, request, access_token, refresh_token)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=get_access_ttl_minutes() * 60,
    )


@router.get("/me", response_model=AdminInfo)
async def get_current_user(admin: AdminUser = Depends(get_current_admin)):
    """
    Get current authenticated admin info with RBAC permissions.
    """
    # Check if password is auto-generated (needs changing)
    password_is_generated = False
    totp_enabled = False
    admin_email = None
    unlimited_traffic_policy = "allowed"
    unrestricted_user_access = False
    max_users = None
    max_traffic_gb = None
    max_nodes = None
    max_hosts = None
    users_created = 0
    traffic_used_bytes = 0
    nodes_created = 0
    hosts_created = 0

    if admin.account_id:
        try:
            from web.backend.core.rbac import get_admin_account_by_id
            account = await get_admin_account_by_id(admin.account_id)
            if account:
                if account.get("is_generated_password"):
                    password_is_generated = True
                totp_enabled = bool(account.get("totp_enabled"))
                admin_email = account.get("email")
                unlimited_traffic_policy = account.get("unlimited_traffic_policy", "allowed")
                unrestricted_user_access = account.get("unrestricted_user_access", False) or False
                max_users = account.get("max_users")
                max_traffic_gb = account.get("max_traffic_gb")
                max_nodes = account.get("max_nodes")
                max_hosts = account.get("max_hosts")
                users_created = account.get("users_created", 0) or 0
                traffic_used_bytes = account.get("traffic_used_bytes", 0) or 0
                nodes_created = account.get("nodes_created", 0) or 0
                hosts_created = account.get("hosts_created", 0) or 0
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
        account_id=admin.account_id,
        max_users=max_users,
        max_traffic_gb=max_traffic_gb,
        max_nodes=max_nodes,
        max_hosts=max_hosts,
        users_created=users_created,
        traffic_used_bytes=traffic_used_bytes,
        nodes_created=nodes_created,
        hosts_created=hosts_created,
        unlimited_traffic_policy=unlimited_traffic_policy,
        unrestricted_user_access=unrestricted_user_access,
        auth_method=admin.auth_method,
        password_is_generated=password_is_generated,
        totp_enabled=totp_enabled,
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
    # Инвалидируем прочие сессии этого админа: старые токены на других устройствах
    # больше не продлятся при refresh (текущую сессию сохраняем).
    try:
        await _sessions.revoke_others(account["id"], _current_sid(request))
    except Exception as e:  # noqa: BLE001
        logger.debug("revoke_others after password change: %s", e)
    return SuccessResponse(message="Password changed successfully")


@router.post("/logout", response_model=SuccessResponse)
async def logout(
    request: Request,
    response: Response,
    admin: AdminUser = Depends(get_current_admin),
):
    """Logout: invalidate access + refresh tokens and clear auth cookies."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header[7:]
    else:
        access_token = request.cookies.get(ACCESS_COOKIE)

    if access_token:
        payload = decode_token(access_token)
        if payload and "exp" in payload:
            token_blacklist.add(access_token, float(payload["exp"]))
            logger.info("Token blacklisted for user '%s'", admin.username)
        # Отозвать сессию этого входа, чтобы она ушла из списка активных
        sid = payload.get("sid") if payload else None
        if sid and getattr(admin, "account_id", None):
            await _sessions.revoke_session(admin.account_id, sid)

    # Refresh из cookie тоже гасим — иначе сессию можно воскресить
    refresh_cookie = request.cookies.get(REFRESH_COOKIE)
    if refresh_cookie:
        payload = decode_token(refresh_cookie, token_type="refresh")
        if payload and "exp" in payload:
            token_blacklist.add(refresh_cookie, float(payload["exp"]))

    clear_auth_cookies(response)
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

    # Password reset — рвём ВСЕ сессии этого аккаунта (сброс вне сессии, current нет)
    try:
        await _sessions.revoke_others(admin_id, None)
    except Exception as e:  # noqa: BLE001
        logger.debug("revoke sessions after password reset: %s", e)

    client_ip = get_client_ip(request)
    logger.info("Password reset completed for user '%s' (id=%d) from %s", account["username"], admin_id, client_ip)

    return SuccessResponse(message="Password has been reset successfully. You can now log in.")


# ── Passkeys / WebAuthn ──────────────────────────────────────────


class WaRegisterFinish(BaseModel):
    token: str
    credential: dict
    name: Optional[str] = None


class WaLoginBegin(BaseModel):
    username: Optional[str] = None


class WaLoginFinish(BaseModel):
    token: str
    credential: dict


@router.post("/webauthn/register/begin")
async def wa_register_begin(request: Request, admin: AdminUser = Depends(get_current_admin)):
    from web.backend.core.admin_accounts import get_admin_account_by_id
    from web.backend.core import webauthn_svc as wa
    account = await get_admin_account_by_id(admin.account_id) if getattr(admin, "account_id", None) else None
    if not account:
        raise api_error(400, E.FORBIDDEN, "Passkey доступен только для аккаунтов admin_accounts")
    try:
        return await wa.begin_registration(request, account)
    except wa.WebAuthnError as e:
        raise api_error(400, E.FORBIDDEN, str(e))


@router.post("/webauthn/register/finish", response_model=SuccessResponse)
async def wa_register_finish(request: Request, data: WaRegisterFinish,
                             admin: AdminUser = Depends(get_current_admin)):
    from web.backend.core import webauthn_svc as wa
    try:
        await wa.finish_registration(request, data.token, data.credential, data.name)
    except wa.WebAuthnError as e:
        raise api_error(400, E.FORBIDDEN, str(e))
    return SuccessResponse(message="Passkey добавлен")


@router.get("/webauthn/credentials")
async def wa_credentials(admin: AdminUser = Depends(get_current_admin)):
    from web.backend.core import webauthn_svc as wa
    if not getattr(admin, "account_id", None):
        return {"items": []}
    items = await wa.list_credentials(admin.account_id)
    return {"items": [{"id": c["id"], "name": c.get("name"), "created_at": c.get("created_at"),
                       "last_used_at": c.get("last_used_at"), "transports": c.get("transports")}
                      for c in items]}


@router.delete("/webauthn/credentials/{cred_id}", response_model=SuccessResponse)
async def wa_delete_credential(cred_id: int, admin: AdminUser = Depends(get_current_admin)):
    from web.backend.core import webauthn_svc as wa
    if getattr(admin, "account_id", None):
        await wa.delete_credential(cred_id, admin.account_id)
    return SuccessResponse(message="Passkey удалён")


@router.post("/webauthn/login/begin")
@limiter.limit("10/minute")
async def wa_login_begin(request: Request, data: WaLoginBegin):
    from web.backend.core import webauthn_svc as wa
    try:
        return await wa.begin_authentication(request, data.username)
    except wa.WebAuthnError as e:
        raise api_error(400, E.FORBIDDEN, str(e))


@router.post("/webauthn/login/finish", response_model=LoginResponse)
@limiter.limit("10/minute")
async def wa_login_finish(request: Request, response: Response, data: WaLoginFinish):
    from web.backend.core import webauthn_svc as wa
    client_ip = get_client_ip(request)
    try:
        acc = await wa.finish_authentication(request, data.token, data.credential)
    except wa.WebAuthnError as e:
        login_guard.record_failure(client_ip)
        log_auth_failure(client_ip, "passkey", "passkey", str(e))
        raise api_error(401, E.INVALID_TOKEN, str(e))
    login_guard.record_success(client_ip)
    username = acc.get("username") or (str(acc.get("telegram_id")) if acc.get("telegram_id") else f"admin{acc['id']}")
    subject = ("pwd:" + acc["username"]) if acc.get("username") else str(acc.get("telegram_id"))
    _check_method_policy(acc, "passkey", client_ip, username)
    logger.info("Passkey login for '%s' from %s", username, client_ip)
    await notify_login_success(ip=client_ip, username=username, auth_method="passkey")
    access_token, refresh_token = await _issue_login(
        request, response, subject, username, "passkey", account=acc)
    return LoginResponse(access_token=access_token, refresh_token=refresh_token)


# ── OAuth2 SSO (Google / GitHub) ─────────────────────────────────


class OAuthCredsIn(BaseModel):
    client_id: str
    client_secret: str
    # только для generic OIDC («oidc»): базовый URL провайдера и имя кнопки
    issuer: Optional[str] = None
    display_name: Optional[str] = None


class OAuthCallbackIn(BaseModel):
    code: str
    state: str


@router.get("/oauth/providers")
async def oauth_providers():
    """Список провайдеров + настроен ли (без секретов). Публично — для кнопок входа."""
    from web.backend.core import oauth_svc as oa
    return {"items": oa.providers()}


@router.put("/oauth/providers/{provider}")
async def oauth_set_provider(provider: str, data: OAuthCredsIn,
                             admin: AdminUser = Depends(require_permission("oauth", "manage"))):
    from web.backend.core import oauth_svc as oa
    if not oa.is_provider(provider):
        raise api_error(404, E.FORBIDDEN, "Неизвестный провайдер")
    if provider == "oidc" and not (data.issuer or "").strip():
        raise api_error(400, E.INVALID_INPUT, "Для generic OIDC обязателен issuer URL")
    await oa.save_creds(provider, data.client_id, data.client_secret,
                        issuer=data.issuer, display_name=data.display_name)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="oauth.provider.set", resource="oauth", resource_id=provider)
    return {"configured": oa.is_configured(provider)}


@router.delete("/oauth/providers/{provider}")
async def oauth_del_provider(provider: str,
                             admin: AdminUser = Depends(require_permission("oauth", "manage"))):
    from web.backend.core import oauth_svc as oa
    await oa.clear_creds(provider)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="oauth.provider.clear", resource="oauth", resource_id=provider)
    return {"configured": False}


@router.post("/oauth/{provider}/login-url")
@limiter.limit("15/minute")
async def oauth_login_url(request: Request, provider: str):
    from web.backend.core import oauth_svc as oa
    if not oa.is_provider(provider):
        raise api_error(404, E.FORBIDDEN, "Неизвестный провайдер")
    try:
        return {"url": await oa.build_authorize_url(request, provider, "login", None)}
    except oa.OAuthError as e:
        raise api_error(400, E.FORBIDDEN, str(e))


@router.post("/oauth/{provider}/link-url")
async def oauth_link_url(request: Request, provider: str,
                         admin: AdminUser = Depends(get_current_admin)):
    from web.backend.core import oauth_svc as oa
    if not getattr(admin, "account_id", None):
        raise api_error(400, E.FORBIDDEN, "OAuth-привязка доступна только для аккаунтов admin_accounts")
    if not oa.is_provider(provider):
        raise api_error(404, E.FORBIDDEN, "Неизвестный провайдер")
    try:
        return {"url": await oa.build_authorize_url(request, provider, "link", admin.account_id)}
    except oa.OAuthError as e:
        raise api_error(400, E.FORBIDDEN, str(e))


@router.post("/oauth/callback")
@limiter.limit("15/minute")
async def oauth_callback(request: Request, response: Response, data: OAuthCallbackIn):
    from web.backend.core import oauth_svc as oa
    from web.backend.core.admin_accounts import get_admin_account_by_id
    try:
        res = await oa.exchange(request, data.code, data.state)
    except oa.OAuthError as e:
        raise api_error(400, E.INVALID_TOKEN, str(e))
    st, ui, provider = res["state"], res["userinfo"], res["provider"]

    if st.get("mode") == "link":
        aid = st.get("aid")
        if not aid:
            raise api_error(400, E.FORBIDDEN, "Нет аккаунта в state")
        try:
            await oa.save_link(int(aid), provider, ui["external_id"], ui.get("email"), ui.get("name"))
        except oa.OAuthError as e:
            raise api_error(400, E.FORBIDDEN, str(e))
        return {"mode": "link", "linked": True, "email": ui.get("email"), "provider": provider}

    # mode=login — только по существующей привязке (авто-создания нет)
    link = await oa.get_link(provider, ui["external_id"])
    if not link:
        raise api_error(403, E.NOT_AN_ADMIN, "Этот аккаунт не привязан ни к одному админу панели")
    acc = await get_admin_account_by_id(int(link["account_id"]))
    if not acc:
        raise api_error(403, E.NOT_AN_ADMIN, "Привязанный аккаунт не найден")
    await oa.touch_link(provider, ui["external_id"])
    client_ip = get_client_ip(request)
    login_guard.record_success(client_ip)
    username = acc.get("username") or (str(acc.get("telegram_id")) if acc.get("telegram_id") else f"admin{acc['id']}")
    subject = ("pwd:" + acc["username"]) if acc.get("username") else str(acc.get("telegram_id"))
    _check_method_policy(acc, "oauth", client_ip, username)
    logger.info("OAuth(%s) login for '%s' from %s", provider, username, client_ip)
    await notify_login_success(ip=client_ip, username=username, auth_method=f"oauth:{provider}")
    access_token, refresh_token = await _issue_login(
        request, response, subject, username, "oauth", account=acc)
    return {"mode": "login", "access_token": access_token, "refresh_token": refresh_token}


@router.get("/oauth/links")
async def oauth_links(admin: AdminUser = Depends(get_current_admin)):
    from web.backend.core import oauth_svc as oa
    if not getattr(admin, "account_id", None):
        return {"items": []}
    items = await oa.list_links(admin.account_id)
    return {"items": [{"id": l["id"], "provider": l["provider"], "email": l.get("email"),
                       "name": l.get("name"), "created_at": l.get("created_at"),
                       "last_used_at": l.get("last_used_at")} for l in items]}


@router.delete("/oauth/links/{link_id}", response_model=SuccessResponse)
async def oauth_del_link(link_id: int, admin: AdminUser = Depends(get_current_admin)):
    from web.backend.core import oauth_svc as oa
    if getattr(admin, "account_id", None):
        await oa.delete_link(link_id, admin.account_id)
    return SuccessResponse(message="Привязка удалена")


# ── 2FA (TOTP) — управление из активной сессии ───────────────────


async def _authed_account(admin: AdminUser):
    if not getattr(admin, "account_id", None):
        raise api_error(400, E.FORBIDDEN, "2FA доступна только для аккаунтов admin_accounts")
    from web.backend.core.admin_accounts import get_admin_account_by_id
    acc = await get_admin_account_by_id(admin.account_id)
    if not acc:
        raise api_error(404, E.USER_NOT_FOUND, "Аккаунт не найден")
    return acc


@router.post("/2fa/setup", response_model=TotpSetupResponse)
async def totp_setup_authed(admin: AdminUser = Depends(get_current_admin)):
    account = await _authed_account(admin)
    if account.get("totp_enabled"):
        raise api_error(400, E.FORBIDDEN, "2FA уже включена")
    from web.backend.core.rbac import update_admin_account
    secret = generate_totp_secret()
    uri = get_provisioning_uri(secret, admin.username)
    codes = generate_backup_codes()
    await update_admin_account(account["id"], totp_secret=encrypt_totp_secret(secret),
                               backup_codes=encrypt_backup_codes(codes))
    return TotpSetupResponse(secret=secret, qr_code=generate_qr_base64(uri),
                             provisioning_uri=uri, backup_codes=codes)


@router.post("/2fa/enable", response_model=SuccessResponse)
async def totp_enable_authed(data: TotpVerifyRequest, admin: AdminUser = Depends(get_current_admin)):
    account = await _authed_account(admin)
    if account.get("totp_enabled"):
        raise api_error(400, E.FORBIDDEN, "2FA уже включена")
    if not account.get("totp_secret"):
        raise api_error(400, E.FORBIDDEN, "Сначала вызови /2fa/setup")
    secret = decrypt_totp_secret(account["totp_secret"])
    if not verify_totp_code(secret, data.code, account_id=account["id"]):
        raise api_error(401, E.INVALID_TOKEN, "Неверный код")
    from web.backend.core.rbac import update_admin_account
    await update_admin_account(account["id"], totp_enabled=True)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="2fa.enable", resource="auth", resource_id="totp")
    return SuccessResponse(message="2FA включена")


@router.post("/2fa/disable", response_model=SuccessResponse)
async def totp_disable_authed(data: TotpVerifyRequest, admin: AdminUser = Depends(get_current_admin)):
    account = await _authed_account(admin)
    if not account.get("totp_enabled") or not account.get("totp_secret"):
        raise api_error(400, E.FORBIDDEN, "2FA не включена")
    secret = decrypt_totp_secret(account["totp_secret"])
    ok = verify_totp_code(secret, data.code, account_id=account["id"])
    if not ok:
        ok, _ = verify_backup_code(account.get("backup_codes"), data.code)
    if not ok:
        raise api_error(401, E.INVALID_TOKEN, "Неверный код")
    from web.backend.core.rbac import update_admin_account
    await update_admin_account(account["id"], totp_enabled=False)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="2fa.disable", resource="auth", resource_id="totp")
    return SuccessResponse(message="2FA отключена")


@router.post("/2fa/backup-codes", response_model=TotpSetupResponse)
async def totp_regen_backup(data: TotpVerifyRequest, admin: AdminUser = Depends(get_current_admin)):
    account = await _authed_account(admin)
    if not account.get("totp_enabled") or not account.get("totp_secret"):
        raise api_error(400, E.FORBIDDEN, "2FA не включена")
    secret = decrypt_totp_secret(account["totp_secret"])
    if not verify_totp_code(secret, data.code, account_id=account["id"]):
        raise api_error(401, E.INVALID_TOKEN, "Неверный код")
    from web.backend.core.rbac import update_admin_account
    codes = generate_backup_codes()
    await update_admin_account(account["id"], backup_codes=encrypt_backup_codes(codes))
    return TotpSetupResponse(secret="", qr_code="", provisioning_uri="", backup_codes=codes)


# ── Активные сессии — список / отзыв (self-service, scope по account_id) ──


def _current_sid(request: Request) -> Optional[str]:
    """Достать sid текущего входа из access-токена (Bearer или cookie)."""
    auth_header = request.headers.get("authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else request.cookies.get(ACCESS_COOKIE)
    if not token:
        return None
    payload = decode_token(token)
    return payload.get("sid") if payload else None


@router.get("/sessions")
async def list_admin_sessions(request: Request, admin: AdminUser = Depends(get_current_admin)):
    """Свои активные сессии (текущая помечена current)."""
    if not getattr(admin, "account_id", None):
        return {"items": []}
    cur = _current_sid(request)
    items = await _sessions.list_sessions(admin.account_id)
    return {"items": [{
        "id": s["id"],
        "auth_method": s.get("auth_method"),
        "ip": s.get("ip"),
        "user_agent": s.get("user_agent"),
        "created_at": s.get("created_at"),
        "last_seen_at": s.get("last_seen_at"),
        "current": s["id"] == cur,
    } for s in items]}


@router.delete("/sessions/{sid}", response_model=SuccessResponse)
async def revoke_admin_session(sid: str, admin: AdminUser = Depends(get_current_admin)):
    """Отозвать одну свою сессию."""
    if getattr(admin, "account_id", None):
        await _sessions.revoke_session(admin.account_id, sid)
        await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                              action="session.revoke", resource="auth", resource_id=sid[:12])
    return SuccessResponse(message="Сессия отозвана")


@router.post("/sessions/revoke-others", response_model=SuccessResponse)
async def revoke_other_admin_sessions(request: Request, admin: AdminUser = Depends(get_current_admin)):
    """Отозвать все свои сессии, кроме текущей."""
    revoked = 0
    if getattr(admin, "account_id", None):
        revoked = await _sessions.revoke_others(admin.account_id, _current_sid(request))
        await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                              action="session.revoke_others", resource="auth", resource_id=str(revoked))
    return SuccessResponse(message=f"Отозвано сессий: {revoked}")

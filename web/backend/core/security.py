"""Security utilities for web panel."""
import json
import hmac
import hashlib
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple

from jose import jwt, JWTError

from web.backend.core.config import get_web_settings

logger = logging.getLogger(__name__)


def get_access_ttl_minutes() -> int:
    """Resolve access-token TTL: DB setting > env > default."""
    try:
        from shared.config_service import config_service
        val = config_service.get("web_session_access_minutes")
        if val is not None and str(val).strip():
            return int(val)
    except Exception:
        pass
    return get_web_settings().jwt_expire_minutes


def get_refresh_ttl_hours() -> int:
    """Resolve refresh-token TTL: DB setting > env > default."""
    try:
        from shared.config_service import config_service
        val = config_service.get("web_session_refresh_hours")
        if val is not None and str(val).strip():
            return int(val)
    except Exception:
        pass
    return get_web_settings().jwt_refresh_hours


def verify_telegram_auth(auth_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Verify Telegram Login Widget authentication data.

    See: https://core.telegram.org/widgets/login#checking-authorization

    Args:
        auth_data: Dictionary with Telegram auth data (id, first_name, auth_date, hash, etc.)

    Returns:
        Tuple of (is_valid, error_message). error_message is empty if valid.
    """
    settings = get_web_settings()

    # Work with a copy to not modify the original
    data = dict(auth_data)

    # Extract hash from data
    check_hash = data.pop('hash', None)
    if not check_hash:
        logger.warning("Telegram auth: missing hash")
        return False, "Missing hash in auth data"

    # Check that data is not too old (24 hours max)
    auth_date = data.get('auth_date')
    if auth_date:
        try:
            auth_timestamp = int(auth_date)
            current_time = int(time.time())
            age_seconds = current_time - auth_timestamp

            if age_seconds > 86400:
                logger.warning(f"Telegram auth: data too old ({age_seconds}s)")
                return False, f"Auth data expired (age: {age_seconds}s, max: 86400s)"

            if age_seconds < -60:  # Allow 1 minute clock skew
                logger.warning(f"Telegram auth: future timestamp ({age_seconds}s)")
                return False, "Auth data has future timestamp"

        except (ValueError, TypeError) as e:
            logger.warning(f"Telegram auth: invalid auth_date: {e}")
            return False, f"Invalid auth_date format: {auth_date}"
    else:
        logger.warning("Telegram auth: missing auth_date")
        return False, "Missing auth_date"

    # Create data-check-string (sorted alphabetically)
    # Only include non-None values
    data_check_arr = []
    for key in sorted(data.keys()):
        value = data[key]
        if value is not None:
            data_check_arr.append(f"{key}={value}")
    data_check_string = "\n".join(data_check_arr)

    logger.debug(f"Telegram auth: data_check_string = {repr(data_check_string)}")

    # Create secret key from bot token (SHA256 hash of bot token)
    secret_key = hashlib.sha256(settings.telegram_bot_token.encode()).digest()

    # Calculate HMAC-SHA256 hash
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    # Compare hashes securely
    is_valid = hmac.compare_digest(calculated_hash, check_hash)

    if not is_valid:
        logger.warning(
            f"Telegram auth: hash mismatch for user {data.get('id')}. "
            f"Expected: {calculated_hash[:16]}..., Got: {check_hash[:16]}..."
        )
        return False, "Invalid signature"

    logger.info(f"Telegram auth: success for user {data.get('id')} ({data.get('username', 'no username')})")
    return True, ""


def verify_telegram_auth_simple(auth_data: Dict[str, Any]) -> bool:
    """
    Simple wrapper for verify_telegram_auth that returns only boolean.

    Args:
        auth_data: Dictionary with Telegram auth data

    Returns:
        True if authentication is valid, False otherwise.
    """
    is_valid, _ = verify_telegram_auth(auth_data)
    return is_valid


# Telegram Mini App initData: срок годности подписи. Совпадает с окном
# Login Widget — мини-апп подписывает данные один раз при открытии, а
# фронт переиспользует их для повторного входа после перезагрузки
# страницы (в iframe web.telegram.org куки SameSite=Lax не доезжают).
WEBAPP_INIT_DATA_MAX_AGE = 86400


def verify_telegram_webapp_init_data(
    init_data: str,
    max_age_seconds: int = WEBAPP_INIT_DATA_MAX_AGE,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Verify Telegram Mini App (Web App) initData.

    See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    Отличия от Login Widget (verify_telegram_auth): initData приходит
    строкой query-string, а секретный ключ — это HMAC(key="WebAppData",
    msg=bot_token), а не sha256(bot_token). В data-check-string входят
    ВСЕ пары кроме hash (включая signature и query_id).

    Args:
        init_data: Raw ``window.Telegram.WebApp.initData`` query string.
        max_age_seconds: Максимальный возраст подписи.

    Returns:
        Tuple of (is_valid, error_message, user). ``user`` — распарсенный
        объект Telegram-пользователя; пустой словарь при ошибке.
    """
    from urllib.parse import parse_qsl

    if not init_data or not init_data.strip():
        return False, "Missing init data", {}

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False, "Malformed init data", {}

    data = dict(pairs)
    # Дубли ключей ломают однозначность data-check-string — отказываем,
    # чтобы нельзя было протащить второе значение мимо подписи.
    if len(data) != len(pairs):
        return False, "Duplicate keys in init data", {}

    check_hash = data.pop("hash", None)
    if not check_hash:
        return False, "Missing hash in init data", {}

    if "auth_date" not in data:
        return False, "Missing auth_date", {}

    # Signature check — до всего остального
    data_check_string = "\n".join(f"{key}={data[key]}" for key in sorted(data))
    secret_key = hmac.new(
        b"WebAppData",
        get_web_settings().telegram_bot_token.encode(),
        hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, check_hash):
        logger.warning("Telegram WebApp auth: hash mismatch")
        return False, "Invalid signature", {}

    # Freshness
    try:
        auth_timestamp = int(data["auth_date"])
    except (ValueError, TypeError):
        return False, "Invalid auth_date format", {}

    age_seconds = int(time.time()) - auth_timestamp
    if age_seconds > max_age_seconds:
        logger.warning("Telegram WebApp auth: data too old (%ss)", age_seconds)
        return False, f"Init data expired (age: {age_seconds}s, max: {max_age_seconds}s)", {}
    if age_seconds < -60:  # 1 минута на расхождение часов
        logger.warning("Telegram WebApp auth: future timestamp (%ss)", age_seconds)
        return False, "Init data has future timestamp", {}

    # User payload
    raw_user = data.get("user")
    if not raw_user:
        return False, "Missing user in init data", {}
    try:
        user = json.loads(raw_user)
    except (ValueError, TypeError):
        return False, "Malformed user in init data", {}
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        return False, "Invalid user in init data", {}

    logger.info(
        "Telegram WebApp auth: success for user %s (%s)",
        user.get("id"), user.get("username", "no username"),
    )
    return True, "", user


def verify_admin_password(username: str, password: str) -> bool:
    """
    Verify admin credentials against .env (sync fallback).

    Used as last resort when async DB checks have already been tried.

    Returns:
        True if credentials match, False otherwise.
    """
    settings = get_web_settings()

    if not settings.admin_login or not settings.admin_password:
        return False

    # Username comparison (case-insensitive)
    if username.lower() != settings.admin_login.lower():
        return False

    stored = settings.admin_password

    # Normalize Cyrillic look-alikes to Latin (same as hash_password)
    from web.backend.core.admin_credentials import _normalize_password
    password = _normalize_password(password)

    # If stored password is a bcrypt hash, verify with bcrypt
    if stored.startswith("$2b$") or stored.startswith("$2a$"):
        try:
            import bcrypt as _bcrypt
            return _bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except Exception as e:
            logger.error("bcrypt verification failed: %s", e)
            return False

    # Plain-text comparison using constant-time function
    return hmac.compare_digest(password, stored)


async def verify_admin_password_async(username: str, password: str) -> bool:
    """
    Async version of verify_admin_password.

    Checks RBAC admin_accounts first, then .env.

    Returns:
        True if credentials match, False otherwise.
    """
    # 1. Check admin_accounts table (RBAC)
    try:
        from web.backend.core.rbac import get_admin_account_by_username
        from web.backend.core.admin_credentials import verify_password
        account = await get_admin_account_by_username(username)
        if account and account.get("password_hash"):
            if not account.get("is_active", True):
                logger.warning("Login denied for disabled admin account: %s", username)
                return False
            result = verify_password(password, account["password_hash"])
            if not result:
                logger.warning("Password verification failed for admin: %s", username)
            return result
    except Exception as e:
        logger.warning("admin_accounts check failed: %s", e)

    # 2. Fallback to .env
    return verify_admin_password(username, password)


def create_access_token(
    subject: str,
    username: str,
    auth_method: str = "telegram",
    sid: Optional[str] = None,
) -> str:
    """
    Create JWT access token.

    Args:
        subject: Token subject (telegram_id as string, or "pwd:<username>")
        username: Display username
        auth_method: "telegram" or "password"
        sid: Optional session id (admin_sessions.id) for session tracking/revocation

    Returns:
        Encoded JWT token
    """
    settings = get_web_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=get_access_ttl_minutes())

    payload = {
        "sub": subject,
        "username": username,
        "exp": int(expire.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "type": "access",
        "auth_method": auth_method,
    }
    if sid:
        payload["sid"] = sid

    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_temp_2fa_token(subject: str, auth_method: str = "password") -> str:
    """Create a short-lived JWT used only for the 2FA verification step.

    Valid for 5 minutes; type='2fa_temp'.
    """
    settings = get_web_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)

    payload = {
        "sub": subject,
        "exp": int(expire.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "type": "2fa_temp",
        "auth_method": auth_method,
    }

    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_password_reset_token(admin_id: int, username: str) -> str:
    """Create a short-lived JWT for password reset (30 minutes, type='password_reset')."""
    settings = get_web_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)

    payload = {
        "sub": str(admin_id),
        "username": username,
        "exp": int(expire.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "type": "password_reset",
    }

    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, sid: Optional[str] = None) -> str:
    """
    Create JWT refresh token.

    Args:
        subject: Token subject (telegram_id as string, or "pwd:<username>")
        sid: Optional session id (admin_sessions.id), carried across rotations

    Returns:
        Encoded JWT refresh token
    """
    settings = get_web_settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=get_refresh_ttl_hours())

    payload = {
        "sub": subject,
        "exp": int(expire.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "type": "refresh",
    }
    if sid:
        payload["sid"] = sid

    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
    """
    Decode and validate JWT token.

    Args:
        token: JWT token to decode
        token_type: Expected token type (default "access"). Pass None to skip type check.

    Returns:
        Token payload if valid and type matches, None otherwise
    """
    settings = get_web_settings()

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        if token_type is not None and payload.get("type") != token_type:
            logger.warning(
                "Token type mismatch: expected=%s, got=%s",
                token_type, payload.get("type"),
            )
            return None
        return payload
    except JWTError as e:
        logger.debug(f"Token decode error: {e}")
        return None

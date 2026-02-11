"""Security utilities for web panel."""
import hmac
import hashlib
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple

from jose import jwt, JWTError

from web.backend.core.config import get_web_settings

logger = logging.getLogger(__name__)


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
            return verify_password(password, account["password_hash"])
    except Exception as e:
        logger.warning("admin_accounts check failed: %s", e)

    # 2. Fallback to .env
    return verify_admin_password(username, password)


def create_access_token(
    subject: str,
    username: str,
    auth_method: str = "telegram",
) -> str:
    """
    Create JWT access token.

    Args:
        subject: Token subject (telegram_id as string, or "pwd:<username>")
        username: Display username
        auth_method: "telegram" or "password"

    Returns:
        Encoded JWT token
    """
    settings = get_web_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)

    payload = {
        "sub": subject,
        "username": username,
        "exp": int(expire.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "type": "access",
        "auth_method": auth_method,
    }

    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    """
    Create JWT refresh token.

    Args:
        subject: Token subject (telegram_id as string, or "pwd:<username>")

    Returns:
        Encoded JWT refresh token
    """
    settings = get_web_settings()
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_refresh_hours)

    payload = {
        "sub": subject,
        "exp": int(expire.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "type": "refresh",
    }

    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate JWT token.

    Args:
        token: JWT token to decode

    Returns:
        Token payload if valid, None otherwise
    """
    settings = get_web_settings()

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError as e:
        logger.debug(f"Token decode error: {e}")
        return None

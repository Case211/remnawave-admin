"""Security utilities for web panel."""
import hmac
import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from jose import jwt, JWTError

from web.backend.core.config import get_web_settings


def verify_telegram_auth(auth_data: Dict[str, Any]) -> bool:
    """
    Verify Telegram Login Widget authentication data.

    See: https://core.telegram.org/widgets/login#checking-authorization

    Args:
        auth_data: Dictionary with Telegram auth data (id, first_name, auth_date, hash, etc.)

    Returns:
        True if authentication is valid, False otherwise.
    """
    settings = get_web_settings()

    # Extract hash from data
    check_hash = auth_data.pop('hash', None)
    if not check_hash:
        return False

    # Check that data is not too old (24 hours max)
    auth_date = auth_data.get('auth_date')
    if auth_date:
        try:
            auth_timestamp = int(auth_date)
            if int(time.time()) - auth_timestamp > 86400:
                return False
        except (ValueError, TypeError):
            return False

    # Create data-check-string
    data_check_arr = []
    for key in sorted(auth_data.keys()):
        value = auth_data[key]
        if value is not None:
            data_check_arr.append(f"{key}={value}")
    data_check_string = "\n".join(data_check_arr)

    # Create secret key from bot token
    secret_key = hashlib.sha256(settings.telegram_bot_token.encode()).digest()

    # Calculate hash
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    # Compare hashes
    return hmac.compare_digest(calculated_hash, check_hash)


def create_access_token(telegram_id: int, username: str) -> str:
    """
    Create JWT access token.

    Args:
        telegram_id: User's Telegram ID
        username: User's username

    Returns:
        Encoded JWT token
    """
    settings = get_web_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)

    payload = {
        "sub": str(telegram_id),
        "username": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(telegram_id: int) -> str:
    """
    Create JWT refresh token.

    Args:
        telegram_id: User's Telegram ID

    Returns:
        Encoded JWT refresh token
    """
    settings = get_web_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_days)

    payload = {
        "sub": str(telegram_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
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
    except JWTError:
        return None

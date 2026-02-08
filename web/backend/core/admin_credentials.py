"""Admin credentials management — DB storage, validation, generation.

Table `admin_credentials` is auto-created on first startup.
On first run (no rows in table), a secure password is generated and
printed to the console. The admin can then change it from the web UI.
"""
import logging
import secrets
import string
import re
from typing import Optional, Tuple

from passlib.hash import bcrypt

logger = logging.getLogger(__name__)

# ── Password policy ──────────────────────────────────────────────

MIN_PASSWORD_LENGTH = 8
GENERATED_PASSWORD_LENGTH = 20

# Characters for generated passwords (no ambiguous chars: 0/O, 1/l/I)
_LOWER = "abcdefghjkmnpqrstuvwxyz"
_UPPER = "ABCDEFGHJKMNPQRSTUVWXYZ"
_DIGITS = "23456789"
_SPECIAL = "!@#$%^&*_+-="
_ALL_CHARS = _LOWER + _UPPER + _DIGITS + _SPECIAL


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Check password meets complexity requirements.

    Requirements:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Returns:
        (is_valid, error_message)
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"

    if not re.search(r"[!@#$%^&*_+\-=\[\]{}|;:',.<>?/\\~`\"()]", password):
        return False, "Password must contain at least one special character"

    return True, ""


def generate_password(length: int = GENERATED_PASSWORD_LENGTH) -> str:
    """Generate a cryptographically secure random password.

    Guarantees at least one char from each category.
    Uses `secrets` module for cryptographic randomness.
    """
    # Guarantee one of each type
    password_chars = [
        secrets.choice(_LOWER),
        secrets.choice(_UPPER),
        secrets.choice(_DIGITS),
        secrets.choice(_SPECIAL),
    ]

    # Fill the rest randomly
    for _ in range(length - 4):
        password_chars.append(secrets.choice(_ALL_CHARS))

    # Shuffle to avoid predictable positions
    result = list(password_chars)
    secrets.SystemRandom().shuffle(result)
    return "".join(result)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt (12 rounds)."""
    return bcrypt.hash(password, rounds=12)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.verify(password, password_hash)
    except Exception as e:
        logger.error("Password verification error: %s", e)
        return False


# ── Database operations ──────────────────────────────────────────

_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS admin_credentials (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_generated BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
"""


async def ensure_table() -> None:
    """Create admin_credentials table if it doesn't exist."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            await conn.execute(_TABLE_SQL)
    except Exception as e:
        logger.error("Failed to create admin_credentials table: %s", e)


async def get_admin_by_username(username: str) -> Optional[dict]:
    """Look up admin credentials by username (case-insensitive)."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, username, password_hash, is_generated "
                "FROM admin_credentials WHERE LOWER(username) = LOWER($1)",
                username,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to query admin_credentials: %s", e)
        return None


async def admin_exists() -> bool:
    """Check if any admin account exists in the database."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return False
        async with db_service.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM admin_credentials LIMIT 1")
            return row is not None
    except Exception as e:
        logger.error("Failed to check admin_credentials: %s", e)
        return False


async def create_admin(username: str, password: str, is_generated: bool = False) -> bool:
    """Create a new admin account with hashed password."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return False
        pw_hash = hash_password(password)
        async with db_service.acquire() as conn:
            await conn.execute(
                "INSERT INTO admin_credentials (username, password_hash, is_generated) "
                "VALUES ($1, $2, $3) "
                "ON CONFLICT (username) DO UPDATE SET "
                "password_hash = $2, is_generated = $3, updated_at = NOW()",
                username, pw_hash, is_generated,
            )
        return True
    except Exception as e:
        logger.error("Failed to create admin: %s", e)
        return False


async def update_password(username: str, new_password: str) -> bool:
    """Update admin password (marks is_generated=false)."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return False
        pw_hash = hash_password(new_password)
        async with db_service.acquire() as conn:
            result = await conn.execute(
                "UPDATE admin_credentials SET password_hash = $2, "
                "is_generated = false, updated_at = NOW() "
                "WHERE LOWER(username) = LOWER($1)",
                username, pw_hash,
            )
            return "UPDATE 1" in result
    except Exception as e:
        logger.error("Failed to update password: %s", e)
        return False


async def first_run_setup() -> Optional[str]:
    """Run on startup: create table, generate password if first run.

    Returns:
        The generated password if first run, None otherwise.
    """
    await ensure_table()

    if await admin_exists():
        logger.info("Admin account exists in database")
        return None

    # First run — generate credentials
    password = generate_password()
    username = "admin"

    if await create_admin(username, password, is_generated=True):
        return password
    return None

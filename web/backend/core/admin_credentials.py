"""Admin credentials utilities — password hashing, validation, generation.

All admin accounts are stored in the admin_accounts (RBAC) table.
This module provides password-related utility functions used across the app.
"""
import logging
import secrets
import re
from typing import Optional, Tuple

import bcrypt as _bcrypt

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
    return _bcrypt.hashpw(
        password.encode("utf-8"), _bcrypt.gensalt(rounds=12)
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return _bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except Exception as e:
        logger.error("Password verification error: %s", e)
        return False


# ── First-run setup (creates account in admin_accounts) ──────────

async def first_run_setup() -> Optional[str]:
    """Run on startup: generate admin password if no accounts exist.

    Creates the initial admin in admin_accounts (RBAC) table.

    Returns:
        The generated password if first run, None otherwise.
    """
    try:
        from web.backend.core.rbac import (
            admin_account_exists,
            get_role_by_name,
            create_admin_account,
        )

        if await admin_account_exists():
            logger.info("Admin account exists in database")
            return None

        # Get superadmin role
        role = await get_role_by_name("superadmin")
        if not role:
            logger.error(
                "Cannot create first admin: 'superadmin' role not found. "
                "Run migrations first."
            )
            return None

        # First run — generate credentials
        password = generate_password()
        username = "admin"
        pw_hash = hash_password(password)

        account = await create_admin_account(
            username=username,
            password_hash=pw_hash,
            telegram_id=None,
            role_id=role["id"],
            is_generated_password=True,
        )

        if account:
            return password

        logger.error("Failed to create initial admin account")
        return None

    except Exception as e:
        logger.error("first_run_setup failed: %s", e)
        return None

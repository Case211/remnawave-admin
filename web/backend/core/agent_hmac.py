"""HMAC-SHA256 signing and verification for agent commands.

Every command sent from backend to agent is signed with HMAC-SHA256.
Key material: WEB_SECRET_KEY + agent_token.
Payload includes a timestamp for replay protection (60s window).
"""
import hashlib
import hmac
import json
import time
from typing import Any, Dict

from web.backend.core.config import get_web_settings


def _derive_key(agent_token: str) -> bytes:
    """Derive HMAC key from secret + agent token."""
    settings = get_web_settings()
    return hashlib.sha256(
        f"{settings.secret_key}:{agent_token}".encode()
    ).digest()


def sign_command(payload: Dict[str, Any], agent_token: str) -> str:
    """Sign a command payload with HMAC-SHA256.

    Adds a `_ts` timestamp field to the payload before signing.
    Returns the hex-encoded signature.
    """
    payload_copy = dict(payload)
    payload_copy["_ts"] = int(time.time())

    canonical = json.dumps(payload_copy, sort_keys=True, separators=(",", ":"))
    key = _derive_key(agent_token)
    sig = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
    return sig


def sign_command_with_ts(payload: Dict[str, Any], agent_token: str) -> tuple[Dict[str, Any], str]:
    """Sign a command payload and return (payload_with_ts, signature)."""
    payload_copy = dict(payload)
    payload_copy["_ts"] = int(time.time())

    canonical = json.dumps(payload_copy, sort_keys=True, separators=(",", ":"))
    key = _derive_key(agent_token)
    sig = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
    return payload_copy, sig


def verify_command_signature(
    payload: Dict[str, Any],
    signature: str,
    agent_token: str,
    max_age_seconds: int = 60,
) -> bool:
    """Verify HMAC signature and check timestamp freshness.

    Returns True if signature is valid and timestamp is within max_age_seconds.
    """
    ts = payload.get("_ts")
    if ts is None:
        return False

    # Check replay window
    now = int(time.time())
    if abs(now - ts) > max_age_seconds:
        return False

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    key = _derive_key(agent_token)
    expected = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

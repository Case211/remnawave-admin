"""Offline JWT license verification for paid plugins.

Plugins ship a hard-coded Ed25519 public key and validate license tokens
locally — there is no callback to a license server. The license is a JWT
signed with EdDSA (Ed25519). The expected payload looks like::

    {
      "iss": "rwa-licensing",
      "sub": "<panel fingerprint or domain>",
      "plugins": ["debugger"],
      "tier": "pro",
      "iat": 1781836400,
      "exp": 1797846400
    }

This module deliberately does **not** depend on PyJWT/jose — only on
``cryptography``, which the panel already pulls in for password hashing.
A custom Ed25519 JWT verifier is ~50 lines and avoids surprising algorithm
quirks (e.g. ``alg=none`` confusion attacks) by hard-coding the algorithm.

Usage from a plugin::

    from web.backend.core.license import (
        LicenseState, verify_offline_jwt, decide_license_state,
    )

    PUBLIC_KEY = b"...32 bytes raw or PEM..."  # hard-coded in the plugin

    claims, error = verify_offline_jwt(
        token=os.environ.get("RWA_LICENSE_KEY", ""),
        public_key=PUBLIC_KEY,
        plugin_id="debugger",
    )
    state: LicenseState = decide_license_state(claims, error)
"""
from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass
from typing import Iterable, Literal, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

logger = logging.getLogger(__name__)

LicenseState = Literal["valid", "expired", "missing", "not_required"]


@dataclass(frozen=True)
class LicenseClaims:
    sub: Optional[str]
    plugins: tuple[str, ...]
    tier: Optional[str]
    iat: Optional[int]
    exp: Optional[int]
    raw: dict


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _load_public_key(public_key: bytes) -> Ed25519PublicKey:
    """Accept either 32-byte raw Ed25519 public key or PEM-encoded."""
    if len(public_key) == 32:
        return Ed25519PublicKey.from_public_bytes(public_key)
    pem_obj = load_pem_public_key(public_key)
    if not isinstance(pem_obj, Ed25519PublicKey):
        raise ValueError("public key is not Ed25519")
    return pem_obj


def peek_jwt_payload(token: str) -> Optional[dict]:
    """Decode a JWT *without* verifying its signature.

    Used by the in-panel installer's master-license flow: the panel
    doesn't have access to every plugin's public key, but it still
    needs to know which plugin ids the JWT covers and when it expires
    so it can fan-out the token to the right ``plugin_licenses`` rows.

    Signature verification still happens when the plugin actually loads
    (via :func:`verify_offline_jwt` against its own embedded public key),
    so a forged payload here can't bypass licensing — at worst the
    operator wastes a row in ``plugin_licenses`` that no plugin will
    accept.

    Returns ``None`` for malformed tokens; never raises.
    """
    if not token or "." not in token:
        return None
    parts = token.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        payload = json.loads(_b64url_decode(parts[1]))
    except (ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
    return pem_obj


def verify_offline_jwt(
    token: str,
    public_key: bytes,
    plugin_id: str,
    *,
    now: Optional[int] = None,
    expected_issuer: str = "rwa-licensing",
) -> tuple[Optional[LicenseClaims], Optional[str]]:
    """Validate a license JWT against ``public_key``.

    Returns ``(claims, None)`` on success, ``(None, reason)`` on failure.
    Reasons are short stable strings ("missing", "malformed", "bad_signature",
    "expired", "wrong_issuer", "wrong_alg", "plugin_not_licensed") so the
    caller can surface them in logs or telemetry without leaking key material.

    The verifier does **not** raise on bad input — never trust user-supplied
    license tokens, always handle errors as data.
    """
    if not token:
        return None, "missing"

    parts = token.strip().split(".")
    if len(parts) != 3:
        return None, "malformed"

    try:
        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
        signature = _b64url_decode(parts[2])
    except (ValueError, json.JSONDecodeError):
        return None, "malformed"

    # Hard-code the algorithm to avoid alg=none attacks.
    if header.get("alg") != "EdDSA":
        return None, "wrong_alg"

    signing_input = (parts[0] + "." + parts[1]).encode("ascii")

    try:
        key = _load_public_key(public_key)
        key.verify(signature, signing_input)
    except (InvalidSignature, ValueError):
        return None, "bad_signature"

    if expected_issuer and payload.get("iss") != expected_issuer:
        return None, "wrong_issuer"

    plugins = tuple(payload.get("plugins") or ())
    if plugin_id not in plugins:
        return None, "plugin_not_licensed"

    exp = payload.get("exp")
    current = now if now is not None else int(time.time())
    if exp is not None and current >= int(exp):
        # Return the claims anyway so callers can render "expired since X"
        return (
            LicenseClaims(
                sub=payload.get("sub"),
                plugins=plugins,
                tier=payload.get("tier"),
                iat=payload.get("iat"),
                exp=int(exp),
                raw=payload,
            ),
            "expired",
        )

    return (
        LicenseClaims(
            sub=payload.get("sub"),
            plugins=plugins,
            tier=payload.get("tier"),
            iat=payload.get("iat"),
            exp=int(exp) if exp is not None else None,
            raw=payload,
        ),
        None,
    )


def decide_license_state(claims: Optional[LicenseClaims], error: Optional[str]) -> LicenseState:
    """Translate ``verify_offline_jwt`` output to a manifest license state.

    - ``None`` claims with reason ``missing`` / ``malformed`` / ``bad_signature``
      / ``wrong_issuer`` / ``wrong_alg`` / ``plugin_not_licensed`` → ``missing``
    - ``expired`` reason → ``expired``
    - clean validation → ``valid``
    """
    if error == "expired":
        return "expired"
    if error or claims is None:
        return "missing"
    return "valid"


def cache_seconds_until_recheck(claims: Optional[LicenseClaims], default: int = 3600) -> int:
    """How long the caller may safely cache the license decision.

    Don't cache past ``exp`` — re-check sooner so a freshly expired token
    flips to "expired" without waiting for the cache to time out.
    """
    if claims is None or claims.exp is None:
        return default
    remaining = int(claims.exp) - int(time.time())
    if remaining <= 0:
        return 60  # expired — recheck once a minute, no point hammering
    return max(60, min(default, remaining))

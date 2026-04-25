"""Tests for the offline JWT license verifier."""
from __future__ import annotations

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
)

from web.backend.core.license import (
    cache_seconds_until_recheck,
    decide_license_state,
    verify_offline_jwt,
)


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _make_jwt(
    private: Ed25519PrivateKey,
    payload: dict,
    *,
    alg: str = "EdDSA",
) -> str:
    header = {"alg": alg, "typ": "JWT"}
    h = _b64url(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode("ascii")
    sig = private.sign(signing_input)
    return f"{h}.{p}.{_b64url(sig)}"


@pytest.fixture(scope="module")
def keypair() -> tuple[Ed25519PrivateKey, bytes]:
    priv = Ed25519PrivateKey.generate()
    pub_raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return priv, pub_raw


def test_valid_token_round_trip(keypair):
    priv, pub = keypair
    payload = {
        "iss": "rwa-licensing",
        "sub": "panel-123",
        "plugins": ["debugger"],
        "tier": "pro",
        "iat": int(time.time()) - 10,
        "exp": int(time.time()) + 3600,
    }
    token = _make_jwt(priv, payload)
    claims, err = verify_offline_jwt(token, pub, plugin_id="debugger")
    assert err is None
    assert claims is not None
    assert claims.sub == "panel-123"
    assert claims.tier == "pro"
    assert "debugger" in claims.plugins
    assert decide_license_state(claims, err) == "valid"


def test_missing_token(keypair):
    _, pub = keypair
    claims, err = verify_offline_jwt("", pub, plugin_id="debugger")
    assert err == "missing"
    assert claims is None
    assert decide_license_state(claims, err) == "missing"


def test_malformed_token(keypair):
    _, pub = keypair
    claims, err = verify_offline_jwt("not.a.jwt.at.all", pub, plugin_id="debugger")
    assert err == "malformed"
    assert decide_license_state(claims, err) == "missing"


def test_bad_signature(keypair):
    priv, _ = keypair
    other = Ed25519PrivateKey.generate()
    other_pub = other.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    payload = {
        "iss": "rwa-licensing",
        "plugins": ["debugger"],
        "exp": int(time.time()) + 3600,
    }
    token = _make_jwt(priv, payload)
    # Token signed with priv, verifying against an unrelated key
    claims, err = verify_offline_jwt(token, other_pub, plugin_id="debugger")
    assert err == "bad_signature"
    assert decide_license_state(claims, err) == "missing"


def test_wrong_alg_rejected(keypair):
    priv, pub = keypair
    payload = {"iss": "rwa-licensing", "plugins": ["debugger"]}
    token = _make_jwt(priv, payload, alg="HS256")
    claims, err = verify_offline_jwt(token, pub, plugin_id="debugger")
    assert err == "wrong_alg"


def test_wrong_issuer(keypair):
    priv, pub = keypair
    payload = {
        "iss": "evil-co",
        "plugins": ["debugger"],
        "exp": int(time.time()) + 3600,
    }
    token = _make_jwt(priv, payload)
    claims, err = verify_offline_jwt(token, pub, plugin_id="debugger")
    assert err == "wrong_issuer"


def test_plugin_not_in_token(keypair):
    priv, pub = keypair
    payload = {
        "iss": "rwa-licensing",
        "plugins": ["debugger"],
        "exp": int(time.time()) + 3600,
    }
    token = _make_jwt(priv, payload)
    claims, err = verify_offline_jwt(token, pub, plugin_id="other-plugin")
    assert err == "plugin_not_licensed"


def test_expired_returns_claims_with_expired_state(keypair):
    priv, pub = keypair
    payload = {
        "iss": "rwa-licensing",
        "plugins": ["debugger"],
        "iat": int(time.time()) - 7200,
        "exp": int(time.time()) - 3600,
    }
    token = _make_jwt(priv, payload)
    claims, err = verify_offline_jwt(token, pub, plugin_id="debugger")
    assert err == "expired"
    assert claims is not None
    assert decide_license_state(claims, err) == "expired"


def test_pem_public_key_accepted(keypair):
    priv, _ = keypair
    pem = priv.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    )
    payload = {
        "iss": "rwa-licensing",
        "plugins": ["debugger"],
        "exp": int(time.time()) + 60,
    }
    token = _make_jwt(priv, payload)
    claims, err = verify_offline_jwt(token, pem, plugin_id="debugger")
    assert err is None
    assert claims is not None


def test_cache_window_clamps_to_exp(keypair):
    priv, pub = keypair
    exp = int(time.time()) + 120
    payload = {"iss": "rwa-licensing", "plugins": ["debugger"], "exp": exp}
    token = _make_jwt(priv, payload)
    claims, _ = verify_offline_jwt(token, pub, plugin_id="debugger")
    seconds = cache_seconds_until_recheck(claims, default=3600)
    # default is 3600 but exp is in 120s — must clamp under 120
    assert 60 <= seconds <= 120

"""Tests for deps.get_client_ip — trusted-proxy gated client IP resolution.

The forwarding headers (X-Real-IP / X-Forwarded-For) are attacker-controllable,
so they must be honored only when the immediate peer is a trusted reverse proxy.
A client hitting the backend port directly must not be able to spoof its IP.
"""
import pytest

from web.backend.core.config import get_web_settings
from web.backend.api import deps
from web.backend.api.deps import get_client_ip


class _FakeClient:
    def __init__(self, host):
        self.host = host


class FakeRequest:
    def __init__(self, peer="203.0.113.7", headers=None):
        self.client = _FakeClient(peer) if peer is not None else None
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}


@pytest.fixture(autouse=True)
def _reset_caches(monkeypatch):
    """Each test sets WEB_TRUSTED_PROXIES fresh; clear the two relevant caches."""
    def _set(value):
        monkeypatch.setenv("WEB_TRUSTED_PROXIES", value)
        get_web_settings.cache_clear()
        deps._trusted_proxy_networks.cache_clear()
    yield _set
    get_web_settings.cache_clear()
    deps._trusted_proxy_networks.cache_clear()


# ── Untrusted / direct connection: headers must be ignored ──────────────

def test_direct_public_peer_ignores_spoofed_real_ip(_reset_caches):
    _reset_caches("10.0.0.0/8")  # public peer is NOT trusted
    req = FakeRequest(peer="203.0.113.9", headers={"X-Real-IP": "10.0.0.5"})
    assert get_client_ip(req) == "203.0.113.9"


def test_direct_public_peer_ignores_spoofed_forwarded_for(_reset_caches):
    _reset_caches("10.0.0.0/8")
    req = FakeRequest(
        peer="203.0.113.9",
        headers={"X-Forwarded-For": "1.1.1.1, 10.0.0.5"},
    )
    assert get_client_ip(req) == "203.0.113.9"


def test_missing_client_returns_unknown(_reset_caches):
    _reset_caches("")
    req = FakeRequest(peer=None)
    assert get_client_ip(req) == "unknown"


# ── Trusted proxy: real client IP is taken from headers ─────────────────

def test_trusted_proxy_uses_x_real_ip(_reset_caches):
    _reset_caches("172.18.0.0/16")
    req = FakeRequest(peer="172.18.0.5", headers={"X-Real-IP": "203.0.113.50"})
    assert get_client_ip(req) == "203.0.113.50"


def test_trusted_proxy_xff_rightmost_untrusted(_reset_caches):
    _reset_caches("172.18.0.0/16")
    # Client -> edge(8.8.8.8) -> our proxy(172.18.0.5). Rightmost untrusted is the
    # real client edge, not a left-most value a client could inject.
    req = FakeRequest(
        peer="172.18.0.5",
        headers={"X-Forwarded-For": "evil-spoof, 203.0.113.50, 172.18.0.9"},
    )
    assert get_client_ip(req) == "203.0.113.50"


def test_trusted_proxy_invalid_real_ip_falls_back_to_peer(_reset_caches):
    _reset_caches("172.18.0.0/16")
    req = FakeRequest(peer="172.18.0.5", headers={"X-Real-IP": "not-an-ip"})
    assert get_client_ip(req) == "172.18.0.5"


# ── Default (empty) trusts private ranges, matching nginx ───────────────

def test_default_trusts_private_peer(_reset_caches):
    _reset_caches("")
    req = FakeRequest(peer="172.18.0.5", headers={"X-Real-IP": "203.0.113.50"})
    assert get_client_ip(req) == "203.0.113.50"


def test_default_ignores_headers_from_public_peer(_reset_caches):
    _reset_caches("")
    req = FakeRequest(peer="198.51.100.10", headers={"X-Real-IP": "10.0.0.1"})
    assert get_client_ip(req) == "198.51.100.10"

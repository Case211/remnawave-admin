"""Tests for HMAC-SHA256 agent command signing and verification."""
import hashlib
import hmac as hmac_mod
import json
import time

import pytest
from unittest.mock import patch, MagicMock

from web.backend.core.agent_hmac import (
    _derive_key,
    sign_command,
    sign_command_with_ts,
    verify_command_signature,
)


def _fake_settings(secret_key="test-secret"):
    s = MagicMock()
    s.secret_key = secret_key
    return s


@pytest.fixture(autouse=True)
def _mock_settings():
    with patch("web.backend.core.agent_hmac.get_web_settings", return_value=_fake_settings()):
        yield


class TestDeriveKey:
    """Tests for _derive_key."""

    def test_returns_bytes(self):
        key = _derive_key("agent-token-1")
        assert isinstance(key, bytes)
        assert len(key) == 32  # SHA-256 digest

    def test_different_tokens_produce_different_keys(self):
        k1 = _derive_key("token-a")
        k2 = _derive_key("token-b")
        assert k1 != k2

    def test_depends_on_secret_key(self):
        k1 = _derive_key("token")
        with patch(
            "web.backend.core.agent_hmac.get_web_settings",
            return_value=_fake_settings("other-secret"),
        ):
            k2 = _derive_key("token")
        assert k1 != k2

    def test_deterministic(self):
        assert _derive_key("token") == _derive_key("token")


class TestSignCommand:
    """Tests for sign_command."""

    def test_returns_hex_string(self):
        sig = sign_command({"action": "restart"}, "agent-tok")
        assert isinstance(sig, str)
        assert len(sig) == 64  # SHA-256 hex

    def test_different_payloads_different_sigs(self):
        s1 = sign_command({"action": "restart"}, "tok")
        s2 = sign_command({"action": "stop"}, "tok")
        assert s1 != s2

    def test_does_not_mutate_original_payload(self):
        payload = {"action": "restart"}
        sign_command(payload, "tok")
        assert "_ts" not in payload


class TestSignCommandWithTs:
    """Tests for sign_command_with_ts."""

    def test_returns_tuple(self):
        result = sign_command_with_ts({"action": "restart"}, "tok")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_payload_contains_ts(self):
        payload_with_ts, sig = sign_command_with_ts({"action": "restart"}, "tok")
        assert "_ts" in payload_with_ts
        assert isinstance(payload_with_ts["_ts"], int)

    def test_signature_is_hex(self):
        _, sig = sign_command_with_ts({"action": "restart"}, "tok")
        assert len(sig) == 64


class TestVerifyCommandSignature:
    """Tests for verify_command_signature."""

    def test_valid_signature_returns_true(self):
        payload_with_ts, sig = sign_command_with_ts({"action": "restart"}, "tok")
        assert verify_command_signature(payload_with_ts, sig, "tok") is True

    def test_invalid_signature_returns_false(self):
        payload_with_ts, _ = sign_command_with_ts({"action": "restart"}, "tok")
        assert verify_command_signature(payload_with_ts, "bad" * 16, "tok") is False

    def test_wrong_token_returns_false(self):
        payload_with_ts, sig = sign_command_with_ts({"action": "restart"}, "tok-a")
        assert verify_command_signature(payload_with_ts, sig, "tok-b") is False

    def test_missing_ts_returns_false(self):
        assert verify_command_signature({"action": "restart"}, "sig", "tok") is False

    def test_expired_ts_returns_false(self):
        old_ts = int(time.time()) - 120  # 2 min ago
        payload = {"action": "restart", "_ts": old_ts}
        # Build valid signature for this payload
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        key = _derive_key("tok")
        sig = hmac_mod.new(key, canonical.encode(), hashlib.sha256).hexdigest()
        assert verify_command_signature(payload, sig, "tok") is False

    def test_ts_within_window_returns_true(self):
        payload_with_ts, sig = sign_command_with_ts({"action": "restart"}, "tok")
        assert verify_command_signature(payload_with_ts, sig, "tok", max_age_seconds=60) is True

    def test_key_order_does_not_matter(self):
        """sign_command uses sort_keys, so key order is irrelevant."""
        ts = int(time.time())
        payload_a = {"action": "restart", "node": "n1", "_ts": ts}
        payload_b = {"node": "n1", "_ts": ts, "action": "restart"}

        canonical = json.dumps(payload_a, sort_keys=True, separators=(",", ":"))
        key = _derive_key("tok")
        sig = hmac_mod.new(key, canonical.encode(), hashlib.sha256).hexdigest()

        assert verify_command_signature(payload_a, sig, "tok") is True
        assert verify_command_signature(payload_b, sig, "tok") is True

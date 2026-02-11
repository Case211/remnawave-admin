"""Tests for web.backend.core.token_blacklist — token revocation."""
import time

import pytest

from web.backend.core.token_blacklist import TokenBlacklist


class TestTokenBlacklist:
    """Token blacklist operations."""

    def setup_method(self):
        self.bl = TokenBlacklist()

    def test_fresh_token_not_blacklisted(self):
        assert not self.bl.is_blacklisted("some-token")

    def test_add_and_check(self):
        self.bl.add("token-1", time.time() + 3600)
        assert self.bl.is_blacklisted("token-1")

    def test_different_token_not_blacklisted(self):
        self.bl.add("token-1", time.time() + 3600)
        assert not self.bl.is_blacklisted("token-2")

    def test_expired_token_auto_removed(self):
        self.bl.add("expired-token", time.time() - 1)
        assert not self.bl.is_blacklisted("expired-token")

    def test_multiple_tokens(self):
        future = time.time() + 3600
        self.bl.add("t1", future)
        self.bl.add("t2", future)
        self.bl.add("t3", future)
        assert self.bl.is_blacklisted("t1")
        assert self.bl.is_blacklisted("t2")
        assert self.bl.is_blacklisted("t3")
        assert not self.bl.is_blacklisted("t4")

    def test_cleanup_removes_expired(self):
        self.bl.add("old", time.time() - 100)
        self.bl.add("valid", time.time() + 3600)

        # Force cleanup
        self.bl._last_cleanup = 0
        self.bl._maybe_cleanup()

        assert not self.bl.is_blacklisted("old")
        assert self.bl.is_blacklisted("valid")

"""Tests for web.backend.core.login_guard — brute-force protection."""
import time
from unittest.mock import patch

import pytest

from web.backend.core.login_guard import LoginGuard, MAX_ATTEMPTS, LOCKOUT_SECONDS


class TestLoginGuard:
    """LoginGuard brute-force protection tests."""

    def setup_method(self):
        self.guard = LoginGuard()

    def test_fresh_ip_not_locked(self):
        assert not self.guard.is_locked("1.2.3.4")

    def test_single_failure_not_locked(self):
        self.guard.record_failure("1.2.3.4")
        assert not self.guard.is_locked("1.2.3.4")

    def test_max_failures_causes_lockout(self):
        ip = "10.0.0.1"
        for _ in range(MAX_ATTEMPTS):
            self.guard.record_failure(ip)
        assert self.guard.is_locked(ip)

    def test_record_failure_returns_true_on_lockout(self):
        ip = "10.0.0.2"
        for i in range(MAX_ATTEMPTS - 1):
            result = self.guard.record_failure(ip)
            assert not result
        result = self.guard.record_failure(ip)
        assert result

    def test_remaining_seconds(self):
        ip = "10.0.0.3"
        for _ in range(MAX_ATTEMPTS):
            self.guard.record_failure(ip)
        remaining = self.guard.remaining_seconds(ip)
        assert 0 < remaining <= LOCKOUT_SECONDS

    def test_remaining_seconds_not_locked(self):
        assert self.guard.remaining_seconds("unknown") == 0

    def test_success_resets_failures(self):
        ip = "10.0.0.4"
        for _ in range(MAX_ATTEMPTS - 1):
            self.guard.record_failure(ip)
        self.guard.record_success(ip)
        # Should be fresh again
        assert not self.guard.is_locked(ip)
        assert self.guard.remaining_seconds(ip) == 0

    def test_different_ips_independent(self):
        ip1 = "10.0.0.5"
        ip2 = "10.0.0.6"
        for _ in range(MAX_ATTEMPTS):
            self.guard.record_failure(ip1)
        assert self.guard.is_locked(ip1)
        assert not self.guard.is_locked(ip2)

    def test_lockout_expires(self):
        ip = "10.0.0.7"
        for _ in range(MAX_ATTEMPTS):
            self.guard.record_failure(ip)
        assert self.guard.is_locked(ip)

        # Simulate time passing beyond lockout
        rec = self.guard._records[ip]
        rec.locked_until = time.time() - 1

        assert not self.guard.is_locked(ip)

    def test_expired_lockout_resets_failures(self):
        ip = "10.0.0.8"
        for _ in range(MAX_ATTEMPTS):
            self.guard.record_failure(ip)

        # Expire the lockout
        rec = self.guard._records[ip]
        rec.locked_until = time.time() - 1
        self.guard.is_locked(ip)  # triggers reset

        # Should need full MAX_ATTEMPTS again to lock
        for _ in range(MAX_ATTEMPTS - 1):
            self.guard.record_failure(ip)
        assert not self.guard.is_locked(ip)

"""Brute-force protection for login endpoints.

Tracks failed login attempts per IP and locks out after threshold.
"""
import threading
import time
import logging
from dataclasses import dataclass, field
from typing import Dict

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5           # Lock after this many consecutive failures
LOCKOUT_SECONDS = 900      # 15 minutes lockout
CLEANUP_INTERVAL = 300     # Clean stale entries every 5 minutes


@dataclass
class _IPRecord:
    failures: int = 0
    locked_until: float = 0.0
    last_attempt: float = field(default_factory=time.time)


class LoginGuard:
    """In-memory per-IP brute-force protection."""

    def __init__(self):
        self._records: Dict[str, _IPRecord] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

    def is_locked(self, ip: str) -> bool:
        """Check if IP is currently locked out."""
        with self._lock:
            rec = self._records.get(ip)
            if not rec:
                return False
            if rec.locked_until > time.time():
                return True
            # Lockout expired — reset
            if rec.locked_until > 0:
                rec.failures = 0
                rec.locked_until = 0.0
            return False

    def remaining_seconds(self, ip: str) -> int:
        """Get remaining lockout seconds for an IP (0 if not locked)."""
        with self._lock:
            rec = self._records.get(ip)
            if not rec:
                return 0
            remaining = rec.locked_until - time.time()
            return max(0, int(remaining))

    def record_failure(self, ip: str) -> bool:
        """Record a failed login attempt. Returns True if IP is now locked."""
        with self._lock:
            self._maybe_cleanup()
            rec = self._records.get(ip)
            if not rec:
                rec = _IPRecord()
                self._records[ip] = rec

            rec.failures += 1
            rec.last_attempt = time.time()

            if rec.failures >= MAX_ATTEMPTS:
                rec.locked_until = time.time() + LOCKOUT_SECONDS
                logger.warning(
                    "IP %s locked out for %ds after %d failed login attempts",
                    ip, LOCKOUT_SECONDS, rec.failures,
                )
                return True
            return False

    def record_success(self, ip: str) -> None:
        """Reset failure counter on successful login."""
        with self._lock:
            self._records.pop(ip, None)

    def _maybe_cleanup(self) -> None:
        """Remove stale entries (called under lock)."""
        now = time.time()
        if now - self._last_cleanup < CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        stale = [
            ip for ip, rec in self._records.items()
            if rec.locked_until < now and now - rec.last_attempt > LOCKOUT_SECONDS
        ]
        for ip in stale:
            del self._records[ip]


login_guard = LoginGuard()

"""In-memory token blacklist with TTL-based expiration."""
import threading
import time
from typing import Dict


class TokenBlacklist:
    """
    Thread-safe in-memory token blacklist.

    Tokens are stored with their expiry time and automatically
    cleaned up when they would have expired anyway.
    """

    def __init__(self):
        self._blacklist: Dict[str, float] = {}  # token_jti -> expiry_timestamp
        self._lock = threading.Lock()
        self._cleanup_interval = 300  # cleanup every 5 minutes
        self._last_cleanup = time.time()

    def add(self, token: str, expires_at: float) -> None:
        """
        Add a token to the blacklist.

        Args:
            token: The JWT token string (or its jti)
            expires_at: Unix timestamp when the token expires naturally
        """
        with self._lock:
            self._blacklist[token] = expires_at
            self._maybe_cleanup()

    def is_blacklisted(self, token: str) -> bool:
        """
        Check if a token is blacklisted.

        Args:
            token: The JWT token string (or its jti)

        Returns:
            True if the token is blacklisted
        """
        with self._lock:
            if token not in self._blacklist:
                return False
            # Check if the entry has expired (token would be invalid anyway)
            if self._blacklist[token] < time.time():
                del self._blacklist[token]
                return False
            return True

    def _maybe_cleanup(self) -> None:
        """Remove expired entries periodically (called under lock)."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now
        expired = [k for k, v in self._blacklist.items() if v < now]
        for k in expired:
            del self._blacklist[k]


token_blacklist = TokenBlacklist()

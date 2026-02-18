"""Redis-backed cache service with in-memory fallback.

If REDIS_URL is configured, uses Redis for distributed caching.
Otherwise, falls back to a simple in-memory TTL cache.
"""
import asyncio
import json
import logging
import time
from functools import wraps
from typing import Any, Optional

logger = logging.getLogger(__name__)

# TTL presets (seconds)
CACHE_TTL_SHORT = 30       # overview, fleet, system components
CACHE_TTL_MEDIUM = 60      # traffic, timeseries, deltas
CACHE_TTL_LONG = 300       # geo, trends, top-users


class _InMemoryCache:
    """Simple in-memory TTL cache (fallback when Redis is unavailable)."""

    def __init__(self):
        self._store: dict[str, tuple[float, str]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: str, ex: int = 60) -> None:
        async with self._lock:
            self._store[key] = (time.monotonic() + ex, value)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def flush_pattern(self, pattern: str) -> int:
        """Delete keys matching a glob pattern (simple prefix match)."""
        prefix = pattern.rstrip("*")
        async with self._lock:
            to_delete = [k for k in self._store if k.startswith(prefix)]
            for k in to_delete:
                del self._store[k]
            return len(to_delete)

    async def close(self) -> None:
        self._store.clear()


class CacheService:
    """Unified cache interface: Redis if available, in-memory otherwise."""

    def __init__(self):
        self._redis = None
        self._fallback = _InMemoryCache()
        self._using_redis = False

    async def connect(self, redis_url: Optional[str] = None) -> bool:
        """Try to connect to Redis. Returns True if successful."""
        if not redis_url:
            logger.info("No REDIS_URL configured, using in-memory cache")
            return False
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            await self._redis.ping()
            self._using_redis = True
            logger.info("Redis cache connected: %s", redis_url.split("@")[-1])
            return True
        except Exception as e:
            logger.warning("Redis connection failed (%s), using in-memory cache", e)
            self._redis = None
            self._using_redis = False
            return False

    async def get(self, key: str) -> Optional[str]:
        if self._using_redis:
            try:
                return await self._redis.get(key)
            except Exception as e:
                logger.debug("Redis GET failed for key %s: %s", key, e)
        return await self._fallback.get(key)

    async def set(self, key: str, value: str, ex: int = 60) -> None:
        if self._using_redis:
            try:
                await self._redis.set(key, value, ex=ex)
                return
            except Exception as e:
                logger.debug("Redis SET failed for key %s: %s", key, e)
        await self._fallback.set(key, value, ex=ex)

    async def delete(self, key: str) -> None:
        if self._using_redis:
            try:
                await self._redis.delete(key)
                return
            except Exception as e:
                logger.debug("Redis DELETE failed for key %s: %s", key, e)
        await self._fallback.delete(key)

    async def flush_pattern(self, pattern: str) -> int:
        """Delete keys matching a glob pattern."""
        if self._using_redis:
            try:
                keys = []
                async for key in self._redis.scan_iter(match=pattern, count=100):
                    keys.append(key)
                if keys:
                    await self._redis.delete(*keys)
                return len(keys)
            except Exception as e:
                logger.debug("Redis flush_pattern failed for %s: %s", pattern, e)
        return await self._fallback.flush_pattern(pattern)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
        await self._fallback.close()

    @property
    def is_redis(self) -> bool:
        return self._using_redis

    # ── JSON helpers ──────────────────────────────────────────

    async def get_json(self, key: str) -> Optional[Any]:
        raw = await self.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set_json(self, key: str, value: Any, ex: int = 60) -> None:
        await self.set(key, json.dumps(value, default=str), ex=ex)


# Singleton
cache = CacheService()


def cached(prefix: str, ttl: int = CACHE_TTL_MEDIUM, key_args: tuple = ()):
    """Decorator for caching async endpoint results.

    Usage:
        @cached("analytics:overview", ttl=30)
        async def get_overview(...): ...

        @cached("analytics:timeseries", ttl=60, key_args=("period", "metric"))
        async def get_timeseries(period, metric, ...): ...
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            # Build cache key from prefix + selected kwargs
            parts = [prefix]
            for arg_name in key_args:
                val = kwargs.get(arg_name, "")
                parts.append(f"{arg_name}={val}")
            cache_key = ":".join(parts)

            # Try cache first
            cached_val = await cache.get_json(cache_key)
            if cached_val is not None:
                return cached_val

            # Call the original function
            result = await fn(*args, **kwargs)

            # Serialize: if result is a Pydantic model, convert to dict
            to_cache = result
            if hasattr(result, "model_dump"):
                to_cache = result.model_dump()
            elif hasattr(result, "dict"):
                to_cache = result.dict()

            await cache.set_json(cache_key, to_cache, ex=ttl)
            return result

        return wrapper
    return decorator

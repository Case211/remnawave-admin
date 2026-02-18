"""Tests for CacheService — in-memory cache, Redis fallback, and @cached decorator."""
import asyncio
import json
import time

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from web.backend.core.cache import (
    _InMemoryCache,
    CacheService,
    cached,
    CACHE_TTL_SHORT,
    CACHE_TTL_MEDIUM,
    CACHE_TTL_LONG,
)


# ── TTL Constants ────────────────────────────────────────────


class TestCacheTTLConstants:
    def test_short(self):
        assert CACHE_TTL_SHORT == 30

    def test_medium(self):
        assert CACHE_TTL_MEDIUM == 60

    def test_long(self):
        assert CACHE_TTL_LONG == 300


# ── _InMemoryCache ───────────────────────────────────────────


class TestInMemoryCache:
    """Tests for the in-memory TTL cache fallback."""

    @pytest.fixture()
    def mem_cache(self):
        return _InMemoryCache()

    @pytest.mark.asyncio
    async def test_set_and_get(self, mem_cache):
        await mem_cache.set("key1", "value1", ex=60)
        result = await mem_cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, mem_cache):
        result = await mem_cache.get("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_expired_entry_returns_none(self, mem_cache):
        await mem_cache.set("key1", "value1", ex=0)
        # Wait a tiny bit for monotonic clock to advance
        await asyncio.sleep(0.01)
        result = await mem_cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, mem_cache):
        await mem_cache.set("key1", "value1")
        await mem_cache.delete("key1")
        assert await mem_cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_no_error(self, mem_cache):
        await mem_cache.delete("missing")

    @pytest.mark.asyncio
    async def test_flush_pattern(self, mem_cache):
        await mem_cache.set("analytics:overview", "v1")
        await mem_cache.set("analytics:timeseries", "v2")
        await mem_cache.set("users:list", "v3")

        count = await mem_cache.flush_pattern("analytics:*")
        assert count == 2
        assert await mem_cache.get("analytics:overview") is None
        assert await mem_cache.get("users:list") == "v3"

    @pytest.mark.asyncio
    async def test_close_clears_store(self, mem_cache):
        await mem_cache.set("key1", "value1")
        await mem_cache.close()
        assert await mem_cache.get("key1") is None


# ── CacheService ─────────────────────────────────────────────


class TestCacheService:
    """Tests for CacheService with in-memory fallback."""

    @pytest.fixture()
    def svc(self):
        return CacheService()

    @pytest.mark.asyncio
    async def test_connect_none_returns_false(self, svc):
        result = await svc.connect(None)
        assert result is False
        assert svc.is_redis is False

    @pytest.mark.asyncio
    async def test_get_set_without_redis(self, svc):
        await svc.connect(None)
        await svc.set("key", "val", ex=60)
        result = await svc.get("key")
        assert result == "val"

    @pytest.mark.asyncio
    async def test_delete_without_redis(self, svc):
        await svc.connect(None)
        await svc.set("key", "val")
        await svc.delete("key")
        assert await svc.get("key") is None

    @pytest.mark.asyncio
    async def test_get_json_set_json(self, svc):
        await svc.connect(None)
        data = {"users": [1, 2, 3], "total": 3}
        await svc.set_json("data:key", data, ex=60)
        result = await svc.get_json("data:key")
        assert result == data

    @pytest.mark.asyncio
    async def test_get_json_nonexistent(self, svc):
        await svc.connect(None)
        assert await svc.get_json("missing") is None

    @pytest.mark.asyncio
    async def test_flush_pattern_without_redis(self, svc):
        await svc.connect(None)
        await svc.set("a:1", "v1")
        await svc.set("a:2", "v2")
        await svc.set("b:1", "v3")
        count = await svc.flush_pattern("a:*")
        assert count == 2

    @pytest.mark.asyncio
    async def test_redis_get_error_falls_back(self, svc):
        """When Redis GET fails, falls back to in-memory."""
        svc._using_redis = True
        svc._redis = AsyncMock()
        svc._redis.get = AsyncMock(side_effect=Exception("redis down"))

        # Set in fallback
        await svc._fallback.set("key", "fallback-val", ex=60)

        result = await svc.get("key")
        assert result == "fallback-val"

    @pytest.mark.asyncio
    async def test_redis_set_error_falls_back(self, svc):
        """When Redis SET fails, falls back to in-memory."""
        svc._using_redis = True
        svc._redis = AsyncMock()
        svc._redis.set = AsyncMock(side_effect=Exception("redis down"))

        await svc.set("key", "val", ex=60)
        # Should be in fallback
        result = await svc._fallback.get("key")
        assert result == "val"

    @pytest.mark.asyncio
    async def test_close(self, svc):
        await svc.connect(None)
        await svc.set("key", "val")
        await svc.close()


# ── @cached decorator ────────────────────────────────────────


class TestCachedDecorator:
    """Tests for the @cached decorator."""

    @pytest.mark.asyncio
    async def test_cache_miss_calls_function(self):
        call_count = 0

        @cached("test:prefix", ttl=60)
        async def my_func():
            nonlocal call_count
            call_count += 1
            return {"result": 42}

        result = await my_func()
        assert result == {"result": 42}
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_cache_hit_skips_function(self):
        call_count = 0

        @cached("test:hit", ttl=60)
        async def my_func():
            nonlocal call_count
            call_count += 1
            return {"result": 42}

        await my_func()
        await my_func()
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_key_args_differentiate_calls(self):
        call_count = 0

        @cached("test:args", ttl=60, key_args=("period",))
        async def my_func(period="day"):
            nonlocal call_count
            call_count += 1
            return {"period": period}

        await my_func(period="day")
        await my_func(period="week")
        assert call_count == 2

        # Same period again → cache hit
        await my_func(period="day")
        assert call_count == 2

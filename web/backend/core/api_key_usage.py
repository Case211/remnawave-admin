"""Buffered last_used_at updates for API keys.

Avoids UPDATE-per-request row lock under high RPS. Collects "key used" events
in memory and flushes to DB every N seconds.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL_SEC = float(os.getenv("API_KEY_LAST_USED_FLUSH_SEC", "30"))

_pending: dict[int, float] = {}
# Запросы ключей: (key_id, method, path, status, ip, duration_ms, ts)
_requests: list[tuple] = []
_REQUESTS_BUFFER_MAX = 5000
# Сколько запросов на ключ держать в журнале
REQUESTS_KEEP_PER_KEY = 500
_lock = asyncio.Lock()
_flush_task: Optional[asyncio.Task] = None
_stop = asyncio.Event()


async def mark_used(key_id: int) -> None:
    """Record that a key was used. Flushed asynchronously."""
    async with _lock:
        import time
        _pending[key_id] = time.time()


def record_request(key_id: int, method: str, path: str, status: int,
                   ip: Optional[str], duration_ms: int) -> None:
    """Запомнить запрос ключа; в базу уходит пачкой при сбросе."""
    import time
    if len(_requests) < _REQUESTS_BUFFER_MAX:
        _requests.append((key_id, method, path[:500], status, ip, duration_ms, time.time()))


async def _flush_requests() -> None:
    if not _requests:
        return
    batch = list(_requests)
    _requests.clear()
    try:
        from datetime import datetime, timezone
        from shared.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            await conn.executemany(
                "INSERT INTO api_key_requests (key_id, method, path, status_code, ip_address, duration_ms, created_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                [(k, m, p, s, ip, d, datetime.fromtimestamp(ts, tz=timezone.utc)) for k, m, p, s, ip, d, ts in batch],
            )
            await conn.execute(
                "DELETE FROM api_key_requests r USING ("
                "  SELECT id FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY key_id ORDER BY id DESC) AS rn "
                "  FROM api_key_requests WHERE key_id = ANY($1::int[])) x WHERE rn > $2"
                ") old WHERE r.id = old.id",
                list({b[0] for b in batch}), REQUESTS_KEEP_PER_KEY,
            )
    except Exception as e:
        logger.warning("Failed to flush API key requests: %s", e)


async def _flush() -> None:
    await _flush_requests()
    async with _lock:
        if not _pending:
            return
        snapshot = dict(_pending)
        _pending.clear()
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            for key_id, ts in snapshot.items():
                from datetime import datetime, timezone
                await conn.execute(
                    "UPDATE api_keys SET last_used_at = $2 WHERE id = $1",
                    key_id, datetime.fromtimestamp(ts, tz=timezone.utc),
                )
    except Exception as e:
        logger.warning("Failed to flush API key last_used_at: %s", e)


async def _loop() -> None:
    logger.debug("API key usage buffer started (interval=%ss)", _FLUSH_INTERVAL_SEC)
    while not _stop.is_set():
        try:
            await asyncio.wait_for(_stop.wait(), timeout=_FLUSH_INTERVAL_SEC)
        except asyncio.TimeoutError:
            pass
        await _flush()
    await _flush()
    logger.info("API key usage buffer stopped")


def start() -> None:
    global _flush_task
    if _flush_task and not _flush_task.done():
        return
    _stop.clear()
    _flush_task = asyncio.create_task(_loop(), name="api-key-usage-flush")


async def stop() -> None:
    _stop.set()
    if _flush_task:
        try:
            await asyncio.wait_for(_flush_task, timeout=5)
        except asyncio.TimeoutError:
            _flush_task.cancel()

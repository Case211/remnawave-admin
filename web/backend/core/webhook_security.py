"""Webhook security helpers: SSRF protection, HMAC v1/v2, retry queue.

- `check_url_safety(url)` — rejects private IP ranges to prevent SSRF.
- `sign_payload(secret, body, version)` — HMAC-SHA256, v2 prepends timestamp.
- `webhook_retry_worker()` — background task consuming webhook_retry_queue.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import socket
import time
from typing import Optional, Tuple
from urllib.parse import urlparse

from shared.db_schema import WEBHOOK_DELIVERIES_TABLE, WEBHOOK_SUBSCRIPTIONS_TABLE, WEBHOOK_RETRY_QUEUE_TABLE
from shared.db_query import select_sql, insert_sql, update_sql

import httpx

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────

WEBHOOK_TIMEOUT_SEC = float(os.getenv("WEBHOOK_TIMEOUT_SEC", "10"))
WEBHOOK_MAX_ATTEMPTS = int(os.getenv("WEBHOOK_MAX_ATTEMPTS", "3"))
WEBHOOK_AUTO_DISABLE_AFTER = int(os.getenv("WEBHOOK_AUTO_DISABLE_AFTER", "50"))
WEBHOOK_BACKOFF_SECONDS = [60, 300, 1500]  # 1m, 5m, 25m
WEBHOOK_RETRY_WORKER_INTERVAL = float(os.getenv("WEBHOOK_RETRY_WORKER_INTERVAL", "10"))
WEBHOOK_ALLOW_PRIVATE_URL = os.getenv("WEBHOOK_ALLOW_PRIVATE_URL", "0") == "1"
WEBHOOK_SIGNATURE_TOLERANCE_SEC = 300  # documented replay window

# ── SSRF protection ──────────────────────────────────────────────

_PRIVATE_NETWORKS = [
    ipaddress.ip_network(n) for n in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "127.0.0.0/8", "169.254.0.0/16", "::1/128", "fc00::/7", "fe80::/10",
    )
]


def check_url_safety(url: str) -> Tuple[bool, Optional[str]]:
    """Validate a webhook URL. Returns (ok, error_message)."""
    if not url:
        return False, "URL is empty"
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Malformed URL: {e}"
    if parsed.scheme not in ("http", "https"):
        return False, "URL must use http or https"
    if not parsed.hostname:
        return False, "URL has no host"
    if WEBHOOK_ALLOW_PRIVATE_URL:
        return True, None

    host = parsed.hostname
    try:
        ipaddress.ip_address(host)
        hosts_to_check = [host]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
            hosts_to_check = list({info[4][0] for info in infos})
        except socket.gaierror as e:
            return False, f"Cannot resolve host: {e}"

    for h in hosts_to_check:
        try:
            addr = ipaddress.ip_address(h)
        except ValueError:
            continue
        for net in _PRIVATE_NETWORKS:
            if addr in net:
                return False, f"URL resolves to private address {addr}"
    return True, None


# ── HMAC ─────────────────────────────────────────────────────────

def sign_payload(secret: str, body: str, version: str = "v1") -> Tuple[dict, int]:
    """Compute webhook signature headers.

    v1 (legacy): sha256(secret, body)
    v2: sha256(secret, f"{timestamp}.{body}") + X-Webhook-Timestamp header

    Returns (headers_dict, timestamp).
    """
    ts = int(time.time())
    if version == "v2":
        signed = f"{ts}.{body}".encode()
        sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
        return (
            {
                "X-Webhook-Signature": f"sha256={sig}",
                "X-Webhook-Timestamp": str(ts),
                "X-Webhook-Signature-Version": "v2",
            },
            ts,
        )
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return ({"X-Webhook-Signature": f"sha256={sig}"}, ts)


# ── Delivery + retry queue ───────────────────────────────────────

async def _log_delivery(
    webhook_id: int,
    event: str,
    status_code: int,
    response_body: Optional[str],
    error: Optional[str],
    duration_ms: int,
) -> None:
    """Persist a delivery attempt. Best-effort — never raises."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            await conn.execute(
                insert_sql(WEBHOOK_DELIVERIES_TABLE,
                    ["webhook_id", "event", "status_code", "response_body", "error", "duration_ms"]),
                webhook_id, event, status_code,
                (response_body[:5000] if response_body else None),
                (error[:500] if error else None),
                duration_ms,
            )
            await conn.execute(
                f"DELETE FROM {WEBHOOK_DELIVERIES_TABLE} WHERE webhook_id = $1 "
                f"AND id NOT IN (SELECT id FROM {WEBHOOK_DELIVERIES_TABLE} "
                f"WHERE webhook_id = $1 ORDER BY sent_at DESC LIMIT 200)",
                webhook_id,
            )
    except Exception as e:
        logger.warning("Failed to log webhook delivery %d: %s", webhook_id, e)


async def _bump_failure(webhook_id: int) -> bool:
    """Increment consecutive_failures + failure_count. Auto-disables on threshold.

    Returns True if webhook was auto-disabled now.
    """
    from shared.database import db_service
    if not db_service.is_connected:
        return False
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            update_sql(WEBHOOK_SUBSCRIPTIONS_TABLE,
                "failure_count = failure_count + 1, consecutive_failures = consecutive_failures + 1",
                "id = $1", returning="consecutive_failures, is_active"),
            webhook_id,
        )
        if not row:
            return False
        if row["is_active"] and row["consecutive_failures"] >= WEBHOOK_AUTO_DISABLE_AFTER:
            await conn.execute(
                update_sql(WEBHOOK_SUBSCRIPTIONS_TABLE,
                    "is_active = false, auto_disabled_at = NOW(), disabled_reason = $2",
                    "id = $1"),
                webhook_id,
                f"Auto-disabled after {WEBHOOK_AUTO_DISABLE_AFTER} consecutive failures",
            )
            logger.warning("Webhook %d auto-disabled after repeated failures", webhook_id)
            return True
    return False


async def _mark_success(webhook_id: int) -> None:
    from shared.database import db_service
    if not db_service.is_connected:
        return
    async with db_service.acquire() as conn:
        await conn.execute(
            update_sql(WEBHOOK_SUBSCRIPTIONS_TABLE,
                "last_triggered_at = NOW(), consecutive_failures = 0",
                "id = $1"),
            webhook_id,
        )


async def _enqueue_retry(
    webhook_id: int, event: str, payload: dict, attempt: int, error: str,
) -> None:
    """Schedule a retry. attempt is the one that just failed (1-based)."""
    if attempt >= WEBHOOK_MAX_ATTEMPTS:
        return
    delay = WEBHOOK_BACKOFF_SECONDS[min(attempt - 1, len(WEBHOOK_BACKOFF_SECONDS) - 1)]
    from shared.database import db_service
    if not db_service.is_connected:
        return
    async with db_service.acquire() as conn:
        await conn.execute(
            insert_sql(WEBHOOK_RETRY_QUEUE_TABLE,
                ["webhook_id", "event", "payload", "attempt", "max_attempts", "next_try_at", "last_error"],
                values="$1, $2, $3::jsonb, $4, $5, NOW() + ($6 || ' seconds')::interval, $7"),
            webhook_id, event, json.dumps(payload, default=str),
            attempt + 1, WEBHOOK_MAX_ATTEMPTS, str(delay), error[:500],
        )


async def deliver_once(
    webhook_id: int, url: str, secret: Optional[str], signature_version: str,
    event: str, payload: dict,
) -> Tuple[bool, int, Optional[str], Optional[str], int]:
    """Execute one HTTP attempt. Returns (success, status_code, response_body, error, duration_ms)."""
    body = json.dumps({"event": event, "data": payload}, default=str)
    headers = {"Content-Type": "application/json", "X-Webhook-Event": event}
    if secret:
        sig_headers, _ = sign_payload(secret, body, signature_version or "v1")
        headers.update(sig_headers)

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SEC) as hc:
            resp = await hc.post(url, content=body, headers=headers)
        elapsed = int((time.perf_counter() - start) * 1000)
        return (
            resp.is_success,
            resp.status_code,
            resp.text if resp.text else None,
            None,
            elapsed,
        )
    except Exception as e:
        elapsed = int((time.perf_counter() - start) * 1000)
        return (False, 0, None, str(e)[:500], elapsed)


# Держим ссылки на fire-and-forget таски, иначе GC может убить их на лету
_fire_tasks: set = set()


def fire_event(event: str, payload: dict) -> None:
    """Fire-and-forget диспатч события: не блокирует вызывающий код
    (HTTP-хендлер, пайплайн коллектора) на время доставки вебхуков.

    Безопасен в любом async-контексте; если активных подписок на событие
    нет — dispatch_event выходит после одного SELECT.
    """
    try:
        task = asyncio.get_running_loop().create_task(dispatch_event(event, payload))
        _fire_tasks.add(task)
        task.add_done_callback(_fire_tasks.discard)
    except RuntimeError:
        # Нет running loop (синхронный контекст) — событие пропускаем,
        # это вспомогательный канал, ронять вызывающий код нельзя.
        logger.warning("fire_event(%s) skipped: no running event loop", event)


async def dispatch_event(event: str, payload: dict) -> None:
    """Fan out an event to all active subscriptions. First attempt synchronous;
    failures enqueue to webhook_retry_queue.
    """
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(WEBHOOK_SUBSCRIPTIONS_TABLE,
                    "id, url, secret, signature_version",
                    "WHERE is_active = true AND $1 = ANY(events)"),
                event,
            )
        if not rows:
            return

        tasks = [
            _attempt_and_handle(
                r["id"], r["url"], r["secret"],
                r["signature_version"] or "v1", event, payload, attempt=1,
            )
            for r in rows
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logger.error("dispatch_event failed: %s", e)


async def _attempt_and_handle(
    webhook_id: int, url: str, secret: Optional[str], signature_version: str,
    event: str, payload: dict, attempt: int,
) -> None:
    ok, status_code, response_body, error, elapsed = await deliver_once(
        webhook_id, url, secret, signature_version, event, payload,
    )
    await _log_delivery(webhook_id, event, status_code, response_body, error, elapsed)
    if ok:
        await _mark_success(webhook_id)
        return
    logger.warning(
        "Webhook %d attempt %d failed (status=%s, error=%s)",
        webhook_id, attempt, status_code, error,
    )
    disabled = await _bump_failure(webhook_id)
    if disabled:
        return
    err_str = error or f"HTTP {status_code}"
    await _enqueue_retry(webhook_id, event, payload, attempt, err_str)


# ── Retry worker ─────────────────────────────────────────────────

_worker_task: Optional[asyncio.Task] = None
_worker_stop = asyncio.Event()


async def _process_retry_batch() -> int:
    """Pull due retries and attempt delivery. Returns number processed."""
    from shared.database import db_service
    if not db_service.is_connected:
        return 0
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            f"""
            DELETE FROM {WEBHOOK_RETRY_QUEUE_TABLE}
            WHERE id IN (
                SELECT id FROM {WEBHOOK_RETRY_QUEUE_TABLE}
                WHERE next_try_at <= NOW()
                ORDER BY next_try_at ASC
                LIMIT 20
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, webhook_id, event, payload, attempt, max_attempts
            """
        )
    if not rows:
        return 0

    async def _one(row):
        webhook_id = row["webhook_id"]
        async with db_service.acquire() as conn:
            wh = await conn.fetchrow(
                select_sql(WEBHOOK_SUBSCRIPTIONS_TABLE,
                    "url, secret, signature_version, is_active",
                    "WHERE id = $1"),
                webhook_id,
            )
        if not wh or not wh["is_active"]:
            return
        try:
            payload = json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
        except Exception:
            payload = {}
        await _attempt_and_handle(
            webhook_id, wh["url"], wh["secret"],
            wh["signature_version"] or "v1",
            row["event"], payload, attempt=row["attempt"],
        )

    await asyncio.gather(*(_one(r) for r in rows), return_exceptions=True)
    return len(rows)


async def _worker_loop() -> None:
    logger.info("Webhook retry worker started (interval=%ss)", WEBHOOK_RETRY_WORKER_INTERVAL)
    while not _worker_stop.is_set():
        try:
            await _process_retry_batch()
        except Exception as e:
            logger.exception("Retry worker iteration failed: %s", e)
        try:
            await asyncio.wait_for(_worker_stop.wait(), timeout=WEBHOOK_RETRY_WORKER_INTERVAL)
        except asyncio.TimeoutError:
            pass
    logger.info("Webhook retry worker stopped")


def start_retry_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _worker_stop.clear()
    _worker_task = asyncio.create_task(_worker_loop(), name="webhook-retry-worker")


async def stop_retry_worker() -> None:
    _worker_stop.set()
    if _worker_task:
        try:
            await asyncio.wait_for(_worker_task, timeout=5)
        except asyncio.TimeoutError:
            _worker_task.cancel()

"""Prometheus metrics for the web backend.

Exports a `/metrics` endpoint (text format 0.0.4) for external scrape
by Prometheus / VictoriaMetrics. Includes HTTP middleware metrics and
panel-specific gauges refreshed by a background updater.

Cardinality note: HTTP path label uses the route *pattern* (e.g.
`/api/v2/users/{user_id}`) — never the raw URL — so user UUIDs and
similar IDs don't blow up label sets.

Counters fired from app code (collector, violation pipeline, etc.) are
defined here too; just `import ... from web.backend.core.metrics` and
call `.inc()` / `.labels(...).inc()`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ── HTTP metrics ─────────────────────────────────────────────────

HTTP_REQUESTS_TOTAL = Counter(
    "panel_http_requests_total",
    "Total HTTP requests handled by the panel backend.",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "panel_http_request_duration_seconds",
    "HTTP request handling latency in seconds.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "panel_http_requests_in_progress",
    "Number of HTTP requests currently being processed.",
    ["method"],
)

# ── Panel-state gauges (refreshed by updater) ────────────────────

PANEL_ONLINE_USERS = Gauge(
    "panel_online_users",
    "Unique users seen in user_connections in the last 2 minutes.",
)

PANEL_TOTAL_USERS = Gauge(
    "panel_total_users",
    "Total users in panel DB.",
)

PANEL_ACTIVE_USERS = Gauge(
    "panel_active_users",
    "Users with status='ACTIVE'.",
)

PANEL_TOTAL_NODES = Gauge(
    "panel_total_nodes",
    "Total nodes in panel DB.",
)

PANEL_ONLINE_NODES = Gauge(
    "panel_online_nodes",
    "Nodes that are connected and not disabled.",
)

PANEL_VIOLATIONS_OPEN = Gauge(
    "panel_violations_open",
    "Violations with status='ACTIVE'.",
)

PANEL_DB_POOL_SIZE = Gauge(
    "panel_db_pool_size",
    "Configured PostgreSQL pool size.",
)

PANEL_DB_POOL_USED = Gauge(
    "panel_db_pool_used",
    "Currently checked-out connections from the PostgreSQL pool.",
)

# ── App event counters ───────────────────────────────────────────
# These are imported and incremented by the relevant subsystems.

COLLECTOR_BATCHES_RECEIVED = Counter(
    "panel_collector_batches_received_total",
    "Total node-agent batches accepted by /collector/batch.",
)

COLLECTOR_BATCHES_REJECTED = Counter(
    "panel_collector_batches_rejected_total",
    "Total node-agent batches rejected (rate limit, auth, malformed).",
    ["reason"],
)

VIOLATIONS_DETECTED = Counter(
    "panel_violations_detected_total",
    "Violations detected by the pipeline.",
    ["severity"],
)

NOTIFICATIONS_SENT = Counter(
    "panel_notifications_sent_total",
    "Notifications dispatched.",
    ["channel"],
)


# ── HTTP middleware ──────────────────────────────────────────────


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records HTTP RPS / latency / in-flight for every matched route."""

    async def dispatch(self, request: Request, call_next):
        method = request.method
        HTTP_REQUESTS_IN_PROGRESS.labels(method=method).inc()
        start = time.perf_counter()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            raise
        finally:
            duration = time.perf_counter() - start
            HTTP_REQUESTS_IN_PROGRESS.labels(method=method).dec()
            path = _route_template(request)
            HTTP_REQUESTS_TOTAL.labels(
                method=method, path=path, status=str(status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method, path=path,
            ).observe(duration)


def _route_template(request: Request) -> str:
    """Return the route pattern (e.g. /api/v2/users/{user_id}) or 'other'.

    Using the raw URL would create a label per user UUID and explode cardinality.
    """
    route = request.scope.get("route")
    if route is None:
        # Unmatched URL or middleware ran before routing — collapse to a constant.
        return "other"
    path = getattr(route, "path", None) or getattr(route, "path_format", None)
    return path or "other"


# ── /metrics endpoint helpers ────────────────────────────────────


def metrics_auth_token() -> Optional[str]:
    token = os.getenv("METRICS_AUTH_TOKEN", "").strip()
    return token or None


def render_metrics() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics response."""
    return generate_latest(), CONTENT_TYPE_LATEST


# ── Background gauge updater ─────────────────────────────────────


class GaugeUpdater:
    """Periodically refreshes panel_* gauges from the database."""

    def __init__(self, interval_seconds: int = 15):
        self.interval = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Prometheus gauge updater started (every %ds)", self.interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Prometheus gauge updater stopped")

    async def _loop(self) -> None:
        # initial small delay so DB warms up
        await asyncio.sleep(5)
        while self._running:
            try:
                await self._refresh()
            except Exception as e:
                logger.warning("Gauge refresh failed: %s", e)
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break

    async def _refresh(self) -> None:
        from shared.database import db_service
        if not db_service.is_connected:
            return

        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(DISTINCT user_uuid) FROM user_connections
                     WHERE user_uuid IS NOT NULL
                       AND connected_at >= NOW() - INTERVAL '2 minutes'
                    ) AS online_users,
                    (SELECT COUNT(*) FROM users) AS total_users,
                    (SELECT COUNT(*) FROM users WHERE UPPER(status) = 'ACTIVE') AS active_users,
                    (SELECT COUNT(*) FROM nodes) AS total_nodes,
                    (SELECT COUNT(*) FROM nodes
                     WHERE is_connected = true AND NOT is_disabled
                    ) AS online_nodes,
                    (SELECT COUNT(*) FROM violations
                     WHERE COALESCE(status, 'ACTIVE') = 'ACTIVE'
                    ) AS violations_open
                """
            )

        if row:
            PANEL_ONLINE_USERS.set(int(row["online_users"] or 0))
            PANEL_TOTAL_USERS.set(int(row["total_users"] or 0))
            PANEL_ACTIVE_USERS.set(int(row["active_users"] or 0))
            PANEL_TOTAL_NODES.set(int(row["total_nodes"] or 0))
            PANEL_ONLINE_NODES.set(int(row["online_nodes"] or 0))
            PANEL_VIOLATIONS_OPEN.set(int(row["violations_open"] or 0))

        # asyncpg pool stats
        pool = getattr(db_service, "_pool", None) or getattr(db_service, "pool", None)
        if pool is not None:
            try:
                size = pool.get_size()
                idle = pool.get_idle_size()
                PANEL_DB_POOL_SIZE.set(int(size))
                PANEL_DB_POOL_USED.set(int(max(0, size - idle)))
            except Exception:
                pass


gauge_updater = GaugeUpdater()

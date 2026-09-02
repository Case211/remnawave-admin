"""
Collector API для приёма данных о подключениях от Node Agent.

Endpoint: POST /batch
Аутентификация: Bearer token (токен агента из таблицы nodes.agent_token)
"""
import asyncio
import hashlib
import hmac as hmac_mod
import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from shared.database import db_service
from shared.db_schema import NODES_TABLE
from web.backend.core import torrent_p2p_whitelist
from shared.db_query import select_sql
from shared.connection_monitor import ConnectionMonitor
from shared.violation_detector import IntelligentViolationDetector
from shared.agent_tokens import get_node_by_token
from shared.config_service import config_service
from shared.metrics import (
    COLLECTOR_BATCHES_RECEIVED,
    COLLECTOR_BATCHES_REJECTED,
    COLLECTOR_CONNECTIONS_PROCESSED,
)
from web.backend.core.webhook_security import fire_event

logger = logging.getLogger(__name__)


async def _resolve_user_key(user_uuid: str) -> str | int:
    """Resolve a local user uuid to the identifier the Panel API expects."""
    from shared.data_access import resolve_panel_user_id
    return await resolve_panel_user_id(user_uuid)

# Инициализируем сервисы (синглтоны на уровне модуля)
connection_monitor = ConnectionMonitor(db_service)
violation_detector = IntelligentViolationDetector(db_service, connection_monitor)

# Per-user cooldown for violation checks (avoid re-checking every 30s batch)
_violation_check_cooldown: dict[str, datetime] = {}
_cooldown_lock = asyncio.Lock()
VIOLATION_CHECK_COOLDOWN_MINUTES = 15
MAX_COOLDOWN_SIZE = 100000

# Periodic cleanup of old violations
_last_violation_cleanup: datetime = datetime.min

# Periodic cleanup of old metrics snapshots and connections
_last_metrics_cleanup: datetime = datetime.min
CLEANUP_INTERVAL_HOURS = 24
METRICS_RETENTION_DAYS = 30
CONNECTIONS_RETENTION_DAYS = 30

# Semaphore: limit concurrent background violation detection batches
_violation_semaphore = asyncio.Semaphore(3)

# ── Violation detection queue ──────────────────────────────
# Instead of spawning a task per batch, accumulate user UUIDs in a set
# and drain them in a single background worker. No data is ever dropped.
_pending_violation_users: set = set()
_violation_worker_task: Optional[asyncio.Task] = None
_VIOLATION_DRAIN_INTERVAL = 3.0  # seconds between drain cycles
_VIOLATION_CHUNK_SIZE = 200      # max users per drain cycle

# ── Queue metrics ─────────────────────────────────────────
_stats = {
    "total_enqueued": 0,         # Total users ever enqueued
    "total_processed": 0,        # Total users processed by worker
    "total_violations_found": 0, # Total violations detected
    "total_skipped_cooldown": 0, # Skipped due to cooldown
    "total_batches_received": 0, # Total HTTP batch requests
    "total_batches_rejected": 0, # Rate-limited batch requests
    "total_tasks_dropped": 0,    # Background tasks dropped (torrent etc.)
    "peak_queue_size": 0,        # Peak queue size seen
    "last_drain_duration_ms": 0, # Last drain cycle duration
    "worker_started_at": None,   # When worker was last started
}

async def _violation_worker():
    """Single long-lived worker that drains _pending_violation_users in chunks."""
    import time
    _stats["worker_started_at"] = datetime.utcnow().isoformat()

    while True:
        try:
            # Read configurable parameters each cycle (hot-reload from settings)
            drain_interval = config_service.get("violation_drain_interval", _VIOLATION_DRAIN_INTERVAL)
            chunk_size = config_service.get("violation_chunk_size", _VIOLATION_CHUNK_SIZE)
            await asyncio.sleep(drain_interval)
            if not _pending_violation_users:
                continue

            # Track peak queue size
            queue_size = len(_pending_violation_users)
            if queue_size > _stats["peak_queue_size"]:
                _stats["peak_queue_size"] = queue_size

            # Take only a chunk, leave the rest for next cycle
            batch = set()
            while _pending_violation_users and len(batch) < chunk_size:
                batch.add(_pending_violation_users.pop())

            remaining = len(_pending_violation_users)
            if remaining > 0:
                logger.info("Violation queue: processing %d, %d remaining", len(batch), remaining)

            t0 = time.monotonic()
            await _run_violation_detection(batch)
            _stats["last_drain_duration_ms"] = int((time.monotonic() - t0) * 1000)
            _stats["total_processed"] += len(batch)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Violation worker error: %s", e, exc_info=True)

def _enqueue_violation_users(user_uuids: set):
    """Add users to the pending violation check queue and ensure the worker is running."""
    global _violation_worker_task
    _pending_violation_users.update(user_uuids)
    _stats["total_enqueued"] += len(user_uuids)

    # Start worker if not running
    if _violation_worker_task is None or _violation_worker_task.done():
        _violation_worker_task = asyncio.create_task(_violation_worker())


def _shared_hwid_user_uuids(groups: list) -> set:
    """UUID всех юзеров из групп get_shared_hwids() (форма: {hwid, users: [{uuid, ...}]})."""
    return {
        u["uuid"]
        for g in groups or []
        for u in (g.get("users") or [])
        if u.get("uuid")
    }

# ── Generic background task helper (for torrent etc.) ──────
_background_tasks: set = set()
_MAX_BACKGROUND_TASKS = 20

def _schedule_background_task(coro):
    """Schedule a background task with tracking and bounded concurrency."""
    done = {t for t in _background_tasks if t.done()}
    _background_tasks.difference_update(done)

    max_tasks = config_service.get("violation_max_background_tasks", _MAX_BACKGROUND_TASKS)
    if len(_background_tasks) >= max_tasks:
        logger.warning(
            "Background task dropped: %d tasks already queued (limit %d)",
            len(_background_tasks), max_tasks,
        )
        _stats["total_tasks_dropped"] += 1
        return

    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# Кэш имён нод: {node_uuid: (node_name, cached_at)}
_node_name_cache: dict[str, tuple[str, datetime]] = {}
_NODE_NAME_TTL_MINUTES = 30

# Rate limiter для /batch: не более одного запроса в секунду с одной ноды
_node_last_batch: dict[str, float] = {}
MIN_BATCH_INTERVAL = 1.0  # seconds

# Адреса собственной инфраструктуры: {ip}. Ноды заводят редко, пяти минут
# кэша хватает, а разбирать событие дороже, чем держать это множество.
_infra_ips_cache: tuple[float, frozenset[str]] = (0.0, frozenset())
_INFRA_IPS_TTL = 300  # seconds

# Порты, на которых слушает наша инфраструктура: ssh, веб-панель, selfsteal
# и API ноды. Всё остальное на тех же адресах — обычный интернет.
_INFRA_PORTS = frozenset({22, 80, 443, 2222, 8443})

# За какое окно считаем накопленные торрент-события пользователя. Полчаса
# ловят и короткую раздачу, и неспешную закачку, но не тянут вчерашний шум.
_TORRENT_EVENT_WINDOW_MINUTES = 30


async def _get_node_name(node_uuid: str) -> str:
    """Вернуть имя ноды по UUID (с кэшем и TTL). Fallback — первые 8 символов UUID."""
    cached = _node_name_cache.get(node_uuid)
    now = datetime.now()
    if cached and (now - cached[1]).total_seconds() < _NODE_NAME_TTL_MINUTES * 60:
        return cached[0]
    try:
        node = await db_service.get_node_by_uuid(node_uuid)
        name = node.get("name") or node_uuid[:8] if node else node_uuid[:8]
        _node_name_cache[node_uuid] = (name, now)
        return name
    except Exception:
        return cached[0] if cached else node_uuid[:8]

async def _own_infrastructure_ips() -> frozenset[str]:
    """Адреса наших же нод — панельный адрес и адрес, с которого стучится агент."""
    global _infra_ips_cache
    cached_at, ips = _infra_ips_cache
    now = time.time()
    if ips and now - cached_at < _INFRA_IPS_TTL:
        return ips
    try:
        async with db_service.acquire() as conn:
            rows = await conn.fetch(select_sql(NODES_TABLE, "address, agent_ip"))
    except Exception as e:
        logger.warning("Cannot read node addresses: %s", e)
        return ips
    fresh = {
        str(value).strip()
        for row in rows
        for value in (row["address"], row["agent_ip"])
        if value and str(value).strip()
    }
    _infra_ips_cache = (now, frozenset(fresh))
    return _infra_ips_cache[1]


def _split_destination(destination: str) -> tuple[str, Optional[int]]:
    """Разобрать «host:port» — Xray пишет назначение одной строкой."""
    value = (destination or "").strip()
    if value.startswith("["):  # IPv6 в скобках
        host, _, rest = value[1:].partition("]")
        port = rest[1:] if rest.startswith(":") else ""
    elif value.count(":") == 1:
        host, _, port = value.partition(":")
    else:
        host, port = value, ""
    try:
        return host, int(port)
    except ValueError:
        return host, None


def _is_own_service(destination: str, infra_ips: frozenset) -> bool:
    """Поток к нашему же серверу на его служебный порт.

    Только на служебный: за нодой сидят наши же клиенты, и пир на
    торрент-порту за ней — настоящий обмен, а не туннель между серверами.
    """
    host, port = _split_destination(destination)
    return host in infra_ips and port in _INFRA_PORTS


router = APIRouter()


# ── Pydantic models ──────────────────────────────────────────────


class ConnectionReport(BaseModel):
    """Одно подключение от агента."""
    user_email: str
    ip_address: str
    node_uuid: str
    connected_at: datetime
    disconnected_at: Optional[datetime] = None
    bytes_sent: int = 0
    bytes_received: int = 0
    # Агенты постарше поля не шлют — тогда транспорт подключения остаётся
    # неизвестным и определяется по ноде целиком, как раньше.
    inbound_tag: str = ""


class SystemMetricsReport(BaseModel):
    """Системные метрики ноды."""
    cpu_percent: float = 0.0
    cpu_cores: int = 0
    memory_percent: float = 0.0
    memory_total_bytes: int = 0
    memory_used_bytes: int = 0
    disk_percent: float = 0.0
    disk_total_bytes: int = 0
    disk_used_bytes: int = 0
    disk_read_speed_bps: int = 0
    disk_write_speed_bps: int = 0
    uptime_seconds: int = 0


class NetworkMetricsReport(BaseModel):
    """Сетевые метрики хоста ноды (агент 1.3.0+).

    Приходят, только если агент дотянулся до network namespace хоста — иначе
    поле пустое. Пустое и «нули» тут значат разное: первое — нет данных,
    второе — на ноде действительно тихо.
    """
    rx_bps: int = 0
    tx_bps: int = 0
    rx_pps: int = 0
    tx_pps: int = 0
    rx_drop_ps: int = 0
    tx_drop_ps: int = 0
    conntrack_count: Optional[int] = None
    conntrack_max: Optional[int] = None
    tcp_established: int = 0
    tcp_syncookies_ps: int = 0
    tcp_listen_drop_ps: int = 0


class TorrentEventReport(BaseModel):
    """Торрент-событие от агента."""
    user_email: str
    ip_address: str
    destination: str
    inbound_tag: str = ""
    outbound_tag: str = "TORRENT"
    node_uuid: str
    detected_at: datetime
    # Чем поймали: тег роутинга Xray (только открытое рукопожатие
    # BitTorrent) или вердикт nDPI (видит и шифрованный поток, DHT, uTP).
    # Агенты постарше поля не шлют — им остаётся прежний источник.
    detected_by: str = "xray_routing"


class BatchReport(BaseModel):
    """Батч подключений от одной ноды."""
    node_uuid: str
    timestamp: datetime
    connections: list[ConnectionReport] = Field(default=[], max_length=5000)
    torrent_events: list[TorrentEventReport] = Field(default=[], max_length=1000)
    system_metrics: Optional[SystemMetricsReport] = None
    network_metrics: Optional[NetworkMetricsReport] = None
    agent_version: Optional[str] = Field(default=None, max_length=32)


# ── Auth ─────────────────────────────────────────────────────────


async def _find_user_uuid_by_identifier(identifier: str) -> Optional[str]:
    """Поиск user_uuid по email, short_uuid или raw_data ID."""
    user_uuid = None

    if identifier.startswith("user_"):
        user_id_str = identifier.replace("user_", "")
        user = await db_service.get_user_by_short_uuid(user_id_str)
        if user:
            user_uuid = user.get("uuid")

    if not user_uuid:
        user_uuid = await db_service.get_user_uuid_by_email(identifier)

    if not user_uuid and identifier.startswith("user_"):
        user_id_str = identifier.replace("user_", "")
        user_uuid = await db_service.get_user_uuid_by_id_from_raw_data(user_id_str)

    return user_uuid


async def verify_agent_token(
    request: Request,
    authorization: str = Header(..., alias="Authorization"),
) -> str:
    """Проверяет Bearer token агента. Возвращает node_uuid."""
    from web.backend.api.deps import get_client_ip
    client_ip = get_client_ip(request)

    logger.debug("Verifying agent token (length: %d) from %s", len(authorization) if authorization else 0, client_ip)

    if not authorization.startswith("Bearer "):
        logger.warning("Invalid authorization header format from %s", client_ip)
        COLLECTOR_BATCHES_REJECTED.labels(reason="malformed").inc()
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = authorization[7:].strip()
    if not token:
        logger.warning("Token is empty, from %s", client_ip)
        COLLECTOR_BATCHES_REJECTED.labels(reason="auth").inc()
        raise HTTPException(status_code=401, detail="Token is required")

    node_uuid = await get_node_by_token(db_service, token)
    if not node_uuid:
        node_name_hint = ""
        try:
            async with db_service.acquire() as conn:
                row = await conn.fetchrow(
                    select_sql(NODES_TABLE, "name, address", "WHERE address LIKE $1 LIMIT 1"),
                    f"%{client_ip}%",
                )
                if row:
                    node_name_hint = f" (possible node: {row['name']} / {row['address']})"
        except Exception as e:
            logger.debug("Failed to resolve node name by IP: %s", e)
        logger.warning(
            "Invalid agent token attempted: %s from %s%s",
            token[:8] + "...", client_ip, node_name_hint,
        )
        COLLECTOR_BATCHES_REJECTED.labels(reason="auth").inc()
        raise HTTPException(status_code=403, detail="Invalid or expired token")

    logger.debug("Agent token verified for node: %s from %s", node_uuid, client_ip)
    await _remember_agent_ip(node_uuid, _public_ip_for_agent(request, client_ip))
    return node_uuid


def _is_private_ip(ip: str) -> bool:
    import ipaddress
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return parsed.is_private or parsed.is_loopback or parsed.is_link_local


def _public_ip_for_agent(request: Request, peer_ip: str) -> Optional[str]:
    """Публичный IP ноды для nodes.agent_ip.

    Когда батч заходит через внутренний прокси (nginx в docker-сети),
    peer — приватный 172.x: у всех нод получался один и тот же «IP».
    В этом случае берём правый ПУБЛИЧНЫЙ hop X-Forwarded-For (его дописал
    наш прокси — снаружи не подделывается) или X-Real-IP. Приватный адрес
    как agent_ip бесполезен для BS-Check/финансов — лучше ничего.
    """
    if peer_ip and not _is_private_ip(peer_ip):
        return peer_ip
    xff = request.headers.get("x-forwarded-for", "")
    for hop in reversed([h.strip() for h in xff.split(",") if h.strip()]):
        if not _is_private_ip(hop):
            return hop
    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip and not _is_private_ip(real_ip):
        return real_ip
    return None


# Последний записанный agent_ip по нодам — чтобы не долбить UPDATE каждым батчем
_agent_ip_cache: Dict[str, str] = {}


async def _remember_agent_ip(node_uuid: str, client_ip: Optional[str]) -> None:
    """Публичный IP ноды по source-IP батча (nodes.agent_ip).

    За оверлеем (NetBird) nodes.address — туннельный, а хостерские API отдают
    публичные адреса; agent_ip — мост для сопоставления серверов с нодами.
    Приватные адреса сюда не попадают (см. _public_ip_for_agent).
    """
    if not client_ip or _agent_ip_cache.get(node_uuid) == client_ip:
        return
    _agent_ip_cache[node_uuid] = client_ip
    try:
        async with db_service.acquire() as conn:
            await conn.execute(
                f"UPDATE {NODES_TABLE} SET agent_ip = $2 WHERE uuid = $1::uuid",
                node_uuid, client_ip,
            )
    except Exception as e:
        _agent_ip_cache.pop(node_uuid, None)
        logger.debug("Failed to store agent_ip for %s: %s", node_uuid, e)


# ── Endpoints ────────────────────────────────────────────────────


@router.post("/batch")
async def receive_connections(
    report: BatchReport,
    request: Request,
    node_uuid: str = Depends(verify_agent_token),
):
    """Принимает батч подключений от Node Agent."""
    # Rate limit: reject if less than MIN_BATCH_INTERVAL seconds since last batch
    now_ts = time.monotonic()
    last_ts = _node_last_batch.get(node_uuid, 0.0)
    if now_ts - last_ts < MIN_BATCH_INTERVAL:
        _stats["total_batches_rejected"] += 1
        COLLECTOR_BATCHES_REJECTED.labels(reason="rate_limit").inc()
        raise HTTPException(status_code=429, detail="Too many requests: batch interval too short")
    _node_last_batch[node_uuid] = now_ts
    _stats["total_batches_received"] += 1
    COLLECTOR_BATCHES_RECEIVED.inc()
    if report.connections:
        COLLECTOR_CONNECTIONS_PROCESSED.inc(len(report.connections))

    node_name = await _get_node_name(node_uuid)
    _conn_count = len(report.connections) if report.connections else 0
    _has_metrics = "yes" if report.system_metrics else "no"
    logger.info("Batch received      node=%-20s  connections=%-4d  metrics=%s", node_name, _conn_count, _has_metrics)

    if report.node_uuid != node_uuid:
        logger.warning("Node UUID mismatch: token=%s, report=%s", node_uuid, report.node_uuid)
        COLLECTOR_BATCHES_REJECTED.labels(reason="mismatch").inc()
        raise HTTPException(status_code=403, detail="Token does not match the reported node UUID")

    # Версия агента (UPDATE только при изменении — не дёргаем БД каждым батчем)
    if report.agent_version:
        try:
            await db_service.update_node_agent_version(node_uuid, report.agent_version)
        except Exception as e:
            logger.debug("Failed to update agent version for node %s: %s", node_uuid, e)

    # System metrics
    if report.system_metrics:
        # Агенты до 1.3.0 сетевых метрик не шлют — тогда None, и колонки не трогаем
        network = report.network_metrics.model_dump() if report.network_metrics else None
        try:
            await db_service.update_node_metrics(
                node_uuid=node_uuid,
                cpu_usage=report.system_metrics.cpu_percent,
                cpu_cores=report.system_metrics.cpu_cores,
                memory_usage=report.system_metrics.memory_percent,
                memory_total_bytes=report.system_metrics.memory_total_bytes,
                memory_used_bytes=report.system_metrics.memory_used_bytes,
                disk_usage=report.system_metrics.disk_percent,
                disk_total_bytes=report.system_metrics.disk_total_bytes,
                disk_used_bytes=report.system_metrics.disk_used_bytes,
                disk_read_speed_bps=report.system_metrics.disk_read_speed_bps,
                disk_write_speed_bps=report.system_metrics.disk_write_speed_bps,
                uptime_seconds=report.system_metrics.uptime_seconds,
                network=network,
            )
            logger.debug("System metrics updated for node %s", node_uuid)

            # Save snapshot for historical analytics
            try:
                await db_service.insert_node_metrics_snapshot(
                    node_uuid=node_uuid,
                    cpu_usage=report.system_metrics.cpu_percent,
                    cpu_cores=report.system_metrics.cpu_cores,
                    memory_usage=report.system_metrics.memory_percent,
                    memory_total_bytes=report.system_metrics.memory_total_bytes,
                    memory_used_bytes=report.system_metrics.memory_used_bytes,
                    disk_usage=report.system_metrics.disk_percent,
                    disk_total_bytes=report.system_metrics.disk_total_bytes,
                    disk_used_bytes=report.system_metrics.disk_used_bytes,
                    disk_read_speed_bps=report.system_metrics.disk_read_speed_bps,
                    disk_write_speed_bps=report.system_metrics.disk_write_speed_bps,
                    uptime_seconds=report.system_metrics.uptime_seconds,
                    network=network,
                )
            except Exception as e:
                logger.debug("Failed to save metrics snapshot for node %s: %s", node_uuid, e)
        except Exception as e:
            logger.warning("Failed to update system metrics for node %s: %s", node_uuid, e)

    # Periodic cleanup of old data (once per 24h)
    global _last_metrics_cleanup
    now = datetime.utcnow()
    if (now - _last_metrics_cleanup).total_seconds() > CLEANUP_INTERVAL_HOURS * 3600:
        _last_metrics_cleanup = now
        try:
            m_days = int(config_service.get("metrics_retention_days", METRICS_RETENTION_DAYS) or METRICS_RETENTION_DAYS)
            deleted = await db_service.cleanup_old_metrics_snapshots(m_days)
            if deleted > 0:
                logger.info("Cleaned up %d old metrics snapshots", deleted)
        except Exception as e:
            logger.warning("Failed to cleanup old metrics snapshots: %s", e)
        try:
            c_days = int(config_service.get("connections_retention_days", CONNECTIONS_RETENTION_DAYS) or CONNECTIONS_RETENTION_DAYS)
            deleted = await db_service.cleanup_old_connections(c_days)
            if deleted > 0:
                logger.info("Cleaned up %d old connections", deleted)
        except Exception as e:
            logger.warning("Failed to cleanup old connections: %s", e)
        try:
            created = await db_service.ensure_connection_partitions(months_ahead=3)
            if created > 0:
                logger.info("Created %d new connection partitions", created)
        except Exception as e:
            logger.debug("Failed to ensure connection partitions: %s", e)
        try:
            t_days = int(config_service.get("torrent_retention_days", 90) or 90)
            deleted = await db_service.cleanup_old_torrent_events(t_days)
            if deleted > 0:
                logger.info("Cleaned up %d old torrent events", deleted)
        except Exception as e:
            logger.warning("Failed to cleanup old torrent events: %s", e)

    if not report.connections and not report.torrent_events:
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "processed": 0, "message": "No connections to process",
                     "metrics_updated": report.system_metrics is not None},
        )

    # ── Batch resolve all user identifiers to UUIDs ──────────────
    user_uuid_cache: dict[str, Optional[str]] = {}

    if report.connections or report.torrent_events:
        all_identifiers = set()
        for conn in report.connections:
            all_identifiers.add(conn.user_email)
        for event in (report.torrent_events or []):
            all_identifiers.add(event.user_email)

        # Classify identifiers
        emails = []
        short_uuids_raw = []
        for ident in all_identifiers:
            if ident.startswith("user_"):
                short_uuids_raw.append(ident)
            else:
                emails.append(ident)

        # Batch resolve emails and short_uuids (2 queries instead of N)
        if emails:
            email_map = await db_service.get_email_to_uuid_map(emails)
            for email, uid in email_map.items():
                user_uuid_cache[email] = uid

        if short_uuids_raw:
            short_uuids_clean = [s.replace("user_", "") for s in short_uuids_raw]
            short_map = await db_service.get_short_uuid_to_uuid_map(short_uuids_clean)
            for short, uid in short_map.items():
                user_uuid_cache[f"user_{short}"] = uid

        # Fallback for unresolved identifiers (individual lookup)
        for ident in all_identifiers:
            if ident not in user_uuid_cache:
                uid = await _find_user_uuid_by_identifier(ident)
                user_uuid_cache[ident] = uid

    # Helper for torrent events (reuses the cache)
    async def _cached_find_user(identifier: str) -> Optional[str]:
        if identifier not in user_uuid_cache:
            user_uuid_cache[identifier] = await _find_user_uuid_by_identifier(identifier)
        return user_uuid_cache[identifier]

    # ── Batch upsert connections (replaces per-connection loop) ─────
    processed = 0
    errors = 0

    if report.connections:
        batch_connections = []
        for conn in report.connections:
            user_uuid = user_uuid_cache.get(conn.user_email)
            if not user_uuid:
                logger.warning("User not found for identifier=%s, skipping", conn.user_email)
                errors += 1
                continue
            batch_connections.append({
                "user_uuid": user_uuid,
                "ip_address": conn.ip_address,
                "node_uuid": conn.node_uuid,
                "device_info": {
                    "user_email": conn.user_email,
                    "inbound_tag": conn.inbound_tag or None,
                    "bytes_sent": conn.bytes_sent,
                    "bytes_received": conn.bytes_received,
                    "connected_at": conn.connected_at.isoformat() if conn.connected_at else None,
                    "disconnected_at": conn.disconnected_at.isoformat() if conn.disconnected_at else None,
                },
                "connected_at": conn.connected_at,
            })

        if batch_connections:
            for attempt in range(3):
                try:
                    result = await db_service.batch_upsert_connections(
                        batch_connections, stale_threshold_minutes=2
                    )
                    processed = result["upserted"]
                    logger.info("Batch upserted      node=%-20s  upserted=%-4d  stale=%-3d  errors=%d", node_name, result["upserted"], result["closed_stale"], errors)
                    break
                except Exception as e:
                    if "deadlock" in str(e).lower() and attempt < 2:
                        logger.warning("Deadlock on batch upsert for %s, retry %d/2", node_name, attempt + 1)
                        await asyncio.sleep(0.1 * (attempt + 1))
                        continue
                    logger.error("Batch upsert failed for node %s: %s", node_name, e, exc_info=True)
                    errors += len(batch_connections)

    if errors > 0:
        logger.warning("Batch errors        node=%-20s  total=%-4d  processed=%-4d  errors=%d", node_name, len(report.connections), processed, errors)

    # Post-processing: violation detection in background
    # Stale connection closing is now handled inside batch_upsert_connections
    if processed > 0:
        try:
            # Only include users that had connections in this batch (not torrent-only users)
            affected_user_uuids = set(
                user_uuid_cache[conn.user_email]
                for conn in report.connections
                if user_uuid_cache.get(conn.user_email)
            )
            _enqueue_violation_users(affected_user_uuids)
        except Exception as e:
            logger.warning("Error in post-processing: %s", e)

    # ── Torrent events processing ──────────────────────────
    torrent_processed = 0
    if report.torrent_events:
        torrent_enabled = config_service.get("torrent_detection_enabled", True)
        if torrent_enabled:
            # Поток к своему же серверу на его служебный порт — это туннель
            # между нашими нодами: торрента внутри не видит никто, включая
            # nDPI, он метит шифрованный поток по косвенным признакам. Такие
            # события отбрасываем, не доводя ни до базы, ни до наказания.
            infra_ips = await _own_infrastructure_ips()
            torrent_events = [
                event for event in report.torrent_events
                if not _is_own_service(event.destination, infra_ips)
            ]
            ignored_infra = len(report.torrent_events) - len(torrent_events)
            if ignored_infra:
                logger.info(
                    "Torrent events: %d to own infrastructure ignored (node=%s)",
                    ignored_infra, node_name,
                )

            # Resolve user UUIDs and build batch
            batch_events = []
            for event in torrent_events:
                try:
                    user_uuid_t = await _cached_find_user(event.user_email)
                    if not user_uuid_t:
                        continue
                    batch_events.append({
                        "user_uuid": user_uuid_t,
                        "node_uuid": event.node_uuid,
                        "ip_address": event.ip_address,
                        "destination": event.destination,
                        "inbound_tag": event.inbound_tag,
                        "outbound_tag": event.outbound_tag,
                        "detected_at": event.detected_at,
                        "detected_by": event.detected_by,
                    })
                except Exception as e:
                    logger.warning("Error resolving torrent event for %s: %s", event.user_email, e)

            if batch_events:
                torrent_processed = await db_service.batch_save_torrent_events(batch_events)

            if torrent_processed > 0:
                logger.warning(
                    "Torrent events: node=%s count=%d", node_name, torrent_processed
                )
                _schedule_background_task(
                    _process_torrent_violations(torrent_events, user_uuid_cache)
                )

    return JSONResponse(
        status_code=200,
        content={
            "status": "ok", "processed": processed, "errors": errors,
            "torrent_events": torrent_processed, "node_uuid": node_uuid,
        },
    )


async def _process_torrent_violations(
    events: list[TorrentEventReport],
    user_uuid_cache: dict[str, Optional[str]],
):
    """Background: create violations and send notifications for torrent events."""
    try:
        # Вердикт nDPI висит на адресе назначения, а не на человеке. Если по
        # тому же адресу события есть и у других — за ним стоит не один
        # пользователь (мессенджер, CDN, публичный резолвер), и обвинять
        # некого. Проверка тут, а не в агенте: на нодах он обновляется не в
        # один день, а защита нужна всем сразу.
        shared = await db_service.shared_torrent_destinations(
            [event.destination for event in events]
        )
        if shared:
            events = [event for event in events if event.destination not in shared]
            logger.info(
                "Torrent violations: %d destination(s) shared by several users, skipped",
                len(shared),
            )
            if not events:
                return

        # Group events by user
        events_by_user: dict[str, list[TorrentEventReport]] = {}
        for event in events:
            user_uuid = user_uuid_cache.get(event.user_email)
            if user_uuid:
                events_by_user.setdefault(user_uuid, []).append(event)

        auto_action = config_service.get("torrent_auto_action", "notify")
        try:
            min_events = int(config_service.get("torrent_min_events", 5) or 1)
        except (TypeError, ValueError):
            min_events = 5
        try:
            min_peers = int(config_service.get("torrent_min_peers", 3) or 1)
        except (TypeError, ValueError):
            min_peers = 3

        for user_uuid, user_events in events_by_user.items():
            try:
                # Check whitelist — skip fully whitelisted or torrent-excluded users
                whitelisted, excluded = await db_service.is_user_violation_whitelisted(user_uuid)
                if whitelisted and (excluded is None or "torrent" in excluded):
                    logger.debug("User %s is whitelisted for torrent, skipping", user_uuid)
                    continue

                # Одиночное срабатывание — это шум: настоящий обмен даёт сотни
                # событий за минуты. Считаем накопленное по базе, а не по
                # батчу: рой приезжает кусками, и в отдельном куске событий
                # может быть немного.
                if min_events > 1:
                    recent = await db_service.count_recent_torrent_events(
                        user_uuid, minutes=_TORRENT_EVENT_WINDOW_MINUTES,
                    )
                    if recent < min_events:
                        logger.info(
                            "Torrent: %d event(s) for %s in %d min — below threshold %d",
                            recent, user_uuid[:8], _TORRENT_EVENT_WINDOW_MINUTES, min_events,
                        )
                        continue

                # Событий может набить и одно долгое соединение — рой это не
                # доказывает. У обмена десятки пиров сразу; у ложного
                # срабатывания адрес один и тот же (ловился антивирус,
                # которому эвристика приписала шифрованный BitTorrent).
                if min_peers > 1:
                    peers = await db_service.count_recent_torrent_peers(
                        user_uuid, minutes=_TORRENT_EVENT_WINDOW_MINUTES,
                    )
                    if peers < min_peers:
                        logger.info(
                            "Torrent: %d peer(s) for %s in %d min — below threshold %d",
                            peers, user_uuid[:8], _TORRENT_EVENT_WINDOW_MINUTES, min_peers,
                        )
                        continue

                # Dedup: skip if torrent violation exists within last 10 min
                existing = await db_service.get_recent_torrent_violation(user_uuid, minutes=10)
                if existing:
                    continue

                user_info = await db_service.get_user_by_uuid(user_uuid)
                username = user_info.get("username", "n/a") if user_info else "n/a"
                email = user_info.get("email") if user_info else None
                telegram_id = user_info.get("telegramId") if user_info else None

                destinations = list(set(e.destination for e in user_events))
                # Игровые лаунчеры раздают обновления настоящим BitTorrent, и
                # вердикт по ним верный — отличается только адресат. Отсев
                # идёт здесь, на последнем шаге: резолвить ASN на каждое
                # событие батча было бы дорого и незачем.
                destinations = await torrent_p2p_whitelist.filter_destinations(destinations)
                if not destinations:
                    logger.info(
                        "Torrent: у %s остались только адреса легального P2P — не нарушение",
                        user_uuid[:8],
                    )
                    continue
                ips = list(set(e.ip_address for e in user_events))

                # Save as violation (score=100)
                violation_id, violation_created = await db_service.save_violation(
                    user_uuid=user_uuid,
                    score=100.0,
                    recommended_action="hard_block",
                    username=username,
                    email=email,
                    telegram_id=telegram_id,
                    confidence=1.0,
                    ip_addresses=ips,
                    reasons=[
                        f"Torrent traffic detected ({len(user_events)} events)",
                        *[f"Destination: {d}" for d in destinations[:5]],
                    ],
                    simultaneous_connections=len(ips),
                    unique_ips_count=len(ips),
                )

                if not violation_created:
                    # Дедуп: свежая pending-запись уже есть — не спамим событиями
                    logger.debug("Torrent violation deduplicated for user %s (id=%s)", user_uuid, violation_id)
                    continue

                fire_event("violation.created", {
                    "violation_id": violation_id,
                    "user_uuid": user_uuid,
                    "username": username,
                    "score": 100.0,
                    "recommended_action": "hard_block",
                    "reasons": [f"Torrent traffic detected ({len(user_events)} events)"],
                    "ip_addresses": ips,
                    "source": "torrent",
                })

                # Notification
                try:
                    from web.backend.core.violation_notifier import send_torrent_notification
                    await send_torrent_notification(
                        user_uuid=user_uuid,
                        user_info=user_info,
                        torrent_events=user_events,
                        destinations=destinations,
                        ips=ips,
                    )
                except Exception as e:
                    logger.warning("Failed to send torrent notification: %s", e)

                # Automation event
                try:
                    from web.backend.core.automation_engine import engine as automation_engine
                    await automation_engine.handle_event("torrent.detected", {
                        "user_uuid": user_uuid,
                        "uuid": user_uuid,
                        "username": username,
                        "email": email,
                        "destinations": destinations,
                        "ips": ips,
                        "event_count": len(user_events),
                        "node_uuid": user_events[0].node_uuid,
                        "score": 100.0,
                    })
                except Exception as e:
                    logger.warning("Automation event failed: %s", e)

                # WebSocket broadcast
                try:
                    from web.backend.api.v2.websocket import broadcast_violation
                    await broadcast_violation({
                        "type": "torrent",
                        "user_uuid": user_uuid,
                        "username": username,
                        "score": 100.0,
                        "destinations": destinations,
                        "reasons": [f"Torrent traffic: {len(user_events)} events"],
                    })
                except Exception as e:
                    logger.debug("WebSocket broadcast failed for torrent violation: %s", e)

                # Auto-block if configured
                if auto_action == "block_user":
                    try:
                        from shared.api_client import api_client
                        await api_client.disable_user(await _resolve_user_key(user_uuid))
                        logger.info("Auto-blocked user %s for torrent usage", user_uuid)
                        fire_event("user.blocked", {
                            "uuid": user_uuid,
                            "username": username,
                            "reason": "torrent",
                            "details": f"Torrent traffic detected ({len(user_events)} events)",
                            "blocked_by": "auto",
                        })
                    except Exception as e:
                        logger.warning("Failed to auto-block user %s: %s", user_uuid, e)

            except Exception as e:
                logger.warning("Error processing torrent violation for user %s: %s", user_uuid, e)

    except Exception as e:
        logger.error("Background torrent violation processing failed: %s", e)


async def _run_violation_detection(affected_user_uuids: set):
    """Background task: check affected users for violations using batch queries."""
    try:
        violations_enabled = config_service.get("violations_enabled", True)
        if not violations_enabled:
            return

        min_score = config_service.get("violations_min_score", 50.0)

        # Cleanup stale cooldown entries (older than 1h)
        now_cleanup = datetime.utcnow()
        expired_keys = [k for k, v in _violation_check_cooldown.items()
                       if (now_cleanup - v).total_seconds() > 3600]
        for k in expired_keys:
            del _violation_check_cooldown[k]
        if expired_keys:
            logger.debug("Cooldown cleanup: removed %d expired entries, %d remaining",
                         len(expired_keys), len(_violation_check_cooldown))

        # Adaptive cooldown based on total tracked users
        total_tracked = len(_violation_check_cooldown) + len(affected_user_uuids)
        if total_tracked > 50000:
            adaptive_cooldown = 60
        elif total_tracked > 10000:
            adaptive_cooldown = 30
        elif total_tracked > 5000:
            adaptive_cooldown = 20
        elif total_tracked > 1000:
            adaptive_cooldown = 15
        else:
            adaptive_cooldown = None

        cooldown_minutes = adaptive_cooldown if adaptive_cooldown is not None else config_service.get("violation_check_cooldown_minutes", VIOLATION_CHECK_COOLDOWN_MINUTES)

        # Filter out users on cooldown
        to_check: list[str] = []
        for uuid in affected_user_uuids:
            last_check = _violation_check_cooldown.get(uuid)
            if last_check and (now_cleanup - last_check).total_seconds() < cooldown_minutes * 60:
                _stats["total_skipped_cooldown"] += 1
                continue
            to_check.append(uuid)

        if not to_check:
            return

        # Batch whitelist check
        whitelist_map = await db_service.batch_get_whitelist_status(to_check)
        excluded_map: dict[str, list[str] | None] = {}
        remaining: list[str] = []
        for uuid in to_check:
            whitelisted, excluded = whitelist_map.get(uuid, (False, None))
            if whitelisted and excluded is None:
                continue
            if excluded:
                excluded_map[uuid] = excluded
            remaining.append(uuid)

        if not remaining:
            return

        # Batch violation detection (all DB queries batched inside)
        scores = await violation_detector.check_users_batch(
            remaining,
            window_minutes=60,
            excluded_analyzers_map=excluded_map,
        )

        # Post-processing: handle violations and update cooldowns
        violators: list[str] = []
        for uuid in remaining:
            violation_score = scores.get(uuid)
            had_violation = bool(violation_score and violation_score.total >= min_score)
            _violation_check_cooldown[uuid] = datetime.utcnow() if not had_violation else (
                datetime.utcnow() - timedelta(minutes=max(0, cooldown_minutes - 5))
            )
            if had_violation:
                violators.append(uuid)

        # Load HWID devices once for all remaining (used by violators + blacklist check)
        all_devices = await db_service.batch_get_user_hwid_devices(remaining)

        # Process violators (small subset, per-user is fine)
        if violators:
            users_info = await db_service.batch_get_users_info(violators)

            for uuid in violators:
                try:
                    violation_score = scores[uuid]
                    _stats["total_violations_found"] += 1
                    logger.warning(
                        "Violation detected: user=%s score=%.1f action=%s reasons=%s",
                        uuid, violation_score.total,
                        violation_score.recommended_action.value,
                        violation_score.reasons[:3],
                    )
                    await _handle_violation(
                        uuid, violation_score,
                        users_info.get(uuid),
                        all_devices.get(uuid, []),
                        whitelist_map.get(uuid, (False, None))[0],
                    )
                except Exception as e:
                    logger.warning("Error handling violation for %s: %s", uuid, e)

        # HWID blacklist check for all remaining users
        try:
            all_hwids: set[str] = set()
            hwid_to_users: dict[str, list[str]] = {}
            for uid, devices in all_devices.items():
                for d in devices:
                    hwid = d.get("hwid")
                    if hwid:
                        all_hwids.add(hwid)
                        hwid_to_users.setdefault(hwid, []).append(uid)

            if all_hwids:
                bl_matches = await db_service.check_hwids_against_blacklist(list(all_hwids))
                if bl_matches:
                    from web.backend.api.v2.violations import _handle_blacklisted_hwid_users
                    matched_uids = {
                        uid for m in bl_matches for uid in hwid_to_users.get(m["hwid"], [])
                    }
                    # Статусы и имена одним запросом: без них в уведомление уходит
                    # голый UUID, а уже отключённые попадают в него снова и снова
                    bl_users = await db_service.batch_get_users_info(list(matched_uids))
                    for match in bl_matches:
                        affected = []
                        for uid in hwid_to_users.get(match["hwid"], []):
                            info = bl_users.get(uid) or {}
                            # Юзер уже отключён — мера принята, повторять нечего.
                            # Скан ходит каждые 30 минут, и без этой отсечки он
                            # рапортует об одном и том же до скончания века
                            if str(info.get("status") or "").upper() == "DISABLED":
                                continue
                            affected.append({"user_uuid": uid, "username": info.get("username")})
                        if affected:
                            await _handle_blacklisted_hwid_users(
                                match["hwid"], match["action"],
                                match.get("reason"), affected,
                            )
        except Exception as e:
            logger.debug("Batch HWID blacklist check failed: %s", e)

        # User blacklist check (telegram ID)
        if config_service.get("user_blacklist_enabled", False):
            try:
                if violators and set(remaining) == set(violators):
                    users_info_bl = users_info
                else:
                    users_info_bl = await db_service.batch_get_users_info(remaining)
                for uid, uinfo in users_info_bl.items():
                    tg_id = uinfo.get("telegram_id") or uinfo.get("telegramId")
                    if tg_id:
                        bl_entry = await db_service.is_telegram_id_blacklisted(int(tg_id))
                        if bl_entry and config_service.get("user_blacklist_auto_block", False):
                            try:
                                from shared.api_client import api_client
                                await api_client.disable_user(await _resolve_user_key(uid))
                                logger.info("Auto-blocked blacklisted user: %s (tg_id=%d)", uid, tg_id)
                                fire_event("user.blocked", {
                                    "uuid": uid,
                                    "username": uinfo.get("username"),
                                    "reason": "blacklist",
                                    "details": bl_entry.get("reason", ""),
                                    "blocked_by": "auto",
                                })
                            except Exception:
                                pass
            except Exception as e:
                logger.debug("Batch user blacklist check failed: %s", e)

        # Evict oldest cooldown entries if too large
        if len(_violation_check_cooldown) > MAX_COOLDOWN_SIZE:
            sorted_keys = sorted(_violation_check_cooldown, key=_violation_check_cooldown.get)
            evict_count = len(sorted_keys) // 5
            for k in sorted_keys[:evict_count]:
                _violation_check_cooldown.pop(k, None)

        # Periodic cleanup of old violations
        global _last_violation_cleanup
        if (datetime.utcnow() - _last_violation_cleanup).total_seconds() > 3600:
            retention_days = config_service.get("violation_retention_days", 90)
            cleaned = await db_service.cleanup_old_violations(retention_days)
            if cleaned:
                logger.info("Cleaned up %d old violations (retention: %d days)", cleaned, retention_days)
            _last_violation_cleanup = datetime.utcnow()

    except Exception as e:
        logger.error("Background violation detection failed: %s", e, exc_info=True)


async def _handle_violation(
    user_uuid: str,
    violation_score,
    user_info: dict | None,
    hwid_devices: list,
    is_whitelisted: bool,
):
    """Post-process a single detected violation: notify, save, auto-block."""
    # Юзер уже отключён в панели (заблокирован админом/автоблоком) — не плодим
    # новые нарушения и уведомления по остаточным коннектам: админ меру принял,
    # а «нарушения по кругу» на всю сеть кросс-аккаунтов только заваливают его
    status = str((user_info or {}).get("status") or "").upper()
    if status == "DISABLED":
        logger.debug("Skipping violation for disabled user %s", user_uuid)
        return

    active_conns = await connection_monitor.get_user_active_connections(user_uuid, max_age_minutes=5)

    ip_metadata = {}
    if active_conns:
        try:
            from shared.geoip import get_geoip_service
            geoip = get_geoip_service()
            unique_ips = list(set(str(c.ip_address) for c in active_conns))
            ip_metadata = await geoip.lookup_batch(unique_ips)
        except Exception as geo_error:
            logger.warning("GeoIP lookup failed for user %s: %s", user_uuid, geo_error)

    notification_sent = False
    if not is_whitelisted:
        try:
            from web.backend.core.violation_notifier import send_violation_notification
            await send_violation_notification(
                user_uuid=user_uuid,
                violation_score={
                    "total": violation_score.total,
                    "recommended_action": violation_score.recommended_action,
                    "reasons": violation_score.reasons,
                    "breakdown": violation_score.breakdown,
                    "confidence": violation_score.confidence,
                },
                user_info=user_info,
                active_connections=active_conns,
                ip_metadata=ip_metadata,
            )
            notification_sent = True
        except Exception as notify_error:
            logger.warning("Failed to send violation notification for user %s: %s", user_uuid, notify_error)

    try:
        breakdown = violation_score.breakdown
        temporal = breakdown.get("temporal")
        geo = breakdown.get("geo")
        asn = breakdown.get("asn")
        profile = breakdown.get("profile")
        device = breakdown.get("device")
        hwid = breakdown.get("hwid")
        ua = breakdown.get("user_agent")

        ip_addresses = list(set(str(c.ip_address) for c in active_conns)) if active_conns else None
        username = user_info.get("username") if user_info else None
        email = user_info.get("email") if user_info else None
        telegram_id = user_info.get("telegram_id") if user_info else None
        device_limit = user_info.get("hwidDeviceLimit", 1) if user_info else 1

        violation_id, violation_created = await db_service.save_violation(
            user_uuid=user_uuid,
            score=violation_score.total,
            recommended_action=violation_score.recommended_action.value,
            username=username, email=email, telegram_id=telegram_id,
            confidence=violation_score.confidence,
            temporal_score=temporal.score if temporal else None,
            geo_score=geo.score if geo else None,
            asn_score=asn.score if asn else None,
            profile_score=profile.score if profile else None,
            device_score=device.score if device else None,
            ip_addresses=ip_addresses,
            countries=list(geo.countries) if geo and geo.countries else None,
            cities=list(geo.cities) if geo and geo.cities else None,
            asn_types=list(asn.asn_types) if asn and asn.asn_types else None,
            os_list=device.os_list if device else None,
            client_list=device.client_list if device else None,
            reasons=violation_score.reasons[:10] if violation_score.reasons else None,
            simultaneous_connections=temporal.simultaneous_connections_count if temporal else None,
            unique_ips_count=len(ip_addresses) if ip_addresses else None,
            device_limit=device_limit,
            impossible_travel=geo.impossible_travel_detected if geo else False,
            is_mobile=asn.is_mobile_carrier if asn else False,
            is_datacenter=asn.is_datacenter if asn else False,
            is_vpn=asn.is_vpn if asn else False,
            hwid_score=hwid.score if hwid else None,
            hwid_matched_users=json.dumps(hwid.matched_details) if hwid and hwid.matched_details else None,
            user_agent_score=ua.score if ua else None,
            suspicious_user_agents=json.dumps([
                {"request_id": s.request_id, "user_agent": s.user_agent,
                 "request_ip": s.request_ip, "request_at": s.request_at,
                 "classification": s.classification}
                for s in ua.suspicious_agents
            ]) if ua and ua.suspicious_agents else None,
        )

        if not violation_created:
            # Дедуп вернул существующую pending-запись: события и автоблок уже
            # отработали при её создании — повторные срабатывания (в т.ч.
            # автоматизаций на violation.created) только путают админа.
            logger.debug("Violation deduplicated for user %s (id=%s)", user_uuid, violation_id)
            return

        if notification_sent and violation_id:
            # Уведомление уходит до сохранения (id ещё нет), поэтому отметка ставится
            # здесь. Без неё кулдаун повторных уведомлений считает, что юзеру ещё
            # ничего не отправляли: он берёт MAX(notified_at) по пользователю.
            try:
                await db_service.mark_violation_notified(violation_id)
            except Exception as mark_error:
                logger.warning("Failed to mark violation %s as notified: %s", violation_id, mark_error)

        fire_event("violation.created", {
            "violation_id": violation_id,
            "user_uuid": user_uuid,
            "username": username,
            "score": violation_score.total,
            "confidence": violation_score.confidence,
            "recommended_action": violation_score.recommended_action.value,
            "reasons": violation_score.reasons[:10] if violation_score.reasons else [],
            "ip_addresses": ip_addresses,
            "source": "detector",
        })

        from shared.violation_detector import ViolationAction

        # Детектор рекомендует разобраться вручную — можно вместо этого сразу
        # урезать скорость. Мера обратимая и не выкидывает человека из сети,
        # поэтому в отличие от автоблокировки её не страшно применять на
        # среднем скоре; выключено по умолчанию, решает администратор.
        if (
            violation_score.recommended_action == ViolationAction.SOFT_BLOCK
            and config_service.get("violation_auto_soft_throttle", False)
        ):
            try:
                from shared.config_service import config_service as _cfg
                from shared.throttle import apply_throttle

                rate_kbit = int(_cfg.get("throttle_default_kbit", 1024) or 1024)
                ok, err, moved = await apply_throttle(
                    user_uuid=user_uuid,
                    rate_kbit=rate_kbit,
                    reason=f"Автоматически по скору {violation_score.total:.1f}",
                    admin_username="auto",
                )
                if ok:
                    logger.warning(
                        "Auto-throttled user %s to %d kbit (score=%.1f)%s",
                        user_uuid[:8], rate_kbit, violation_score.total,
                        " + reserve squad" if moved else "",
                    )
                    from web.backend.core.throttle_sync import push_throttles
                    await push_throttles()
                else:
                    logger.warning("Auto-throttle failed for %s: %s", user_uuid[:8], err)
            except Exception as throttle_error:
                logger.warning("Auto-throttle error for %s: %s", user_uuid[:8], throttle_error)

        if violation_score.recommended_action == ViolationAction.HARD_BLOCK:
            if config_service.get("violation_auto_hard_block", True):
                from shared.api_client import api_client
                blocked_count = 0
                try:
                    await api_client.disable_user(await _resolve_user_key(user_uuid))
                    blocked_count += 1
                    logger.warning("Auto-blocked user %s score=%.1f", user_uuid[:8], violation_score.total)
                    fire_event("user.blocked", {
                        "uuid": user_uuid,
                        "username": username,
                        "reason": "violation",
                        "details": f"hard_block recommended (score={violation_score.total:.1f})",
                        "violation_id": violation_id,
                        "blocked_by": "auto",
                    })
                except Exception as block_error:
                    logger.warning("Failed to auto-block user %s: %s", user_uuid, block_error)

                # Соучастники накрутки триалов блокируются вместе с проверяемым.
                # Иначе связка остаётся рабочей: после бана одного остальные видят
                # уже один живой триал, под правило не попадают, и накрутка стоит
                # абузеру ровно один аккаунт из N. Список приходит от анализатора
                # и содержит только чужие подписки с ЖИВЫМ триалом на том же HWID —
                # платные и истёкшие туда не попадают.
                for accomplice_uuid in (getattr(hwid, "active_trial_accomplices", None) or []):
                    try:
                        await api_client.disable_user(await _resolve_user_key(accomplice_uuid))
                        blocked_count += 1
                        logger.warning(
                            "Auto-blocked trial-abuse accomplice %s (violation %s)",
                            accomplice_uuid[:8], violation_id,
                        )
                        fire_event("user.blocked", {
                            "uuid": accomplice_uuid,
                            "username": None,
                            "reason": "violation",
                            "details": f"trial abuse accomplice of {user_uuid}",
                            "violation_id": violation_id,
                            "blocked_by": "auto",
                        })
                    except Exception as block_error:
                        logger.warning(
                            "Failed to auto-block accomplice %s: %s", accomplice_uuid, block_error,
                        )

                # Нарушение помечается решённым: меру система уже приняла. Без этого
                # запись остаётся в «неразрешённых» (метрики фильтруют по
                # action_taken IS NULL) и админ видит требование действия, которого
                # делать не нужно.
                if blocked_count and violation_id:
                    try:
                        comment = (
                            "Автоблокировка детектора"
                            if blocked_count == 1
                            else f"Автоблокировка детектора: заблокировано аккаунтов — {blocked_count}"
                        )
                        await db_service.update_violation_action(
                            violation_id=violation_id,
                            action_taken="hard_block",
                            admin_telegram_id=None,
                            admin_comment=comment,
                        )
                    except Exception as mark_error:
                        logger.warning(
                            "Failed to mark violation %s as auto-resolved: %s", violation_id, mark_error,
                        )
            else:
                logger.info(
                    "Auto-block skipped for user %s (violation_auto_hard_block=off, score=%.1f)",
                    user_uuid[:8], violation_score.total,
                )

        try:
            from web.backend.api.v2.websocket import broadcast_violation
            await broadcast_violation({
                "user_uuid": user_uuid,
                "username": username,
                "score": violation_score.total,
                "recommended_action": violation_score.recommended_action.value,
                "reasons": violation_score.reasons[:5],
            })
        except Exception:
            pass

    except Exception as save_error:
        logger.warning("Failed to save violation for user %s: %s", user_uuid, save_error)


@router.get("/health")
async def collector_health():
    """Health check endpoint — includes violation worker and queue health."""
    worker_alive = _violation_worker_task is not None and not _violation_worker_task.done()
    queue_size = len(_pending_violation_users)
    queue_overloaded = queue_size > 5000

    health_status = "ok"
    if not db_service.is_connected:
        health_status = "degraded"
    if queue_overloaded:
        health_status = "degraded"

    status_code = 200 if health_status == "ok" else 503

    return JSONResponse(
        status_code=status_code,
        content={
            "status": health_status,
            "service": "collector",
            "database_connected": db_service.is_connected,
            "violation_worker_alive": worker_alive,
            "violation_queue_size": queue_size,
            "violation_queue_overloaded": queue_overloaded,
        },
    )


@router.get("/stats")
async def collector_stats(request: Request):
    """Collector pipeline metrics — queue depth, processing rates, bottleneck indicators.

    Requires admin JWT token (not agent token) for security.
    """
    # Verify admin auth (collector endpoints skip middleware, so check manually)
    from web.backend.core.security import decode_token
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Authentication required"})
    payload = decode_token(auth_header[7:], token_type="access")
    if not payload:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})
    queue_size = len(_pending_violation_users)
    cooldown_size = len(_violation_check_cooldown)
    bg_tasks = len({t for t in _background_tasks if not t.done()})

    # Determine queue health
    if queue_size == 0:
        queue_health = "idle"
    elif queue_size < 500:
        queue_health = "ok"
    elif queue_size < 2000:
        queue_health = "busy"
    else:
        queue_health = "overloaded"

    return JSONResponse(
        status_code=200,
        content={
            "queue": {
                "pending_users": queue_size,
                "peak_queue_size": _stats["peak_queue_size"],
                "health": queue_health,
            },
            "processing": {
                "total_enqueued": _stats["total_enqueued"],
                "total_processed": _stats["total_processed"],
                "total_violations_found": _stats["total_violations_found"],
                "total_skipped_cooldown": _stats["total_skipped_cooldown"],
                "last_drain_duration_ms": _stats["last_drain_duration_ms"],
                "backlog": _stats["total_enqueued"] - _stats["total_processed"],
            },
            "input": {
                "total_batches_received": _stats["total_batches_received"],
                "total_batches_rejected": _stats["total_batches_rejected"],
            },
            "background_tasks": {
                "active": bg_tasks,
                "dropped": _stats["total_tasks_dropped"],
            },
            "cooldown_cache_size": cooldown_size,
            "config": {
                "drain_interval_sec": config_service.get("violation_drain_interval", _VIOLATION_DRAIN_INTERVAL),
                "chunk_size": config_service.get("violation_chunk_size", _VIOLATION_CHUNK_SIZE),
                "cooldown_minutes": config_service.get("violation_check_cooldown_minutes", VIOLATION_CHECK_COOLDOWN_MINUTES),
                "max_background_tasks": config_service.get("violation_max_background_tasks", _MAX_BACKGROUND_TASKS),
            },
            "worker_started_at": _stats["worker_started_at"],
        },
    )


# ── Webhook proxy ─────────────────────────────────────────────────

def _verify_webhook_signature(request: Request, body: bytes) -> bool:
    """Verify HMAC-SHA256 signature from Panel webhook."""
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        client_host = request.client.host if request.client else None
        return client_host in ("127.0.0.1", "::1", "localhost")

    signature = (
        request.headers.get("x-remnawave-signature")
        or request.headers.get("X-Remnawave-Signature")
        or ""
    )
    if not signature:
        return False

    if signature == secret:
        return True

    try:
        expected = hmac_mod.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac_mod.compare_digest(expected, signature)
    except Exception:
        return False


def _person_key(telegram_id, email, uuid: str):
    """Человек за подпиской: telegram_id → email → uuid.

    Та же лесенка, что у HWID-анализатора: несколько подписок одного человека
    (мультитариф Bedolaga, регистрация без Telegram) считаются одним аккаунтом.
    """
    if telegram_id is not None:
        return ("tg", telegram_id)
    normalized = (email or "").strip().lower()
    return ("email", normalized) if normalized else ("uuid", uuid)


async def _notify_hwid_reuse(sync_result: dict) -> None:
    """Устройство привязали к аккаунту, а его уже видели на другом — сказать сразу.

    Периодический скан заметит это в течение получаса, и всё это время свежий
    триал работает. Вебхук приходит в момент привязки, поэтому окно закрывается
    здесь. Шумим не на всякое совпадение: пара «пробная → купленная» у одного
    человека — это конверсия, а не абуз, и по журналу она встречается впятеро
    чаще реальных нарушений.
    """
    user_uuid = sync_result.get("user_uuid")
    hwid = sync_result.get("hwid")
    if not user_uuid or not hwid or not db_service.is_connected:
        return
    if not config_service.get("violations_enabled", True):
        return

    try:
        groups = await db_service.get_shared_hwids_for_user(str(user_uuid))
    except Exception as e:  # noqa: BLE001
        logger.debug("HWID reuse check failed for %s: %s", user_uuid, e)
        return

    group = next((g for g in groups if g.get("hwid") == hwid), None)
    others = (group or {}).get("other_users") or []
    if not others:
        return

    # Устройство уже в чёрном списке — про него скажет блеклист-путь, и скажет
    # больше: кого отключили. Два сообщения об одном событии админу не нужны.
    try:
        if await db_service.check_hwids_against_blacklist([str(hwid)]):
            return
    except Exception as e:  # noqa: BLE001
        logger.debug("HWID blacklist pre-check failed for %s: %s", hwid, e)

    self_key = _person_key(group.get("self_telegram_id"), group.get("self_email"), str(user_uuid))
    self_trial = bool(group.get("self_is_trial"))

    strangers, repeat_trials = [], []
    for other in others:
        key = _person_key(other.get("telegram_id"), other.get("email"), other.get("uuid", ""))
        if key != self_key:
            strangers.append(other)
        elif self_trial and other.get("is_trial"):
            repeat_trials.append(other)

    if not strangers and not repeat_trials:
        return

    # Дотягиваем то, чего нет в связке: как выглядит само устройство и что за
    # подписка у принимающего аккаунта — без этого карточка получается пустой
    device = None
    target: Dict[str, Any] = {"uuid": str(user_uuid), "is_trial": self_trial,
                              "telegram_id": group.get("self_telegram_id"),
                              "email": group.get("self_email")}
    try:
        devices = await db_service.get_user_hwid_devices(str(user_uuid))
        device = next((d for d in devices if d.get("hwid") == hwid), None)
        info = (await db_service.batch_get_users_info([str(user_uuid)])).get(str(user_uuid)) or {}
        target["username"] = info.get("username")
        target["status"] = info.get("status")
        target["expire_at"] = info.get("expireAt") or info.get("expire_at")
    except Exception as e:  # noqa: BLE001
        logger.debug("HWID reuse card details failed for %s: %s", user_uuid, e)

    from web.backend.core.hwid_cards import reuse_card
    from web.backend.core.notification_service import create_notification
    try:
        await create_notification(
            title="Повторная пробная с того же устройства" if repeat_trials
                  else "HWID переехал на другой аккаунт",
            body=reuse_card(str(hwid), target, repeat_trials, strangers, device),
            type="alert",
            severity="critical" if repeat_trials else "warning",
            link="/violations",
            source="hwid_reuse",
            source_id=str(hwid),
            channels=["in_app", "telegram", "push"],
            topic_type="violations",
            event="violation.hwid_reused",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("HWID reuse notification failed: %s", e)


@router.post("/webhook")
async def collector_webhook(request: Request):
    """Webhook proxy: sync to DB, then forward to bot for Telegram notifications."""
    body = await request.body()

    if not _verify_webhook_signature(request, body):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        data = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event = data.get("event", "")
    event_data = data.get("data", {})

    logger.info("Webhook received: %s", event)

    # 1. Sync to DB (collector owns sync)
    sync_result = None
    try:
        from shared.sync import sync_service
        sync_result = await sync_service.handle_webhook_event(event, event_data)
        if event == "user_hwid_devices.added":
            await _notify_hwid_reuse(sync_result or {})
    except Exception as e:
        logger.warning("Webhook sync failed for %s: %s", event, e)

    # Diff едет боту вместе с событием. Бот сам старое состояние уже не
    # достанет: коллектор только что записал новое в общую базу, и повторное
    # сравнение «база против панели» даёт пусто — уведомление выходило с
    # «Изменения не определены», хотя поле реально поменялось.
    forward_body = body
    if isinstance(sync_result, dict) and (sync_result.get("old_data") or sync_result.get("changes")):
        try:
            enriched = dict(data)
            enriched["diff"] = {
                "old_data": sync_result.get("old_data"),
                "changes": sync_result.get("changes") or [],
            }
            forward_body = json.dumps(enriched, default=str).encode("utf-8")
        except Exception as e:
            logger.debug("Webhook diff attach failed for %s: %s", event, e)

    # 2. Forward to bot for Telegram notifications (fire-and-forget)
    # Uses INTERNAL_API_SECRET instead of X-Remnawave-Signature
    bot_callback_url = os.environ.get("BOT_CALLBACK_URL", "http://bot:8080/internal/panel-event")
    internal_secret = os.environ.get("INTERNAL_API_SECRET", "")
    if internal_secret:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    bot_callback_url,
                    content=forward_body,
                    headers={
                        "content-type": "application/json",
                        "X-Internal-Api-Secret": internal_secret,
                    },
                )
                if resp.status_code != 200:
                    logger.warning("Bot callback forward failed: %d", resp.status_code)
        except Exception as e:
            logger.warning("Bot callback forward error: %s", e)
    else:
        # Fallback: forward raw webhook to legacy bot webhook (deprecated)
        logger.warning(
            "DEPRECATED: INTERNAL_API_SECRET is not set. "
            "Falling back to legacy BOT_WEBHOOK_URL (%s). "
            "Set INTERNAL_API_SECRET in .env and remove BOT_WEBHOOK_URL to use the new "
            "internal API proxy (adds RBAC, quota enforcement, and audit logging).",
            os.environ.get("BOT_WEBHOOK_URL", "http://bot:8080/webhook"),
        )
        bot_webhook_url = os.environ.get("BOT_WEBHOOK_URL", "http://bot:8080/webhook")
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    bot_webhook_url,
                    content=body,
                    headers={
                        "content-type": "application/json",
                        "x-remnawave-signature": request.headers.get("x-remnawave-signature", ""),
                    },
                )
                if resp.status_code != 200:
                    logger.warning("Bot webhook forward failed: %d", resp.status_code)
        except Exception as e:
            logger.warning("Bot webhook forward error: %s", e)

    return JSONResponse(status_code=200, content={"status": "ok", "event": event})

"""
Collector API для приёма данных о подключениях от Node Agent.

Endpoint: POST /batch
Аутентификация: Bearer token (токен агента из таблицы nodes.agent_token)

Заменяет аналогичный endpoint из бота (src/services/collector.py),
перенося всю логику violation detection в web backend.
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from shared.database import db_service
from shared.connection_monitor import ConnectionMonitor
from shared.violation_detector import IntelligentViolationDetector
from shared.agent_tokens import get_node_by_token
from shared.config_service import config_service

logger = logging.getLogger(__name__)

# Инициализируем сервисы (синглтоны на уровне модуля)
connection_monitor = ConnectionMonitor(db_service)
violation_detector = IntelligentViolationDetector(db_service, connection_monitor)

# Per-user cooldown for violation checks (avoid re-checking every 30s batch)
_violation_check_cooldown: dict[str, datetime] = {}
VIOLATION_CHECK_COOLDOWN_MINUTES = 15
MAX_COOLDOWN_SIZE = 10000

# Periodic cleanup of old violations
_last_violation_cleanup: datetime = datetime.min

# Periodic cleanup of old metrics snapshots and connections
_last_metrics_cleanup: datetime = datetime.min
CLEANUP_INTERVAL_HOURS = 24
METRICS_RETENTION_DAYS = 30
CONNECTIONS_RETENTION_DAYS = 30

# Semaphore: limit concurrent background violation detection batches
_violation_semaphore = asyncio.Semaphore(3)

# Кэш имён нод: {node_uuid: node_name}
_node_name_cache: dict[str, str] = {}


async def _get_node_name(node_uuid: str) -> str:
    """Вернуть имя ноды по UUID (с кэшем). Fallback — первые 8 символов UUID."""
    if node_uuid not in _node_name_cache:
        try:
            node = await db_service.get_node_by_uuid(node_uuid)
            _node_name_cache[node_uuid] = node.get("name") or node_uuid[:8] if node else node_uuid[:8]
        except Exception:
            return node_uuid[:8]
    return _node_name_cache[node_uuid]

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


class TorrentEventReport(BaseModel):
    """Торрент-событие от агента."""
    user_email: str
    ip_address: str
    destination: str
    inbound_tag: str = ""
    outbound_tag: str = "TORRENT"
    node_uuid: str
    detected_at: datetime


class BatchReport(BaseModel):
    """Батч подключений от одной ноды."""
    node_uuid: str
    timestamp: datetime
    connections: list[ConnectionReport] = Field(default=[], max_length=5000)
    torrent_events: list[TorrentEventReport] = Field(default=[], max_length=1000)
    system_metrics: Optional[SystemMetricsReport] = None


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
    client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else "unknown"
    )

    logger.debug("Verifying agent token (length: %d) from %s", len(authorization) if authorization else 0, client_ip)

    if not authorization.startswith("Bearer "):
        logger.warning("Invalid authorization header format from %s", client_ip)
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = authorization[7:].strip()
    if not token:
        logger.warning("Token is empty, from %s", client_ip)
        raise HTTPException(status_code=401, detail="Token is required")

    node_uuid = await get_node_by_token(db_service, token)
    if not node_uuid:
        node_name_hint = ""
        try:
            async with db_service.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT name, address FROM nodes WHERE address LIKE $1 LIMIT 1",
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
        raise HTTPException(status_code=403, detail="Invalid or expired token")

    logger.debug("Agent token verified for node: %s from %s", node_uuid, client_ip)
    return node_uuid


# ── Endpoints ────────────────────────────────────────────────────


@router.post("/batch")
async def receive_connections(
    report: BatchReport,
    request: Request,
    node_uuid: str = Depends(verify_agent_token),
):
    """Принимает батч подключений от Node Agent."""
    node_name = await _get_node_name(node_uuid)
    logger.info(
        "Batch received: node=%s connections=%d metrics=%s",
        node_name, len(report.connections) if report.connections else 0,
        "yes" if report.system_metrics else "no",
    )

    if report.node_uuid != node_uuid:
        logger.warning("Node UUID mismatch: token=%s, report=%s", node_uuid, report.node_uuid)
        raise HTTPException(status_code=403, detail="Token does not match the reported node UUID")

    # System metrics
    if report.system_metrics:
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
                )
            except Exception:
                pass  # Non-critical, don't block collector
        except Exception as e:
            logger.warning("Failed to update system metrics for node %s: %s", node_uuid, e)

    # Periodic cleanup of old data (once per 24h)
    global _last_metrics_cleanup
    now = datetime.utcnow()
    if (now - _last_metrics_cleanup).total_seconds() > CLEANUP_INTERVAL_HOURS * 3600:
        _last_metrics_cleanup = now
        try:
            deleted = await db_service.cleanup_old_metrics_snapshots(METRICS_RETENTION_DAYS)
            if deleted > 0:
                logger.info("Cleaned up %d old metrics snapshots", deleted)
        except Exception:
            pass
        try:
            deleted = await db_service.cleanup_old_connections(CONNECTIONS_RETENTION_DAYS)
            if deleted > 0:
                logger.info("Cleaned up %d old connections", deleted)
        except Exception:
            pass
        try:
            deleted = await db_service.cleanup_old_torrent_events(90)
            if deleted > 0:
                logger.info("Cleaned up %d old torrent events", deleted)
        except Exception:
            pass

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
                    "bytes_sent": conn.bytes_sent,
                    "bytes_received": conn.bytes_received,
                    "connected_at": conn.connected_at.isoformat() if conn.connected_at else None,
                    "disconnected_at": conn.disconnected_at.isoformat() if conn.disconnected_at else None,
                },
                "connected_at": conn.connected_at,
            })

        if batch_connections:
            try:
                result = await db_service.batch_upsert_connections(
                    batch_connections, stale_threshold_minutes=2
                )
                processed = result["upserted"]
                logger.info(
                    "Batch upserted: node=%s upserted=%d closed_stale=%d errors=%d",
                    node_name, result["upserted"], result["closed_stale"], errors,
                )
            except Exception as e:
                logger.error("Batch upsert failed for node %s: %s", node_name, e, exc_info=True)
                errors += len(batch_connections)

    if errors > 0:
        logger.warning("Batch processed with errors: node=%s total=%d processed=%d errors=%d",
                       node_uuid, len(report.connections), processed, errors)

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
            asyncio.create_task(
                _run_violation_detection(affected_user_uuids)
            )
        except Exception as e:
            logger.warning("Error in post-processing: %s", e)

    # ── Torrent events processing ──────────────────────────
    torrent_processed = 0
    if report.torrent_events:
        torrent_enabled = config_service.get("torrent_detection_enabled", True)
        if torrent_enabled:
            # Resolve user UUIDs and build batch
            batch_events = []
            for event in report.torrent_events:
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
                    })
                except Exception as e:
                    logger.warning("Error resolving torrent event for %s: %s", event.user_email, e)

            if batch_events:
                torrent_processed = await db_service.batch_save_torrent_events(batch_events)

            if torrent_processed > 0:
                logger.warning(
                    "Torrent events: node=%s count=%d", node_name, torrent_processed
                )
                asyncio.create_task(
                    _process_torrent_violations(report.torrent_events, user_uuid_cache)
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
        # Group events by user
        events_by_user: dict[str, list[TorrentEventReport]] = {}
        for event in events:
            user_uuid = user_uuid_cache.get(event.user_email)
            if user_uuid:
                events_by_user.setdefault(user_uuid, []).append(event)

        auto_action = config_service.get("torrent_auto_action", "notify")

        for user_uuid, user_events in events_by_user.items():
            try:
                # Dedup: skip if torrent violation exists within last 10 min
                existing = await db_service.get_recent_torrent_violation(user_uuid, minutes=10)
                if existing:
                    continue

                user_info = await db_service.get_user_by_uuid(user_uuid)
                username = user_info.get("username", "n/a") if user_info else "n/a"
                email = user_info.get("email") if user_info else None
                telegram_id = user_info.get("telegramId") if user_info else None

                destinations = list(set(e.destination for e in user_events))
                ips = list(set(e.ip_address for e in user_events))

                # Save as violation (score=100)
                violation_id = await db_service.save_violation(
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
                except Exception:
                    pass

                # Auto-block if configured
                if auto_action == "block_user":
                    try:
                        from shared.api_client import api_client
                        await api_client.disable_user(user_uuid)
                        logger.info("Auto-blocked user %s for torrent usage", user_uuid)
                    except Exception as e:
                        logger.warning("Failed to auto-block user %s: %s", user_uuid, e)

            except Exception as e:
                logger.warning("Error processing torrent violation for user %s: %s", user_uuid, e)

    except Exception as e:
        logger.error("Background torrent violation processing failed: %s", e)


async def _check_single_user(user_uuid: str, min_score: float, sem: asyncio.Semaphore, cooldown_override: Optional[int] = None):
    """Check a single user for violations (with semaphore for concurrency control)."""
    async with sem:
        try:
            # Whitelist check
            whitelisted, excluded_analyzers = await db_service.is_user_violation_whitelisted(user_uuid)
            if whitelisted and excluded_analyzers is None:
                return

            # Per-user cooldown (adaptive or config-based)
            now_check = datetime.utcnow()
            last_check = _violation_check_cooldown.get(user_uuid)
            cooldown_minutes = cooldown_override if cooldown_override is not None else config_service.get("violation_check_cooldown_minutes", VIOLATION_CHECK_COOLDOWN_MINUTES)
            if last_check and (now_check - last_check).total_seconds() < cooldown_minutes * 60:
                return

            stats = await connection_monitor.get_user_connection_stats(user_uuid, window_minutes=60)
            if stats:
                logger.debug(
                    "Connection stats for user %s: active=%d, unique_ips=%d, simultaneous=%d",
                    user_uuid, stats.active_connections_count,
                    stats.unique_ips_in_window, stats.simultaneous_connections,
                )

            violation_score = await violation_detector.check_user(
                user_uuid, window_minutes=60, excluded_analyzers=excluded_analyzers
            )

            had_violation = bool(violation_score and violation_score.total >= min_score)

            # Ставим кулдаун только если нарушений нет — при нарушении проверяем каждый раз
            if not had_violation:
                # Evict oldest 20% entries if cooldown dict is too large
                if len(_violation_check_cooldown) > MAX_COOLDOWN_SIZE:
                    sorted_keys = sorted(_violation_check_cooldown, key=_violation_check_cooldown.get)
                    for k in sorted_keys[:len(sorted_keys) // 5]:
                        _violation_check_cooldown.pop(k, None)
                _violation_check_cooldown[user_uuid] = datetime.utcnow()
            else:
                # Сбрасываем кулдаун чтобы не пропустить продолжение нарушения
                _violation_check_cooldown.pop(user_uuid, None)

            if had_violation:
                logger.warning(
                    "Violation detected: user=%s score=%.1f action=%s reasons=%s",
                    user_uuid, violation_score.total,
                    violation_score.recommended_action.value,
                    violation_score.reasons[:3],
                )

                active_conns = await connection_monitor.get_user_active_connections(user_uuid, max_age_minutes=5)
                user_info = await db_service.get_user_by_uuid(user_uuid)

                ip_metadata = {}
                if active_conns:
                    try:
                        from shared.geoip import get_geoip_service
                        geoip = get_geoip_service()
                        unique_ips = list(set(str(c.ip_address) for c in active_conns))
                        ip_metadata = await geoip.lookup_batch(unique_ips)
                    except Exception as geo_error:
                        logger.debug("Failed to get GeoIP data: %s", geo_error)

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

                    ip_addresses = list(set(str(c.ip_address) for c in active_conns)) if active_conns else None
                    username = user_info.get("username") if user_info else None
                    email = user_info.get("email") if user_info else None
                    telegram_id = user_info.get("telegram_id") if user_info else None
                    device_limit = user_info.get("hwidDeviceLimit", 1) if user_info else 1

                    await db_service.save_violation(
                        user_uuid=user_uuid,
                        score=violation_score.total,
                        recommended_action=violation_score.recommended_action.value,
                        username=username,
                        email=email,
                        telegram_id=telegram_id,
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
                    )
                    logger.info("Violation saved to DB for user %s: score=%.1f", user_uuid, violation_score.total)
                except Exception as save_error:
                    logger.warning("Failed to save violation to DB for user %s: %s", user_uuid, save_error)
            else:
                if violation_score:
                    logger.info("User %s: score=%.1f (below threshold %.1f)", user_uuid, violation_score.total, min_score)
        except Exception as e:
            logger.warning("Error checking violations for user %s: %s", user_uuid, e)


async def _run_violation_detection(affected_user_uuids: set):
    """Background task: check affected users for violations (parallel with semaphore)."""
    async with _violation_semaphore:
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

            # Adaptive concurrency and cooldown based on total tracked users
            total_tracked = len(_violation_check_cooldown) + len(affected_user_uuids)
            if total_tracked > 10000:
                max_concurrent = 3
                adaptive_cooldown = 30
            elif total_tracked > 5000:
                max_concurrent = 5
                adaptive_cooldown = 15
            elif total_tracked > 1000:
                max_concurrent = 7
                adaptive_cooldown = 10
            else:
                max_concurrent = 10
                adaptive_cooldown = None  # use config default

            user_sem = asyncio.Semaphore(max_concurrent)
            await asyncio.gather(
                *(_check_single_user(uuid, min_score, user_sem, adaptive_cooldown) for uuid in affected_user_uuids),
                return_exceptions=True,
            )

            # Periodic cleanup of old violations
            global _last_violation_cleanup
            if (datetime.utcnow() - _last_violation_cleanup).total_seconds() > 3600:
                retention_days = config_service.get("violation_retention_days", 90)
                cleaned = await db_service.cleanup_old_violations(retention_days)
                if cleaned:
                    logger.info("Cleaned up %d old violations (retention: %d days)", cleaned, retention_days)
                _last_violation_cleanup = datetime.utcnow()

        except Exception as e:
            logger.error("Background violation detection failed: %s", e)


@router.get("/health")
async def collector_health():
    """Health check endpoint."""
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "service": "collector", "database_connected": db_service.is_connected},
    )

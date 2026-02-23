"""
Collector API для приёма данных о подключениях от Node Agent.

Endpoint: POST /batch
Аутентификация: Bearer token (токен агента из таблицы nodes.agent_token)

Заменяет аналогичный endpoint из бота (src/services/collector.py),
перенося всю логику violation detection в web backend.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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
VIOLATION_CHECK_COOLDOWN_MINUTES = 5

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


class BatchReport(BaseModel):
    """Батч подключений от одной ноды."""
    node_uuid: str
    timestamp: datetime
    connections: list[ConnectionReport] = []
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
        except Exception:
            pass
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
    logger.debug(
        "Batch received: node=%s connections=%d metrics=%s",
        node_uuid[:8], len(report.connections) if report.connections else 0,
        "yes" if report.system_metrics else "no",
    )

    if report.node_uuid != node_uuid:
        logger.warning("Node UUID mismatch: token=%s, report=%s", node_uuid, report.node_uuid)
        raise HTTPException(status_code=403, detail=f"Token does not match node UUID. Expected: {node_uuid}")

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
        except Exception as e:
            logger.warning("Failed to update system metrics for node %s: %s", node_uuid, e)

    if not report.connections:
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "processed": 0, "message": "No connections to process",
                     "metrics_updated": report.system_metrics is not None},
        )

    # Per-batch UUID cache
    user_uuid_cache: dict[str, Optional[str]] = {}

    async def _cached_find_user(identifier: str) -> Optional[str]:
        if identifier not in user_uuid_cache:
            user_uuid_cache[identifier] = await _find_user_uuid_by_identifier(identifier)
        return user_uuid_cache[identifier]

    # Process connections
    processed = 0
    errors = 0

    for conn in report.connections:
        try:
            user_uuid = await _cached_find_user(conn.user_email)
            if not user_uuid:
                logger.warning("User not found for identifier=%s, skipping", conn.user_email)
                errors += 1
                continue

            connection_id = await db_service.add_user_connection(
                user_uuid=user_uuid,
                ip_address=conn.ip_address,
                node_uuid=conn.node_uuid,
                device_info={
                    "user_email": conn.user_email,
                    "bytes_sent": conn.bytes_sent,
                    "bytes_received": conn.bytes_received,
                    "connected_at": conn.connected_at.isoformat() if conn.connected_at else None,
                    "disconnected_at": conn.disconnected_at.isoformat() if conn.disconnected_at else None,
                },
                connected_at=conn.connected_at,
            )

            if connection_id:
                logger.debug("Connection recorded: id=%d user=%s ip=%s", connection_id, conn.user_email, conn.ip_address)
                processed += 1
            else:
                errors += 1

        except Exception as e:
            logger.error("Error processing connection for %s: %s", conn.user_email, e, exc_info=True)
            errors += 1

    if errors > 0:
        logger.warning("Batch processed with errors: node=%s total=%d processed=%d errors=%d",
                       node_uuid, len(report.connections), processed, errors)
    else:
        logger.debug("Batch processed: node=%s total=%d processed=%d", node_uuid[:8], len(report.connections), processed)

    # Post-processing: auto-close old connections + violation detection
    if processed > 0:
        try:
            affected_user_uuids = set()
            new_connections_by_user: dict[str, set[str]] = {}

            for conn in report.connections:
                user_uuid = await _cached_find_user(conn.user_email)
                if user_uuid:
                    affected_user_uuids.add(user_uuid)
                    if user_uuid not in new_connections_by_user:
                        new_connections_by_user[user_uuid] = set()
                    new_connections_by_user[user_uuid].add(str(conn.ip_address))

            # Auto-close old connections (>5 min without activity)
            for user_uuid in affected_user_uuids:
                try:
                    active_connections = await db_service.get_user_active_connections(user_uuid, limit=1000, max_age_minutes=5)
                    now = datetime.utcnow()
                    closed_count = 0
                    new_ips = new_connections_by_user.get(user_uuid, set())

                    for active_conn in active_connections:
                        conn_time = active_conn.get("connected_at")
                        if not conn_time:
                            continue
                        if isinstance(conn_time, str):
                            try:
                                conn_time = datetime.fromisoformat(conn_time.replace("Z", "+00:00"))
                            except ValueError:
                                continue
                        if not isinstance(conn_time, datetime):
                            continue
                        if conn_time.tzinfo:
                            conn_time = conn_time.replace(tzinfo=None)

                        age_minutes = (now - conn_time).total_seconds() / 60
                        if age_minutes > 5:
                            conn_ip = str(active_conn.get("ip_address", ""))
                            if conn_ip not in new_ips:
                                conn_id = active_conn.get("id")
                                if conn_id:
                                    await db_service.close_user_connection(conn_id)
                                    closed_count += 1

                    if closed_count > 0:
                        logger.debug("Auto-closed %d old connections for user %s", closed_count, user_uuid)
                except Exception as e:
                    logger.warning("Error auto-closing connections for user %s: %s", user_uuid, e, exc_info=True)

            # Violation detection for each affected user
            violations_enabled = config_service.get("violations_enabled", True)
            min_score = config_service.get("violations_min_score", 50.0)

            # Cleanup stale cooldown entries (older than 1h)
            now_cleanup = datetime.utcnow()
            expired_keys = [k for k, v in _violation_check_cooldown.items()
                           if (now_cleanup - v).total_seconds() > 3600]
            for k in expired_keys:
                del _violation_check_cooldown[k]

            for user_uuid in affected_user_uuids:
                if not violations_enabled:
                    break

                # Whitelist check: skip detection for whitelisted users
                if await db_service.is_user_violation_whitelisted(user_uuid):
                    continue

                # Per-user cooldown: skip if already checked recently
                now_check = datetime.utcnow()
                last_check = _violation_check_cooldown.get(user_uuid)
                if last_check and (now_check - last_check).total_seconds() < VIOLATION_CHECK_COOLDOWN_MINUTES * 60:
                    logger.debug("Violation check cooldown active for user %s, skipping", user_uuid)
                    continue

                try:
                    # Connection stats (для violations.log)
                    stats = await connection_monitor.get_user_connection_stats(user_uuid, window_minutes=60)
                    if stats:
                        logger.debug(
                            "Connection stats for user %s: active=%d, unique_ips=%d, simultaneous=%d",
                            user_uuid, stats.active_connections_count,
                            stats.unique_ips_in_window, stats.simultaneous_connections,
                        )

                    violation_score = await violation_detector.check_user(user_uuid, window_minutes=60)

                    # Update cooldown regardless of score
                    _violation_check_cooldown[user_uuid] = datetime.utcnow()

                    if violation_score and violation_score.total >= min_score:
                        logger.warning(
                            "Violation detected: user=%s score=%.1f action=%s reasons=%s",
                            user_uuid, violation_score.total,
                            violation_score.recommended_action.value,
                            violation_score.reasons[:3],
                        )

                        # Fetch data once for both notification and DB save
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

                        # Send notification via web backend notification_service
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

                        # Save violation to DB
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
                            logger.debug("Violation saved to DB for user %s: score=%.1f", user_uuid, violation_score.total)
                        except Exception as save_error:
                            logger.warning("Failed to save violation to DB for user %s: %s", user_uuid, save_error)
                    else:
                        if violation_score:
                            logger.debug("User %s: score=%.1f (below threshold)", user_uuid, violation_score.total)
                except Exception as e:
                    logger.warning("Error checking violations for user %s: %s", user_uuid, e)
        except Exception as e:
            logger.warning("Error in post-processing: %s", e)

    return JSONResponse(
        status_code=200,
        content={"status": "ok", "processed": processed, "errors": errors, "node_uuid": node_uuid},
    )


@router.get("/health")
async def collector_health():
    """Health check endpoint."""
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "service": "collector", "database_connected": db_service.is_connected},
    )

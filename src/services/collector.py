"""
Collector API для приёма данных о подключениях от Node Agent.

Endpoint: POST /api/v1/connections/batch
Аутентификация: Bearer token (токен агента из таблицы nodes.agent_token)
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from aiogram import Bot

from src.services.database import db_service
from src.services.connection_monitor import ConnectionMonitor
from src.services.violation_detector import IntelligentViolationDetector
from src.utils.agent_tokens import get_node_by_token
from src.utils.logger import logger
from src.utils.notifications import send_violation_notification

# Инициализируем сервисы
connection_monitor = ConnectionMonitor(db_service)
violation_detector = IntelligentViolationDetector(db_service, connection_monitor)


router = APIRouter(prefix="/api/v1/connections", tags=["collector"])


class ConnectionReport(BaseModel):
    """Одно подключение от агента."""
    user_email: str
    ip_address: str
    node_uuid: str
    connected_at: datetime
    disconnected_at: Optional[datetime] = None
    bytes_sent: int = 0
    bytes_received: int = 0


class BatchReport(BaseModel):
    """Батч подключений от одной ноды."""
    node_uuid: str
    timestamp: datetime
    connections: list[ConnectionReport] = []


async def _find_user_uuid_by_identifier(identifier: str) -> Optional[str]:
    """
    Вспомогательная функция для поиска user_uuid по различным идентификаторам.
    
    Args:
        identifier: Email или формат "user_XXX" (где XXX - ID пользователя)
    
    Returns:
        UUID пользователя или None
    """
    user_uuid = None
    
    # Если это формат "user_XXX", извлекаем ID
    if identifier.startswith("user_"):
        user_id_str = identifier.replace("user_", "")
        # Пытаемся найти по short_uuid (может быть числовой ID)
        user = await db_service.get_user_by_short_uuid(user_id_str)
        if user:
            user_uuid = user.get("uuid")
    
    # Если не нашли, пытаемся найти по email (обычный формат)
    if not user_uuid:
        user_uuid = await db_service.get_user_uuid_by_email(identifier)
    
    # Если всё ещё не нашли, пытаемся найти в raw_data по ID
    if not user_uuid and identifier.startswith("user_"):
        user_id_str = identifier.replace("user_", "")
        user_uuid = await db_service.get_user_uuid_by_id_from_raw_data(user_id_str)
    
    return user_uuid


async def verify_agent_token(authorization: str = Header(..., alias="Authorization")) -> str:
    """
    Проверяет токен агента из заголовка Authorization: Bearer {token}.
    Возвращает node_uuid если токен валиден.
    """
    logger.debug("Verifying agent token (length: %d)", len(authorization) if authorization else 0)
    
    if not authorization.startswith("Bearer "):
        logger.warning("Invalid authorization header format")
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    
    token = authorization[7:].strip()  # Убираем "Bearer "
    if not token:
        logger.warning("Token is empty")
        raise HTTPException(status_code=401, detail="Token is required")
    
    # Проверяем токен в БД
    node_uuid = await get_node_by_token(db_service, token)
    if not node_uuid:
        logger.warning("Invalid agent token attempted: %s", token[:8] + "...")
        raise HTTPException(status_code=403, detail="Invalid or expired token")
    
    logger.debug("Agent token verified for node: %s", node_uuid)
    return node_uuid


@router.post("/batch")
async def receive_connections(
    report: BatchReport,
    request: Request,
    node_uuid: str = Depends(verify_agent_token),
):
    """
    Принимает батч подключений от Node Agent.
    
    Проверяет:
    1. Токен агента (через verify_agent_token)
    2. Соответствие node_uuid из токена и из тела запроса
    
    Записывает подключения в таблицу user_connections.
    """
    # Логируем только на уровне DEBUG для уменьшения шума в логах
    logger.debug(
        "Received batch request: node_uuid=%s connections_count=%d",
        node_uuid,
        len(report.connections) if report.connections else 0
    )
    # Проверяем что node_uuid из токена совпадает с node_uuid в запросе
    if report.node_uuid != node_uuid:
        logger.warning(
            "Node UUID mismatch: token=%s, report=%s",
            node_uuid,
            report.node_uuid
        )
        raise HTTPException(
            status_code=403,
            detail=f"Token does not match node UUID. Expected: {node_uuid}"
        )
    
    if not report.connections:
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "processed": 0, "message": "No connections to process"}
        )
    
    # Записываем подключения в БД
    processed = 0
    errors = 0
    
    for conn in report.connections:
        try:
            # Пытаемся найти пользователя по разным идентификаторам
            user_uuid = await _find_user_uuid_by_identifier(conn.user_email)
            
            if not user_uuid:
                logger.warning(
                    "User not found for identifier=%s, skipping connection",
                    conn.user_email
                )
                errors += 1
                continue
            
            # Записываем подключение
            # Используем время из логов агента, чтобы сохранить микросекунды
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
                connected_at=conn.connected_at  # Передаём время из логов агента
            )
            
            if connection_id:
                logger.debug(
                    "Connection recorded: id=%d user=%s ip=%s node=%s",
                    connection_id,
                    conn.user_email,
                    conn.ip_address,
                    conn.node_uuid
                )
                processed += 1
            else:
                errors += 1
                
        except Exception as e:
            logger.error("Error processing connection for %s: %s", conn.user_email, e, exc_info=True)
            errors += 1
    
    # Логируем только если есть ошибки или на уровне DEBUG
    if errors > 0:
        logger.warning(
            "Batch processed with errors: node=%s connections=%d processed=%d errors=%d",
            node_uuid,
            len(report.connections),
            processed,
            errors
        )
    else:
        logger.debug(
            "Batch processed: node=%s connections=%d processed=%d",
            node_uuid,
            len(report.connections),
            processed
        )
    
    # После обработки подключений автоматически закрываем старые подключения
    # (старше 5 минут без активности) для пользователей, у которых появились новые подключения
    # Это необходимо, так как агент не видит события отключения в логах Xray
    if processed > 0:
        try:
            # Собираем UUID пользователей, для которых были записаны подключения
            affected_user_uuids = set()
            # Также собираем информацию о новых подключениях по IP для каждого пользователя
            new_connections_by_user = {}  # {user_uuid: set(ip_addresses)}
            
            for conn in report.connections:
                user_uuid = await _find_user_uuid_by_identifier(conn.user_email)
                if user_uuid:
                    affected_user_uuids.add(user_uuid)
                    if user_uuid not in new_connections_by_user:
                        new_connections_by_user[user_uuid] = set()
                    new_connections_by_user[user_uuid].add(str(conn.ip_address))
            
            # Закрываем старые подключения (старше 5 минут) для этих пользователей
            for user_uuid in affected_user_uuids:
                try:
                    # Получаем активные подключения пользователя (только за последние 5 минут)
                    active_connections = await db_service.get_user_active_connections(user_uuid, limit=1000, max_age_minutes=5)
                    now = datetime.utcnow()
                    closed_count = 0
                    new_ips = new_connections_by_user.get(user_uuid, set())
                    
                    for active_conn in active_connections:
                        conn_time = active_conn.get("connected_at")
                        if not conn_time:
                            continue
                        
                        # Преобразуем в datetime если нужно
                        if isinstance(conn_time, str):
                            try:
                                conn_time = datetime.fromisoformat(conn_time.replace('Z', '+00:00'))
                            except ValueError:
                                continue
                        
                        if not isinstance(conn_time, datetime):
                            continue
                        
                        # Убираем timezone для сравнения
                        if conn_time.tzinfo:
                            conn_time = conn_time.replace(tzinfo=None)
                        
                        # Если подключение старше 5 минут и нет новых подключений с этим IP,
                        # считаем его устаревшим и закрываем
                        age_minutes = (now - conn_time).total_seconds() / 60
                        if age_minutes > 5:
                            conn_ip = str(active_conn.get("ip_address", ""))
                            # Если нет новых подключений с этим IP, закрываем старое
                            if conn_ip not in new_ips:
                                conn_id = active_conn.get("id")
                                if conn_id:
                                    await db_service.close_user_connection(conn_id)
                                    closed_count += 1
                    
                    if closed_count > 0:
                        logger.debug(
                            "Auto-closed %d old connections for user %s",
                            closed_count,
                            user_uuid
                        )
                except Exception as e:
                    logger.warning("Error auto-closing old connections for user %s: %s", user_uuid, e, exc_info=True)
            
            # Обновляем статистику и проверяем нарушения для каждого затронутого пользователя
            
            # Обновляем статистику и проверяем нарушения для каждого затронутого пользователя
            for user_uuid in affected_user_uuids:
                try:
                    stats = await connection_monitor.get_user_connection_stats(user_uuid, window_minutes=60)
                    if stats:
                        logger.debug(
                            "Connection stats for user %s: active=%d, unique_ips=%d, simultaneous=%d",
                            user_uuid,
                            stats.active_connections_count,
                            stats.unique_ips_in_window,
                            stats.simultaneous_connections
                        )
                    
                    # Проверяем нарушения
                    violation_score = await violation_detector.check_user(user_uuid, window_minutes=60)
                    if violation_score:
                        if violation_score.total >= violation_detector.THRESHOLDS['monitor']:
                            logger.warning(
                                "Violation detected for user %s: score=%.1f, action=%s, reasons=%s",
                                user_uuid,
                                violation_score.total,
                                violation_score.recommended_action.value,
                                violation_score.reasons[:3]
                            )

                            # Отправляем уведомление в Telegram топик
                            try:
                                bot: Bot | None = getattr(request.app.state, 'bot', None)
                                if bot:
                                    violation_dict = {
                                        'total': violation_score.total,
                                        'recommended_action': violation_score.recommended_action,
                                        'reasons': violation_score.reasons,
                                        'breakdown': violation_score.breakdown,
                                        'confidence': violation_score.confidence,
                                    }

                                    # Получаем информацию о пользователе из БД
                                    user_info = await db_service.get_user_by_uuid(user_uuid)

                                    # Получаем активные подключения для уведомления
                                    active_connections = await connection_monitor.get_user_active_connections(
                                        user_uuid, max_age_minutes=5
                                    )

                                    # Получаем GeoIP метаданные для IP адресов
                                    ip_metadata = {}
                                    if active_connections:
                                        try:
                                            from src.services.geoip import get_geoip_service
                                            geoip = get_geoip_service()
                                            unique_ips = list(set(str(c.ip_address) for c in active_connections))
                                            ip_metadata = await geoip.lookup_batch(unique_ips)
                                        except Exception as geo_error:
                                            logger.debug("Failed to get GeoIP data for notification: %s", geo_error)

                                    # Отправляем уведомление асинхронно (не блокируем обработку запроса)
                                    user_info = await db_service.get_user_by_uuid(user_uuid)
                                    await send_violation_notification(
                                        bot=bot,
                                        user_uuid=user_uuid,
                                        violation_score=violation_dict,
                                        user_info=user_info,
                                        active_connections=active_connections,
                                        ip_metadata=ip_metadata,
                                    )
                                else:
                                    logger.debug("Bot not available in app.state, skipping notification")
                            except Exception as notify_error:
                                logger.warning(
                                    "Failed to send violation notification for user %s: %s",
                                    user_uuid,
                                    notify_error
                                )
                        else:
                            logger.debug(
                                "User %s: score=%.1f (below threshold)",
                                user_uuid,
                                violation_score.total
                            )
                except Exception as e:
                    logger.warning(
                        "Error updating connection stats/violations for user %s: %s",
                        user_uuid,
                        e
                    )
        except Exception as e:
            logger.warning("Error updating connection stats after batch processing: %s", e)
    
    response_data = {
        "status": "ok",
        "processed": processed,
        "errors": errors,
        "node_uuid": node_uuid,
    }
    
    # Логируем ответ только на уровне DEBUG
    logger.debug("Sending response: %s", response_data)
    
    # Создаём JSONResponse с явным указанием media_type
    response = JSONResponse(
        status_code=200,
        content=response_data,
        media_type="application/json"
    )
    
    # Логируем заголовки ответа для отладки
    logger.debug("Response headers: %s", dict(response.headers))
    
    return response


@router.get("/health")
async def collector_health():
    """Проверка здоровья Collector API."""
    response_data = {
        "status": "ok",
        "service": "collector",
        "database_connected": db_service.is_connected,
    }
    logger.info("Health check requested, returning: %s", response_data)
    return JSONResponse(
        status_code=200,
        content=response_data,
        media_type="application/json"
    )


@router.post("/test")
async def collector_test():
    """Тестовый эндпоинт для проверки работы API."""
    test_data = {
        "status": "ok",
        "message": "Collector API is working",
        "test": True
    }
    logger.info("Test endpoint called, returning: %s", test_data)
    return JSONResponse(
        status_code=200,
        content=test_data,
        media_type="application/json"
    )

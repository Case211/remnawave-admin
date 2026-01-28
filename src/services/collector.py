"""
Collector API для приёма данных о подключениях от Node Agent.

Endpoint: POST /api/v1/connections/batch
Аутентификация: Bearer token (токен агента из таблицы nodes.agent_token)
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from src.services.database import db_service
from src.utils.agent_tokens import get_node_by_token
from src.utils.logger import logger


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


async def verify_agent_token(authorization: str = Header(..., alias="Authorization")) -> str:
    """
    Проверяет токен агента из заголовка Authorization: Bearer {token}.
    Возвращает node_uuid если токен валиден.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    
    token = authorization[7:].strip()  # Убираем "Bearer "
    if not token:
        raise HTTPException(status_code=401, detail="Token is required")
    
    # Проверяем токен в БД
    node_uuid = await get_node_by_token(db_service, token)
    if not node_uuid:
        logger.warning("Invalid agent token attempted: %s", token[:8] + "...")
        raise HTTPException(status_code=403, detail="Invalid or expired token")
    
    return node_uuid


@router.post("/batch")
async def receive_connections(
    report: BatchReport,
    node_uuid: str = Depends(verify_agent_token),
):
    """
    Принимает батч подключений от Node Agent.
    
    Проверяет:
    1. Токен агента (через verify_agent_token)
    2. Соответствие node_uuid из токена и из тела запроса
    
    Записывает подключения в таблицу user_connections.
    """
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
        return {"status": "ok", "processed": 0, "message": "No connections to process"}
    
    # Записываем подключения в БД
    processed = 0
    errors = 0
    
    for conn in report.connections:
        try:
            # Находим user_uuid по email
            user_uuid = await db_service.get_user_uuid_by_email(conn.user_email)
            
            if not user_uuid:
                logger.warning(
                    "User not found for email=%s, skipping connection",
                    conn.user_email
                )
                errors += 1
                continue
            
            # Записываем подключение
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
                }
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
    
    logger.info(
        "Batch processed: node=%s connections=%d processed=%d errors=%d",
        node_uuid,
        len(report.connections),
        processed,
        errors
    )
    
    return {
        "status": "ok",
        "processed": processed,
        "errors": errors,
        "node_uuid": node_uuid,
    }


@router.get("/health")
async def collector_health():
    """Проверка здоровья Collector API."""
    return {
        "status": "ok",
        "service": "collector",
        "database_connected": db_service.is_connected,
    }

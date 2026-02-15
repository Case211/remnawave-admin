"""WebSocket endpoint for real-time updates."""
import asyncio
import json
import logging
from datetime import datetime
from typing import Set, Dict, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query

from web.backend.api.deps import get_current_admin_ws, AdminUser

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Менеджер WebSocket подключений."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, admin: AdminUser):
        """Подключить клиента."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)
        logger.info(f"WebSocket connected: admin {admin.telegram_id or admin.username} ({admin.auth_method})")
        logger.info(f"Active connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Отключить клиента."""
        async with self._lock:
            self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Active: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Отправить сообщение всем подключённым клиентам."""
        if not self.active_connections:
            return

        # Сериализуем один раз
        data = json.dumps(message, default=str)

        # Отправляем всем
        disconnected = set()
        for connection in self.active_connections.copy():
            try:
                await asyncio.wait_for(connection.send_text(data), timeout=5.0)
            except Exception as e:
                logger.debug(f"Failed to send to client: {e}")
                disconnected.add(connection)

        # Удаляем отключённых
        if disconnected:
            async with self._lock:
                self.active_connections -= disconnected

    async def send_to(self, websocket: WebSocket, message: Dict[str, Any]):
        """Отправить сообщение конкретному клиенту."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.debug(f"Failed to send to client: {e}")


# Глобальный менеджер подключений
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    WebSocket endpoint для real-time обновлений.

    Подключение: ws://host/api/v2/ws?token=JWT_TOKEN

    События:
    - connection: Новое подключение пользователя
    - violation: Обнаружено нарушение
    - node_status: Изменение статуса ноды
    - user_update: Обновление пользователя
    """
    # Проверяем аутентификацию
    try:
        admin = await get_current_admin_ws(websocket, token)
    except Exception as e:
        logger.warning(f"WebSocket auth failed: {e}")
        return

    await manager.connect(websocket, admin)

    try:
        # Отправляем приветствие
        await manager.send_to(websocket, {
            "type": "connected",
            "data": {
                "message": "Connected to Remnawave Admin WebSocket",
                "timestamp": datetime.utcnow().isoformat(),
            }
        })

        # Слушаем сообщения от клиента
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0  # Timeout для проверки соединения
                )

                # Обрабатываем ping/pong
                if data == "ping":
                    await websocket.send_text("pong")
                elif data.startswith("{"):
                    # JSON сообщение
                    try:
                        msg = json.loads(data)
                        await handle_client_message(websocket, admin, msg)
                    except json.JSONDecodeError as e:
                        logger.debug("Non-critical: %s", e)

            except asyncio.TimeoutError:
                # Отправляем ping для проверки соединения
                try:
                    await websocket.send_text("ping")
                except Exception as e:
                    logger.debug("Non-critical: %s", e)
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(websocket)


async def handle_client_message(
    websocket: WebSocket,
    admin: AdminUser,
    message: Dict[str, Any]
):
    """Обработка сообщений от клиента."""
    msg_type = message.get("type")

    if msg_type == "subscribe":
        # Подписка на определённые события
        topics = message.get("topics", [])
        logger.debug(f"Admin {admin.telegram_id} subscribed to: {topics}")
        await manager.send_to(websocket, {
            "type": "subscribed",
            "data": {"topics": topics}
        })

    elif msg_type == "ping":
        await manager.send_to(websocket, {"type": "pong"})


# ==================== Функции для отправки событий ====================

async def broadcast_violation(violation_data: Dict[str, Any]):
    """Отправить событие о нарушении."""
    await manager.broadcast({
        "type": "violation",
        "data": violation_data,
        "timestamp": datetime.utcnow().isoformat(),
    })
    # Dispatch to automation engine (fire-and-forget)
    try:
        from web.backend.core.automation_engine import engine as automation_engine
        asyncio.create_task(automation_engine.handle_event("violation.detected", violation_data))
    except Exception as e:
        logger.debug("Non-critical: %s", e)


async def broadcast_connection(connection_data: Dict[str, Any]):
    """Отправить событие о подключении."""
    await manager.broadcast({
        "type": "connection",
        "data": connection_data,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def broadcast_node_status(node_data: Dict[str, Any]):
    """Отправить событие о статусе ноды."""
    await manager.broadcast({
        "type": "node_status",
        "data": node_data,
        "timestamp": datetime.utcnow().isoformat(),
    })
    # Dispatch to automation engine (fire-and-forget)
    try:
        from web.backend.core.automation_engine import engine as automation_engine
        is_connected = node_data.get("is_connected", node_data.get("isConnected", True))
        if not is_connected:
            asyncio.create_task(automation_engine.handle_event("node.went_offline", node_data))
    except Exception as e:
        logger.debug("Non-critical: %s", e)


async def broadcast_user_update(user_data: Dict[str, Any]):
    """Отправить событие об обновлении пользователя."""
    await manager.broadcast({
        "type": "user_update",
        "data": user_data,
        "timestamp": datetime.utcnow().isoformat(),
    })
    # Dispatch traffic exceeded events to automation engine (fire-and-forget)
    try:
        from web.backend.core.automation_engine import engine as automation_engine
        limit = user_data.get("traffic_limit_bytes", user_data.get("trafficLimitBytes", 0))
        used = user_data.get("used_traffic_bytes", user_data.get("usedTrafficBytes", 0))
        if limit and used and used > limit:
            asyncio.create_task(automation_engine.handle_event("user.traffic_exceeded", user_data))
    except Exception as e:
        logger.debug("Non-critical: %s", e)


async def broadcast_activity(activity_type: str, message: str, details: Dict[str, Any] = None):
    """Отправить событие активности для Live Activity feed."""
    await manager.broadcast({
        "type": "activity",
        "data": {
            "activity_type": activity_type,
            "message": message,
            "details": details or {},
        },
        "timestamp": datetime.utcnow().isoformat(),
    })


async def broadcast_agent_v2_status(node_uuid: str, is_connected: bool):
    """Broadcast agent v2 connection status change."""
    await manager.broadcast({
        "type": "agent_v2_status",
        "data": {
            "node_uuid": node_uuid,
            "connected": is_connected,
        },
        "timestamp": datetime.utcnow().isoformat(),
    })


async def broadcast_audit_event(
    admin_username: str,
    action: str,
    resource: str,
    resource_id: str = None,
):
    """Broadcast an audit log event for real-time admin notifications."""
    await manager.broadcast({
        "type": "audit",
        "data": {
            "admin_username": admin_username,
            "action": action,
            "resource": resource,
            "resource_id": resource_id,
        },
        "timestamp": datetime.utcnow().isoformat(),
    })

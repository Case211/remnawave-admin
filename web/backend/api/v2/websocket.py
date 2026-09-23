"""WebSocket endpoint for real-time updates."""
import asyncio
import json
import logging
from datetime import datetime
from typing import Set, Dict, Any, Optional, Tuple

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from web.backend.api.deps import get_current_admin_ws, ws_auth_invalid, AdminUser

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Менеджер WebSocket подключений с topic-based подписками."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._subscriptions: Dict[WebSocket, Set[str]] = {}
        self._admins: Dict[WebSocket, AdminUser] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, admin: AdminUser):
        """Подключить клиента."""
        await websocket.accept(
            subprotocol=getattr(websocket.state, "auth_subprotocol", None)
        )
        async with self._lock:
            self.active_connections.add(websocket)
            self._subscriptions[websocket] = set()
            self._admins[websocket] = admin  # для RBAC-фильтра рассылки
        logger.info(f"WebSocket connected: admin {admin.telegram_id or admin.username} ({admin.auth_method})")
        logger.info(f"Active connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        """Отключить клиента."""
        async with self._lock:
            self.active_connections.discard(websocket)
            self._subscriptions.pop(websocket, None)
            self._admins.pop(websocket, None)
        logger.info(f"WebSocket disconnected. Active: {len(self.active_connections)}")

    @staticmethod
    def _admin_can(admin: Optional[AdminUser], permission: Optional[Tuple[str, str]]) -> bool:
        """Есть ли у админа право на событие (superadmin/legacy — всегда)."""
        if permission is None:
            return True
        if admin is None:
            return False
        if getattr(admin, "account_id", None) is None or admin.role == "superadmin":
            return True
        return admin.has_permission(permission[0], permission[1])

    def subscribe(self, websocket: WebSocket, topics: list):
        """Подписать клиента на topics."""
        if websocket in self._subscriptions:
            self._subscriptions[websocket].update(topics)

    def has_subscribers(self, topic: str) -> bool:
        """Проверить есть ли подписчики на topic."""
        return any(topic in subs for subs in self._subscriptions.values())

    async def broadcast(self, message: Dict[str, Any], topic: str = None,
                        permission: Optional[Tuple[str, str]] = None):
        """Отправить сообщение клиентам (параллельно).

        topic — только подписчикам; permission (resource, action) — только тем,
        у кого есть право (RBAC-фильтр, чтобы события не текли между скоупами).
        """
        if not self.active_connections:
            return

        # Filter by topic if specified
        if topic:
            targets = {ws for ws in self.active_connections
                       if topic in self._subscriptions.get(ws, set())}
        else:
            targets = self.active_connections.copy()

        # RBAC-фильтр: событие уходит только админам с нужным правом
        if permission is not None:
            targets = {ws for ws in targets if self._admin_can(self._admins.get(ws), permission)}

        if not targets:
            return

        data = json.dumps(message, default=str)

        async def _send_one(ws: WebSocket):
            try:
                await asyncio.wait_for(ws.send_text(data), timeout=3.0)
                return None
            except Exception:
                return ws

        results = await asyncio.gather(*(_send_one(c) for c in targets))
        disconnected = {ws for ws in results if ws is not None}
        if disconnected:
            async with self._lock:
                self.active_connections -= disconnected
                for ws in disconnected:
                    self._subscriptions.pop(ws, None)

    async def send_to(self, websocket: WebSocket, message: Dict[str, Any]):
        """Отправить сообщение конкретному клиенту."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.debug(f"Failed to send to client: {e}")


# Глобальный менеджер подключений
manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint для real-time обновлений.

    Аутентификация: Sec-WebSocket-Protocol "access-token, <jwt>"
    (fallback: ?token= — deprecated, для старых клиентов).

    События:
    - connection: Новое подключение пользователя
    - violation: Обнаружено нарушение
    - node_status: Изменение статуса ноды
    - user_update: Обновление пользователя
    """
    # Проверяем аутентификацию
    try:
        admin = await get_current_admin_ws(websocket)
    except Exception as e:
        logger.debug("WebSocket auth failed: %s", e)
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
            # Перепроверка авторизации: рвём push-поток после logout/отзыва (H1)
            reason = ws_auth_invalid(websocket)
            if reason:
                await websocket.close(code=4001, reason=reason)
                break
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
        manager.subscribe(websocket, topics)
        logger.debug(f"Admin {admin.telegram_id or admin.username} subscribed to: {topics}")
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
    }, permission=("violations", "view"))
    # Dispatch to automation engine (fire-and-forget). Торрент в автоматизации
    # уходит своим событием torrent.detected — второй раз как нарушение его не
    # шлём: иначе правило «блокировать шаринг» блокировало за торрент в обход
    # настройки torrent_auto_action.
    if violation_data.get("type") == "torrent":
        return
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
    }, permission=("users", "view"))


async def broadcast_node_status(node_data: Dict[str, Any]):
    """Отправить событие о статусе ноды."""
    await manager.broadcast({
        "type": "node_status",
        "data": node_data,
        "timestamp": datetime.utcnow().isoformat(),
    }, permission=("nodes", "view"))
    # node.went_offline в автоматизации шлёт детектор движка: он знает, с
    # какого момента нода лежит, и не считает выключенные ноды упавшими


async def broadcast_user_update(user_data: Dict[str, Any]):
    """Отправить событие об обновлении пользователя."""
    await manager.broadcast({
        "type": "user_update",
        "data": user_data,
        "timestamp": datetime.utcnow().isoformat(),
    }, permission=("users", "view"))
    # user.traffic_exceeded шлёт детектор движка — один раз на превышение,
    # а не на каждое обновление юзера


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
    }, permission=("nodes", "view"))


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
    }, permission=("admins", "view"))


async def broadcast_dashboard_stats(stats: Dict[str, Any]):
    """Push dashboard overview stats to subscribed clients."""
    await manager.broadcast({
        "type": "dashboard_stats",
        "data": stats,
        "timestamp": datetime.utcnow().isoformat(),
    }, topic="dashboard")


async def dashboard_publisher_loop():
    """Background task: push dashboard stats every 15s to subscribed clients."""
    await asyncio.sleep(5)  # initial delay for startup
    while True:
        try:
            if manager.has_subscribers("dashboard"):
                try:
                    from shared.database import db_service
                    if db_service.is_connected:
                        async with db_service.acquire() as conn:
                            user_row = await conn.fetchrow(
                                "SELECT COUNT(*) AS total, "
                                "COUNT(*) FILTER (WHERE LOWER(status) = 'active') AS active, "
                                "COUNT(*) FILTER (WHERE LOWER(status) = 'disabled') AS disabled, "
                                "COUNT(*) FILTER (WHERE LOWER(status) = 'expired') AS expired "
                                "FROM users"
                            )
                            node_row = await conn.fetchrow(
                                "SELECT COUNT(*) AS total, "
                                "COUNT(*) FILTER (WHERE is_connected AND NOT is_disabled) AS online, "
                                "COALESCE(SUM(users_online), 0) AS users_online "
                                "FROM nodes"
                            )
                        await broadcast_dashboard_stats({
                            "total_users": user_row["total"],
                            "active_users": user_row["active"],
                            "disabled_users": user_row["disabled"],
                            "expired_users": user_row["expired"],
                            "total_nodes": node_row["total"],
                            "online_nodes": node_row["online"],
                            "users_online": node_row["users_online"],
                        })
                except Exception as e:
                    logger.debug("Dashboard publisher error: %s", e)
        except Exception as e:
            logger.debug("Dashboard publisher outer error: %s", e)
        await asyncio.sleep(15)

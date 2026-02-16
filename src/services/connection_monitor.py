"""
ConnectionMonitor — сервис для мониторинга и анализа подключений пользователей.

Агрегирует данные со всех нод, определяет активные соединения и предоставляет
метрики для Anti-Abuse системы.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from shared.database import DatabaseService
from shared.logger import logger


@dataclass
class ConnectionStats:
    """Статистика подключений пользователя."""
    user_uuid: str
    active_connections_count: int
    unique_ips_in_window: int
    simultaneous_connections: int
    total_connections_last_24h: int
    last_connection_at: Optional[datetime] = None


@dataclass
class ActiveConnection:
    """Активное подключение пользователя."""
    connection_id: int
    user_uuid: str
    ip_address: str
    node_uuid: Optional[str]
    connected_at: datetime
    device_info: Optional[Dict[str, Any]] = None


class ConnectionMonitor:
    """
    Сервис для мониторинга подключений пользователей.
    
    Агрегирует данные со всех нод, определяет активные соединения
    и предоставляет метрики для Anti-Abuse системы.
    """
    
    def __init__(self, db_service: DatabaseService):
        self.db = db_service
    
    async def get_user_active_connections(
        self,
        user_uuid: str,
        limit: int = 100,
        max_age_minutes: int = 5
    ) -> List[ActiveConnection]:
        """
        Получить список активных (не отключённых) подключений пользователя.
        
        Args:
            user_uuid: UUID пользователя
            limit: Максимальное количество записей
            max_age_minutes: Максимальный возраст подключения в минутах (по умолчанию 5 минут)
                           Подключения старше этого возраста считаются неактивными
        
        Returns:
            Список активных подключений
        """
        if not self.db.is_connected:
            logger.warning("Database not connected, cannot get active connections")
            return []
        
        try:
            connections_data = await self.db.get_user_active_connections(user_uuid, limit, max_age_minutes)
            
            active_connections = []
            for conn_data in connections_data:
                active_connections.append(
                    ActiveConnection(
                        connection_id=conn_data.get("id"),
                        user_uuid=conn_data.get("user_uuid"),
                        ip_address=str(conn_data.get("ip_address", "")),
                        node_uuid=conn_data.get("node_uuid"),
                        connected_at=conn_data.get("connected_at"),
                        device_info=conn_data.get("device_info"),
                    )
                )
            
            logger.debug(
                "Found %d active connections for user %s",
                len(active_connections),
                user_uuid
            )
            return active_connections
            
        except Exception as e:
            logger.error(
                "Error getting active connections for user %s: %s",
                user_uuid,
                e,
                exc_info=True
            )
            return []
    
    async def get_user_connection_stats(
        self,
        user_uuid: str,
        window_minutes: int = 60
    ) -> Optional[ConnectionStats]:
        """
        Получить статистику подключений пользователя.
        
        Args:
            user_uuid: UUID пользователя
            window_minutes: Временное окно для подсчёта уникальных IP (по умолчанию 60 минут)
        
        Returns:
            Статистика подключений или None при ошибке
        """
        if not self.db.is_connected:
            logger.warning("Database not connected, cannot get connection stats")
            return None
        
        try:
            # Получаем активные подключения (только за последние 5 минут)
            active_connections = await self.get_user_active_connections(user_uuid, limit=1000, max_age_minutes=5)
            active_connections_count = len(active_connections)
            
            # Подсчитываем уникальные IP в окне
            unique_ips_in_window = await self.db.get_unique_ips_in_window(
                user_uuid,
                window_minutes
            )
            
            # Подсчитываем одновременные подключения
            simultaneous_connections = await self.db.get_simultaneous_connections(user_uuid)
            
            # Получаем историю за последние 24 часа
            history_24h = await self.db.get_connection_history(user_uuid, days=1, limit=10000)
            total_connections_last_24h = len(history_24h)
            
            # Определяем время последнего подключения
            last_connection_at = None
            if active_connections:
                last_connection_at = max(
                    conn.connected_at for conn in active_connections
                )
            elif history_24h:
                last_connection_at = max(
                    datetime.fromisoformat(str(conn.get("connected_at")))
                    if isinstance(conn.get("connected_at"), str)
                    else conn.get("connected_at")
                    for conn in history_24h
                    if conn.get("connected_at")
                )
            
            stats = ConnectionStats(
                user_uuid=user_uuid,
                active_connections_count=active_connections_count,
                unique_ips_in_window=unique_ips_in_window,
                simultaneous_connections=simultaneous_connections,
                total_connections_last_24h=total_connections_last_24h,
                last_connection_at=last_connection_at
            )
            
            logger.debug(
                "Connection stats for user %s: active=%d, unique_ips=%d, simultaneous=%d",
                user_uuid,
                active_connections_count,
                unique_ips_in_window,
                simultaneous_connections
            )
            
            return stats
            
        except Exception as e:
            logger.error(
                "Error getting connection stats for user %s: %s",
                user_uuid,
                e,
                exc_info=True
            )
            return None
    
    async def get_unique_ips_for_user(
        self,
        user_uuid: str,
        window_minutes: int = 60
    ) -> List[str]:
        """
        Получить список уникальных IP адресов пользователя в указанном окне.
        
        Args:
            user_uuid: UUID пользователя
            window_minutes: Временное окно в минутах
        
        Returns:
            Список уникальных IP адресов
        """
        if not self.db.is_connected:
            return []
        
        try:
            history = await self.db.get_connection_history(
                user_uuid,
                days=max(1, window_minutes // (24 * 60) + 1),  # Минимум 1 день
                limit=10000
            )
            
            # Фильтруем по временному окну
            cutoff_time = datetime.utcnow() - timedelta(minutes=window_minutes)
            unique_ips = set()
            
            for conn in history:
                connected_at = conn.get("connected_at")
                if connected_at:
                    # Преобразуем в datetime если нужно
                    if isinstance(connected_at, str):
                        try:
                            # Пробуем разные форматы
                            if connected_at.endswith('Z'):
                                connected_at = datetime.fromisoformat(connected_at.replace('Z', '+00:00'))
                            else:
                                connected_at = datetime.fromisoformat(connected_at)
                        except ValueError:
                            # Если не удалось распарсить, пропускаем
                            continue
                    elif not isinstance(connected_at, datetime):
                        continue
                    
                    # Проверяем, что подключение в нужном временном окне
                    if connected_at.tzinfo is None:
                        # Если нет timezone, считаем что UTC
                        connected_at = connected_at.replace(tzinfo=None)
                        cutoff_time_naive = cutoff_time.replace(tzinfo=None)
                        if connected_at >= cutoff_time_naive:
                            ip = str(conn.get("ip_address", ""))
                            if ip:
                                unique_ips.add(ip)
                    else:
                        if connected_at >= cutoff_time.replace(tzinfo=connected_at.tzinfo):
                            ip = str(conn.get("ip_address", ""))
                            if ip:
                                unique_ips.add(ip)
            
            return sorted(list(unique_ips))
            
        except Exception as e:
            logger.error(
                "Error getting unique IPs for user %s: %s",
                user_uuid,
                e,
                exc_info=True
            )
            return []
    
    async def get_all_active_connections_count(self) -> int:
        """
        Получить общее количество активных подключений по всем пользователям.
        
        Returns:
            Общее количество активных подключений
        """
        if not self.db.is_connected:
            return 0
        
        try:
            async with self.db.acquire() as conn:
                result = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM user_connections
                    WHERE disconnected_at IS NULL
                    """
                )
                return result or 0
        except Exception as e:
            logger.error("Error getting all active connections count: %s", e, exc_info=True)
            return 0

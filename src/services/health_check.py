"""Сервис для периодической проверки доступности панели."""
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot

from shared.api_client import ApiClientError, api_client
from shared.logger import logger
from src.utils.notifications import send_service_notification


class PanelHealthChecker:
    """Проверяет доступность панели и отправляет уведомления при недоступности."""
    
    def __init__(self, bot: Bot, check_interval: int = 60) -> None:
        """
        Инициализирует health checker.
        
        Args:
            bot: Экземпляр бота для отправки уведомлений
            check_interval: Интервал проверки в секундах (по умолчанию 60)
        """
        self.bot = bot
        self.check_interval = check_interval
        self.is_running = False
        self.last_check_time: Optional[datetime] = None
        self.last_status: Optional[bool] = None
        self.consecutive_failures = 0
        self.last_notification_time: Optional[datetime] = None
        self.notification_cooldown = timedelta(minutes=5)  # Не отправлять уведомления чаще чем раз в 5 минут
        
    async def check_panel_health(self) -> bool:
        """
        Проверяет доступность панели.
        
        Returns:
            True если панель доступна, False если недоступна
        """
        try:
            start_time = datetime.now()
            await api_client.get_health()
            duration = (datetime.now() - start_time).total_seconds() * 1000

            was_down = self.consecutive_failures > 0
            self.last_check_time = datetime.now()
            self.last_status = True
            self.consecutive_failures = 0

            # Одна строка на СМЕНУ состояния: восстановление — info, штатный
            # пульс — debug (здоровая панель не должна занимать лог).
            if was_down:
                logger.info("✅ Panel health: recovered | %.0fms", duration)
            else:
                logger.debug("✅ Panel health: OK | %.0fms", duration)
            return True
        except ApiClientError as exc:
            self.last_check_time = datetime.now()
            self.last_status = False
            self.consecutive_failures += 1
            
            error_type = type(exc).__name__
            logger.warning(
                "❌ Panel health: FAIL | %s | failures=%d",
                error_type,
                self.consecutive_failures
            )
            
            # Отправляем уведомление только если:
            # 1. Это не первая проверка (чтобы не спамить при старте)
            # 2. Прошло достаточно времени с последнего уведомления
            # 3. Это уже несколько неудачных попыток подряд (>= 2)
            should_notify = (
                self.last_notification_time is None or
                datetime.now() - self.last_notification_time >= self.notification_cooldown
            ) and self.consecutive_failures >= 2
            
            if should_notify:
                await self._send_unavailable_notification(error_type, str(exc))
                self.last_notification_time = datetime.now()
            
            return False
        except Exception as exc:
            self.last_check_time = datetime.now()
            self.last_status = False
            self.consecutive_failures += 1
            
            error_type = type(exc).__name__
            logger.error(
                "❌ Panel health: ERROR | %s | failures=%d",
                error_type,
                self.consecutive_failures,
                exc_info=exc
            )
            
            should_notify = (
                self.last_notification_time is None or
                datetime.now() - self.last_notification_time >= self.notification_cooldown
            ) and self.consecutive_failures >= 2
            
            if should_notify:
                await self._send_unavailable_notification(error_type, str(exc))
                self.last_notification_time = datetime.now()
            
            return False
    
    async def _send_unavailable_notification(self, error_type: str, error_message: str) -> None:
        """Отправляет уведомление о недоступности панели."""
        try:
            # Обрезаем длинные сообщения об ошибках
            if len(error_message) > 200:
                error_message = error_message[:200] + "..."
            
            event_data = {
                "status": "unavailable",
                "error_type": error_type,
                "error_message": error_message,
                "consecutive_failures": self.consecutive_failures,
                "last_check": self.last_check_time.isoformat() if self.last_check_time else None,
            }
            
            await send_service_notification(
                self.bot,
                "panel.unavailable",
                event_data,
            )
            
            logger.info(
                "📢 Sent panel unavailable notification | failures=%d",
                self.consecutive_failures
            )
        except Exception as exc:
            logger.error("Failed to send unavailable notification: %s", exc, exc_info=True)
    
    async def start(self) -> None:
        """Запускает периодическую проверку панели."""
        if self.is_running:
            logger.warning("Panel health checker is already running")
            return
        
        self.is_running = True
        logger.debug("🏥 Health checker started | interval=%ds", self.check_interval)
        
        # Первая проверка сразу при старте
        await self.check_panel_health()
        
        # Затем периодические проверки
        while self.is_running:
            await asyncio.sleep(self.check_interval)
            if self.is_running:
                await self.check_panel_health()
    
    def stop(self) -> None:
        """Останавливает периодическую проверку панели."""
        if not self.is_running:
            return
        
        self.is_running = False
        logger.info("🏥 Health checker stopped")
    
    def get_status(self) -> dict:
        """
        Возвращает текущий статус health checker.
        
        Returns:
            Словарь с информацией о статусе
        """
        return {
            "is_running": self.is_running,
            "last_check": self.last_check_time.isoformat() if self.last_check_time else None,
            "last_status": "available" if self.last_status else "unavailable" if self.last_status is not None else "unknown",
            "consecutive_failures": self.consecutive_failures,
            "check_interval": self.check_interval,
        }

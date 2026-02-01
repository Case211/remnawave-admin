"""
ReportScheduler — планировщик автоматических отчётов по нарушениям.

Асинхронный планировщик на базе asyncio для отправки:
- Ежедневных отчётов
- Еженедельных отчётов
- Ежемесячных отчётов
"""
import asyncio
from datetime import datetime, time, timezone
from typing import Optional

from aiogram import Bot

from src.config import get_settings
from src.services.config_service import config_service
from src.services.database import db_service
from src.services.violation_reports import ReportType, violation_report_service
from src.utils.logger import logger


class ReportScheduler:
    """
    Планировщик автоматических отчётов по нарушениям.

    Проверяет время каждую минуту и отправляет отчёты в настроенное время.
    """

    def __init__(self, bot: Bot):
        """
        Инициализация планировщика.

        Args:
            bot: Экземпляр Telegram бота для отправки сообщений
        """
        self._bot = bot
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Отслеживание отправленных отчётов (чтобы не дублировать)
        self._last_daily_date: Optional[str] = None
        self._last_weekly_date: Optional[str] = None
        self._last_monthly_date: Optional[str] = None

    @property
    def is_running(self) -> bool:
        """Проверяет, запущен ли планировщик."""
        return self._running

    async def start(self) -> None:
        """Запускает планировщик."""
        if self._running:
            logger.warning("Report scheduler is already running")
            return

        if not db_service.is_connected:
            logger.warning("Database not connected, report scheduler disabled")
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("📊 Report scheduler started")

    async def stop(self) -> None:
        """Останавливает планировщик."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("📊 Report scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Основной цикл планировщика."""
        while self._running:
            try:
                await self._check_and_send_reports()
                # Проверяем каждую минуту
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in report scheduler loop: %s", e, exc_info=True)
                await asyncio.sleep(60)

    async def _check_and_send_reports(self) -> None:
        """Проверяет время и отправляет отчёты если нужно."""
        # Проверяем, включены ли отчёты глобально
        if not config_service.get("reports_enabled", True):
            return

        now = datetime.now(timezone.utc)
        current_time = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")
        current_weekday = now.weekday()  # 0 = Monday
        current_day_of_month = now.day

        # Проверяем ежедневный отчёт
        await self._check_daily_report(current_time, current_date)

        # Проверяем еженедельный отчёт
        await self._check_weekly_report(current_time, current_date, current_weekday)

        # Проверяем ежемесячный отчёт
        await self._check_monthly_report(current_time, current_date, current_day_of_month)

    async def _check_daily_report(self, current_time: str, current_date: str) -> None:
        """Проверяет и отправляет ежедневный отчёт."""
        if not config_service.get("reports_daily_enabled", True):
            return

        if self._last_daily_date == current_date:
            return  # Уже отправили сегодня

        report_time = config_service.get("reports_daily_time", "09:00")

        if current_time == report_time:
            logger.info("📊 Sending daily violation report...")
            try:
                await self._send_report(ReportType.DAILY)
                self._last_daily_date = current_date
            except Exception as e:
                logger.error("Failed to send daily report: %s", e, exc_info=True)

    async def _check_weekly_report(
        self,
        current_time: str,
        current_date: str,
        current_weekday: int
    ) -> None:
        """Проверяет и отправляет еженедельный отчёт."""
        if not config_service.get("reports_weekly_enabled", True):
            return

        if self._last_weekly_date == current_date:
            return  # Уже отправили сегодня

        report_day = config_service.get("reports_weekly_day", 0)  # 0 = Monday
        report_time = config_service.get("reports_weekly_time", "10:00")

        if current_weekday == report_day and current_time == report_time:
            logger.info("📊 Sending weekly violation report...")
            try:
                await self._send_report(ReportType.WEEKLY)
                self._last_weekly_date = current_date
            except Exception as e:
                logger.error("Failed to send weekly report: %s", e, exc_info=True)

    async def _check_monthly_report(
        self,
        current_time: str,
        current_date: str,
        current_day: int
    ) -> None:
        """Проверяет и отправляет ежемесячный отчёт."""
        if not config_service.get("reports_monthly_enabled", True):
            return

        if self._last_monthly_date == current_date:
            return  # Уже отправили сегодня

        report_day = config_service.get("reports_monthly_day", 1)
        report_time = config_service.get("reports_monthly_time", "10:00")

        if current_day == report_day and current_time == report_time:
            logger.info("📊 Sending monthly violation report...")
            try:
                await self._send_report(ReportType.MONTHLY)
                self._last_monthly_date = current_date
            except Exception as e:
                logger.error("Failed to send monthly report: %s", e, exc_info=True)

    async def _send_report(self, report_type: ReportType) -> None:
        """
        Генерирует и отправляет отчёт.

        Args:
            report_type: Тип отчёта
        """
        settings = get_settings()

        # Получаем chat_id для отправки
        chat_id = settings.notifications_chat_id
        if not chat_id:
            logger.warning("Cannot send report: notifications_chat_id not configured")
            return

        # Получаем topic_id для отчётов
        topic_id = config_service.get("reports_topic_id", None)
        if not topic_id:
            # Используем топик нарушений как fallback
            topic_id = settings.notifications_topic_violations

        # Настраиваем параметры генерации
        min_score = config_service.get("reports_min_score", 30.0)
        top_count = config_service.get("reports_top_violators_count", 10)

        violation_report_service.set_min_score(min_score)
        violation_report_service.set_top_violators_limit(top_count)

        # Генерируем отчёт
        report = await violation_report_service.generate_report(report_type, save_to_db=True)

        # Проверяем, нужно ли отправлять пустой отчёт
        send_empty = config_service.get("reports_send_empty", False)
        if report.total_violations == 0 and not send_empty:
            logger.info("Skipping empty %s report (no violations)", report_type.value)
            return

        # Отправляем отчёт
        try:
            kwargs = {
                "chat_id": chat_id,
                "text": report.message_text,
                "parse_mode": "HTML"
            }

            if topic_id:
                kwargs["message_thread_id"] = topic_id

            await self._bot.send_message(**kwargs)

            # Отмечаем отчёт как отправленный
            last_report = await db_service.get_last_report(report_type.value)
            if last_report:
                await db_service.mark_report_sent(last_report['id'])

            logger.info(
                "📊 Sent %s report: %d violations, %d users",
                report_type.value, report.total_violations, report.unique_users
            )

        except Exception as e:
            logger.error("Failed to send %s report to Telegram: %s", report_type.value, e)
            raise

    async def send_report_manually(
        self,
        report_type: ReportType,
        chat_id: int,
        topic_id: Optional[int] = None
    ) -> str:
        """
        Отправляет отчёт вручную по запросу пользователя.

        Args:
            report_type: Тип отчёта
            chat_id: ID чата для отправки
            topic_id: ID топика (опционально)

        Returns:
            Текст отчёта
        """
        # Настраиваем параметры
        min_score = config_service.get("reports_min_score", 30.0)
        top_count = config_service.get("reports_top_violators_count", 10)

        violation_report_service.set_min_score(min_score)
        violation_report_service.set_top_violators_limit(top_count)

        # Генерируем отчёт
        report = await violation_report_service.generate_report(report_type, save_to_db=True)

        # Отправляем
        kwargs = {
            "chat_id": chat_id,
            "text": report.message_text,
            "parse_mode": "HTML"
        }

        if topic_id:
            kwargs["message_thread_id"] = topic_id

        await self._bot.send_message(**kwargs)

        return report.message_text

    async def get_next_report_times(self) -> dict:
        """
        Возвращает информацию о следующих запланированных отчётах.

        Returns:
            Словарь с временем следующих отчётов
        """
        now = datetime.now(timezone.utc)

        result = {
            "reports_enabled": config_service.get("reports_enabled", True),
            "daily": None,
            "weekly": None,
            "monthly": None
        }

        if config_service.get("reports_daily_enabled", True):
            report_time = config_service.get("reports_daily_time", "09:00")
            result["daily"] = {
                "enabled": True,
                "time": report_time,
                "last_sent": self._last_daily_date
            }

        if config_service.get("reports_weekly_enabled", True):
            report_day = config_service.get("reports_weekly_day", 0)
            report_time = config_service.get("reports_weekly_time", "10:00")
            day_names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
            result["weekly"] = {
                "enabled": True,
                "day": day_names[report_day],
                "time": report_time,
                "last_sent": self._last_weekly_date
            }

        if config_service.get("reports_monthly_enabled", True):
            report_day = config_service.get("reports_monthly_day", 1)
            report_time = config_service.get("reports_monthly_time", "10:00")
            result["monthly"] = {
                "enabled": True,
                "day": report_day,
                "time": report_time,
                "last_sent": self._last_monthly_date
            }

        return result


# Глобальный экземпляр планировщика (инициализируется в main.py)
report_scheduler: Optional[ReportScheduler] = None


def get_report_scheduler() -> Optional[ReportScheduler]:
    """Возвращает глобальный экземпляр планировщика."""
    return report_scheduler


def init_report_scheduler(bot: Bot) -> ReportScheduler:
    """
    Инициализирует глобальный экземпляр планировщика.

    Args:
        bot: Экземпляр Telegram бота

    Returns:
        Экземпляр ReportScheduler
    """
    global report_scheduler
    report_scheduler = ReportScheduler(bot)
    return report_scheduler

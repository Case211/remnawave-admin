"""
ViolationReportService — сервис генерации отчётов по нарушениям.

Поддерживает:
- Ежедневные отчёты (daily)
- Еженедельные отчёты (weekly)
- Ежемесячные отчёты (monthly)
- Сравнение с предыдущим периодом
- Топ нарушителей
- Распределение по странам, провайдерам, типам нарушений
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from shared.analyzers.models import ACTION_LABELS
from shared.database import db_service
from shared.logger import logger


class ReportType(Enum):
    """Типы отчётов."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass
class ViolationReportData:
    """Данные отчёта по нарушениям."""
    report_type: ReportType
    period_start: datetime
    period_end: datetime

    # Статистика
    total_violations: int = 0
    critical_count: int = 0  # score >= 80
    warning_count: int = 0   # score 50-79
    monitor_count: int = 0   # score 30-49
    unique_users: int = 0
    avg_score: float = 0.0
    max_score: float = 0.0

    # Сравнение с предыдущим периодом
    prev_total_violations: Optional[int] = None
    trend_percent: Optional[float] = None
    trend_direction: str = "stable"  # up, down, stable

    # Топ нарушителей
    top_violators: List[Dict[str, Any]] = field(default_factory=list)

    # Распределение
    by_country: Dict[str, int] = field(default_factory=dict)
    by_action: Dict[str, int] = field(default_factory=dict)
    by_asn_type: Dict[str, int] = field(default_factory=dict)

    # Сгенерированный текст
    message_text: str = ""


class ViolationReportService:
    """
    Сервис генерации отчётов по нарушениям.

    Поддерживает генерацию ежедневных, еженедельных и ежемесячных отчётов
    с анализом трендов и сравнением с предыдущим периодом.
    """

    # Эмодзи для визуализации
    TREND_EMOJI = {
        "up": "📈",
        "down": "📉",
        "stable": "➡️"
    }

    SEVERITY_EMOJI = {
        "critical": "🔴",
        "warning": "🟠",
        "monitor": "🟡",
        "safe": "🟢"
    }

    # Названия действий общие с уведомлениями (shared/analyzers/models.py):
    # одно и то же нарушение не должно называться по-разному в двух местах.
    ACTION_NAMES = ACTION_LABELS

    ASN_TYPE_NAMES = {
        "mobile": "Мобильные",
        "mobile_isp": "Мобильные ISP",
        "fixed": "Проводные",
        "isp": "ISP",
        "regional_isp": "Региональные ISP",
        "hosting": "Хостинг",
        "datacenter": "Датацентры",
        "vpn": "VPN",
        "business": "Корпоративные",
        "infrastructure": "Инфраструктура"
    }

    def __init__(self):
        """Инициализирует сервис отчётов."""
        self._min_score_for_report = 30.0  # Минимальный скор для включения в отчёт
        self._top_violators_limit = 10     # Количество топ нарушителей

    def set_min_score(self, min_score: float) -> None:
        """Установить минимальный скор для включения в отчёт."""
        self._min_score_for_report = max(0.0, min(100.0, min_score))

    def set_top_violators_limit(self, limit: int) -> None:
        """Установить количество топ нарушителей."""
        self._top_violators_limit = max(1, min(50, limit))

    def _get_period_bounds(
        self,
        report_type: ReportType,
        reference_date: Optional[datetime] = None
    ) -> tuple[datetime, datetime]:
        """
        Получить границы периода для отчёта.

        Args:
            report_type: Тип отчёта
            reference_date: Опорная дата (по умолчанию - сейчас)

        Returns:
            Tuple (start, end) с границами периода
        """
        if reference_date is None:
            reference_date = datetime.now(timezone.utc)

        # Убираем время, оставляем только дату
        ref_date = reference_date.replace(hour=0, minute=0, second=0, microsecond=0)

        if report_type == ReportType.DAILY:
            # Вчера
            end = ref_date
            start = end - timedelta(days=1)
        elif report_type == ReportType.WEEKLY:
            # Прошлая неделя (понедельник-воскресенье)
            days_since_monday = ref_date.weekday()
            last_monday = ref_date - timedelta(days=days_since_monday + 7)
            start = last_monday
            end = last_monday + timedelta(days=7)
        elif report_type == ReportType.MONTHLY:
            # Прошлый месяц
            first_of_this_month = ref_date.replace(day=1)
            end = first_of_this_month
            # Первый день прошлого месяца
            if first_of_this_month.month == 1:
                start = first_of_this_month.replace(year=first_of_this_month.year - 1, month=12)
            else:
                start = first_of_this_month.replace(month=first_of_this_month.month - 1)
        else:
            raise ValueError(f"Unknown report type: {report_type}")

        return start, end

    def _get_previous_period_bounds(
        self,
        report_type: ReportType,
        current_start: datetime,
        current_end: datetime
    ) -> tuple[datetime, datetime]:
        """
        Получить границы предыдущего периода для сравнения.

        Args:
            report_type: Тип отчёта
            current_start: Начало текущего периода
            current_end: Конец текущего периода

        Returns:
            Tuple (start, end) с границами предыдущего периода
        """
        period_length = current_end - current_start

        if report_type == ReportType.MONTHLY:
            # Для месячных отчётов - предыдущий месяц
            if current_start.month == 1:
                prev_start = current_start.replace(year=current_start.year - 1, month=12)
            else:
                prev_start = current_start.replace(month=current_start.month - 1)
            prev_end = current_start
        else:
            # Для дневных и недельных - просто сдвигаем на длину периода
            prev_start = current_start - period_length
            prev_end = current_end - period_length

        return prev_start, prev_end

    async def generate_report(
        self,
        report_type: ReportType,
        reference_date: Optional[datetime] = None,
        save_to_db: bool = True
    ) -> ViolationReportData:
        """
        Сгенерировать отчёт по нарушениям.

        Args:
            report_type: Тип отчёта (daily/weekly/monthly)
            reference_date: Опорная дата (по умолчанию - сейчас)
            save_to_db: Сохранять ли отчёт в БД

        Returns:
            ViolationReportData с данными отчёта
        """
        # Определяем границы периода
        period_start, period_end = self._get_period_bounds(report_type, reference_date)

        logger.info(
            "Generating %s violation report for period %s - %s",
            report_type.value, period_start, period_end
        )

        # Создаём объект отчёта
        report = ViolationReportData(
            report_type=report_type,
            period_start=period_start,
            period_end=period_end
        )

        # Получаем статистику за период
        stats = await db_service.get_violations_stats_for_period(
            period_start, period_end, self._min_score_for_report
        )

        report.total_violations = stats.get('total', 0)
        # SQL-статистика отдаёт severity-бакеты critical/high/medium, а не
        # warning/monitor — исторические имена полей отчёта маппим на них,
        # иначе warning_count/monitor_count всегда 0.
        report.critical_count = stats.get('critical', 0)
        report.warning_count = stats.get('high', 0)
        report.monitor_count = stats.get('medium', 0)
        report.unique_users = stats.get('unique_users', 0)
        report.avg_score = stats.get('avg_score', 0.0)
        report.max_score = stats.get('max_score', 0.0)

        # Получаем статистику предыдущего периода для сравнения
        prev_start, prev_end = self._get_previous_period_bounds(
            report_type, period_start, period_end
        )
        prev_stats = await db_service.get_violations_stats_for_period(
            prev_start, prev_end, self._min_score_for_report
        )

        report.prev_total_violations = prev_stats.get('total', 0)

        # Вычисляем тренд
        if report.prev_total_violations and report.prev_total_violations > 0:
            change = report.total_violations - report.prev_total_violations
            report.trend_percent = (change / report.prev_total_violations) * 100

            if report.trend_percent > 5:
                report.trend_direction = "up"
            elif report.trend_percent < -5:
                report.trend_direction = "down"
            else:
                report.trend_direction = "stable"
        else:
            report.trend_percent = None
            report.trend_direction = "stable"

        # Получаем топ нарушителей
        report.top_violators = await db_service.get_top_violators_for_period(
            period_start, period_end, self._min_score_for_report, self._top_violators_limit
        )

        # Получаем распределения
        report.by_country = await db_service.get_violations_by_country(
            period_start, period_end, self._min_score_for_report
        )
        report.by_action = await db_service.get_violations_by_action(
            period_start, period_end, self._min_score_for_report
        )
        report.by_asn_type = await db_service.get_violations_by_asn_type(
            period_start, period_end, self._min_score_for_report
        )

        # Генерируем текст отчёта
        report.message_text = self._format_report_message(report)

        # Сохраняем в БД
        if save_to_db:
            await self._save_report_to_db(report)

        logger.info(
            "Generated %s report: %d violations, %d users",
            report_type.value, report.total_violations, report.unique_users
        )

        return report

    def _format_report_message(self, report: ViolationReportData) -> str:
        """
        Форматирует текст отчёта для отправки в Telegram.

        Args:
            report: Данные отчёта

        Returns:
            Отформатированный текст
        """
        lines = []

        # Заголовок
        report_titles = {
            ReportType.DAILY: "📊 Ежедневный отчёт по нарушениям",
            ReportType.WEEKLY: "📊 Еженедельный отчёт по нарушениям",
            ReportType.MONTHLY: "📊 Ежемесячный отчёт по нарушениям"
        }
        lines.append(f"<b>{report_titles[report.report_type]}</b>")
        lines.append("")

        # Период
        period_start_str = report.period_start.strftime("%d.%m.%Y")
        period_end_str = (report.period_end - timedelta(seconds=1)).strftime("%d.%m.%Y")
        if period_start_str == period_end_str:
            lines.append(f"📅 <b>Период:</b> {period_start_str}")
        else:
            lines.append(f"📅 <b>Период:</b> {period_start_str} — {period_end_str}")
        lines.append("")

        # Основная статистика
        lines.append("<b>📈 Общая статистика:</b>")
        lines.append(f"  • Всего нарушений: <b>{report.total_violations}</b>")
        lines.append(f"  • Уникальных пользователей: <b>{report.unique_users}</b>")

        if report.total_violations > 0:
            lines.append(f"  • Средний скор: <b>{report.avg_score:.1f}</b>")
            lines.append(f"  • Максимальный скор: <b>{report.max_score:.1f}</b>")
        lines.append("")

        # Распределение по severity
        if report.total_violations > 0:
            lines.append("<b>🎯 По уровню критичности:</b>")
            if report.critical_count > 0:
                pct = (report.critical_count / report.total_violations) * 100
                lines.append(f"  {self.SEVERITY_EMOJI['critical']} Критичные (≥80): <b>{report.critical_count}</b> ({pct:.0f}%)")
            if report.warning_count > 0:
                pct = (report.warning_count / report.total_violations) * 100
                lines.append(f"  {self.SEVERITY_EMOJI['warning']} Предупреждения (50-79): <b>{report.warning_count}</b> ({pct:.0f}%)")
            if report.monitor_count > 0:
                pct = (report.monitor_count / report.total_violations) * 100
                lines.append(f"  {self.SEVERITY_EMOJI['monitor']} Мониторинг (30-49): <b>{report.monitor_count}</b> ({pct:.0f}%)")
            lines.append("")

        # Тренд
        if report.prev_total_violations is not None:
            trend_emoji = self.TREND_EMOJI[report.trend_direction]
            if report.trend_percent is not None:
                trend_str = f"{'+' if report.trend_percent > 0 else ''}{report.trend_percent:.1f}%"
            else:
                trend_str = "—"

            lines.append(f"<b>{trend_emoji} Тренд:</b> {trend_str} (было: {report.prev_total_violations})")
            lines.append("")

        # Топ нарушителей
        if report.top_violators:
            lines.append("<b>👥 Топ нарушителей:</b>")
            for i, violator in enumerate(report.top_violators[:5], 1):
                username = violator.get('username') or violator.get('email') or str(violator.get('user_uuid'))[:8]
                count = violator.get('violations_count', 0)
                max_score = violator.get('max_score', 0)
                lines.append(f"  {i}. {self._escape_html(username)}: <b>{count}</b> (макс: {max_score:.0f})")
            lines.append("")

        # Распределение по странам (топ-5)
        if report.by_country:
            lines.append("<b>🌍 По странам:</b>")
            sorted_countries = sorted(report.by_country.items(), key=lambda x: x[1], reverse=True)[:5]
            for country, count in sorted_countries:
                flag = self._get_country_flag(country)
                lines.append(f"  {flag} {country}: <b>{count}</b>")
            lines.append("")

        # Распределение по типам провайдеров (топ-5)
        if report.by_asn_type:
            lines.append("<b>🔌 По типам провайдеров:</b>")
            sorted_types = sorted(report.by_asn_type.items(), key=lambda x: x[1], reverse=True)[:5]
            for asn_type, count in sorted_types:
                type_name = self.ASN_TYPE_NAMES.get(asn_type, asn_type)
                lines.append(f"  • {type_name}: <b>{count}</b>")
            lines.append("")

        # Распределение по действиям
        if report.by_action:
            lines.append("<b>⚡ По рекомендуемым действиям:</b>")
            sorted_actions = sorted(report.by_action.items(), key=lambda x: x[1], reverse=True)
            for action, count in sorted_actions:
                action_name = self.ACTION_NAMES.get(action, action)
                lines.append(f"  • {action_name.capitalize()}: <b>{count}</b>")

        # Футер
        lines.append("")
        generated_at = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        lines.append(f"<i>Сгенерировано: {generated_at}</i>")

        return "\n".join(lines)

    def _escape_html(self, text: str) -> str:
        """Экранирует HTML-символы."""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _get_country_flag(self, country_code: str) -> str:
        """Получить эмодзи флага страны."""
        if not country_code or len(country_code) != 2:
            return "🏳️"

        # Преобразуем код страны в regional indicator symbols
        try:
            flag = "".join(chr(0x1F1E6 + ord(c) - ord('A')) for c in country_code.upper())
            return flag
        except Exception:
            return "🏳️"

    async def _save_report_to_db(self, report: ViolationReportData) -> Optional[int]:
        """
        Сохраняет отчёт в базу данных.

        Args:
            report: Данные отчёта

        Returns:
            ID созданного отчёта или None
        """
        try:
            report_id = await db_service.save_violation_report(
                report_type=report.report_type.value,
                period_start=report.period_start,
                period_end=report.period_end,
                total_violations=report.total_violations,
                critical_count=report.critical_count,
                warning_count=report.warning_count,
                monitor_count=report.monitor_count,
                unique_users=report.unique_users,
                prev_total_violations=report.prev_total_violations,
                trend_percent=report.trend_percent,
                top_violators=json.dumps(report.top_violators, default=str) if report.top_violators else None,
                by_country=json.dumps(report.by_country) if report.by_country else None,
                by_action=json.dumps(report.by_action) if report.by_action else None,
                by_asn_type=json.dumps(report.by_asn_type) if report.by_asn_type else None,
                message_text=report.message_text
            )
            return report_id
        except Exception as e:
            logger.error("Error saving report to DB: %s", e, exc_info=True)
            return None

    async def get_custom_report(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: Optional[float] = None
    ) -> ViolationReportData:
        """
        Сгенерировать отчёт за произвольный период.

        Args:
            start_date: Начало периода
            end_date: Конец периода
            min_score: Минимальный скор (опционально)

        Returns:
            ViolationReportData с данными отчёта
        """
        if min_score is not None:
            original_min_score = self._min_score_for_report
            self._min_score_for_report = min_score

        report = ViolationReportData(
            report_type=ReportType.DAILY,  # Используем daily как базовый тип
            period_start=start_date,
            period_end=end_date
        )

        # Получаем статистику
        stats = await db_service.get_violations_stats_for_period(
            start_date, end_date, self._min_score_for_report
        )

        report.total_violations = stats.get('total', 0)
        # SQL-статистика отдаёт severity-бакеты critical/high/medium, а не
        # warning/monitor — исторические имена полей отчёта маппим на них,
        # иначе warning_count/monitor_count всегда 0.
        report.critical_count = stats.get('critical', 0)
        report.warning_count = stats.get('high', 0)
        report.monitor_count = stats.get('medium', 0)
        report.unique_users = stats.get('unique_users', 0)
        report.avg_score = stats.get('avg_score', 0.0)
        report.max_score = stats.get('max_score', 0.0)

        # Получаем топ нарушителей
        report.top_violators = await db_service.get_top_violators_for_period(
            start_date, end_date, self._min_score_for_report, self._top_violators_limit
        )

        # Получаем распределения
        report.by_country = await db_service.get_violations_by_country(
            start_date, end_date, self._min_score_for_report
        )
        report.by_action = await db_service.get_violations_by_action(
            start_date, end_date, self._min_score_for_report
        )
        report.by_asn_type = await db_service.get_violations_by_asn_type(
            start_date, end_date, self._min_score_for_report
        )

        # Генерируем текст
        report.message_text = self._format_report_message(report)

        if min_score is not None:
            self._min_score_for_report = original_min_score

        return report

    async def export_violations_csv(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 30.0
    ) -> str:
        """
        Экспортировать нарушения в CSV формат.

        Args:
            start_date: Начало периода
            end_date: Конец периода
            min_score: Минимальный скор

        Returns:
            CSV-строка с данными
        """
        violations = await db_service.get_violations_for_period(
            start_date, end_date, min_score, limit=10000
        )

        if not violations:
            return "Нет данных за указанный период"

        # Заголовки CSV
        headers = [
            "ID", "Дата", "Пользователь", "Email", "Telegram ID",
            "Скор", "Действие", "IP адреса", "Страны", "Провайдеры",
            "Одновременных подключений", "Причины"
        ]

        lines = [";".join(headers)]

        for v in violations:
            row = [
                str(v.get('id', '')),
                v.get('detected_at', '').strftime("%d.%m.%Y %H:%M") if v.get('detected_at') else '',
                v.get('username', '') or '',
                v.get('email', '') or '',
                str(v.get('telegram_id', '') or ''),
                f"{v.get('score', 0):.1f}",
                v.get('recommended_action', ''),
                ", ".join(v.get('ip_addresses', []) or []),
                ", ".join(v.get('countries', []) or []),
                ", ".join(v.get('asn_types', []) or []),
                str(v.get('simultaneous_connections', '') or ''),
                "; ".join(v.get('reasons', []) or [])
            ]
            # Экранируем точки с запятой в значениях
            row = [val.replace(";", ",") if val else "" for val in row]
            lines.append(";".join(row))

        return "\n".join(lines)


# Глобальный экземпляр сервиса
violation_report_service = ViolationReportService()

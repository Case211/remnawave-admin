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

from shared import timefmt
from shared.analyzers.models import ACTION_LABELS
from shared.database import db_service
from shared.i18n import tr
from shared.logger import logger
from shared.tg_card import Card, b, copy, i, join, section


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

    # id сохранённого отчёта (None — не сохранялся)
    id: Optional[int] = None


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

    def __init__(self):
        """Инициализирует сервис отчётов."""
        self._min_score_for_report = 30.0  # Минимальный скор для включения в отчёт
        self._top_violators_limit = 10     # Количество топ нарушителей

    def configure_from_settings(self) -> None:
        """Мин. скор и размер топа — из настроек: отчёт из веба и из бота
        за один период должен выйти одинаковым."""
        from shared.config_service import config_service
        try:
            self.set_min_score(float(config_service.get("reports_min_score", 30.0) or 30.0))
        except (TypeError, ValueError):
            pass
        try:
            self.set_top_violators_limit(int(config_service.get("reports_top_violators_count", 10) or 10))
        except (TypeError, ValueError):
            pass

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

        # Сутки считаем по зоне отображения: «вчера» у админа в Москве — с полуночи
        # до полуночи по Москве, а не с 03:00 до 03:00. Границы остаются
        # aware-датами, в запросах к базе они сами пересчитываются в UTC.
        local = timefmt.to_display(reference_date)
        ref_date = local.replace(hour=0, minute=0, second=0, microsecond=0)

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

        # Текст отчёта — HTML-вид его карточки: хранится в базе и виден в панели
        report.message_text = self.build_card(report).to_html()

        # Сохраняем в БД
        if save_to_db:
            report.id = await self._save_report_to_db(report)
            if report.id:
                from shared.webhook_outbox import enqueue_event
                await enqueue_event("report.generated", {
                    "report_id": report.id,
                    "report_type": report.report_type.value,
                    "period_start": report.period_start,
                    "period_end": report.period_end,
                    "total_violations": report.total_violations,
                    "critical_count": report.critical_count,
                    "unique_users": report.unique_users,
                    "trend_percent": report.trend_percent,
                })

        logger.info(
            "Generated %s report: %d violations, %d users",
            report_type.value, report.total_violations, report.unique_users
        )

        return report

    def build_card(self, report: ViolationReportData) -> Card:
        """Отчёт карточкой: сводка полями, уровни/топ/страны таблицами, остальное свёрнуто.

        Её HTML-вид — это и ``message_text``: тот же текст хранится в базе и
        показывается в панели, а в Telegram уходят rich-блоки.
        """
        total = report.total_violations
        card = Card(tr(f"notify.report.title.{report.report_type.value}"), emoji="📊")
        start = timefmt.fmt_date(report.period_start)
        end = timefmt.fmt_date(report.period_end - timedelta(seconds=1))
        card.lead(b(start if start == end else f"{start} — {end}"))

        trend = None
        if report.prev_total_violations is not None:
            pct = report.trend_percent
            arrow = self.TREND_EMOJI.get(report.trend_direction, "")
            change = f"{'+' if pct > 0 else ''}{pct:.1f}%" if pct is not None else "—"
            trend = join(f"{arrow} {change}", tr("notify.report.trend_was", count=report.prev_total_violations))
        card.fields([
            (tr("notify.report.field.total"), b(str(total))),
            (tr("notify.report.field.trend"), trend),
            (tr("notify.report.field.users"), str(report.unique_users)),
            (tr("notify.report.field.avg"), f"{report.avg_score:.1f}" if total and report.avg_score else None),
            (tr("notify.report.field.max"), f"{report.max_score:.1f}" if total and report.max_score else None),
        ])
        if not total:
            card.text(i(tr("notify.report.empty")))
            return card.stamp()

        levels = [(level, count) for level, count in (("critical", report.critical_count),
                  ("warning", report.warning_count), ("monitor", report.monitor_count)) if count]
        if levels:
            card.section(tr("notify.report.severity"))
            card.table(
                [[f"{self.SEVERITY_EMOJI[level]} {tr(f'notify.report.level.{level}')}", b(str(count)),
                  f"{count / total * 100:.0f}%"] for level, count in levels],
                head=[tr("notify.report.col.level"), tr("notify.report.col.count"), tr("notify.report.col.share")],
                align=["left", "right", "right"],
            )

        if report.top_violators:
            card.section(tr("notify.report.top"))
            card.table(
                [[str(n), _violator_cell(v),
                  b(str(v.get("violations_count", 0))), f"{(v.get('max_score') or 0):.0f}"]
                 for n, v in enumerate(report.top_violators[:10], 1)],
                head=["#", tr("notify.report.col.user"), tr("notify.report.col.violations"),
                      tr("notify.report.col.max")],
                align=["right", "left", "right", "right"],
            )

        if report.by_country:
            card.section(tr("notify.report.countries"))
            card.table(
                [[f"{self._get_country_flag(country)} {country}", b(str(count))]
                 for country, count in sorted(report.by_country.items(), key=lambda x: x[1], reverse=True)[:5]],
                head=[tr("notify.report.col.country"), tr("notify.report.col.violations")],
                align=["left", "right"],
            )

        details = section()
        if report.by_asn_type:
            details.section(tr("notify.report.providers"))
            details.table(
                [[self._asn_type_name(kind), b(str(count))]
                 for kind, count in sorted(report.by_asn_type.items(), key=lambda x: x[1], reverse=True)[:5]],
                head=[tr("notify.report.col.type"), tr("notify.report.col.count")], align=["left", "right"],
            )
        if report.by_action:
            details.section(tr("notify.report.actions"))
            details.table(
                [[_action_name(action), b(str(count))]
                 for action, count in sorted(report.by_action.items(), key=lambda x: x[1], reverse=True)],
                head=[tr("notify.report.col.action"), tr("notify.report.col.count")], align=["left", "right"],
            )
        card.details(tr("notify.report.details"), details)
        return card.stamp()

    @staticmethod
    def _asn_type_name(kind: str) -> str:
        name = tr(f"notify.report.asn.{kind}")
        return kind if name == f"notify.report.asn.{kind}" else name

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
            "ID", f"Дата ({timefmt.label()})", "Пользователь", "Email", "Telegram ID",
            "Скор", "Действие", "IP адреса", "Страны", "Провайдеры",
            "Одновременных подключений", "Причины"
        ]

        lines = [";".join(headers)]

        for v in violations:
            row = [
                str(v.get('id', '')),
                timefmt.fmt(v.get('detected_at'), "%d.%m.%Y %H:%M", with_label=False),
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


def _action_name(action: str) -> str:
    """Название действия — общее с уведомлениями: одно нарушение не называется по-разному."""
    name = tr(f"notify.violation.action.{action}")
    return name if name != f"notify.violation.action.{action}" else ACTION_LABELS.get(action, action)


def _json_value(value: Any, default: Any) -> Any:
    """JSON-колонка: драйвер отдаёт её строкой или уже разобранной."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return default
    return value if value is not None else default


def _violator_cell(v: dict):
    """Кто в топе: имя копируется касанием; без имени — полный UUID под его началом."""
    name = v.get("username") or v.get("email")
    if name:
        return copy(name)
    uuid = str(v.get("user_uuid") or "")
    return copy(uuid, uuid[:8]) if uuid else "—"


def report_from_row(row: Dict[str, Any]) -> ViolationReportData:
    """Сохранённый отчёт обратно в данные — чтобы переслать его той же карточкой."""
    return ViolationReportData(
        report_type=ReportType(row["report_type"]),
        period_start=row["period_start"],
        period_end=row["period_end"],
        total_violations=row.get("total_violations") or 0,
        critical_count=row.get("critical_count") or 0,
        warning_count=row.get("warning_count") or 0,
        monitor_count=row.get("monitor_count") or 0,
        unique_users=row.get("unique_users") or 0,
        prev_total_violations=row.get("prev_total_violations"),
        trend_percent=row.get("trend_percent"),
        top_violators=_json_value(row.get("top_violators"), []),
        by_country=_json_value(row.get("by_country"), {}),
        by_action=_json_value(row.get("by_action"), {}),
        by_asn_type=_json_value(row.get("by_asn_type"), {}),
        message_text=row.get("message_text") or "",
        id=row.get("id"),
    )


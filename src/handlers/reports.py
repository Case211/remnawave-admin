from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe, require_permission
from src.keyboards.reports_menu import (
    reports_back_keyboard,
    reports_custom_period_keyboard,
    reports_history_keyboard,
    reports_menu_keyboard,
    reports_schedule_keyboard,
    reports_view_keyboard,
)
from src.utils.auth import BotAdmin
from shared import timefmt
from shared.config_service import config_service
from shared.database import db_service
from src.services.report_scheduler import get_report_scheduler
from src.services.violation_reports import ReportType, violation_report_service
from shared.logger import logger

router = Router(name="reports")


@router.callback_query(F.data == "menu:reports")
async def show_reports_menu(callback: CallbackQuery, admin: BotAdmin) -> None:
    text = _("reports.menu_title")
    await _edit_text_safe(callback.message, text, reply_markup=reports_menu_keyboard(admin=admin), parse_mode="HTML")


@router.callback_query(F.data == "reports:menu")
async def show_reports_menu_alt(callback: CallbackQuery, admin: BotAdmin) -> None:
    await show_reports_menu(callback, admin=admin)


@router.callback_query(F.data.startswith("reports:generate:"))
async def generate_report(callback: CallbackQuery, admin: BotAdmin) -> None:
    if not await require_permission(callback, admin, "reports", "create"):
        return
    report_type_str = callback.data.split(":")[2]

    report_type_map = {
        "daily": ReportType.DAILY,
        "weekly": ReportType.WEEKLY,
        "monthly": ReportType.MONTHLY
    }

    report_type = report_type_map.get(report_type_str)
    if not report_type:
        await callback.answer(_("reports.unknown_type"), show_alert=True)
        return

    await callback.answer(_("reports.generating"))

    try:
        min_score = config_service.get("reports_min_score", 30.0)
        top_count = config_service.get("reports_top_violators_count", 10)

        violation_report_service.set_min_score(min_score)
        violation_report_service.set_top_violators_limit(top_count)

        report = await violation_report_service.generate_report(report_type, save_to_db=True)

        if report.total_violations == 0:
            text = _("reports.generated_empty").format(
                start=timefmt.fmt_date(report.period_start),
                end=timefmt.fmt_date(report.period_end - timedelta(seconds=1)),
            )
            await _edit_text_safe(callback.message, text, reply_markup=reports_back_keyboard(), parse_mode="HTML")
        else:
            await callback.message.edit_text(report.message_text, parse_mode="HTML", reply_markup=reports_back_keyboard())

    except Exception as e:
        logger.error("Error generating report: %s", e, exc_info=True)
        await callback.answer(_("reports.generate_error"), show_alert=True)


@router.callback_query(F.data == "reports:custom")
async def show_custom_period_menu(callback: CallbackQuery, admin: BotAdmin) -> None:
    text = _("reports.custom_period_title")
    await _edit_text_safe(callback.message, text, reply_markup=reports_custom_period_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("reports:custom:"))
async def generate_custom_report(callback: CallbackQuery, admin: BotAdmin) -> None:
    if not await require_permission(callback, admin, "reports", "create"):
        return
    try:
        days = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer(_("reports.invalid_period"), show_alert=True)
        return

    await callback.answer(_("reports.generating"))

    try:
        now = datetime.now(timezone.utc)
        end_date = now
        start_date = now - timedelta(days=days)

        min_score = config_service.get("reports_min_score", 30.0)
        top_count = config_service.get("reports_top_violators_count", 10)

        violation_report_service.set_min_score(min_score)
        violation_report_service.set_top_violators_limit(top_count)

        report = await violation_report_service.get_custom_report(start_date, end_date, min_score)

        if report.total_violations == 0:
            text = _("reports.custom_generated_empty").format(days=days)
            await _edit_text_safe(callback.message, text, reply_markup=reports_back_keyboard(), parse_mode="HTML")
        else:
            report.message_text = report.message_text.replace(
                _("reports.daily_title"),
                _("reports.custom_title").format(days=days),
            )
            await callback.message.edit_text(report.message_text, parse_mode="HTML", reply_markup=reports_back_keyboard())

    except Exception as e:
        logger.error("Error generating custom report: %s", e, exc_info=True)
        await callback.answer(_("reports.generate_error"), show_alert=True)


@router.callback_query(F.data == "reports:history")
async def show_reports_history(callback: CallbackQuery, admin: BotAdmin) -> None:
    reports = await db_service.get_reports_history(limit=50)

    if not reports:
        text = _("reports.history_empty")
        await _edit_text_safe(callback.message, text, reply_markup=reports_back_keyboard(), parse_mode="HTML")
        return

    text = _("reports.history_title")
    await _edit_text_safe(callback.message, text, reply_markup=reports_history_keyboard(reports), parse_mode="HTML")


@router.callback_query(F.data.startswith("reports:history:page:"))
async def show_reports_history_page(callback: CallbackQuery, admin: BotAdmin) -> None:
    try:
        page = int(callback.data.split(":")[3])
    except (IndexError, ValueError):
        page = 0

    reports = await db_service.get_reports_history(limit=50)

    text = _("reports.history_title")
    await _edit_text_safe(callback.message, text, reply_markup=reports_history_keyboard(reports, page), parse_mode="HTML")


@router.callback_query(F.data.startswith("reports:view:"))
async def view_report(callback: CallbackQuery, admin: BotAdmin) -> None:
    try:
        report_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer(_("reports.invalid_id"), show_alert=True)
        return

    reports = await db_service.get_reports_history(limit=100)
    report = next((r for r in reports if r.get('id') == report_id), None)

    if not report:
        await callback.answer(_("reports.not_found"), show_alert=True)
        return

    message_text = report.get('message_text')
    if message_text:
        await callback.message.edit_text(message_text, parse_mode="HTML", reply_markup=reports_view_keyboard(report_id))
    else:
        text = _("reports.view_summary").format(
            id=report_id,
            rtype=report.get('report_type', _("reports.unknown_type")),
            start=timefmt.fmt_date(report.get('period_start'), empty='?'),
            end=timefmt.fmt_date(report['period_end'] - timedelta(seconds=1)) if report.get('period_end') else '?',
            total=report.get('total_violations', 0),
            critical=report.get('critical_count', 0),
            warnings=report.get('warning_count', 0),
            users=report.get('unique_users', 0),
        )
        await _edit_text_safe(callback.message, text, reply_markup=reports_view_keyboard(report_id), parse_mode="HTML")


@router.callback_query(F.data.startswith("reports:forward:"))
async def forward_report(callback: CallbackQuery, admin: BotAdmin) -> None:
    try:
        report_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer(_("reports.invalid_id"), show_alert=True)
        return

    reports = await db_service.get_reports_history(limit=100)
    report = next((r for r in reports if r.get('id') == report_id), None)

    if not report or not report.get('message_text'):
        await callback.answer(_("reports.not_found_unavailable"), show_alert=True)
        return

    await callback.message.answer(report['message_text'], parse_mode="HTML")
    await callback.answer(_("reports.forwarded"))


@router.callback_query(F.data == "reports:schedule")
async def show_reports_schedule(callback: CallbackQuery, admin: BotAdmin) -> None:
    scheduler = get_report_scheduler()

    if scheduler:
        schedule = await scheduler.get_next_report_times()
    else:
        schedule = {"reports_enabled": False}

    lines = [_("reports.schedule_title"), ""]

    if not schedule.get("reports_enabled", True):
        lines.append(_("reports.schedule_disabled"))
    else:
        lines.append(_("reports.schedule_enabled"))
        lines.append("")

        daily = schedule.get("daily")
        if daily and daily.get("enabled"):
            lines.append(_("reports.schedule_daily").format(time=daily.get('time', '09:00')))
            if daily.get("last_sent"):
                lines.append(_("reports.schedule_last_sent").format(time=daily['last_sent']))
        else:
            lines.append(_("reports.schedule_daily_disabled"))

        weekly = schedule.get("weekly")
        if weekly and weekly.get("enabled"):
            lines.append(_("reports.schedule_weekly").format(day=weekly.get('day', 'Mon'), time=weekly.get('time', '10:00')))
            if weekly.get("last_sent"):
                lines.append(_("reports.schedule_last_sent").format(time=weekly['last_sent']))
        else:
            lines.append(_("reports.schedule_weekly_disabled"))

        monthly = schedule.get("monthly")
        if monthly and monthly.get("enabled"):
            lines.append(_("reports.schedule_monthly").format(day=monthly.get('day', 1), time=monthly.get('time', '10:00')))
            if monthly.get("last_sent"):
                lines.append(_("reports.schedule_last_sent").format(time=monthly['last_sent']))
        else:
            lines.append(_("reports.schedule_monthly_disabled"))

    lines.append("")
    lines.append(_("reports.schedule_hint"))

    text = "\n".join(lines)
    await _edit_text_safe(callback.message, text, reply_markup=reports_schedule_keyboard(schedule), parse_mode="HTML")


@router.callback_query(F.data == "reports:toggle")
async def toggle_reports(callback: CallbackQuery, admin: BotAdmin) -> None:
    if not await require_permission(callback, admin, "settings", "edit"):
        return
    current = config_service.get("reports_enabled", True)
    new_value = not current

    success = await config_service.set("reports_enabled", new_value)

    if success:
        status = _("reports.enabled_status") if new_value else _("reports.disabled_status")
        await callback.answer(_("reports.toggle_result").format(status=status), show_alert=False)
        await show_reports_schedule(callback, admin=admin)
    else:
        await callback.answer(_("reports.save_error"), show_alert=True)

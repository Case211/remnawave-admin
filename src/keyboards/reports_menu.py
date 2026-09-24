from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from shared import timefmt


def reports_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = []
    if admin is None or admin.has_perm_sync("reports", "create"):
        rows.append([InlineKeyboardButton(text=_("reports.daily"), callback_data="reports:generate:daily")])
        rows.append([InlineKeyboardButton(text=_("reports.weekly"), callback_data="reports:generate:weekly")])
        rows.append([InlineKeyboardButton(text=_("reports.monthly"), callback_data="reports:generate:monthly")])
        rows.append([InlineKeyboardButton(text=_("reports.custom_period"), callback_data="reports:custom")])
    if admin is None or admin.has_perm_sync("reports", "view"):
        rows.append([InlineKeyboardButton(text=_("reports.history"), callback_data="reports:history")])
    if admin is None or admin.has_perm_sync("reports", "view"):
        rows.append([InlineKeyboardButton(text=_("reports.schedule"), callback_data="reports:schedule")])
    if admin is None or admin.has_perm_sync("settings", "view"):
        rows.append([InlineKeyboardButton(text=_("reports.settings"), callback_data="bot_config:cat:reports")])
    rows.append(nav_row(NavTarget.SYSTEM_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reports_history_keyboard(
    reports: List[dict],
    page: int = 0,
    page_size: int = 5,
) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    total_items = len(reports)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_items)
    page_reports = reports[start_idx:end_idx]

    type_emoji = {
        "daily": "📅",
        "weekly": "📆",
        "monthly": "🗓️"
    }

    for report in page_reports:
        report_type = report.get("report_type", "daily")
        emoji = type_emoji.get(report_type, "📊")
        period_start = report.get("period_start")
        total = report.get("total_violations", 0)

        if period_start:
            date_str = timefmt.fmt_date(period_start)
        else:
            date_str = "?"

        rows.append([InlineKeyboardButton(
            text=_("reports.violations_count").format(emoji=emoji, date=date_str, count=total),
            callback_data=f"reports:view:{report.get('id', 0)}"
        )])

    if total_pages > 1:
        pagination_row = []
        if page > 0:
            pagination_row.append(InlineKeyboardButton(text="◀️", callback_data=f"reports:history:page:{page - 1}"))
        pagination_row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
        if page < total_pages - 1:
            pagination_row.append(InlineKeyboardButton(text="▶️", callback_data=f"reports:history:page:{page + 1}"))
        rows.append(pagination_row)

    rows.append([InlineKeyboardButton(text=_("actions.back"), callback_data="reports:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reports_schedule_keyboard(schedule: dict) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []

    enabled = schedule.get("reports_enabled", True)
    status_text = _("reports.enabled") if enabled else _("reports.disabled")
    rows.append([InlineKeyboardButton(text=status_text, callback_data="reports:toggle")])
    rows.append([InlineKeyboardButton(text=_("reports.configure_schedule"), callback_data="bot_config:cat:reports")])
    rows.append([InlineKeyboardButton(text=_("actions.back"), callback_data="reports:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reports_view_keyboard(report_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=_("reports.forward"), callback_data=f"reports:forward:{report_id}")],
        [InlineKeyboardButton(text=_("actions.back"), callback_data="reports:history")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reports_custom_period_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=_("reports.last_24h"), callback_data="reports:custom:1")],
        [InlineKeyboardButton(text=_("reports.last_3d"), callback_data="reports:custom:3")],
        [InlineKeyboardButton(text=_("reports.last_7d"), callback_data="reports:custom:7")],
        [InlineKeyboardButton(text=_("reports.last_14d"), callback_data="reports:custom:14")],
        [InlineKeyboardButton(text=_("reports.last_30d"), callback_data="reports:custom:30")],
        [InlineKeyboardButton(text=_("actions.back"), callback_data="reports:menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reports_confirm_generate_keyboard(report_type: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=_("reports.generate"), callback_data=f"reports:confirm:{report_type}"),
            InlineKeyboardButton(text=_("actions.cancel"), callback_data="reports:menu"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reports_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("actions.back"), callback_data="reports:menu")],
        ]
    )

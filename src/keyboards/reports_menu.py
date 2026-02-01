"""Клавиатуры для раздела отчётов по нарушениям."""
from typing import List, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def reports_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню отчётов."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Ежедневный отчёт", callback_data="reports:generate:daily")],
            [InlineKeyboardButton(text="📊 Еженедельный отчёт", callback_data="reports:generate:weekly")],
            [InlineKeyboardButton(text="📊 Ежемесячный отчёт", callback_data="reports:generate:monthly")],
            [InlineKeyboardButton(text="📅 Отчёт за период", callback_data="reports:custom")],
            [InlineKeyboardButton(text="📜 История отчётов", callback_data="reports:history")],
            [InlineKeyboardButton(text="⏰ Расписание", callback_data="reports:schedule")],
            [InlineKeyboardButton(text="⚙️ Настройки отчётов", callback_data="bot_config:cat:reports")],
            nav_row(NavTarget.SYSTEM_MENU),
        ]
    )


def reports_history_keyboard(
    reports: List[dict],
    page: int = 0,
    page_size: int = 5
) -> InlineKeyboardMarkup:
    """Клавиатура с историей отчётов."""
    rows: List[List[InlineKeyboardButton]] = []

    # Пагинация
    total_items = len(reports)
    total_pages = max(1, (total_items + page_size - 1) // page_size)
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_items)
    page_reports = reports[start_idx:end_idx]

    # Эмодзи для типов отчётов
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
            date_str = period_start.strftime("%d.%m.%Y")
        else:
            date_str = "?"

        rows.append([
            InlineKeyboardButton(
                text=f"{emoji} {date_str} — {total} наруш.",
                callback_data=f"reports:view:{report.get('id', 0)}"
            )
        ])

    # Пагинация
    if total_pages > 1:
        pagination_row = []
        if page > 0:
            pagination_row.append(
                InlineKeyboardButton(text="◀️", callback_data=f"reports:history:page:{page - 1}")
            )
        pagination_row.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
        )
        if page < total_pages - 1:
            pagination_row.append(
                InlineKeyboardButton(text="▶️", callback_data=f"reports:history:page:{page + 1}")
            )
        rows.append(pagination_row)

    rows.append([InlineKeyboardButton(text=_("actions.back"), callback_data="reports:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reports_schedule_keyboard(schedule: dict) -> InlineKeyboardMarkup:
    """Клавиатура с расписанием отчётов."""
    rows: List[List[InlineKeyboardButton]] = []

    # Статус глобального включения
    enabled = schedule.get("reports_enabled", True)
    status_text = "✅ Отчёты включены" if enabled else "❌ Отчёты выключены"
    rows.append([
        InlineKeyboardButton(text=status_text, callback_data="reports:toggle")
    ])

    rows.append([InlineKeyboardButton(text="⚙️ Настроить расписание", callback_data="bot_config:cat:reports")])
    rows.append([InlineKeyboardButton(text=_("actions.back"), callback_data="reports:menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def reports_view_keyboard(report_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для просмотра отчёта."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Переслать", callback_data=f"reports:forward:{report_id}")],
            [InlineKeyboardButton(text=_("actions.back"), callback_data="reports:history")],
        ]
    )


def reports_custom_period_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора периода для кастомного отчёта."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📅 Последние 24 часа", callback_data="reports:custom:1")],
            [InlineKeyboardButton(text="📅 Последние 3 дня", callback_data="reports:custom:3")],
            [InlineKeyboardButton(text="📅 Последние 7 дней", callback_data="reports:custom:7")],
            [InlineKeyboardButton(text="📅 Последние 14 дней", callback_data="reports:custom:14")],
            [InlineKeyboardButton(text="📅 Последние 30 дней", callback_data="reports:custom:30")],
            [InlineKeyboardButton(text=_("actions.back"), callback_data="reports:menu")],
        ]
    )


def reports_confirm_generate_keyboard(report_type: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения генерации отчёта."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сгенерировать", callback_data=f"reports:confirm:{report_type}"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="reports:menu"),
            ]
        ]
    )


def reports_back_keyboard() -> InlineKeyboardMarkup:
    """Простая клавиатура с кнопкой назад."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("actions.back"), callback_data="reports:menu")],
        ]
    )

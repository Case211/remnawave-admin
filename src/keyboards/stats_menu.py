from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def stats_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("stats.panel_stats"), callback_data="stats:panel")],
            [InlineKeyboardButton(text=_("stats.server_stats"), callback_data="stats:server")],
            [InlineKeyboardButton(text=_("stats.traffic_stats"), callback_data="stats:traffic")],
            nav_row(NavTarget.SYSTEM_MENU),
        ]
    )


def stats_period_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора периода статистики трафика."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("stats.period_today"), callback_data="stats:traffic_period:today"),
                InlineKeyboardButton(text=_("stats.period_week"), callback_data="stats:traffic_period:week"),
            ],
            [
                InlineKeyboardButton(text=_("stats.period_month"), callback_data="stats:traffic_period:month"),
                InlineKeyboardButton(text=_("stats.period_3months"), callback_data="stats:traffic_period:3months"),
            ],
            [
                InlineKeyboardButton(text=_("stats.period_year"), callback_data="stats:traffic_period:year"),
            ],
            nav_row(NavTarget.STATS_MENU),
        ]
    )


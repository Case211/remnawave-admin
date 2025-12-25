from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def user_stats_keyboard(user_uuid: str, back_to: str = NavTarget.USERS_MENU) -> InlineKeyboardMarkup:
    """Клавиатура для статистики пользователя."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("user.stats.subscription_history"), callback_data=f"user_stats:sub_history:{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("user.stats.traffic"), callback_data=f"user_stats:traffic:{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("user.stats.nodes_usage"), callback_data=f"user_stats:nodes:{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("user.stats.hwid"), callback_data=f"user_stats:hwid:{user_uuid}"),
            ],
            nav_row(back_to),
        ]
    )


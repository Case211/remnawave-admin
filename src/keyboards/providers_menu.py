from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def providers_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("provider.create"), callback_data="providers:create")],
            [InlineKeyboardButton(text=_("provider.update"), callback_data="providers:update")],
            [InlineKeyboardButton(text=_("provider.delete"), callback_data="providers:delete")],
            nav_row(NavTarget.BILLING_OVERVIEW),
        ]
    )

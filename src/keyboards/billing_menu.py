from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def billing_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("billing.stats"), callback_data="billing:stats")],
            [InlineKeyboardButton(text=_("billing.create"), callback_data="billing:create")],
            [InlineKeyboardButton(text=_("billing.delete"), callback_data="billing:delete")],
            nav_row(NavTarget.BILLING_OVERVIEW),
        ]
    )

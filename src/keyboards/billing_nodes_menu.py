from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def billing_nodes_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("billing_nodes.stats"), callback_data="billing_nodes:stats")],
            [InlineKeyboardButton(text=_("billing_nodes.create"), callback_data="billing_nodes:create")],
            [InlineKeyboardButton(text=_("billing_nodes.update"), callback_data="billing_nodes:update")],
            [InlineKeyboardButton(text=_("billing_nodes.delete"), callback_data="billing_nodes:delete")],
            nav_row(NavTarget.BILLING_OVERVIEW),
        ]
    )

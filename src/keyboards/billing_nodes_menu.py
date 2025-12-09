from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _


def billing_nodes_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("billing_nodes.create"), callback_data="billing_nodes:create")],
            [InlineKeyboardButton(text=_("billing_nodes.update"), callback_data="billing_nodes:update")],
            [InlineKeyboardButton(text=_("billing_nodes.delete"), callback_data="billing_nodes:delete")],
            [InlineKeyboardButton(text=_("actions.back"), callback_data="menu:back")],
        ]
    )

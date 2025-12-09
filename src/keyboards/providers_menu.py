from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _


def providers_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("provider.create"), callback_data="providers:create")],
            [InlineKeyboardButton(text=_("provider.update"), callback_data="providers:update")],
            [InlineKeyboardButton(text=_("provider.delete"), callback_data="providers:delete")],
            [InlineKeyboardButton(text=_("actions.back"), callback_data="menu:back")],
        ]
    )

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _


def template_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("template.create"), callback_data="template:create")],
            [InlineKeyboardButton(text=_("template.reorder"), callback_data="template:reorder")],
            [InlineKeyboardButton(text=_("actions.back"), callback_data="menu:back")],
        ]
    )

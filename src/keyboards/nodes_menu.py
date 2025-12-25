from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def nodes_list_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для меню списка нод с полным функционалом."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("node.list"), callback_data="nodes:list")],
            [InlineKeyboardButton(text=_("node.create"), callback_data="nodes:create")],
            [InlineKeyboardButton(text=_("node.update"), callback_data="nodes:update")],
            [InlineKeyboardButton(text=_("node.bulk_profile_modification"), callback_data="nodes:bulk_profile")],
            [InlineKeyboardButton(text=_("actions.system_nodes"), callback_data="menu:system_nodes")],
            nav_row(NavTarget.NODES_MENU),
        ]
    )


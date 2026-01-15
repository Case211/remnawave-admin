from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def bulk_nodes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("bulk_nodes.profile"), callback_data="bulk:nodes:profile")],
            [InlineKeyboardButton(text=_("bulk_nodes.enable_all"), callback_data="bulk:nodes:enable_all")],
            [InlineKeyboardButton(text=_("bulk_nodes.disable_all"), callback_data="bulk:nodes:disable_all")],
            [InlineKeyboardButton(text=_("bulk_nodes.restart_all"), callback_data="bulk:nodes:restart_all")],
            [InlineKeyboardButton(text=_("bulk_nodes.reset_traffic_all"), callback_data="bulk:nodes:reset_traffic_all")],
            [InlineKeyboardButton(text=_("bulk_nodes.assign_profile"), callback_data="bulk:nodes:assign_profile")],
            nav_row(NavTarget.BULK_MENU),
        ]
    )

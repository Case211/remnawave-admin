from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def system_nodes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("system_nodes.template_enable_all"), callback_data="system:nodes:enable_all")],
            [InlineKeyboardButton(text=_("system_nodes.template_disable_all"), callback_data="system:nodes:disable_all")],
            [InlineKeyboardButton(text=_("system_nodes.template_restart_all"), callback_data="system:nodes:restart_all")],
            [InlineKeyboardButton(text=_("system_nodes.template_reset_traffic_all"), callback_data="system:nodes:reset_traffic_all")],
            [InlineKeyboardButton(text=_("system_nodes.template_assign_profile"), callback_data="system:nodes:assign_profile")],
            [InlineKeyboardButton(text=_("system_nodes.list"), callback_data="system:nodes:list")],
            nav_row(NavTarget.NODES_LIST),
        ]
    )


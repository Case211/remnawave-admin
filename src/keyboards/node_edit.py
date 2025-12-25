from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def node_edit_keyboard(node_uuid: str, back_to: str = NavTarget.NODES_LIST) -> InlineKeyboardMarkup:
    """Клавиатура для редактирования ноды."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("node.edit_name"), callback_data=f"nef:name::{node_uuid}"),
                InlineKeyboardButton(text=_("node.edit_address"), callback_data=f"nef:address::{node_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("node.edit_port"), callback_data=f"nef:port::{node_uuid}"),
                InlineKeyboardButton(text=_("node.edit_country_code"), callback_data=f"nef:country_code::{node_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("node.edit_provider"), callback_data=f"nef:provider::{node_uuid}"),
                InlineKeyboardButton(text=_("node.edit_config_profile"), callback_data=f"nef:config_profile::{node_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("node.edit_traffic_limit"), callback_data=f"nef:traffic_limit::{node_uuid}"),
                InlineKeyboardButton(text=_("node.edit_notify_percent"), callback_data=f"nef:notify_percent::{node_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("node.edit_traffic_reset_day"), callback_data=f"nef:traffic_reset_day::{node_uuid}"),
                InlineKeyboardButton(text=_("node.edit_consumption_multiplier"), callback_data=f"nef:consumption_multiplier::{node_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("node.edit_tags"), callback_data=f"nef:tags::{node_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("node.delete"), callback_data=f"node_delete:{node_uuid}"),
            ],
            nav_row(back_to),
        ]
    )


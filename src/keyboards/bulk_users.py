from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _


def bulk_users_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("bulk.reset_all_traffic"), callback_data="bulk:users:reset")],
            [InlineKeyboardButton(text=_("bulk.delete_expired"), callback_data="bulk:users:delete:EXPIRED")],
            [
                InlineKeyboardButton(text=_("bulk.extend_all_7"), callback_data="bulk:users:extend_all:7"),
                InlineKeyboardButton(text=_("bulk.extend_all_30"), callback_data="bulk:users:extend_all:30"),
            ],
            [
                InlineKeyboardButton(text=_("bulk.btn_delete"), callback_data="bulk:prompt:delete"),
                InlineKeyboardButton(text=_("bulk.btn_revoke"), callback_data="bulk:prompt:revoke"),
            ],
            [
                InlineKeyboardButton(text=_("bulk.btn_reset_selected"), callback_data="bulk:prompt:reset"),
                InlineKeyboardButton(text=_("bulk.btn_extend_selected"), callback_data="bulk:prompt:extend"),
            ],
            [
                InlineKeyboardButton(text=_("bulk.btn_status"), callback_data="bulk:prompt:status"),
            ],
            [InlineKeyboardButton(text=_("bulk.show_usage"), callback_data="bulk:users:usage")],
            [InlineKeyboardButton(text=_("actions.back"), callback_data="menu:back")],
        ]
    )

"""Клавиатура для меню синхронизации ASN базы."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def asn_sync_menu_keyboard() -> InlineKeyboardMarkup:
    """Меню синхронизации ASN базы."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("asn_sync.full_sync"), callback_data="asn_sync:full")],
            [InlineKeyboardButton(text=_("asn_sync.limit_100"), callback_data="asn_sync:limit:100")],
            [InlineKeyboardButton(text=_("asn_sync.limit_500"), callback_data="asn_sync:limit:500")],
            [InlineKeyboardButton(text=_("asn_sync.limit_1000"), callback_data="asn_sync:limit:1000")],
            [InlineKeyboardButton(text=_("asn_sync.custom_limit"), callback_data="asn_sync:custom")],
            [InlineKeyboardButton(text=_("asn_sync.status"), callback_data="asn_sync:status")],
            nav_row(NavTarget.SYSTEM_MENU),
        ]
    )

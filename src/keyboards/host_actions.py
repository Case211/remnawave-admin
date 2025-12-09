from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _


def host_actions_keyboard(host_uuid: str, is_disabled: bool) -> InlineKeyboardMarkup:
    toggle_action = "enable" if is_disabled else "disable"
    toggle_text = _("host.enable") if is_disabled else _("host.disable")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=toggle_text, callback_data=f"host:{host_uuid}:{toggle_action}"),
            ],
            [
                InlineKeyboardButton(text=_("actions.back"), callback_data="menu:back"),
            ],
        ]
    )

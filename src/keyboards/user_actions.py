from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _


def user_actions_keyboard(user_uuid: str, status: str) -> InlineKeyboardMarkup:
    toggle_action = "enable" if status == "DISABLED" else "disable"
    toggle_text = _("actions.enable") if status == "DISABLED" else _("actions.disable")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=toggle_text, callback_data=f"user:{user_uuid}:{toggle_action}"),
                InlineKeyboardButton(text=_("actions.reset_traffic"), callback_data=f"user:{user_uuid}:reset"),
            ],
            [
                InlineKeyboardButton(text=_("actions.revoke"), callback_data=f"user:{user_uuid}:revoke"),
                InlineKeyboardButton(text=_("actions.back"), callback_data="menu:back"),
            ],
        ]
    )

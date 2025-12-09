from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _


def node_actions_keyboard(node_uuid: str, is_disabled: bool) -> InlineKeyboardMarkup:
    toggle_action = "enable" if is_disabled else "disable"
    toggle_text = _("node.enable") if is_disabled else _("node.disable")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=toggle_text, callback_data=f"node:{node_uuid}:{toggle_action}"),
                InlineKeyboardButton(text=_("node.restart"), callback_data=f"node:{node_uuid}:restart"),
            ],
            [
                InlineKeyboardButton(text=_("node.reset_traffic"), callback_data=f"node:{node_uuid}:reset"),
                InlineKeyboardButton(text=_("actions.back"), callback_data="menu:back"),
            ],
        ]
    )

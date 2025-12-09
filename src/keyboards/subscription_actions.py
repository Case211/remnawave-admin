from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _


def subscription_keyboard(subscription_url: str | None) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text=_("actions.back"), callback_data="menu:back"),
        ]
    ]
    if subscription_url:
        buttons.insert(
            0,
            [
                InlineKeyboardButton(text=_("sub.open_url"), url=subscription_url),
            ],
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)

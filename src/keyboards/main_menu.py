from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("actions.ping"), callback_data="menu:ping"),
                InlineKeyboardButton(text=_("actions.settings"), callback_data="menu:settings"),
            ],
            [
                InlineKeyboardButton(text=_("actions.health"), callback_data="menu:health"),
                InlineKeyboardButton(text=_("actions.stats"), callback_data="menu:stats"),
            ],
            [
                InlineKeyboardButton(text=_("actions.find_user"), callback_data="menu:find_user"),
                InlineKeyboardButton(text=_("actions.nodes"), callback_data="menu:nodes"),
            ],
            [
                InlineKeyboardButton(text=_("actions.hosts"), callback_data="menu:hosts"),
                InlineKeyboardButton(text=_("actions.subs"), callback_data="menu:subs"),
            ],
            [
                InlineKeyboardButton(text=_("actions.tokens"), callback_data="menu:tokens"),
                InlineKeyboardButton(text=_("actions.templates"), callback_data="menu:templates"),
            ],
            [
                InlineKeyboardButton(text=_("actions.snippets"), callback_data="menu:snippets"),
                InlineKeyboardButton(text=_("actions.configs"), callback_data="menu:configs"),
                InlineKeyboardButton(text=_("actions.providers"), callback_data="menu:providers"),
                InlineKeyboardButton(text=_("actions.billing"), callback_data="menu:billing"),
                InlineKeyboardButton(text=_("actions.billing_nodes"), callback_data="menu:billing_nodes"),
            ],
            [
                InlineKeyboardButton(text=_("actions.bulk_users"), callback_data="menu:bulk_users"),
                InlineKeyboardButton(text=_("actions.bulk_hosts"), callback_data="menu:bulk_hosts"),
                InlineKeyboardButton(text=_("actions.bulk_nodes"), callback_data="menu:bulk_nodes"),
            ],
        ]
    )

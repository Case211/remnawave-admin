from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("actions.menu_users"), callback_data="menu:section:users")],
            [InlineKeyboardButton(text=_("actions.menu_nodes"), callback_data="menu:section:nodes")],
            [InlineKeyboardButton(text=_("actions.menu_resources"), callback_data="menu:section:resources")],
            [InlineKeyboardButton(text=_("actions.menu_billing"), callback_data="menu:section:billing")],
            [InlineKeyboardButton(text=_("actions.menu_bulk"), callback_data="menu:section:bulk")],
            [InlineKeyboardButton(text=_("actions.menu_system"), callback_data="menu:section:system")],
        ]
    )


def system_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("actions.health"), callback_data="menu:health")],
            [InlineKeyboardButton(text=_("actions.stats"), callback_data="menu:stats")],
            nav_row(NavTarget.MAIN_MENU),
        ]
    )


def users_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("actions.create_user"), callback_data="menu:create_user")],
            [InlineKeyboardButton(text=_("actions.find_user"), callback_data="menu:find_user")],
            [InlineKeyboardButton(text=_("actions.subs"), callback_data="menu:subs")],
            nav_row(NavTarget.MAIN_MENU),
        ]
    )


def nodes_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("actions.nodes"), callback_data="menu:nodes")],
            [InlineKeyboardButton(text=_("actions.hosts"), callback_data="menu:hosts")],
            [InlineKeyboardButton(text=_("actions.configs"), callback_data="menu:configs")],
            nav_row(NavTarget.MAIN_MENU),
        ]
    )


def resources_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("actions.tokens"), callback_data="menu:tokens")],
            [InlineKeyboardButton(text=_("actions.templates"), callback_data="menu:templates")],
            [InlineKeyboardButton(text=_("actions.snippets"), callback_data="menu:snippets")],
            nav_row(NavTarget.MAIN_MENU),
        ]
    )


def billing_overview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("actions.billing"), callback_data="menu:billing")],
            [InlineKeyboardButton(text=_("actions.billing_nodes"), callback_data="menu:billing_nodes")],
            [InlineKeyboardButton(text=_("actions.providers"), callback_data="menu:providers")],
            nav_row(NavTarget.MAIN_MENU),
        ]
    )


def bulk_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("actions.bulk_users"), callback_data="menu:bulk_users")],
            [InlineKeyboardButton(text=_("actions.bulk_hosts"), callback_data="menu:bulk_hosts")],
            nav_row(NavTarget.MAIN_MENU),
        ]
    )

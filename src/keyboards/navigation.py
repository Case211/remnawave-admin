from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _


class NavTarget:
    MAIN_MENU = "main_menu"
    USERS_MENU = "users_menu"
    NODES_MENU = "nodes_menu"
    RESOURCES_MENU = "resources_menu"
    BILLING_MENU = "billing_menu"
    BILLING_NODES_MENU = "billing_nodes_menu"
    PROVIDERS_MENU = "providers_menu"
    BULK_MENU = "bulk_menu"
    SYSTEM_MENU = "system_menu"
    TEMPLATES_MENU = "templates_menu"
    SNIPPETS_MENU = "snippets_menu"
    TOKENS_MENU = "tokens_menu"
    HOSTS_MENU = "hosts_menu"
    NODES_LIST = "nodes_list"
    CONFIGS_MENU = "configs_menu"
    USER_SEARCH_PROMPT = "user_search_prompt"
    USER_SEARCH_RESULTS = "user_search_results"
    SUBS_LIST = "subs_list"


def nav_row(back_to: str | None = None) -> list[InlineKeyboardButton]:
    buttons = []
    if back_to:
        buttons.append(InlineKeyboardButton(text=_("actions.back"), callback_data=f"nav:back:{back_to}"))
    buttons.append(InlineKeyboardButton(text=_("actions.main_menu"), callback_data="nav:home"))
    return buttons


def nav_keyboard(back_to: str | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[nav_row(back_to)])

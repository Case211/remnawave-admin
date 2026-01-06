from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _


class NavTarget:
    MAIN_MENU = "main_menu"
    USERS_MENU = "users_menu"
    NODES_MENU = "nodes_menu"
    RESOURCES_MENU = "resources_menu"
    BILLING_OVERVIEW = "billing_overview"
    BILLING_MENU = "billing_menu"
    BILLING_NODES_MENU = "billing_nodes_menu"
    PROVIDERS_MENU = "providers_menu"
    BULK_MENU = "bulk_menu"
    SYSTEM_MENU = "system_menu"
    STATS_MENU = "stats_menu"
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


def input_keyboard(action: str | None = None, allow_skip: bool = False, skip_callback: str | None = None) -> InlineKeyboardMarkup:
    """Клавиатура для использования во время ввода данных (только Назад и Главное меню)."""
    # Определяем целевое меню на основе action
    back_to = None
    if action:
        if action.startswith("provider_"):
            back_to = NavTarget.PROVIDERS_MENU
        elif action.startswith("billing_history_"):
            back_to = NavTarget.BILLING_MENU
        elif action.startswith("billing_nodes_"):
            back_to = NavTarget.BILLING_NODES_MENU
        elif action == "user_create" or action == "user_edit":
            back_to = NavTarget.USERS_MENU
        elif action.startswith("bulk_users_"):
            back_to = NavTarget.BULK_MENU
        elif action.startswith("template_"):
            back_to = NavTarget.TEMPLATES_MENU
        elif action == "node_create":
            back_to = NavTarget.NODES_LIST
        elif action == "host_create":
            back_to = NavTarget.HOSTS_MENU
        elif action == "host_edit":
            back_to = NavTarget.HOSTS_MENU
    
    buttons = nav_row(back_to)
    if allow_skip and skip_callback:
        buttons.insert(0, InlineKeyboardButton(text=_("actions.skip_step"), callback_data=skip_callback))
    
    return InlineKeyboardMarkup(inline_keyboard=[buttons])
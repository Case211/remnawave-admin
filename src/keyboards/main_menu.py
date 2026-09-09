from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from src.utils.chat_context import is_private_chat
from src.utils.panel_link import panel_web_app_url


def panel_web_app_button() -> InlineKeyboardButton | None:
    """Кнопка «Открыть панель» (Telegram Mini App) либо None.

    Панель авторизует администратора автоматически по подписанным
    initData — отдельный вход внутри мини-аппа не нужен. Кнопка
    появляется только если задан публичный https-адрес панели.
    """
    if not is_private_chat():
        # В группах Telegram отклоняет всё сообщение с WebApp-кнопкой
        return None
    url = panel_web_app_url()
    if not url:
        return None
    return InlineKeyboardButton(text=_("actions.open_panel"), web_app=WebAppInfo(url=url))


def main_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    kb = []

    row1 = []
    if admin is None or admin.has_perm_sync("users", "view"):
        row1.append(InlineKeyboardButton(text=_("actions.menu_users"), callback_data="menu:section:users"))
    if admin is None or admin.has_perm_sync("nodes", "view"):
        row1.append(InlineKeyboardButton(text=_("actions.menu_nodes"), callback_data="menu:section:nodes"))
    if row1:
        kb.append(row1)

    row2 = []
    if admin is None or admin.has_perm_sync("admins", "view") or admin.has_perm_sync("templates", "view"):
        row2.append(InlineKeyboardButton(text=_("actions.menu_resources"), callback_data="menu:section:resources"))
    if admin is None or admin.has_perm_sync("billing", "view"):
        row2.append(InlineKeyboardButton(text=_("actions.menu_billing"), callback_data="menu:section:billing"))
    if row2:
        kb.append(row2)

    row3 = []
    if admin is None or admin.has_perm_sync("users", "bulk_operations"):
        row3.append(InlineKeyboardButton(text=_("actions.menu_bulk"), callback_data="menu:section:bulk"))
    if admin is None or admin.has_perm_sync("analytics", "view") or admin.has_perm_sync("reports", "view"):
        row3.append(InlineKeyboardButton(text=_("actions.menu_system"), callback_data="menu:section:system"))
    if row3:
        kb.append(row3)

    panel_button = panel_web_app_button()
    if panel_button:
        kb.append([panel_button])

    kb.append([InlineKeyboardButton(text=_("actions.refresh"), callback_data="menu:refresh")])

    return InlineKeyboardMarkup(inline_keyboard=kb)


def system_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    kb = []
    kb.append([InlineKeyboardButton(text=_("actions.health"), callback_data="menu:health")])
    if admin is None or admin.has_perm_sync("analytics", "view"):
        kb.append([InlineKeyboardButton(text=_("actions.stats"), callback_data="menu:stats")])
    if admin is None or admin.has_perm_sync("reports", "view"):
        kb.append([InlineKeyboardButton(text=_("actions.reports"), callback_data="menu:reports")])
    if admin is None or admin.has_perm_sync("settings", "edit"):
        kb.append([InlineKeyboardButton(text=_("actions.bot_config"), callback_data="menu:bot_config")])
    if admin is None or admin.has_perm_sync("settings", "edit"):
        kb.append([InlineKeyboardButton(text=_("actions.sync_asn"), callback_data="menu:sync_asn")])
    kb.append([InlineKeyboardButton(text=_("actions.quota"), callback_data="menu:quota")])
    kb.append(nav_row(NavTarget.MAIN_MENU))
    return InlineKeyboardMarkup(inline_keyboard=kb)


def users_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    kb = []
    if admin is None or admin.has_perm_sync("users", "create"):
        kb.append([InlineKeyboardButton(text=_("actions.create_user"), callback_data="menu:create_user")])
    if admin is None or admin.has_perm_sync("users", "view"):
        kb.append([InlineKeyboardButton(text=_("actions.find_user"), callback_data="menu:find_user")])
        kb.append([InlineKeyboardButton(text=_("actions.subs"), callback_data="menu:subs")])
    kb.append(nav_row(NavTarget.MAIN_MENU))
    return InlineKeyboardMarkup(inline_keyboard=kb)


def nodes_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    kb = []
    if admin is None or admin.has_perm_sync("nodes", "view"):
        kb.append([InlineKeyboardButton(text=_("actions.nodes"), callback_data="menu:nodes")])
    if admin is None or admin.has_perm_sync("hosts", "view"):
        kb.append([InlineKeyboardButton(text=_("actions.hosts"), callback_data="menu:hosts")])
    if admin is None or admin.has_perm_sync("nodes", "view"):
        kb.append([InlineKeyboardButton(text=_("actions.configs"), callback_data="menu:configs")])
    kb.append(nav_row(NavTarget.MAIN_MENU))
    return InlineKeyboardMarkup(inline_keyboard=kb)


def resources_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    kb = []
    if admin is None or admin.has_perm_sync("templates", "view"):
        kb.append([InlineKeyboardButton(text=_("actions.templates"), callback_data="menu:templates")])
    if admin is None or admin.has_perm_sync("admins", "view"):
        kb.append([InlineKeyboardButton(text=_("actions.snippets"), callback_data="menu:snippets")])
    kb.append(nav_row(NavTarget.MAIN_MENU))
    return InlineKeyboardMarkup(inline_keyboard=kb)


def billing_overview_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    kb = []
    if admin is None or admin.has_perm_sync("billing", "view"):
        kb.append([InlineKeyboardButton(text=_("actions.billing"), callback_data="menu:billing")])
        kb.append([InlineKeyboardButton(text=_("actions.billing_nodes"), callback_data="menu:billing_nodes")])
        kb.append([InlineKeyboardButton(text=_("actions.providers"), callback_data="menu:providers")])
    kb.append(nav_row(NavTarget.MAIN_MENU))
    return InlineKeyboardMarkup(inline_keyboard=kb)


def bulk_menu_keyboard(admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    kb = []
    if admin is None or admin.has_perm_sync("users", "bulk_operations"):
        kb.append([InlineKeyboardButton(text=_("actions.bulk_users"), callback_data="menu:bulk_users")])
    if admin is None or admin.has_perm_sync("hosts", "edit"):
        kb.append([InlineKeyboardButton(text=_("actions.bulk_hosts"), callback_data="menu:bulk_hosts")])
    if admin is None or admin.has_perm_sync("nodes", "edit"):
        kb.append([InlineKeyboardButton(text=_("actions.bulk_nodes"), callback_data="menu:bulk_nodes")])
    kb.append(nav_row(NavTarget.MAIN_MENU))
    return InlineKeyboardMarkup(inline_keyboard=kb)

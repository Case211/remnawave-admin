from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.utils.auth import BotAdmin
from src.keyboards import perm_btn


def user_actions_keyboard(user_uuid: str, status: str, back_to: str = NavTarget.USERS_MENU, admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    toggle_action = "enable" if status == "DISABLED" else "disable"
    toggle_text = _("actions.enable") if status == "DISABLED" else _("actions.disable")
    rows = []
    row1 = [b for b in [
        perm_btn(admin, "users", "edit", toggle_text, f"user:{user_uuid}:{toggle_action}"),
        perm_btn(admin, "users", "edit", _("actions.reset_traffic"), f"user:{user_uuid}:reset"),
    ] if b is not None]
    if row1:
        rows.append(row1)
    row2 = [b for b in [
        perm_btn(admin, "users", "delete", _("actions.revoke"), f"user:{user_uuid}:revoke"),
        InlineKeyboardButton(text=_("user.configs_button"), callback_data=f"ucfg:{user_uuid}"),
    ] if b is not None]
    if row2:
        rows.append(row2)
    row3 = [b for b in [
        perm_btn(admin, "users", "view", _("user.qr_button"), f"uqr:{user_uuid}"),
        perm_btn(admin, "users", "edit", _("user.edit"), f"user_edit:{user_uuid}"),
    ] if b is not None]
    if row3:
        rows.append(row3)
    row4 = [
        InlineKeyboardButton(text=_("user.stats"), callback_data=f"user_stats:{user_uuid}"),
    ]
    rows.append(row4)
    rows.append(nav_row(back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_edit_keyboard(user_uuid: str, back_to: str = NavTarget.USERS_MENU, admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = []
    row1 = [b for b in [
        perm_btn(admin, "users", "edit", _("user.edit_traffic_limit"), f"uef:traffic::{user_uuid}"),
        perm_btn(admin, "users", "edit", _("user.edit_strategy"), f"uef:strategy::{user_uuid}"),
    ] if b is not None]
    if row1:
        rows.append(row1)
    row2 = [b for b in [
        perm_btn(admin, "users", "edit", _("user.edit_expire"), f"uef:expire::{user_uuid}"),
    ] if b is not None]
    if row2:
        rows.append(row2)
    row3 = [b for b in [
        perm_btn(admin, "users", "edit", _("user.edit_description"), f"uef:description::{user_uuid}"),
        perm_btn(admin, "users", "edit", _("user.edit_tag"), f"uef:tag::{user_uuid}"),
    ] if b is not None]
    if row3:
        rows.append(row3)
    row4 = [b for b in [
        perm_btn(admin, "users", "edit", _("user.edit_telegram"), f"uef:telegram::{user_uuid}"),
        perm_btn(admin, "users", "edit", _("user.edit_email"), f"uef:email::{user_uuid}"),
    ] if b is not None]
    if row4:
        rows.append(row4)
    row5 = [b for b in [
        perm_btn(admin, "users", "edit", _("user.edit_squad"), f"uef:squad::{user_uuid}"),
    ] if b is not None]
    if row5:
        rows.append(row5)
    row6 = [b for b in [
        InlineKeyboardButton(text=_("user.traffic_by_nodes"), callback_data=f"user_traffic_nodes:{user_uuid}"),
        perm_btn(admin, "users", "edit", _("user.hwid_management"), f"user_hwid_menu:{user_uuid}"),
    ] if b is not None]
    if row6:
        rows.append(row6)
    rows.append(nav_row(back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_edit_squad_keyboard(squads: list[dict], user_uuid: str, back_to: str = NavTarget.USERS_MENU, admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = []
    for idx, s in enumerate(squads):
        btn = perm_btn(admin, "users", "edit", s.get("name", "n/a"), f"uef:squad:{idx}:{user_uuid}")
        if btn:
            rows.append([btn])
    btn = perm_btn(admin, "users", "edit", _("user.remove_squad"), f"uef:squad:remove:{user_uuid}")
    if btn:
        rows.append([btn])
    rows.append(nav_row(back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_edit_strategy_keyboard(user_uuid: str, back_to: str = NavTarget.USERS_MENU, admin: BotAdmin | None = None) -> InlineKeyboardMarkup:
    rows = []
    row1 = [b for b in [
        perm_btn(admin, "users", "edit", "NO_RESET", f"uef:strategy:NO_RESET:{user_uuid}"),
        perm_btn(admin, "users", "edit", "DAY", f"uef:strategy:DAY:{user_uuid}"),
    ] if b is not None]
    if row1:
        rows.append(row1)
    row2 = [b for b in [
        perm_btn(admin, "users", "edit", "WEEK", f"uef:strategy:WEEK:{user_uuid}"),
        perm_btn(admin, "users", "edit", "MONTH", f"uef:strategy:MONTH:{user_uuid}"),
    ] if b is not None]
    if row2:
        rows.append(row2)
    row3 = [b for b in [
        perm_btn(admin, "users", "edit", "MONTH_ROLLING", f"uef:strategy:MONTH_ROLLING:{user_uuid}"),
    ] if b is not None]
    if row3:
        rows.append(row3)
    rows.append(nav_row(back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)

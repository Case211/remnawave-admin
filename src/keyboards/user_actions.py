from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def user_actions_keyboard(user_uuid: str, status: str, back_to: str = NavTarget.USERS_MENU) -> InlineKeyboardMarkup:
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
                InlineKeyboardButton(text=_("user.configs_button"), callback_data=f"user_configs:{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("user.edit"), callback_data=f"user_edit:{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("user.stats"), callback_data=f"user_stats:{user_uuid}"),
            ],
            nav_row(back_to),
        ]
    )


def user_edit_keyboard(user_uuid: str, back_to: str = NavTarget.USERS_MENU) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("user.edit_traffic_limit"), callback_data=f"uef:traffic::{user_uuid}"),
                InlineKeyboardButton(text=_("user.edit_strategy"), callback_data=f"uef:strategy::{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("user.edit_expire"), callback_data=f"uef:expire::{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("user.edit_description"), callback_data=f"uef:description::{user_uuid}"),
                InlineKeyboardButton(text=_("user.edit_tag"), callback_data=f"uef:tag::{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("user.edit_telegram"), callback_data=f"uef:telegram::{user_uuid}"),
                InlineKeyboardButton(text=_("user.edit_email"), callback_data=f"uef:email::{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("user.edit_squad"), callback_data=f"uef:squad::{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("user.traffic_by_nodes"), callback_data=f"user_traffic_nodes:{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=_("user.hwid_management"), callback_data=f"user_hwid_menu:{user_uuid}"),
            ],
            nav_row(back_to),
        ]
    )


def user_edit_squad_keyboard(squads: list[dict], user_uuid: str, back_to: str = NavTarget.USERS_MENU) -> InlineKeyboardMarkup:
    # Используем индекс вместо UUID, чтобы callback_data не превышал 64 байта
    rows = [[InlineKeyboardButton(text=s.get("name", "n/a"), callback_data=f"uef:squad:{idx}:{user_uuid}")] for idx, s in enumerate(squads)]
    rows.append([InlineKeyboardButton(text=_("user.remove_squad"), callback_data=f"uef:squad:remove:{user_uuid}")])
    rows.append(nav_row(back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_edit_strategy_keyboard(user_uuid: str, back_to: str = NavTarget.USERS_MENU) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="NO_RESET", callback_data=f"uef:strategy:NO_RESET:{user_uuid}"),
                InlineKeyboardButton(text="DAY", callback_data=f"uef:strategy:DAY:{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text="WEEK", callback_data=f"uef:strategy:WEEK:{user_uuid}"),
                InlineKeyboardButton(text="MONTH", callback_data=f"uef:strategy:MONTH:{user_uuid}"),
            ],
            nav_row(back_to),
        ]
    )

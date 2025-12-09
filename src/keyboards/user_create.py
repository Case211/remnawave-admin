from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _


def user_create_description_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_("user.skip"), callback_data="user_create:skip:description")]]
    )


def user_create_expire_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("user.expire_7d"), callback_data="user_create:expire:7"),
                InlineKeyboardButton(text=_("user.expire_30d"), callback_data="user_create:expire:30"),
            ],
            [
                InlineKeyboardButton(text=_("user.expire_90d"), callback_data="user_create:expire:90"),
                InlineKeyboardButton(text=_("user.expire_365d"), callback_data="user_create:expire:365"),
            ],
        ]
    )


def user_create_traffic_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("user.traffic_5"), callback_data="user_create:traffic:5"),
                InlineKeyboardButton(text=_("user.traffic_50"), callback_data="user_create:traffic:50"),
            ],
            [
                InlineKeyboardButton(text=_("user.traffic_500"), callback_data="user_create:traffic:500"),
                InlineKeyboardButton(text=_("user.traffic_unlimited"), callback_data="user_create:traffic:unlimited"),
            ],
        ]
    )


def user_create_hwid_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("user.hwid_1"), callback_data="user_create:hwid:1"),
                InlineKeyboardButton(text=_("user.hwid_2"), callback_data="user_create:hwid:2"),
            ],
            [
                InlineKeyboardButton(text=_("user.hwid_5"), callback_data="user_create:hwid:5"),
                InlineKeyboardButton(text=_("user.hwid_10"), callback_data="user_create:hwid:10"),
                InlineKeyboardButton(text=_("user.hwid_unlimited"), callback_data="user_create:hwid:0"),
            ],
        ]
    )


def user_create_telegram_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=_("user.skip"), callback_data="user_create:skip:telegram")]]
    )


def user_create_squad_keyboard(squads: list[dict]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=s.get("name", "n/a"), callback_data=f"user_create:squad:{s.get('uuid')}")] for s in squads]
    rows.append([InlineKeyboardButton(text=_("user.skip"), callback_data="user_create:skip:squad")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_create_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("user.confirm_create"), callback_data="user_create:confirm"),
                InlineKeyboardButton(text=_("user.cancel_create"), callback_data="user_create:cancel"),
            ]
        ]
    )

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def template_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("template.create"), callback_data="template:create")],
            [InlineKeyboardButton(text=_("template.reorder"), callback_data="template:reorder")],
            nav_row(NavTarget.RESOURCES_MENU),
        ]
    )


def template_list_keyboard(templates: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=_("template.create"), callback_data="template:create")],
        [InlineKeyboardButton(text=_("template.reorder"), callback_data="template:reorder")],
    ]
    for tpl in templates[:10]:
        name = tpl.get("name", "n/a")
        tpl_type = tpl.get("templateType", "n/a")
        uuid = tpl.get("uuid", "")
        rows.append(
            [InlineKeyboardButton(text=f"{name} ({tpl_type})", callback_data=f"tplview:{uuid}")]
        )
    rows.append(nav_row(NavTarget.RESOURCES_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)
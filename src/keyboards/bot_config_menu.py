"""Клавиатуры для раздела конфигурации бота."""
from typing import List, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row
from src.services.config_service import ConfigCategory, ConfigItem


# Эмодзи для категорий
CATEGORY_EMOJI = {
    ConfigCategory.GENERAL.value: "🔧",
    ConfigCategory.NOTIFICATIONS.value: "🔔",
    ConfigCategory.SYNC.value: "🔄",
    ConfigCategory.VIOLATIONS.value: "🚨",
    ConfigCategory.COLLECTOR.value: "📡",
    ConfigCategory.LIMITS.value: "📊",
    ConfigCategory.APPEARANCE.value: "🎨",
}


def bot_config_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню конфигурации бота."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("bot_config.categories"), callback_data="bot_config:categories")],
            [InlineKeyboardButton(text=_("bot_config.all_settings"), callback_data="bot_config:all")],
            [InlineKeyboardButton(text=_("bot_config.reload"), callback_data="bot_config:reload")],
            nav_row(NavTarget.SYSTEM_MENU),
        ]
    )


def bot_config_categories_keyboard(categories: List[str]) -> InlineKeyboardMarkup:
    """Клавиатура со списком категорий."""
    rows: List[List[InlineKeyboardButton]] = []

    # Названия категорий
    category_names = {
        "general": _("bot_config.cat_general"),
        "notifications": _("bot_config.cat_notifications"),
        "sync": _("bot_config.cat_sync"),
        "violations": _("bot_config.cat_violations"),
        "collector": _("bot_config.cat_collector"),
        "limits": _("bot_config.cat_limits"),
        "appearance": _("bot_config.cat_appearance"),
    }

    for cat in categories:
        emoji = CATEGORY_EMOJI.get(cat, "📁")
        name = category_names.get(cat, cat.title())
        rows.append([
            InlineKeyboardButton(
                text=f"{emoji} {name}",
                callback_data=f"bot_config:cat:{cat}"
            )
        ])

    rows.append([InlineKeyboardButton(text=_("actions.back"), callback_data="bot_config:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bot_config_category_items_keyboard(
    category: str,
    items: List[ConfigItem],
    page: int = 0,
    page_size: int = 8
) -> InlineKeyboardMarkup:
    """Клавиатура с настройками категории."""
    rows: List[List[InlineKeyboardButton]] = []

    # Пагинация
    total_items = len(items)
    total_pages = (total_items + page_size - 1) // page_size
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, total_items)
    page_items = items[start_idx:end_idx]

    for item in page_items:
        # Определяем статус настройки
        if item.env_var_name:
            import os
            env_val = os.getenv(item.env_var_name)
            if env_val:
                status_emoji = "🔒"  # Установлено через .env
            elif item.value:
                status_emoji = "✅"  # Установлено в БД
            else:
                status_emoji = "⚪"  # По умолчанию
        elif item.value:
            status_emoji = "✅"
        else:
            status_emoji = "⚪"

        display_name = item.display_name or item.key
        rows.append([
            InlineKeyboardButton(
                text=f"{status_emoji} {display_name}",
                callback_data=f"bot_config:item:{item.key}"
            )
        ])

    # Пагинация
    if total_pages > 1:
        pagination_row = []
        if page > 0:
            pagination_row.append(
                InlineKeyboardButton(text="◀️", callback_data=f"bot_config:cat:{category}:page:{page - 1}")
            )
        pagination_row.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
        )
        if page < total_pages - 1:
            pagination_row.append(
                InlineKeyboardButton(text="▶️", callback_data=f"bot_config:cat:{category}:page:{page + 1}")
            )
        rows.append(pagination_row)

    rows.append([InlineKeyboardButton(text=_("actions.back"), callback_data="bot_config:categories")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bot_config_item_keyboard(item: ConfigItem) -> InlineKeyboardMarkup:
    """Клавиатура для отдельной настройки."""
    rows: List[List[InlineKeyboardButton]] = []

    # Если есть предустановленные опции - показываем их
    if item.options:
        for option in item.options[:6]:  # Максимум 6 опций
            rows.append([
                InlineKeyboardButton(
                    text=f"📌 {option}",
                    callback_data=f"bot_config:set:{item.key}:{option}"
                )
            ])

    # Для bool типа - показываем переключатели
    elif item.value_type.value == "bool":
        rows.append([
            InlineKeyboardButton(text="✅ Включить", callback_data=f"bot_config:set:{item.key}:true"),
            InlineKeyboardButton(text="❌ Выключить", callback_data=f"bot_config:set:{item.key}:false"),
        ])

    # Для остальных - кнопка ввода нового значения
    else:
        rows.append([
            InlineKeyboardButton(
                text=_("bot_config.enter_value"),
                callback_data=f"bot_config:input:{item.key}"
            )
        ])

    # Сброс к дефолту
    if item.default_value:
        rows.append([
            InlineKeyboardButton(
                text=_("bot_config.reset_default"),
                callback_data=f"bot_config:reset:{item.key}"
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text=_("actions.back"),
            callback_data=f"bot_config:cat:{item.category.value}"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def bot_config_confirm_keyboard(key: str, action: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"bot_config:confirm:{action}:{key}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"bot_config:item:{key}"),
            ]
        ]
    )

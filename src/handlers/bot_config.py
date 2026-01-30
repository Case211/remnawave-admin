"""Обработчики для управления динамической конфигурацией бота."""
import os
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe
from src.keyboards.bot_config_menu import (
    CATEGORY_EMOJI,
    bot_config_categories_keyboard,
    bot_config_category_items_keyboard,
    bot_config_confirm_keyboard,
    bot_config_item_keyboard,
    bot_config_menu_keyboard,
)
from src.services.config_service import ConfigCategory, ConfigItem, config_service
from src.utils.logger import logger

router = Router(name="bot_config")


class ConfigInputState(StatesGroup):
    """Состояния для ввода значений конфигурации."""
    waiting_value = State()


# Названия категорий
CATEGORY_NAMES = {
    "general": "Общие настройки",
    "notifications": "Уведомления",
    "sync": "Синхронизация",
    "violations": "Детектор нарушений",
    "collector": "Collector API",
    "limits": "Лимиты",
    "appearance": "Внешний вид",
}


def _format_config_value(item: ConfigItem) -> str:
    """Форматирует значение настройки для отображения."""
    value, source = config_service.get_effective_value(item.key)

    if item.is_secret and value:
        display_value = "••••••••"
    elif value is None:
        display_value = _("bot_config.not_set")
    elif isinstance(value, bool):
        display_value = "✅ Да" if value else "❌ Нет"
    else:
        display_value = str(value)

    source_label = {
        "env": "🔒 .env",
        "db": "💾 БД",
        "default": "📋 По умолчанию",
        "none": "⚪ Не задано",
    }.get(source, source)

    return display_value, source_label


def _format_item_details(item: ConfigItem) -> str:
    """Форматирует детальную информацию о настройке."""
    display_value, source_label = _format_config_value(item)

    lines = [
        f"*{item.display_name or item.key}*",
        "",
        f"📝 {item.description or 'Нет описания'}",
        "",
        f"*Текущее значение:* `{display_value}`",
        f"*Источник:* {source_label}",
    ]

    if item.env_var_name:
        lines.append(f"*Переменная .env:* `{item.env_var_name}`")

    if item.default_value:
        lines.append(f"*По умолчанию:* `{item.default_value}`")

    if item.options:
        lines.append(f"*Допустимые значения:* {', '.join(f'`{o}`' for o in item.options)}")

    lines.append(f"*Тип:* `{item.value_type.value}`")

    # Предупреждение если значение установлено через .env
    if item.env_var_name:
        env_val = os.getenv(item.env_var_name)
        if env_val:
            lines.append("")
            lines.append("⚠️ _Значение задано в .env и не может быть изменено через бота_")

    return "\n".join(lines)


# === Callback handlers ===

@router.callback_query(F.data == "menu:bot_config")
async def show_bot_config_menu(callback: CallbackQuery) -> None:
    """Показывает главное меню конфигурации бота."""
    text = f"*{_('bot_config.title')}*\n\n{_('bot_config.description')}"
    await _edit_text_safe(callback, text, reply_markup=bot_config_menu_keyboard())


@router.callback_query(F.data == "bot_config:menu")
async def show_bot_config_menu_alt(callback: CallbackQuery) -> None:
    """Альтернативный callback для меню."""
    await show_bot_config_menu(callback)


@router.callback_query(F.data == "bot_config:categories")
async def show_config_categories(callback: CallbackQuery) -> None:
    """Показывает список категорий настроек."""
    categories = config_service.get_categories()

    if not categories:
        await callback.answer(_("bot_config.no_categories"), show_alert=True)
        return

    text = f"*{_('bot_config.select_category')}*\n\n"
    for cat in categories:
        emoji = CATEGORY_EMOJI.get(cat, "📁")
        name = CATEGORY_NAMES.get(cat, cat.title())
        items = config_service.get_by_category(cat)
        text += f"{emoji} *{name}* — {len(items)} настроек\n"

    await _edit_text_safe(callback, text, reply_markup=bot_config_categories_keyboard(categories))


@router.callback_query(F.data.startswith("bot_config:cat:"))
async def show_category_items(callback: CallbackQuery) -> None:
    """Показывает настройки категории."""
    parts = callback.data.split(":")
    category = parts[2]
    page = 0

    # Проверяем пагинацию
    if len(parts) > 4 and parts[3] == "page":
        try:
            page = int(parts[4])
        except ValueError:
            page = 0

    items = config_service.get_by_category(category)

    if not items:
        await callback.answer(_("bot_config.no_settings"), show_alert=True)
        return

    emoji = CATEGORY_EMOJI.get(category, "📁")
    name = CATEGORY_NAMES.get(category, category.title())

    text = f"*{emoji} {name}*\n\n"
    text += _("bot_config.category_hint")
    text += "\n\n"
    text += "🔒 — установлено в .env\n"
    text += "✅ — установлено в БД\n"
    text += "⚪ — значение по умолчанию"

    await _edit_text_safe(
        callback,
        text,
        reply_markup=bot_config_category_items_keyboard(category, items, page)
    )


@router.callback_query(F.data.startswith("bot_config:item:"))
async def show_config_item(callback: CallbackQuery) -> None:
    """Показывает детали настройки."""
    key = callback.data.split(":")[2]
    item = config_service.get_raw(key)

    if not item:
        await callback.answer(_("bot_config.not_found"), show_alert=True)
        return

    text = _format_item_details(item)
    await _edit_text_safe(callback, text, reply_markup=bot_config_item_keyboard(item))


@router.callback_query(F.data.startswith("bot_config:set:"))
async def set_config_value(callback: CallbackQuery) -> None:
    """Устанавливает значение настройки."""
    parts = callback.data.split(":")
    key = parts[2]
    value = ":".join(parts[3:])  # На случай если значение содержит ":"

    item = config_service.get_raw(key)
    if not item:
        await callback.answer(_("bot_config.not_found"), show_alert=True)
        return

    # Проверяем, не установлено ли значение через .env
    if item.env_var_name:
        env_val = os.getenv(item.env_var_name)
        if env_val:
            await callback.answer(_("bot_config.env_locked"), show_alert=True)
            return

    # Устанавливаем значение
    success = await config_service.set(key, value)

    if success:
        await callback.answer(_("bot_config.saved"), show_alert=False)
        # Обновляем экран с деталями
        await show_config_item(callback)
    else:
        await callback.answer(_("bot_config.save_error"), show_alert=True)


@router.callback_query(F.data.startswith("bot_config:input:"))
async def request_config_input(callback: CallbackQuery, state: FSMContext) -> None:
    """Запрашивает ввод значения настройки."""
    key = callback.data.split(":")[2]
    item = config_service.get_raw(key)

    if not item:
        await callback.answer(_("bot_config.not_found"), show_alert=True)
        return

    # Проверяем .env
    if item.env_var_name:
        env_val = os.getenv(item.env_var_name)
        if env_val:
            await callback.answer(_("bot_config.env_locked"), show_alert=True)
            return

    # Сохраняем контекст и просим ввод
    await state.set_state(ConfigInputState.waiting_value)
    await state.update_data(config_key=key, message_id=callback.message.message_id)

    type_hints = {
        "string": "текстовое значение",
        "int": "целое число",
        "float": "число с плавающей точкой",
        "bool": "true/false",
        "json": "JSON объект",
    }

    hint = type_hints.get(item.value_type.value, "значение")
    text = f"*{_('bot_config.enter_value_prompt')}*\n\n"
    text += f"Настройка: *{item.display_name or item.key}*\n"
    text += f"Ожидается: _{hint}_\n\n"
    text += "_Отправьте значение или /cancel для отмены_"

    await callback.message.edit_text(text, parse_mode="Markdown")


@router.message(ConfigInputState.waiting_value)
async def process_config_input(message: Message, state: FSMContext) -> None:
    """Обрабатывает введённое значение настройки."""
    # Отмена
    if message.text and message.text.lower() in ("/cancel", "отмена"):
        await state.clear()
        await message.answer(_("bot_config.input_cancelled"))
        return

    data = await state.get_data()
    key = data.get("config_key")

    if not key:
        await state.clear()
        await message.answer(_("bot_config.input_error"))
        return

    item = config_service.get_raw(key)
    if not item:
        await state.clear()
        await message.answer(_("bot_config.not_found"))
        return

    value = message.text.strip() if message.text else ""

    # Валидация типа
    try:
        if item.value_type.value == "int":
            int(value)
        elif item.value_type.value == "float":
            float(value)
        elif item.value_type.value == "bool":
            if value.lower() not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
                raise ValueError("Invalid boolean")
        elif item.value_type.value == "json":
            import json
            json.loads(value)
    except (ValueError, json.JSONDecodeError) as e:
        await message.answer(
            f"❌ *Ошибка валидации*\n\n"
            f"Ожидается тип: `{item.value_type.value}`\n"
            f"Ошибка: {str(e)}\n\n"
            f"_Попробуйте снова или /cancel для отмены_",
            parse_mode="Markdown"
        )
        return

    # Сохраняем значение
    success = await config_service.set(key, value)
    await state.clear()

    if success:
        await message.answer(
            f"✅ *Настройка сохранена*\n\n"
            f"*{item.display_name or item.key}*: `{value}`",
            parse_mode="Markdown"
        )
    else:
        await message.answer(_("bot_config.save_error"))


@router.callback_query(F.data.startswith("bot_config:reset:"))
async def confirm_reset_config(callback: CallbackQuery) -> None:
    """Подтверждение сброса настройки."""
    key = callback.data.split(":")[2]
    item = config_service.get_raw(key)

    if not item:
        await callback.answer(_("bot_config.not_found"), show_alert=True)
        return

    text = f"*{_('bot_config.confirm_reset')}*\n\n"
    text += f"Настройка: *{item.display_name or item.key}*\n"
    text += f"Будет сброшено к: `{item.default_value or 'пустое значение'}`"

    await _edit_text_safe(callback, text, reply_markup=bot_config_confirm_keyboard(key, "reset"))


@router.callback_query(F.data.startswith("bot_config:confirm:reset:"))
async def reset_config_value(callback: CallbackQuery) -> None:
    """Сбрасывает настройку к значению по умолчанию."""
    key = callback.data.split(":")[3]

    success = await config_service.reset_to_default(key)

    if success:
        await callback.answer(_("bot_config.reset_done"), show_alert=False)
        # Создаём фейковый callback для показа детлей
        callback.data = f"bot_config:item:{key}"
        await show_config_item(callback)
    else:
        await callback.answer(_("bot_config.reset_error"), show_alert=True)


@router.callback_query(F.data == "bot_config:reload")
async def reload_config(callback: CallbackQuery) -> None:
    """Перезагружает конфигурацию из БД."""
    await config_service.reload()
    await callback.answer(_("bot_config.reloaded"), show_alert=True)
    await show_bot_config_menu(callback)


@router.callback_query(F.data == "bot_config:all")
async def show_all_settings(callback: CallbackQuery) -> None:
    """Показывает все настройки (краткий обзор)."""
    all_items = config_service.get_all()

    if not all_items:
        await callback.answer(_("bot_config.no_settings"), show_alert=True)
        return

    lines = [f"*{_('bot_config.all_settings_title')}*", ""]

    current_category = None
    for item in sorted(all_items.values(), key=lambda x: (x.category.value, x.sort_order)):
        if item.category.value != current_category:
            current_category = item.category.value
            emoji = CATEGORY_EMOJI.get(current_category, "📁")
            name = CATEGORY_NAMES.get(current_category, current_category.title())
            lines.append(f"\n*{emoji} {name}*")

        display_value, source = _format_config_value(item)
        source_icon = {"env": "🔒", "db": "💾", "default": "📋"}.get(source.split()[0].lower() if source else "", "⚪")
        lines.append(f"  {source_icon} {item.display_name or item.key}: `{display_value}`")

    # Ограничиваем длину сообщения
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n_...обрезано_"

    await _edit_text_safe(callback, text, reply_markup=bot_config_menu_keyboard())


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery) -> None:
    """Пустой обработчик для информационных кнопок."""
    await callback.answer()

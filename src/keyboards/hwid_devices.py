from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.keyboards.navigation import NavTarget, nav_row


def hwid_devices_keyboard(user_uuid: str, devices: list[dict], back_to: str = NavTarget.USERS_MENU) -> InlineKeyboardMarkup:
    """Клавиатура для управления HWID устройствами пользователя."""
    rows: list[list[InlineKeyboardButton]] = []
    
    # Кнопки для каждого устройства
    for idx, device in enumerate(devices[:10], 1):  # Ограничиваем до 10 устройств
        hwid = device.get("hwid", "n/a")
        # Обрезаем длинный HWID для отображения
        hwid_display = hwid[:20] + "..." if len(hwid) > 20 else hwid
        # Используем индекс устройства вместо HWID в callback_data, чтобы избежать проблем с двоеточиями
        rows.append([
            InlineKeyboardButton(
                text=f"🗑 {idx}. {hwid_display}",
                callback_data=f"hwid_delete_idx:{user_uuid}:{idx-1}"
            )
        ])
    
    # Кнопка удаления всех устройств
    if devices:
        rows.append([
            InlineKeyboardButton(
                text=_("hwid.delete_all"),
                callback_data=f"hwid_delete_all:{user_uuid}"
            )
        ])
    
    rows.append(nav_row(back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)

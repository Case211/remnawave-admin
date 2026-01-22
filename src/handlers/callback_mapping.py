"""Маппинг коротких callback_data на полные UUID для обхода 64-байтового лимита Telegram.

ВАЖНО: Telegram ограничивает callback_data до 64 байт.
Этот модуль предоставляет механизм сжатия длинных callback с двумя UUID в короткие идентификаторы.

Примеры проблемных callback:
- nef:config_profile:{profile_uuid}:{node_uuid} = 92 байта (превышает на 28 байт!)
- nef:provider:{provider_uuid}:{node_uuid} = 86 байт (превышает на 22 байта!)
- hef:inbound:{inbound_uuid}:{host_uuid} = 85 байт (превышает на 21 байт!)

Решение: короткий callback вида "nef_cfg:cb0001" = ~15 байт
"""

from src.utils.logger import logger

# Глобальный словарь для маппинга коротких ID на UUID
# Формат: {short_id: (uuid1, uuid2, callback_type)}
CALLBACK_MAPPING: dict[str, tuple[str, str | None, str]] = {}

# Счётчик для генерации уникальных коротких ID
_SHORT_ID_COUNTER = 0


def generate_short_callback(uuid1: str, uuid2: str | None, callback_type: str) -> str:
    """Генерирует короткий callback_data и сохраняет маппинг.

    Args:
        uuid1: Первый UUID (обязательный)
        uuid2: Второй UUID (опциональный)
        callback_type: Тип callback (например, "nef_cfg", "hef_inb")

    Returns:
        Короткий callback_data вида "{callback_type}:cb{counter}"

    Example:
        >>> generate_short_callback("550e8400-...", "6ba7b810-...", "nef_cfg")
        'nef_cfg:cb0001'
    """
    global _SHORT_ID_COUNTER
    short_id = f"cb{_SHORT_ID_COUNTER:04d}"
    _SHORT_ID_COUNTER += 1
    CALLBACK_MAPPING[short_id] = (uuid1, uuid2, callback_type)

    result = f"{callback_type}:{short_id}"
    logger.debug(
        "Generated short callback: %s -> uuid1=%s uuid2=%s type=%s",
        result, uuid1[:8] if uuid1 else None, uuid2[:8] if uuid2 else None, callback_type
    )
    return result


def resolve_short_callback(callback_data: str) -> tuple[str, str | None, str] | None:
    """Разрешает короткий callback_data обратно в UUID.

    Args:
        callback_data: Короткий callback_data вида "{callback_type}:cb{counter}"

    Returns:
        Кортеж (uuid1, uuid2, callback_type) или None если не найдено

    Example:
        >>> resolve_short_callback("nef_cfg:cb0001")
        ('550e8400-...', '6ba7b810-...', 'nef_cfg')
    """
    parts = callback_data.split(":")
    if len(parts) < 2:
        logger.warning("Invalid short callback format: %s", callback_data)
        return None

    callback_type, short_id = parts[0], parts[1]
    result = CALLBACK_MAPPING.get(short_id)

    if result is None:
        logger.warning("Short callback not found in mapping: %s", callback_data)
    else:
        logger.debug(
            "Resolved short callback: %s -> uuid1=%s uuid2=%s",
            callback_data, result[0][:8] if result[0] else None, result[1][:8] if result[1] else None
        )

    return result


def clear_callback_mapping() -> None:
    """Очищает маппинг коротких callback.

    ВНИМАНИЕ: Используйте с осторожностью! Очистка маппинга сделает
    все активные короткие callback неработоспособными.
    """
    global _SHORT_ID_COUNTER
    CALLBACK_MAPPING.clear()
    _SHORT_ID_COUNTER = 0
    logger.info("Callback mapping cleared")


def get_mapping_stats() -> dict[str, int]:
    """Возвращает статистику по маппингу коротких callback.

    Returns:
        Словарь со статистикой: {'total_mappings': int, 'next_counter': int}
    """
    return {
        "total_mappings": len(CALLBACK_MAPPING),
        "next_counter": _SHORT_ID_COUNTER,
    }

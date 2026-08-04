"""Dynamic settings shared by Telegram notification senders."""
from typing import Any, Optional

from shared.config_service import config_service


NOTIFICATION_TYPES = (
    "users",
    "nodes",
    "service",
    "hwid",
    "crm",
    "errors",
    "violations",
    "finance",
)


def is_notification_type_enabled(notification_type: Optional[str]) -> bool:
    """Return whether Telegram notifications of this type are enabled."""
    if notification_type not in NOTIFICATION_TYPES:
        return True
    return bool(config_service.get(f"notifications_{notification_type}_enabled", True))


def _is_unset(value: Any) -> bool:
    """Пустое значение из БД — «не задано», а не «задано пустым».

    Очищенное в UI поле сохраняется пустой строкой (``config_service.set``
    гонит значение через ``_value_to_string``, где ``None`` → ``""``), а
    ``_convert_value`` для int-настройки на ``int("")`` спотыкается и
    возвращает саму строку. Без этой нормализации очищенный топик уезжал
    бы в Telegram как ``message_thread_id=""`` — API отвечает ошибкой, и
    уведомление теряется молча, в логах.
    """
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _topic_or_none(value: Any) -> Any:
    """Топик, пригодный к отправке, иначе None (чтобы сработал фолбэк).

    Ноль для Telegram — не топик, а его отсутствие. До перехода на
    динамический конфиг топики выбирались через ``X or общий``, поэтому
    и 0, и пустое проваливались в общий топик; сохраняем это поведение.
    """
    if _is_unset(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return None if value == "0" else value
    return None if value == 0 else value


def resolve_notifications_chat_id(fallback: Any = None) -> Any:
    """Resolve the global Telegram chat using DB-first configuration."""
    value = config_service.get("notifications_chat_id")
    return fallback if _is_unset(value) else value


def resolve_notification_topic(
    notification_type: Optional[str],
    *,
    type_fallback: Any = None,
    general_fallback: Any = None,
) -> Any:
    """Resolve a per-type topic, then the common fallback topic."""
    topic = None
    if notification_type in NOTIFICATION_TYPES:
        topic = _topic_or_none(config_service.get(f"notifications_topic_{notification_type}"))
    if topic is None:
        topic = _topic_or_none(config_service.get("notifications_topic_id"))
    if topic is None:
        topic = _topic_or_none(type_fallback)
    if topic is None:
        topic = _topic_or_none(general_fallback)
    return topic

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


def resolve_notifications_chat_id(fallback: Any = None) -> Any:
    """Resolve the global Telegram chat using DB-first configuration."""
    value = config_service.get("notifications_chat_id")
    return fallback if value is None else value


def resolve_notification_topic(
    notification_type: Optional[str],
    *,
    type_fallback: Any = None,
    general_fallback: Any = None,
) -> Any:
    """Resolve a per-type topic, then the common fallback topic."""
    topic = None
    if notification_type in NOTIFICATION_TYPES:
        topic = config_service.get(f"notifications_topic_{notification_type}")
    if topic is None:
        topic = config_service.get("notifications_topic_id")
    if topic is None:
        topic = type_fallback
    if topic is None:
        topic = general_fallback
    return topic

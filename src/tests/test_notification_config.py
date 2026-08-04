"""Regression tests for DB-backed Telegram notification settings."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from shared.notification_config import (
    is_notification_type_enabled,
    resolve_notification_topic,
    resolve_notifications_chat_id,
)
from src.utils.notifications import send_error_notification


def test_dynamic_notification_destination_uses_database_values():
    values = {
        "notifications_chat_id": -100555,
        "notifications_topic_errors": 42,
    }
    with patch("shared.notification_config.config_service.get", side_effect=lambda key, default=None: values.get(key, default)):
        assert resolve_notifications_chat_id(-100111) == -100555
        assert resolve_notification_topic(
            "errors",
            type_fallback=7,
            general_fallback=9,
        ) == 42


def test_notification_topic_falls_back_to_dynamic_general_topic():
    values = {"notifications_topic_id": 99}
    with patch("shared.notification_config.config_service.get", side_effect=lambda key, default=None: values.get(key, default)):
        assert resolve_notification_topic(
            "hwid",
            type_fallback=7,
            general_fallback=9,
        ) == 99


def test_notification_type_toggle_defaults_to_enabled():
    with patch("shared.notification_config.config_service.get", return_value=True):
        assert is_notification_type_enabled("crm") is True


def test_cleared_topic_falls_back_instead_of_empty_thread_id():
    """Очищенное в UI поле хранится пустой строкой, а не NULL.

    Без нормализации такой топик уходил в Telegram как
    ``message_thread_id=""`` и уведомление молча терялось.
    """
    values = {"notifications_topic_errors": "", "notifications_topic_id": ""}
    with patch("shared.notification_config.config_service.get", side_effect=lambda key, default=None: values.get(key, default)):
        assert resolve_notification_topic(
            "errors",
            type_fallback=7,
            general_fallback=9,
        ) == 7


def test_zero_topic_is_treated_as_no_topic():
    """Ноль — не топик, а его отсутствие (поведение прежнего ``X or общий``)."""
    values = {"notifications_topic_hwid": 0, "notifications_topic_id": 0}
    with patch("shared.notification_config.config_service.get", side_effect=lambda key, default=None: values.get(key, default)):
        assert resolve_notification_topic(
            "hwid",
            type_fallback=0,
            general_fallback=9,
        ) == 9


def test_cleared_chat_id_falls_back_to_env():
    """Пустое поле чата — «не задано», иначе уведомления глохнут молча."""
    with patch("shared.notification_config.config_service.get", side_effect=lambda key, default=None: {"notifications_chat_id": ""}.get(key, default)):
        assert resolve_notifications_chat_id(-100111) == -100111


@pytest.mark.asyncio
async def test_bot_sender_uses_dynamic_chat_and_topic():
    settings = SimpleNamespace(
        notifications_chat_id=-100111,
        notifications_topic_errors=7,
        notifications_topic_id=9,
    )
    bot = AsyncMock()

    with (
        patch("src.utils.notifications.get_settings", return_value=settings),
        patch("src.utils.notifications.is_notification_type_enabled", return_value=True),
        patch("src.utils.notifications.resolve_notifications_chat_id", return_value=-100555),
        patch("src.utils.notifications.resolve_notification_topic", return_value=42),
        patch("src.utils.notifications._send_card", new_callable=AsyncMock) as send_card,
        patch("src.utils.notifications._push_dispatch"),
    ):
        await send_error_notification(bot, "errors.test", {"message": "failed"})

    message = send_card.await_args.args[1]
    assert message["chat_id"] == -100555
    assert message["message_thread_id"] == 42


@pytest.mark.asyncio
async def test_disabled_bot_notification_type_does_not_fall_back():
    settings = SimpleNamespace(notifications_chat_id=-100111)
    bot = AsyncMock()

    with (
        patch("src.utils.notifications.get_settings", return_value=settings),
        patch("src.utils.notifications.is_notification_type_enabled", return_value=False),
        patch("src.utils.notifications._send_card", new_callable=AsyncMock) as send_card,
    ):
        await send_error_notification(bot, "errors.test", {"message": "failed"})

    send_card.assert_not_awaited()

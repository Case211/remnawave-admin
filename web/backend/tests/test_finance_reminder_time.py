"""Напоминания о платежах: день и час — в зоне отображения, а не по UTC.

Раньше «сегодня» бралось из ``date.today()`` контейнера. Сутки сменялись в
00:00 UTC, первая же проверка после этого рассылала всё разом — в три часа
ночи по Москве, — а до утра дата в тексте отставала от календаря админа.
"""
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from web.backend.core.finance import reminders as rem

MSK = ZoneInfo("Europe/Moscow")


def _item(days_left=1, reminded=None):
    return {
        "id": 1, "name": "Node-1", "amount": 5.0, "currency": "EUR",
        "next_due_at": "2026-07-20", "days_left": days_left, "is_overdue": False,
        "provider_name": None, "category_name": None, "url": None,
        "last_reminded_at": reminded,
    }


class TestSendTime:
    def test_before_the_hour_waits(self):
        assert rem.is_send_time(datetime(2026, 7, 19, 3, 53, tzinfo=MSK), 19) is False
        assert rem.is_send_time(datetime(2026, 7, 19, 18, 59, tzinfo=MSK), 19) is False

    def test_from_the_hour_until_midnight_sends(self):
        assert rem.is_send_time(datetime(2026, 7, 19, 19, 0, tzinfo=MSK), 19) is True
        # Панель была выключена в назначенный час — напоминание не теряется.
        assert rem.is_send_time(datetime(2026, 7, 19, 23, 40, tzinfo=MSK), 19) is True

    def test_hour_zero_sends_all_day(self):
        assert rem.is_send_time(datetime(2026, 7, 19, 0, 0, tzinfo=MSK), 0) is True


class TestReminderHourSetting:
    @pytest.mark.parametrize("raw,expected", [
        (19, 19), ("7", 7), (0, 0), (23, 23),
        (24, rem.DEFAULT_REMINDER_HOUR), (-1, rem.DEFAULT_REMINDER_HOUR),
        ("вечером", rem.DEFAULT_REMINDER_HOUR), (None, rem.DEFAULT_REMINDER_HOUR),
    ])
    def test_value_is_clamped_to_a_valid_hour(self, raw, expected):
        with patch("shared.config_service.config_service.get", return_value=raw):
            assert rem._reminder_hour() == expected


class TestLocalDay:
    @pytest.mark.asyncio
    async def test_day_is_taken_in_display_zone(self):
        # 22:30 UTC 19 июля — в Москве уже 01:30 20 июля.
        moment = datetime(2026, 7, 19, 22, 30, tzinfo=timezone.utc).astimezone(MSK)
        db = AsyncMock()
        db.is_connected = True
        db.upcoming_finance_payments = AsyncMock(return_value=[_item()])
        db.update_finance_item = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch("shared.timefmt.now", return_value=moment), \
             patch("web.backend.core.notification_service.create_notification", AsyncMock()):
            sent = await rem.check_and_send_reminders()
        assert sent == 1
        assert db.upcoming_finance_payments.await_args.kwargs["today"] == date(2026, 7, 20)
        assert db.update_finance_item.await_args.kwargs["last_reminded_at"] == date(2026, 7, 20)

    @pytest.mark.asyncio
    async def test_already_reminded_on_the_local_day_is_skipped(self):
        db = AsyncMock()
        db.is_connected = True
        db.upcoming_finance_payments = AsyncMock(return_value=[_item(reminded="2026-07-20")])
        notify = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.create_notification", notify):
            sent = await rem.check_and_send_reminders(today=date(2026, 7, 20))
        assert sent == 0
        notify.assert_not_awaited()

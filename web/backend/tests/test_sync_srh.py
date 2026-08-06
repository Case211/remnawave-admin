"""Синк истории запросов подписки: инкремент переживает откат нумерации.

Регрессия: панель нумерует SRH автоинкрементом и при пересоздании своей
таблицы начинает счёт заново — 1 июля она откатилась с 65089 на единицу.
Синк тянул записи по правилу ``id > max_local_id``, поэтому всё пришедшее
после отката считалось уже известным. Ошибок не было, история просто
перестала наполняться, и виджеты «Sub requests» показывали ноль.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from shared.sync import SyncService, _srh_is_new

LAST_LOCAL = datetime(2026, 7, 1, 4, 16, tzinfo=timezone.utc)


def _rec(rid: int, at: str) -> dict:
    return {"id": rid, "userId": 42, "requestAt": at, "requestIp": "10.0.0.1",
            "userAgent": "Happ/3.26.3/Android", "srrRuleName": "Happ"}


def _page(records: list) -> dict:
    return {"response": {"total": len(records), "records": records}}


def _db_mock():
    db = AsyncMock()
    db.is_connected = True
    db.get_srh_max_request_at.return_value = LAST_LOCAL
    db.upsert_srh_records.side_effect = lambda rows: len(rows)
    db.cleanup_old_srh.return_value = 0
    return db


class TestSrhIsNew:
    def test_new_when_nothing_stored(self):
        assert _srh_is_new(_rec(1, "2026-01-01T00:00:00.000Z"), None) is True

    def test_later_than_stored(self):
        assert _srh_is_new(_rec(1, "2026-08-06T12:00:00.000Z"), LAST_LOCAL) is True

    def test_same_moment_is_not_new(self):
        assert _srh_is_new(_rec(1, "2026-07-01T04:16:00.000Z"), LAST_LOCAL) is False

    def test_older_is_not_new(self):
        assert _srh_is_new(_rec(99999, "2026-06-30T00:00:00.000Z"), LAST_LOCAL) is False

    def test_naive_stamp_treated_as_utc(self):
        """Панель может прислать время без зоны — сравнение не должно падать."""
        rec = {"requestAt": datetime(2026, 8, 6, 12, 0)}
        assert _srh_is_new(rec, LAST_LOCAL) is True

    def test_unparsable_stamp_goes_through(self):
        """Кривой формат не должен молча останавливать наполнение."""
        assert _srh_is_new(_rec(1, "не дата"), LAST_LOCAL) is True


class TestSyncSrh:
    @pytest.mark.asyncio
    async def test_survives_panel_id_reset(self):
        """Главная регрессия: id меньше локального максимума, но запись свежая."""
        svc = SyncService()
        db = _db_mock()
        api = AsyncMock()
        api.get_subscription_request_history.return_value = _page([
            _rec(29470, "2026-08-06T12:42:04.436Z"),
            _rec(29469, "2026-08-06T12:40:58.214Z"),
        ])
        with patch("shared.sync.db_service", db), patch("shared.sync.api_client", api):
            synced = await svc.sync_subscription_request_history()

        assert synced == 2
        assert len(db.upsert_srh_records.await_args.args[0]) == 2

    @pytest.mark.asyncio
    async def test_stops_on_known_records(self):
        """Уже сохранённое повторно не заливаем — иначе каждый тик тянул бы всё."""
        svc = SyncService()
        db = _db_mock()
        api = AsyncMock()
        api.get_subscription_request_history.return_value = _page([
            _rec(29470, "2026-08-06T12:42:04.436Z"),
            _rec(64000, "2026-06-30T10:00:00.000Z"),
        ])
        with patch("shared.sync.db_service", db), patch("shared.sync.api_client", api):
            synced = await svc.sync_subscription_request_history()

        assert synced == 1
        assert api.get_subscription_request_history.await_count == 1

    @pytest.mark.asyncio
    async def test_first_run_takes_everything(self):
        """Пустая локальная история — забираем страницу целиком."""
        svc = SyncService()
        db = _db_mock()
        db.get_srh_max_request_at.return_value = None
        api = AsyncMock()
        api.get_subscription_request_history.return_value = _page([
            _rec(3, "2026-05-01T00:00:00.000Z"), _rec(2, "2026-04-01T00:00:00.000Z"),
        ])
        with patch("shared.sync.db_service", db), patch("shared.sync.api_client", api):
            assert await svc.sync_subscription_request_history() == 2

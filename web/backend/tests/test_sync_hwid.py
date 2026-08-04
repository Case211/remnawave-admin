"""Синк HWID-устройств: вебхук-парсер и полный синк.

Регрессии по багрепорту «HWID webhook event without user UUID or HWID»:
- панель шлёт устройство в ключе hwidUserDevice, а синк ждал hwidDevice —
  added/deleted через вебхук молча не выполнялись (уведомление уходило,
  локальная таблица user_hwid_devices не менялась);
- полный синк не чистил юзеров, у которых в панели удалили ПОСЛЕДНЕЕ
  устройство: их нет в выдаче API вообще, per-user синк их не касался,
  записи висели вечно и накручивали кросс-аккаунт HWID-детект.
"""
from unittest.mock import AsyncMock, patch

import pytest

from shared.sync import SyncService


def _db_mock():
    db = AsyncMock()
    db.is_connected = True
    return db


class TestHwidWebhookParsing:
    @pytest.mark.asyncio
    async def test_deleted_with_hwid_user_device_key(self):
        """Реальный формат панели: устройство в hwidUserDevice -> удаление доходит до БД."""
        svc = SyncService()
        db = _db_mock()
        with patch("shared.sync.db_service", db):
            await svc._handle_hwid_webhook("user_hwid_devices.deleted", {
                "user": {"uuid": "U1"},
                "hwidUserDevice": {"hwid": "HW1"},
            })
        db.delete_hwid_device.assert_awaited_once_with(user_uuid="U1", hwid="HW1")

    @pytest.mark.asyncio
    async def test_added_with_hwid_user_device_key(self):
        svc = SyncService()
        db = _db_mock()
        with patch("shared.sync.db_service", db):
            await svc._handle_hwid_webhook("user_hwid_devices.added", {
                "user": {"uuid": "U1"},
                "hwidUserDevice": {"hwid": "HW1", "platform": "Android"},
            })
        db.upsert_hwid_device.assert_awaited_once()
        kwargs = db.upsert_hwid_device.await_args.kwargs
        assert kwargs["user_uuid"] == "U1"
        assert kwargs["hwid"] == "HW1"
        assert kwargs["platform"] == "Android"

    @pytest.mark.asyncio
    async def test_deleted_with_legacy_hwid_device_key(self):
        """Старый ожидаемый формат hwidDevice продолжает работать."""
        svc = SyncService()
        db = _db_mock()
        with patch("shared.sync.db_service", db):
            await svc._handle_hwid_webhook("user_hwid_devices.deleted", {
                "user": {"uuid": "U1"},
                "hwidDevice": {"hwid": "HW1"},
            })
        db.delete_hwid_device.assert_awaited_once_with(user_uuid="U1", hwid="HW1")

    @pytest.mark.asyncio
    async def test_user_uuid_fallback_from_device(self):
        """Без объекта user берём userUuid из самого устройства."""
        svc = SyncService()
        db = _db_mock()
        with patch("shared.sync.db_service", db):
            await svc._handle_hwid_webhook("user_hwid_devices.deleted", {
                "hwidUserDevice": {"hwid": "HW1", "userUuid": "U1"},
            })
        db.delete_hwid_device.assert_awaited_once_with(user_uuid="U1", hwid="HW1")

    @pytest.mark.asyncio
    async def test_malformed_payload_no_db_calls(self):
        svc = SyncService()
        db = _db_mock()
        with patch("shared.sync.db_service", db):
            await svc._handle_hwid_webhook("user_hwid_devices.deleted", {"foo": 1})
        db.delete_hwid_device.assert_not_awaited()
        db.upsert_hwid_device.assert_not_awaited()


class TestFullSyncStaleCleanup:
    @pytest.mark.asyncio
    async def test_removes_users_absent_from_api(self):
        """Юзеры вне выдачи API (последнее устройство удалено) чистятся из БД."""
        svc = SyncService()
        db = _db_mock()
        db.sync_user_hwid_devices = AsyncMock(return_value=1)
        db.delete_hwid_devices_except_users = AsyncMock(return_value=3)
        api = AsyncMock()
        api.get_all_hwid_devices = AsyncMock(return_value={
            "response": {"devices": [{"userUuid": "A", "hwid": "H1"}], "total": 1},
        })
        with patch("shared.sync.db_service", db), patch("shared.sync.api_client", api):
            total = await svc.sync_all_hwid_devices()
        assert total == 1
        db.delete_hwid_devices_except_users.assert_awaited_once()
        assert set(db.delete_hwid_devices_except_users.await_args.args[0]) == {"A"}

    @pytest.mark.asyncio
    async def test_numeric_user_id_resolved_to_local_uuid(self):
        """Panel v3 шлёт числовой userId — в БД он должен идти как локальный uuid.

        Без резолва число уходило прямо в колонку user_uuid типа uuid и asyncpg
        падал с DataError на каждом юзере, оставляя user_hwid_devices пустой.
        """
        svc = SyncService()
        db = _db_mock()
        db.sync_user_hwid_devices = AsyncMock(return_value=1)
        db.delete_hwid_devices_except_users = AsyncMock(return_value=0)
        db.get_user_uuid_by_panel_id = AsyncMock(return_value="U-157")
        api = AsyncMock()
        api.get_all_hwid_devices = AsyncMock(return_value={
            "response": {"devices": [{"userId": 157, "hwid": "H1"}], "total": 1},
        })
        with patch("shared.sync.db_service", db), patch("shared.sync.api_client", api):
            total = await svc.sync_all_hwid_devices()
        assert total == 1
        db.get_user_uuid_by_panel_id.assert_awaited_once_with(157)
        assert db.sync_user_hwid_devices.await_args.args[0] == "U-157"
        assert set(db.delete_hwid_devices_except_users.await_args.args[0]) == {"U-157"}

    @pytest.mark.asyncio
    async def test_unresolvable_panel_id_is_skipped(self):
        """Панельный id без локальной строки пропускаем, а не пишем в БД как есть."""
        svc = SyncService()
        db = _db_mock()
        db.sync_user_hwid_devices = AsyncMock(return_value=1)
        db.delete_hwid_devices_except_users = AsyncMock(return_value=0)
        db.get_user_uuid_by_panel_id = AsyncMock(return_value=None)
        api = AsyncMock()
        api.get_all_hwid_devices = AsyncMock(return_value={
            "response": {"devices": [{"userId": 999, "hwid": "H1"}], "total": 1},
        })
        with patch("shared.sync.db_service", db), patch("shared.sync.api_client", api):
            total = await svc.sync_all_hwid_devices()
        assert total == 0
        db.sync_user_hwid_devices.assert_not_awaited()
        # Никого не отрезолвили — чистку не запускаем, иначе снесём живые записи.
        db.delete_hwid_devices_except_users.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_api_response_does_not_wipe(self):
        """Пустая/битая выдача API не должна снести всю таблицу."""
        svc = SyncService()
        db = _db_mock()
        db.delete_hwid_devices_except_users = AsyncMock()
        api = AsyncMock()
        api.get_all_hwid_devices = AsyncMock(return_value={
            "response": {"devices": [], "total": 0},
        })
        with patch("shared.sync.db_service", db), patch("shared.sync.api_client", api):
            total = await svc.sync_all_hwid_devices()
        assert total == 0
        db.delete_hwid_devices_except_users.assert_not_awaited()

"""Синк устройств одного юзера не отвязывает всех по пустому или битому ответу панели.

Регрессия: базовый HTTP-клиент на пустое тело возвращает ``{}``, синк принимал
это за «устройств нет» и помечал отвязанными все устройства пользователя разом —
в карточке они уезжали в «Удалённые» одной минутой, хотя в панели никуда не делись.
"""
from unittest.mock import AsyncMock, patch

import pytest

from shared.sync import SyncService


def _db_mock():
    db = AsyncMock()
    db.is_connected = True
    db.sync_user_hwid_devices = AsyncMock(return_value=0)
    db.delete_all_user_hwid_devices = AsyncMock(return_value=0)
    return db


async def _run(api_result):
    svc = SyncService()
    db = _db_mock()
    api = AsyncMock()
    api.get_user_hwid_devices = AsyncMock(return_value=api_result)
    with patch("shared.sync.db_service", db), patch("shared.sync.api_client", api):
        result = await svc.sync_user_hwid_devices("U1")
    return result, db


@pytest.mark.asyncio
@pytest.mark.parametrize("api_result", [{}, {"response": {"total": 3}}, {"response": "oops"}, None])
async def test_unknown_response_does_not_unlink(api_result):
    result, db = await _run(api_result)
    assert result == 0
    db.delete_all_user_hwid_devices.assert_not_awaited()
    db.sync_user_hwid_devices.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("api_result", [{"response": {"total": 0, "devices": []}}, {"response": []}, []])
async def test_explicit_empty_list_unlinks_all(api_result):
    """Панель прямо сказала «устройств нет» — отвязываем, как и раньше."""
    result, db = await _run(api_result)
    assert result == 0
    db.delete_all_user_hwid_devices.assert_awaited_once_with("U1")


@pytest.mark.asyncio
async def test_devices_present_are_synced():
    result, db = await _run({"response": {"total": 1, "devices": [{"hwid": "HW1"}]}})
    db.sync_user_hwid_devices.assert_awaited_once_with("U1", [{"hwid": "HW1"}])
    db.delete_all_user_hwid_devices.assert_not_awaited()

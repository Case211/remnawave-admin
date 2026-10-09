"""Очистка отвязанных устройств из карточки юзера.

Отвязанные строки держатся ради детекта абуза триалов, но по ним же нарушения
приходят снова, когда с клиентом уже разобрались и он удалил устройства.
Стереть их — решение админа: отдельная ручка, право users:edit, скоуп юзеров.
"""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from shared.db.network import NetworkMixin

USER = "aaa-111"
URL = f"/api/v2/users/{USER}/hwid-devices/removed"


def _db(deleted=2, connected=True):
    db = MagicMock()
    db.is_connected = connected
    db.purge_removed_hwid_devices = AsyncMock(return_value=deleted)
    db.delete_hwid_device = AsyncMock()
    return db


def _visible(side_effect=None):
    return patch("web.backend.api.v2.users._ensure_user_visible",
                 new_callable=AsyncMock, side_effect=side_effect)


class TestPurgeEndpoint:
    @pytest.mark.asyncio
    async def test_purges_all_removed(self, client):
        db = _db()
        with patch("shared.database.db_service", db), _visible():
            resp = await client.delete(URL)
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"success": True, "deleted": 2}
        db.purge_removed_hwid_devices.assert_awaited_once_with(USER, hwid=None)
        # «removed» не ушло в маршрут /{device_id} как HWID: в панель не ходили
        db.delete_hwid_device.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_purges_one_device(self, client):
        db = _db(deleted=1)
        with patch("shared.database.db_service", db), _visible():
            resp = await client.delete(URL, params={"hwid": "HW-1"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["deleted"] == 1
        db.purge_removed_hwid_devices.assert_awaited_once_with(USER, hwid="HW-1")

    @pytest.mark.asyncio
    async def test_viewer_cannot_purge(self, viewer_client):
        db = _db()
        with patch("shared.database.db_service", db):
            resp = await viewer_client.delete(URL)
        assert resp.status_code == 403
        db.purge_removed_hwid_devices.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_user_outside_scope_is_refused(self, client):
        db = _db()
        with patch("shared.database.db_service", db), _visible(HTTPException(status_code=403)):
            resp = await client.delete(URL)
        assert resp.status_code == 403
        db.purge_removed_hwid_devices.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_db_down_is_reported(self, client):
        """Без базы стирать нечего — админ должен это увидеть, а не «удалено: 0»."""
        db = _db(connected=False)
        with patch("shared.database.db_service", db), _visible():
            resp = await client.delete(URL)
        assert resp.status_code == 503
        db.purge_removed_hwid_devices.assert_not_awaited()


def _mixin(result="DELETE 3"):
    conn = MagicMock(execute=AsyncMock(return_value=result))

    @asynccontextmanager
    async def acquire():
        yield conn

    return SimpleNamespace(is_connected=True, acquire=acquire), conn


class TestPurgeQuery:
    @pytest.mark.asyncio
    async def test_deletes_only_removed_rows(self):
        db, conn = _mixin()
        assert await NetworkMixin.purge_removed_hwid_devices(db, USER) == 3
        sql, *args = conn.execute.await_args.args
        assert sql.startswith("DELETE FROM")
        assert "removed_at IS NOT NULL" in sql and "hwid =" not in sql
        assert args == [USER]

    @pytest.mark.asyncio
    async def test_one_device_by_hwid(self):
        db, conn = _mixin("DELETE 1")
        assert await NetworkMixin.purge_removed_hwid_devices(db, USER, hwid="HW-1") == 1
        sql, *args = conn.execute.await_args.args
        assert "removed_at IS NOT NULL" in sql and "hwid = $2" in sql
        assert args == [USER, "HW-1"]

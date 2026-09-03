"""Активное соединение переписывается только при смене ноды или device_info.

Регрессия: UPDATE без условия давал апдейт на каждое активное соединение
каждый цикл синка — 94 % всей записи в user_connections.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.db.connections import ConnectionsMixin


class _Service(ConnectionsMixin):
    is_connected = True

    def __init__(self, conn):
        self._conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


def _conn():
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value="inet")
    conn.execute = AsyncMock(side_effect=["UPDATE 0", "INSERT 0 1", "UPDATE 0"])
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    return conn


@pytest.mark.asyncio
async def test_refresh_update_is_guarded_by_real_change():
    conn = _conn()
    result = await _Service(conn).batch_upsert_connections([{
        "user_uuid": "11111111-1111-1111-1111-111111111111",
        "ip_address": "1.2.3.4",
        "node_uuid": "22222222-2222-2222-2222-222222222222",
        "device_info": {"user_email": "a@b", "inbound_tag": "vless"},
        "connected_at": None,
    }])

    assert result == {"upserted": 1, "closed_stale": 0}
    update_sql = conn.execute.await_args_list[0].args[0]
    assert "SET node_uuid" in update_sql
    guard = update_sql.split("disconnected_at IS NULL", 1)[1]
    assert "uc.node_uuid IS DISTINCT FROM COALESCE(batch.n, uc.node_uuid)" in guard
    assert "uc.device_info IS DISTINCT FROM COALESCE(batch.d, uc.device_info)" in guard

"""Синк внешних чёрных списков не переписывает строки, которые не изменились.

Регрессия: upsert обновлял reason и source безусловно, и каждый прогон синка
давал апдейт на каждую строку — сотни тысяч пустых записей на таблице в
тысячу записей.
"""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from shared.db.network import NetworkMixin


class _Service(NetworkMixin):
    def __init__(self, conn):
        self._conn = conn

    @asynccontextmanager
    async def acquire(self):
        yield self._conn


@pytest.mark.asyncio
async def test_update_only_when_reason_or_source_changed():
    conn = AsyncMock()
    entries = [(100, "spam", "https://list.example/a.txt"), (200, "fraud", "https://list.example/a.txt")]

    written = await _Service(conn).bulk_add_to_user_blacklist(entries)

    assert written == 2
    sql, passed = conn.executemany.await_args.args
    assert passed == entries
    assert "ON CONFLICT (telegram_id) DO UPDATE" in sql
    guard = sql.split("DO UPDATE", 1)[1]
    assert "WHERE" in guard
    assert "reason IS DISTINCT FROM EXCLUDED.reason" in guard
    assert "source IS DISTINCT FROM EXCLUDED.source" in guard


@pytest.mark.asyncio
async def test_empty_batch_does_not_touch_db():
    conn = AsyncMock()
    assert await _Service(conn).bulk_add_to_user_blacklist([]) == 0
    conn.executemany.assert_not_awaited()

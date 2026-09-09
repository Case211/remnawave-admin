"""Вебхук панели приходит с пустыми activeInternalSquads — сквады из БД не теряются.

Панель в событиях не заполняет это поле «for performance reasons»; апсерт
по вебхуку стирал сквады, и до следующего полного синка юзер выпадал из
фильтра по скваду.
"""
from unittest.mock import AsyncMock, patch

import pytest

from shared.sync import SyncService


SQUADS = [{"uuid": "S1", "name": "Standard"}]


def _db(existing):
    db = AsyncMock()
    db.is_connected = True
    db.get_user_by_uuid.return_value = existing
    return db


@pytest.mark.asyncio
async def test_empty_squads_in_event_keep_synced_ones():
    db = _db({"uuid": "u1", "username": "alice", "activeInternalSquads": SQUADS})
    with patch("shared.sync.db_service", db):
        result = await SyncService()._handle_user_webhook_with_diff(
            "user.modified", {"uuid": "u1", "username": "alice", "activeInternalSquads": []},
        )
    saved = db.upsert_user.await_args.args[0]["response"]
    assert saved["activeInternalSquads"] == SQUADS
    assert result["new_data"]["activeInternalSquads"] == SQUADS


@pytest.mark.asyncio
async def test_event_with_squads_wins():
    db = _db({"uuid": "u1", "username": "alice", "activeInternalSquads": SQUADS})
    new = [{"uuid": "S2", "name": "Family"}]
    with patch("shared.sync.db_service", db):
        await SyncService()._handle_user_webhook_with_diff(
            "user.modified", {"uuid": "u1", "username": "alice", "activeInternalSquads": new},
        )
    assert db.upsert_user.await_args.args[0]["response"]["activeInternalSquads"] == new


@pytest.mark.asyncio
async def test_new_user_without_history_is_saved_as_is():
    db = _db(None)
    with patch("shared.sync.db_service", db):
        result = await SyncService()._handle_user_webhook_with_diff(
            "user.created", {"uuid": "u9", "username": "bob", "activeInternalSquads": []},
        )
    assert result["is_new"] is True
    assert db.upsert_user.await_args.args[0]["response"]["activeInternalSquads"] == []

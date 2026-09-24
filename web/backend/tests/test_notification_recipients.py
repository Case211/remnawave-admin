"""Уведомления: общее — только админам с правом на раздел; адресное по
WebSocket — только своему админу."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from web.backend.core import notification_service as ns


def test_type_to_resource():
    assert ns.notification_resource("torrent") == "violations"
    assert ns.notification_resource("alert") == "nodes"
    assert ns.notification_resource("info") is None


@pytest.mark.asyncio
async def test_recipients_query_filters_by_resource():
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[{"id": 1}, {"id": 3}])
    assert await ns._recipient_admin_ids(conn, "violation") == [1, 3]
    assert conn.fetch.await_args.args[1] == "violations"
    await ns._recipient_admin_ids(conn, "info")
    assert conn.fetch.await_args.args[1] is None


@pytest.mark.asyncio
async def test_personal_notification_goes_to_own_sockets_only():
    from web.backend.api.v2.websocket import ConnectionManager
    mgr = ConnectionManager()
    mine, other = MagicMock(), MagicMock()
    mine.send_text, other.send_text = AsyncMock(), AsyncMock()
    mgr._admins = {mine: MagicMock(account_id=5), other: MagicMock(account_id=6)}
    await mgr.send_to_account(5, {"type": "notification"})
    mine.send_text.assert_awaited_once()
    other.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_notification_only_for_admins_who_see_the_user(monkeypatch):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[{"id": 1, "role_name": "superadmin"}, {"id": 2, "role_name": "operator"}])

    async def fake_visible(account_id, role):
        return None if account_id == 1 else {"other-user"}

    monkeypatch.setattr("shared.rbac.get_visible_user_uuids", fake_visible)
    assert await ns._recipient_admin_ids(conn, "violation", "USER-1") == [1]
    assert await ns._recipient_admin_ids(conn, "violation") == [1, 2]


@pytest.mark.asyncio
async def test_dnd_skips_external_channels_but_not_critical(monkeypatch):
    calls = []

    async def in_dnd(admin_id):
        return True

    monkeypatch.setattr(ns, "_admin_in_dnd", in_dnd)
    db = MagicMock()
    db.acquire.side_effect = lambda: calls.append("db") or (_ for _ in ()).throw(RuntimeError("stop"))
    monkeypatch.setattr("shared.database.db_service", db)
    await ns._dispatch_external(1, "t", "b", "info", None, ["telegram"])
    assert calls == []
    await ns._dispatch_external(1, "t", "b", "critical", None, ["telegram"])
    assert calls == ["db"]

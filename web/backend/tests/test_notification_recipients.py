"""Уведомления: общее — только админам с правом на раздел; адресное по
WebSocket — только своему админу; алерты не врут про офлайн и нагрузку."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core import notification_service as ns
from web.backend.core.alert_engine import AlertEngine


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


def _conn_with_nodes(nodes):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=nodes)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock()
    db.acquire.return_value = cm
    return db


@pytest.mark.asyncio
async def test_offline_minutes_from_panel_status_and_load_only_from_live_nodes():
    since = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
    nodes = [
        {"uuid": "a", "name": "down", "is_connected": False, "cpu_usage": 99, "memory_usage": 99, "disk_usage": 99,
         "metrics_updated_at": None, "last_status_change": since, "address": "1.1.1.1"},
        {"uuid": "b", "name": "live", "is_connected": True, "cpu_usage": 30, "memory_usage": 40, "disk_usage": 50,
         "metrics_updated_at": None, "last_status_change": None, "address": "2.2.2.2"},
    ]
    with patch("shared.database.db_service", _conn_with_nodes(nodes)), \
            patch("web.backend.core.api_helper.fetch_nodes_from_api", AsyncMock(return_value=[])):
        metrics = await AlertEngine()._collect_metrics()
    assert 44 <= metrics["node_offline_minutes"] <= 46
    # у упавшей ноды остались старые 99 % — в максимум они не идут
    assert metrics["cpu_usage_percent"] == 30 and metrics["max_cpu_node"] == "live"

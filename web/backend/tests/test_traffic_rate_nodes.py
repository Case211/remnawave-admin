"""Карточка «Высокое потребление трафика» называет ноды, через которые ушёл трафик.

Панель по юзеру отдаёт только сумму по всем нодам, разбивку пишет наш синк
дельтами; пока их нет — показываем ноды с соединением в окне. Раньше ноды
искались только по времени начала соединения, и давно открытое соединение
в карточку не попадало: строки с нодами не было вовсе.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core import traffic_rate_monitor as trm

GB = 1024 ** 3
VIOLATOR = {
    "username": "alice", "user_uuid": "11111111-1111-1111-1111-111111111111",
    "delta_gb": 9.21, "elapsed_minutes": 5, "rate_gb_per_hour": 110.45,
}
CFG = {"threshold_gb": 5.0, "window_minutes": 10, "auto_action": "notify", "auto_block_gb": 50.0}
USER_ROW = {
    "status": "active", "used_traffic_bytes": 10 * GB, "traffic_limit_bytes": 0,
    "expire_at": None, "description": None, "short_uuid": None,
}


def _db(fetch_results):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=USER_ROW)
    conn.fetch = AsyncMock(side_effect=fetch_results)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock()
    db.acquire = MagicMock(return_value=cm)
    db.save_violation = AsyncMock(return_value=(1, True))
    return db, conn


async def _card(fetch_results):
    db, conn = _db(fetch_results)
    notify = AsyncMock()
    with patch("shared.database.db_service", db), \
            patch("web.backend.core.notification_service.create_notification", notify), \
            patch("web.backend.core.webhook_security.fire_event", MagicMock()), \
            patch.object(trm, "_sync_lag_minutes", lambda: 5):
        await trm.TrafficRateMonitor()._send_notification(VIOLATOR, CFG)
    assert notify.await_count == 1
    return notify.call_args.kwargs, conn, db


@pytest.mark.asyncio
async def test_nodes_with_traffic_share_come_first():
    kwargs, conn, db = await _card([
        [{"name": "Germany W", "bytes": 9 * GB}, {"name": "Finland", "bytes": int(0.3 * GB)}],
    ])
    assert "🖥 Ноды: <code>Germany W</code> 9.00 GB, <code>Finland</code> 0.30 GB" in kwargs["telegram_body"]
    # Дельта синка пишется с опозданием на интервал синка — смотрим глубже окна.
    assert conn.fetch.await_args_list[0].args[-1] == 15
    # Те же ноды попадают в причину нарушения на странице нарушений.
    assert "Ноды: Germany W, Finland" in db.save_violation.await_args.kwargs["reasons"][0]


@pytest.mark.asyncio
async def test_falls_back_to_connections_when_sync_has_no_deltas():
    kwargs, conn, _ = await _card([[], [{"name": "Finland"}]])
    assert "🖥 Ноды: <code>Finland</code>" in kwargs["telegram_body"]
    assert conn.fetch.await_count == 2
    # Открытое соединение считается, даже если началось задолго до окна.
    assert "disconnected_at IS NULL" in conn.fetch.await_args_list[1].args[0]


@pytest.mark.asyncio
async def test_no_nodes_line_without_data():
    kwargs, _, _ = await _card([[], []])
    assert "Ноды:" not in kwargs["telegram_body"]


def test_format_nodes_tiny_share_is_not_zero():
    assert trm._format_nodes([{"name": "A", "bytes": 1024}]) == "<code>A</code> 0.01 GB"

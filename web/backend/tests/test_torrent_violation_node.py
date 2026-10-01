"""Нода из батча доезжает до торрент-уведомления и до причин нарушения."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.api.v2 import collector

USER_UUID = "11111111-1111-1111-1111-111111111111"


def _event():
    return collector.TorrentEventReport(
        user_email="alice@example.com", ip_address="1.2.3.4",
        destination="tracker.example.org:6881",
        node_uuid="22222222-2222-2222-2222-222222222222",
        detected_at="2026-09-16T10:00:00",
    )


def _db(reviewed_at=None, game_peers=0):
    db = MagicMock()
    db.shared_torrent_destinations = AsyncMock(return_value=set())
    db.is_user_violation_whitelisted = AsyncMock(return_value=(False, None))
    db.last_torrent_review_at = AsyncMock(return_value=reviewed_at)
    db.count_recent_torrent_events = AsyncMock(return_value=50)
    # Без портов — все пиры окна, с портами — только пиры игровых лаунчеров
    db.count_recent_torrent_peers = AsyncMock(
        side_effect=lambda user_uuid, minutes, since=None, ports=None: game_peers if ports else 10,
    )
    db.recent_torrent_destinations = AsyncMock(return_value=["tracker.example.org:6881", "5.6.7.8:6881"])
    db.get_recent_torrent_violation = AsyncMock(return_value=None)
    db.get_user_by_uuid = AsyncMock(return_value={"username": "alice", "email": "alice@example.com"})
    db.save_violation = AsyncMock(return_value=(7, True))
    return db


async def _process(db, settings=None):
    cfg = MagicMock()
    cfg.get = lambda key, default=None: (settings or {}).get(key, default)
    whitelist = MagicMock()
    whitelist.filter_destinations = AsyncMock(side_effect=lambda d: d)
    engine = MagicMock()
    engine.handle_event = AsyncMock()
    notify = AsyncMock()
    with patch.object(collector, "db_service", db), \
            patch.object(collector, "config_service", cfg), \
            patch.object(collector, "torrent_p2p_whitelist", whitelist), \
            patch.object(collector, "fire_event", MagicMock()), \
            patch("web.backend.core.violation_notifier.send_torrent_notification", notify), \
            patch("web.backend.core.automation_engine.engine", engine), \
            patch("web.backend.api.v2.websocket.broadcast_violation", AsyncMock()):
        await collector._process_torrent_violations(
            [_event()], {"alice@example.com": USER_UUID}, node_name="Germany W",
        )
    return notify


@pytest.mark.asyncio
async def test_node_name_reaches_notification_and_reasons():
    db = _db()
    notify = await _process(db)

    kwargs = notify.await_args.kwargs
    assert kwargs["node_name"] == "Germany W"
    # В уведомление — счёт за окно, по которому сработали пороги, а не батч
    assert kwargs["window"]["events"] == 50 and kwargs["window"]["peers"] == 10
    assert kwargs["destinations"] == ["tracker.example.org:6881", "5.6.7.8:6881"]
    assert kwargs["action"] == "notify"
    assert "Node: Germany W" in db.save_violation.await_args.kwargs["reasons"]


@pytest.mark.asyncio
async def test_violation_keeps_the_same_window_as_notification():
    """В вебе было «6 событий» и пять адресов батча, в Telegram — окно на сотни."""
    db = _db()
    await _process(db)

    reasons = db.save_violation.await_args.kwargs["reasons"]
    assert reasons[0] == "Torrent traffic detected (50 events, 10 peers in 30 min)"
    assert "Destination: tracker.example.org:6881" in reasons
    assert "Destination: 5.6.7.8:6881" in reasons
    assert reasons[-1] == "… and 8 more destinations"


@pytest.mark.asyncio
async def test_window_starts_after_operator_review():
    """После «Аннулировать» те же события не собирают новое нарушение."""
    reviewed_at = datetime(2026, 10, 1, 10, 8, tzinfo=timezone.utc)
    db = _db(reviewed_at)
    await _process(db)

    for query in (db.count_recent_torrent_events, db.count_recent_torrent_peers,
                  db.recent_torrent_destinations):
        assert query.await_args.kwargs["since"] == reviewed_at


@pytest.mark.asyncio
async def test_nothing_new_after_review_means_no_violation():
    db = _db(datetime(2026, 10, 1, 10, 8, tzinfo=timezone.utc))
    db.count_recent_torrent_events = AsyncMock(return_value=0)
    db.count_recent_torrent_peers = AsyncMock(return_value=0)
    # Даже при пороге «с первого события» разобранные события не в счёт
    notify = await _process(db, {"torrent_min_events": 1, "torrent_min_peers": 1})

    db.save_violation.assert_not_awaited()
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_game_launcher_swarm_is_not_a_violation():
    """Рой War Thunder: больше половины пиров на порту лаунчера 27032."""
    db = _db(game_peers=8)
    notify = await _process(db)

    assert db.count_recent_torrent_peers.await_args.kwargs["ports"] == [27032]
    db.save_violation.assert_not_awaited()
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_mixed_swarm_is_still_a_violation():
    """Игра плюс обычный торрент-клиент: пиров лаунчера меньшинство — нарушение остаётся."""
    db = _db(game_peers=3)
    await _process(db)

    db.save_violation.assert_awaited_once()

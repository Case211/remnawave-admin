"""Нода из батча доезжает до торрент-уведомления и до причин нарушения."""
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


@pytest.mark.asyncio
async def test_node_name_reaches_notification_and_reasons():
    db = MagicMock()
    db.shared_torrent_destinations = AsyncMock(return_value=set())
    db.is_user_violation_whitelisted = AsyncMock(return_value=(False, None))
    db.count_recent_torrent_events = AsyncMock(return_value=50)
    db.count_recent_torrent_peers = AsyncMock(return_value=10)
    db.get_recent_torrent_violation = AsyncMock(return_value=None)
    db.get_user_by_uuid = AsyncMock(return_value={"username": "alice", "email": "alice@example.com"})
    db.save_violation = AsyncMock(return_value=(7, True))
    cfg = MagicMock()
    cfg.get = lambda key, default=None: default
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

    assert notify.await_args.kwargs["node_name"] == "Germany W"
    assert "Node: Germany W" in db.save_violation.await_args.kwargs["reasons"]

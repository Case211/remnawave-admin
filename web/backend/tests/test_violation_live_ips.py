"""Адреса нарушения — те, что видел детектор, а не «сессии, начатые за 5 минут».

Детектор судит по живой карте активности коллектора, а сохранение брало
адреса отдельным запросом к БД по сессиям, начатым за последние 5 минут.
Сессии, идущие дольше, в него не попадали — а именно на них ловится
одновременное подключение из двух стран. Карточка показывала «IP-адресов: 0»
при двух странах в причинах, уведомление уходило без адресов, разбор
скоринга не сохранялся вовсе.
"""
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.analyzers.models import GeoScore, TemporalScore, ViolationAction
from shared.connection_monitor import ActiveConnection
from web.backend.api.v2 import collector

USER = "11111111-2222-3333-4444-555555555555"


def _conn(ip, node="node-1", minutes_ago=15):
    return ActiveConnection(
        connection_id=0, user_uuid=USER, ip_address=ip, node_uuid=node,
        connected_at=datetime(2026, 9, 30, 11, 16 - minutes_ago, tzinfo=timezone.utc),
    )


def _score():
    return SimpleNamespace(
        total=50.0,
        recommended_action=ViolationAction.WARN,
        reasons=["Одновременные подключения из разных стран: KZ, RU (перекрытие 15 мин)"],
        breakdown={
            "temporal": TemporalScore(score=0.0, reasons=[], simultaneous_connections_count=3),
            "geo": GeoScore(score=90.0, reasons=["…"], countries={"KZ", "RU"}, cities={"Almaty"},
                            impossible_travel_detected=True),
        },
        confidence=0.3,
    )


def _mocks():
    db = MagicMock()
    db.save_violation = AsyncMock(return_value=(35, True))
    db.mark_violation_notified = AsyncMock(return_value=True)
    db.update_violation_action = AsyncMock(return_value=True)
    monitor = MagicMock()
    monitor.get_user_active_connections = AsyncMock(return_value=[])
    notify = AsyncMock()
    patches = [
        patch.object(collector, "db_service", db),
        patch.object(collector, "connection_monitor", monitor),
        patch.object(collector, "fire_event", MagicMock()),
        patch.object(collector.config_service, "get", side_effect=lambda key, default=None: default),
        patch("web.backend.core.violation_notifier.send_violation_notification", notify),
        patch("shared.api_client.api_client.disable_user", new_callable=AsyncMock),
        patch("web.backend.api.v2.websocket.broadcast_violation", new_callable=AsyncMock),
        patch("shared.geoip.get_geoip_service",
              return_value=SimpleNamespace(lookup_batch=AsyncMock(return_value={}))),
    ]
    return db, monitor, notify, patches


async def _run(live):
    db, monitor, notify, patches = _mocks()
    for p in patches:
        p.start()
    try:
        await collector._handle_violation(USER, _score(), None, [], False, live_connections=live)
    finally:
        for p in reversed(patches):
            p.stop()
    return db, monitor, notify


class TestAddressesComeFromTheDetector:
    @pytest.mark.asyncio
    async def test_long_running_sessions_are_kept(self):
        live = [_conn("91.79.17.99", minutes_ago=15), _conn("128.71.64.218", minutes_ago=13),
                _conn("95.82.127.244", "node-2", minutes_ago=9)]
        db, monitor, notify = await _run(live)
        kw = db.save_violation.await_args.kwargs
        assert sorted(kw["ip_addresses"]) == ["128.71.64.218", "91.79.17.99", "95.82.127.244"]
        assert kw["unique_ips_count"] == 3
        # к БД за «сессиями, начатыми за 5 минут» не ходили
        monitor.get_user_active_connections.assert_not_awaited()
        # уведомление получило те же соединения
        assert len(notify.await_args.kwargs["active_connections"]) == 3

    @pytest.mark.asyncio
    async def test_falls_back_to_the_database_without_live_map(self):
        db, monitor, notify = await _run(None)
        monitor.get_user_active_connections.assert_awaited_once()
        assert db.save_violation.await_args.kwargs["ip_addresses"] is None

    @pytest.mark.asyncio
    async def test_empty_live_map_also_falls_back(self):
        db, monitor, _ = await _run([])
        monitor.get_user_active_connections.assert_awaited_once()


class TestBreakdownIsPersisted:
    @pytest.mark.asyncio
    async def test_raw_breakdown_is_json_with_sets_and_dataclasses(self):
        db, _, _ = await _run([_conn("91.79.17.99")])
        raw = db.save_violation.await_args.kwargs["raw_breakdown"]
        data = json.loads(raw)["breakdown"]
        assert data["geo"]["countries"] == ["KZ", "RU"]
        assert data["geo"]["impossible_travel_detected"] is True
        assert data["temporal"]["simultaneous_connections_count"] == 3

    def test_empty_breakdown_is_null(self):
        assert collector._breakdown_json({}) is None
        assert collector._breakdown_json(None) is None

    def test_unusual_values_do_not_break_serialisation(self):
        raw = collector._breakdown_json({
            "x": SimpleNamespace(when=datetime(2026, 9, 30, tzinfo=timezone.utc),
                                 action=ViolationAction.WARN, _private=1, ips={"b", "a"}),
        })
        data = json.loads(raw)["breakdown"]["x"]
        assert data["when"].startswith("2026-09-30")
        assert data["action"] == ViolationAction.WARN.value
        assert data["ips"] == ["a", "b"]
        assert "_private" not in data

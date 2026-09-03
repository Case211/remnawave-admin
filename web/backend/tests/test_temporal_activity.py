"""Одновременность считается по последней активности, а не по стартам.

Агент видит в логе только новые соединения, поэтому у живой сессии старт
может быть часовой давности. По стартам такие сессии в одно окно не
попадали никогда — толпа, подключавшаяся вразнобой, оставалась невидимой.
"""
from datetime import datetime, timedelta

from shared.analyzers.temporal import TemporalAnalyzer
from shared.connection_monitor import ActiveConnection


def _conn(ip, started_sec_ago, seen_sec_ago):
    now = datetime.utcnow()
    return ActiveConnection(
        connection_id=0, user_uuid="u", ip_address=ip, node_uuid="n",
        connected_at=now - timedelta(seconds=started_sec_ago),
        last_seen_at=None if seen_sec_ago is None else now - timedelta(seconds=seen_sec_ago),
    )


def test_sessions_started_hours_apart_count_together_when_alive():
    conns = [_conn(f"10.{i}.{i}.{i}", started_sec_ago=3600 * i + 30, seen_sec_ago=10 + i) for i in range(1, 9)]
    res = TemporalAnalyzer().analyze(conns, [], user_device_count=1)
    assert res.simultaneous_connections_count == 8
    assert res.score == 100.0
    assert res.strong_sharing


def test_quiet_addresses_drop_out_of_the_window():
    live = [_conn(f"10.{i}.{i}.{i}", 900, 20) for i in range(1, 4)]
    quiet = [_conn(f"20.{i}.{i}.{i}", 900, 400) for i in range(1, 6)]  # шесть с лишним минут без активности
    res = TemporalAnalyzer().analyze(live + quiet, [], user_device_count=1)
    assert res.simultaneous_connections_count == 3


def test_without_last_seen_the_start_windows_still_apply():
    conns = [_conn(f"10.{i}.{i}.{i}", started_sec_ago=45 * i, seen_sec_ago=None) for i in range(8)]
    res = TemporalAnalyzer().analyze(conns, [], user_device_count=1)
    assert res.simultaneous_connections_count < 8

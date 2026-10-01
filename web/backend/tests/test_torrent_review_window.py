"""Окно торрент-событий после разбора и узнавание торрент-нарушения по причине.

Регрессия (01.10.2026): после «Аннулировать» окно за полчаса тут же снова
набирало те же события, и новое нарушение приходило через минуты. А
десятиминутный дедуп сравнивал причину целиком — в ней всегда есть счётчик
событий, так что он не срабатывал ни разу.
"""
from datetime import datetime, timezone

import pytest

from shared.db.connections import ConnectionsMixin
from web.backend.core.torrent_p2p_whitelist import is_game_swarm

REVIEWED = datetime(2026, 10, 1, 10, 8, tzinfo=timezone.utc)


class _Conn:
    def __init__(self):
        self.calls = []

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return 0

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        return []


class _DB(ConnectionsMixin):
    is_connected = True

    def __init__(self):
        self.conn = _Conn()

    def acquire(self):
        conn = self.conn

        class _Acquire:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Acquire()


@pytest.mark.asyncio
async def test_recent_torrent_violation_matches_reason_prefix():
    db = _DB()
    await db.get_recent_torrent_violation("u", minutes=10)
    sql, _ = db.conn.calls[0]
    assert "LIKE 'Torrent traffic detected%'" in sql
    assert "= ANY(reasons)" not in sql


@pytest.mark.asyncio
async def test_last_review_looks_only_at_reviewed_torrent_violations():
    db = _DB()
    await db.last_torrent_review_at("u", minutes=30)
    sql, args = db.conn.calls[0]
    assert "MAX(action_taken_at)" in sql
    assert "action_taken IS NOT NULL" in sql
    assert "LIKE 'Torrent traffic detected%'" in sql
    assert args == ("u", 30)


@pytest.mark.asyncio
async def test_window_queries_take_review_cutoff():
    db = _DB()
    await db.count_recent_torrent_events("u", minutes=30, since=REVIEWED)
    await db.count_recent_torrent_peers("u", minutes=30, since=REVIEWED)
    await db.recent_torrent_destinations("u", minutes=30, since=REVIEWED)
    (events_sql, events_args), (peers_sql, peers_args), (dest_sql, dest_args) = db.conn.calls
    assert events_args == ("u", 30, REVIEWED) and "detected_at > $3" in events_sql
    assert peers_args == ("u", 30, REVIEWED, None) and "detected_at > $3" in peers_sql
    assert dest_args == ("u", 30, 10, REVIEWED) and "detected_at > $4" in dest_sql


@pytest.mark.asyncio
async def test_peers_can_be_counted_on_launcher_ports():
    db = _DB()
    await db.count_recent_torrent_peers("u", minutes=30, ports=[27032])
    sql, args = db.conn.calls[0]
    assert args == ("u", 30, None, [27032])
    assert "= ANY($4::int[])" in sql


def test_game_swarm_needs_more_than_half_of_peers():
    assert is_game_swarm(10, 6)
    assert not is_game_swarm(10, 5)
    assert not is_game_swarm(0, 0)

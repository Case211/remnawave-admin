"""Разобранные оператором улики User-Agent не поднимаются заново.

Регрессия (01.10.2026): после «Аннулировать» нарушение «Бот/скрипт в User-Agent»
приходило каждые полчаса. Висящего нарушения больше нет, дедупу склеивать не с
чем, а старый запрос ``curl`` в истории подписки остаётся и снова даёт пол 55.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from shared.analyzers.detector import IntelligentViolationDetector
from shared.analyzers.user_agent import UserAgentAnalyzer
from shared.db.violations import ViolationsMixin

NOW = datetime.now(timezone.utc)
CURL = "curl/8.13.0"


def _srh(ua, minutes_ago, request_id=1):
    return {
        "request_id": request_id,
        "user_agent": ua,
        "request_ip": "1.2.3.4",
        "request_at": NOW - timedelta(minutes=minutes_ago),
    }


HISTORY = [
    _srh("Happ/4.7.2/android/", 5, 1),
    _srh(CURL, 120, 2),
    _srh("Happ/4.7.2/android/", 180, 3),
]


# ── Анализатор ────────────────────────────────────────────────────

class TestAnalyzer:
    def test_request_before_review_is_skipped(self):
        res = UserAgentAnalyzer().analyze(HISTORY, reviewed_until=NOW - timedelta(minutes=60))
        assert not res.has_bot_library
        assert res.score == 0.0
        assert res.reasons == []
        assert res.valid_count == 2

    def test_request_after_review_is_caught_again(self):
        res = UserAgentAnalyzer().analyze(HISTORY, reviewed_until=NOW - timedelta(minutes=180))
        assert res.has_bot_library
        assert [a.request_id for a in res.suspicious_agents] == [2]

    def test_annulled_agent_is_accepted_even_when_repeated(self):
        # Скрипт клиента дёргает подписку и после разбора — оператор уже счёл его ложным срабатыванием
        records = HISTORY + [_srh(CURL, 1, 4)]
        res = UserAgentAnalyzer().analyze(
            records,
            reviewed_until=NOW - timedelta(minutes=60),
            accepted={("bot_library", CURL)},
        )
        assert not res.has_bot_library

    def test_accepted_agent_does_not_cover_other_agents(self):
        records = [_srh(CURL, 10, 1), _srh("vless://abc@host", 10, 2)]
        res = UserAgentAnalyzer().analyze(records, accepted={("bot_library", CURL)})
        assert res.has_link_in_ua
        assert not res.has_bot_library

    def test_naive_and_iso_request_times(self):
        naive = {**_srh(CURL, 120), "request_at": (NOW - timedelta(minutes=120)).replace(tzinfo=None)}
        iso = {**_srh(CURL, 120), "request_at": (NOW - timedelta(minutes=120)).isoformat().replace("+00:00", "Z")}
        for record in (naive, iso):
            res = UserAgentAnalyzer().analyze([record], reviewed_until=NOW - timedelta(minutes=60))
            assert not res.has_bot_library


# ── Детектор ──────────────────────────────────────────────────────

class _NoGeoip:
    async def lookup_batch(self, ips):
        return {}

    async def lookup(self, ip):
        return None


def _detector():
    db = AsyncMock()
    db.is_connected = True
    db.get_recent_violations_count = AsyncMock(return_value=3)
    db.get_connection_history = AsyncMock(return_value=[])
    db.get_user_baseline = AsyncMock(return_value=None)
    db.get_user_devices_count = AsyncMock(return_value=1)
    return IntelligentViolationDetector(db, AsyncMock(), geoip_service=_NoGeoip())


async def _check(det, review):
    return await det.check_user(
        "u",
        prefetched_device_count=1,
        prefetched_active_connections=[],
        prefetched_history_30d=[],
        prefetched_baseline=None,
        prefetched_shared_hwids=[],
        prefetched_srh_records=HISTORY,
        prefetched_ua_review=review,
    )


@pytest.mark.asyncio
async def test_bot_floor_applies_to_unreviewed_request():
    res = await _check(_detector(), {})
    assert res.total >= 55.0


@pytest.mark.asyncio
async def test_bot_floor_skips_reviewed_request():
    res = await _check(_detector(), {"reviewed_until": NOW - timedelta(minutes=60)})
    assert res.total < 50.0


@pytest.mark.asyncio
async def test_batch_check_loads_review_state():
    det = _detector()
    det.db.batch_get_user_devices_counts = AsyncMock(return_value={"u": 1})
    det.db.batch_get_active_connections = AsyncMock(return_value={})
    det.db.batch_get_connection_histories = AsyncMock(return_value={})
    det.db.batch_get_user_baselines = AsyncMock(return_value={})
    det.db.batch_get_shared_hwids = AsyncMock(return_value={})
    det.db.batch_get_srh_records = AsyncMock(return_value={"u": [
        {"id": r["request_id"], "user_agent": r["user_agent"],
         "request_ip": r["request_ip"], "request_at": r["request_at"]}
        for r in HISTORY
    ]})
    det.db.batch_get_ua_review_state = AsyncMock(return_value={
        "u": {"reviewed_until": NOW - timedelta(minutes=60), "accepted": set()},
    })

    results = await det.check_users_batch(["u"])

    det.db.batch_get_ua_review_state.assert_awaited_once_with(["u"])
    assert results["u"].total < 50.0


@pytest.mark.asyncio
async def test_review_state_failure_keeps_detection():
    det = _detector()
    det.db.batch_get_ua_review_state = AsyncMock(side_effect=RuntimeError("db down"))
    res = await det.check_user(
        "u",
        prefetched_device_count=1,
        prefetched_active_connections=[],
        prefetched_history_30d=[],
        prefetched_baseline=None,
        prefetched_shared_hwids=[],
        prefetched_srh_records=HISTORY,
    )
    assert res.total >= 55.0


# ── Отметки о разборе из базы ─────────────────────────────────────

class _Conn:
    def __init__(self, rows):
        self.rows = rows
        self.sql = None
        self.args = None

    async def fetch(self, sql, *args):
        self.sql, self.args = sql, args
        return self.rows


class _DB(ViolationsMixin):
    is_connected = True

    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class _Acquire:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Acquire()


@pytest.mark.asyncio
async def test_review_state_reads_annulled_agents():
    reviewed = NOW - timedelta(minutes=30)
    conn = _Conn([
        {
            "user_uuid": "u",
            "reviewed_until": reviewed,
            # asyncpg без JSON-кодека отдаёт jsonb строкой
            "annulled_agents": '[[{"user_agent": "curl/8.13.0", "classification": "bot_library"}], null]',
        },
        {"user_uuid": "w", "reviewed_until": reviewed, "annulled_agents": None},
    ])

    state = await _DB(conn).batch_get_ua_review_state(["u", "w"])

    assert state["u"] == {"reviewed_until": reviewed, "accepted": {("bot_library", CURL)}}
    assert state["w"] == {"reviewed_until": reviewed, "accepted": set()}
    assert "action_taken IS NOT NULL" in conn.sql
    assert conn.args == (["u", "w"],)

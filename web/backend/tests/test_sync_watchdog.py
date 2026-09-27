"""Сторож синка: одно предупреждение, когда синк встал, и одно — когда ожил."""
from datetime import datetime, timedelta, timezone

import pytest

from shared.database import db_service
from shared.sync import SyncService
from web.backend.core import sync_watchdog

T0 = datetime(2026, 9, 27, 1, 0, tzinfo=timezone.utc)


@pytest.fixture
def world(monkeypatch):
    state = {"meta": None, "sent": []}

    async def get_sync_metadata(key):
        assert key == "users"
        return state["meta"]

    async def notify(title, body, *, severity):
        state["sent"].append((title, severity))

    monkeypatch.setattr(db_service, "get_sync_metadata", get_sync_metadata)
    monkeypatch.setattr(sync_watchdog, "_notify", notify)
    monkeypatch.setattr(SyncService, "_get_sync_interval", staticmethod(lambda: 300))
    return state


def _meta(at, status="success"):
    return {"last_sync_at": at, "sync_status": status}


@pytest.mark.asyncio
async def test_never_synced_is_not_an_alarm(world):
    dog = sync_watchdog.SyncWatchdog(now=T0)
    await dog.check(now=T0 + timedelta(hours=5))
    assert world["sent"] == []


@pytest.mark.asyncio
async def test_stalled_sync_alerts_once_and_recovery_is_reported(world):
    dog = sync_watchdog.SyncWatchdog(now=T0)
    world["meta"] = _meta(T0)
    await dog.check(now=T0 + timedelta(minutes=10))
    assert world["sent"] == []

    await dog.check(now=T0 + timedelta(minutes=20))
    await dog.check(now=T0 + timedelta(minutes=40))
    assert world["sent"] == [("⏸ Синк с панелью стоит", "warning")]

    world["meta"] = _meta(T0 + timedelta(minutes=41))
    await dog.check(now=T0 + timedelta(minutes=42))
    assert world["sent"][-1] == ("▶️ Синк с панелью возобновился", "info")


@pytest.mark.asyncio
async def test_failing_passes_count_as_stalled(world):
    """Неудачный проход тоже ставит отметку времени — смотрим только на успешные."""
    dog = sync_watchdog.SyncWatchdog(now=T0)
    world["meta"] = _meta(T0)
    await dog.check(now=T0 + timedelta(minutes=1))
    world["meta"] = _meta(T0 + timedelta(minutes=19), status="error")
    await dog.check(now=T0 + timedelta(minutes=20))
    assert world["sent"] == [("⏸ Синк с панелью стоит", "warning")]


@pytest.mark.asyncio
async def test_old_mark_right_after_restart_gives_the_collector_time(world):
    """После перезапуска полусуточная отметка в базе — ещё не повод для тревоги."""
    dog = sync_watchdog.SyncWatchdog(now=T0)
    world["meta"] = _meta(T0 - timedelta(hours=12))
    await dog.check(now=T0 + timedelta(minutes=5))
    assert world["sent"] == []
    await dog.check(now=T0 + timedelta(minutes=16))
    assert world["sent"] == [("⏸ Синк с панелью стоит", "warning")]

"""Планировщик отчётов не теряет и не дублирует отчёт."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import report_scheduler as rs


def _cfg(values):
    cfg = MagicMock()
    cfg.get = lambda key, default=None: values.get(key, default)
    return cfg


def _scheduler():
    sched = rs.ReportScheduler.__new__(rs.ReportScheduler)
    sched._last_daily_date = None
    sched._last_weekly_date = None
    sched._last_monthly_date = None
    sched._send_report = AsyncMock()
    return sched


async def _run_daily(existing, now_time="09:07", values=None):
    sched = _scheduler()
    db = MagicMock()
    db.get_report_for_period = AsyncMock(return_value=existing)
    cfg = _cfg({"reports_daily_time": "09:00", **(values or {})})
    with patch.object(rs, "db_service", db), patch.object(rs, "config_service", cfg):
        await sched._check_daily_report(now_time, "2026-09-24")
    return sched


@pytest.mark.asyncio
async def test_late_tick_still_sends():
    # Цикл проскочил 09:00 — отчёт всё равно уходит, а не теряется на сутки
    sched = await _run_daily(existing=None, now_time="09:07")
    sched._send_report.assert_awaited_once()
    assert sched._last_daily_date == "2026-09-24"


@pytest.mark.asyncio
async def test_before_time_does_nothing():
    sched = await _run_daily(existing=None, now_time="08:59")
    sched._send_report.assert_not_awaited()


@pytest.mark.asyncio
async def test_already_sent_period_is_not_resent_after_restart():
    sched = await _run_daily(existing={"sent_at": datetime.now(timezone.utc), "total_violations": 3})
    sched._send_report.assert_not_awaited()
    assert sched._last_daily_date == "2026-09-24"


@pytest.mark.asyncio
async def test_empty_unsent_report_is_not_regenerated_every_minute():
    sched = await _run_daily(existing={"sent_at": None, "total_violations": 0},
                             values={"reports_send_empty": False})
    sched._send_report.assert_not_awaited()


@pytest.mark.asyncio
async def test_generated_but_unsent_report_goes_out():
    # Отчёт сгенерировали вручную из веба — по расписанию он всё равно уходит
    sched = await _run_daily(existing={"sent_at": None, "total_violations": 4})
    sched._send_report.assert_awaited_once()


def test_time_normalization():
    assert rs._normalize_time("9:05", "10:00") == "09:05"
    assert rs._normalize_time("garbage", "10:00") == "10:00"

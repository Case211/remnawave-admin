"""Монитор расхода трафика: сравнивает панель с панелью и пишет каждую карточку в список.

27.09.2026 в 12:40 UTC панель не ответила, монитор взял цифры из локальной
базы — а та из-за вставшего синка отставала на 12 часов. В 13:35 свежая цифра
панели минус полусуточная из базы дала «70 ГБ за 55 минут». Нарушение же со
скором 7,6 (шкала 0–10 вместо 0–100) склеилось с висящим торрентом, и в
списке его не оказалось.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core import traffic_rate_monitor as trm

GB = 1024 ** 3
UUID = "5e32aee7-3fe8-41ed-bfb1-abd501391fe1"
CFG = {"threshold_gb": 50.0, "window_minutes": 60, "cooldown_minutes": 60,
       "auto_action": "notify", "auto_block_gb": 50.0}


def _db(fetch_rows=None):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=fetch_rows or [])
    conn.fetchrow = AsyncMock(return_value=None)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock()
    db.is_connected = True
    db.acquire = MagicMock(return_value=cm)
    db.save_violation = AsyncMock(return_value=(1, True))
    return db


@pytest.mark.asyncio
async def test_panel_down_skips_check_instead_of_reading_stale_db():
    """Снимок из базы в буфер не попадает — следующая проверка сравнит панель с панелью."""
    db = _db(fetch_rows=[{"uuid": UUID, "username": "viktor", "used_traffic_bytes": 18 * GB}])
    api = AsyncMock()
    api.get_users.side_effect = RuntimeError("HTTP error: ConnectTimeout")
    monitor = trm.TrafficRateMonitor()

    with patch("shared.database.db_service", db), patch("shared.api_client.api_client", api):
        await monitor._check_traffic_rates(CFG)

    assert dict(monitor._snapshots) == {}
    db.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_violation_is_saved_on_the_common_scale_with_its_own_kind():
    db = _db()
    violator = {"username": "viktor", "user_uuid": UUID, "delta_gb": 70.11,
                "elapsed_minutes": 55, "rate_gb_per_hour": 75.94}

    with patch("shared.database.db_service", db), \
            patch("web.backend.core.notification_service.create_notification", AsyncMock()), \
            patch("web.backend.core.webhook_security.fire_event", MagicMock()), \
            patch.object(trm, "_sync_lag_minutes", lambda: 5):
        await trm.TrafficRateMonitor()._send_notification(violator, CFG)

    saved = db.save_violation.await_args.kwargs
    assert saved["score"] == 75.94  # шкала 0–100, как у остальных; было 7,6
    assert saved["dedup"] is False  # своя запись на каждую карточку
    assert json.loads(saved["raw_breakdown"])["traffic_rate"]["delta_gb"] == 70.11


@pytest.mark.asyncio
async def test_score_is_capped_at_one_hundred():
    db = _db()
    violator = {"username": "u", "user_uuid": UUID, "delta_gb": 150.0,
                "elapsed_minutes": 60, "rate_gb_per_hour": 150.0}

    with patch("shared.database.db_service", db), \
            patch("web.backend.core.notification_service.create_notification", AsyncMock()), \
            patch("web.backend.core.webhook_security.fire_event", MagicMock()), \
            patch.object(trm, "_sync_lag_minutes", lambda: 5):
        await trm.TrafficRateMonitor()._send_notification(violator, CFG)

    assert db.save_violation.await_args.kwargs["score"] == 100.0

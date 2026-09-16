"""Авто-урезание скорости по расходу трафика доходит до конца.

Регрессия: чистка старых записей кулдауна стояла в конце статического
``_throttle_violator`` и обращалась к ``self``, ``now`` и ``cooldown_seconds``
из другого метода. Скорость урезалась, а следом летел NameError: остальные
нарушители цикла оставались без меры, чистка не работала никогда.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core.traffic_rate_monitor import TrafficRateMonitor

VIOLATOR = {
    "username": "alice", "user_uuid": "11111111-1111-1111-1111-111111111111",
    "delta_gb": 60.0, "elapsed_minutes": 10, "rate_gb_per_hour": 360.0,
}


@pytest.mark.asyncio
async def test_throttle_completes_without_touching_instance_state():
    cfg = MagicMock()
    cfg.get = lambda key, default=None: default
    apply = AsyncMock(return_value=(True, None, False))
    push = AsyncMock()
    with patch("shared.config_service.config_service", cfg), \
            patch("shared.throttle.apply_throttle", apply), \
            patch("web.backend.core.throttle_sync.push_throttles", push):
        await TrafficRateMonitor._throttle_violator(VIOLATOR, 50.0)

    assert apply.await_args.kwargs["user_uuid"] == VIOLATOR["user_uuid"]
    assert push.await_count == 1

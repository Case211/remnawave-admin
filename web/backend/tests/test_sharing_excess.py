"""#309: относительный порог шеринга — источники сверх лимита устройств.

Абсолютный порог одинаков для лимита 1 и 10: режет большие тарифы или мягок к
маленьким. Теперь анализатор отдаёт разбор порога (лимит, буферы, превышения),
он уходит в событие нарушения, а жёсткая мера может считать от лимита юзера.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.analyzers.temporal import TemporalAnalyzer
from shared.config_service import config_service
from shared.connection_monitor import ActiveConnection
from shared.db.violations import ViolationsMixin
from web.backend.core.automation_engine import AutomationEngine

from .test_violation_detector import make_detector, meta, run_check

IPS = [f"{i}.{i}.{i}.{i}" for i in range(1, 8)]  # 7 адресов в разных сетях
_original_get = config_service.get


def _config(**overrides):
    return patch.object(config_service, "get",
                        side_effect=lambda key, default=None: overrides[key] if key in overrides
                        else _original_get(key, default))


def _live(ips):
    """Соединения из карты активности: все в сети прямо сейчас."""
    now = datetime.utcnow()
    return [
        ActiveConnection(connection_id=i, user_uuid="u", ip_address=ip, node_uuid="n",
                         connected_at=now - timedelta(minutes=30), device_info=None,
                         last_seen_at=now - timedelta(seconds=30))
        for i, ip in enumerate(ips)
    ]


def _analyze(ips, device_limit, source_of=None):
    return TemporalAnalyzer().analyze(
        _live(ips), [], max(1, device_limit), source_of=source_of, device_limit=device_limit,
    )


class TestThresholdBreakdown:
    def test_limit_one(self):
        res = _analyze(IPS, 1)
        assert (res.simultaneous_connections_count, res.simultaneous_addresses) == (7, 7)
        assert (res.device_limit, res.network_buffer, res.cgnat_buffer, res.effective_threshold) == (1, 1, 0, 2)
        assert (res.simultaneous_excess, res.effective_excess) == (6, 5)

    def test_limit_three(self):
        res = _analyze(IPS, 3)
        # 3 устройства: буфер на смену сети +3, порог 3 + 3 = 6
        assert (res.effective_threshold, res.simultaneous_excess, res.effective_excess) == (6, 4, 1)

    def test_unlimited_has_no_excess(self):
        """Безлимит (0) не превращается в лимит 1 для превышения."""
        res = _analyze(IPS, 0)
        assert res.device_limit == 0
        assert res.simultaneous_excess is None

    def test_pool_addresses_are_one_source(self):
        pool = {ip: "carrier-pool" for ip in IPS[:4]}
        res = _analyze(IPS, 1, source_of=pool)
        assert (res.simultaneous_connections_count, res.simultaneous_addresses) == (4, 7)
        assert res.simultaneous_excess == 3

    def test_old_callers_without_device_limit(self):
        res = TemporalAnalyzer().analyze(_live(IPS[:3]), [], 2)
        assert (res.device_limit, res.simultaneous_excess) == (2, 1)


def _geo():
    return {ip: meta(ip, country_code="RU", city="Moscow", latitude=55.7, longitude=37.6,
                     asn=100 + i, asn_org=f"ISP-{i}", connection_type="residential")
            for i, ip in enumerate(IPS)}


async def _detect(devices, **config):
    det = make_detector(_geo())
    with _config(**config):
        return await run_check(det, _live(IPS), devices=devices)


class TestHardBlock:
    @pytest.mark.asyncio
    async def test_seven_sources_on_limit_one(self):
        res = await _detect(1, violations_hard_block_simultaneous_excess=5)
        assert "sharing.excess" in res.signals
        assert res.recommended_action.value == "hard_block"
        assert any(r.startswith("Шаринг сверх лимита устройств: 7 источников при лимите 1") for r in res.reasons)

    @pytest.mark.asyncio
    async def test_seven_sources_on_limit_three(self):
        res = await _detect(3, violations_hard_block_simultaneous_excess=5)
        assert "sharing.excess" not in res.signals

    @pytest.mark.asyncio
    async def test_unlimited_is_not_touched(self):
        res = await _detect(0, violations_hard_block_simultaneous_excess=5)
        assert "sharing.excess" not in res.signals
        assert res.breakdown["temporal"].simultaneous_excess is None

    @pytest.mark.asyncio
    async def test_off_by_default(self):
        res = await _detect(1)
        assert "sharing.excess" not in res.signals


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, *args):
        return self.rows


def _db(rows):
    class _Acquire:
        async def __aenter__(self):
            return _Rows(rows)

        async def __aexit__(self, *exc):
            return False

    return SimpleNamespace(is_connected=True, acquire=_Acquire)


@pytest.mark.asyncio
async def test_batch_device_limits_keep_unlimited():
    rows = [
        {"uuid": "a", "raw_data": {"hwidDeviceLimit": 0}},
        {"uuid": "b", "raw_data": {"hwidDeviceLimit": 3}},
        {"uuid": "c", "raw_data": {}},
    ]
    limits = await ViolationsMixin.batch_get_user_devices_counts(_db(rows), ["a", "b", "c"])
    assert limits == {"a": 0, "b": 3, "c": 1}


@pytest.mark.asyncio
async def test_empty_value_in_notification_is_a_dash():
    notify = AsyncMock()
    with patch("web.backend.core.notification_service.create_notification", notify):
        await AutomationEngine()._action_notify(
            {"channel": "telegram", "message": "Сверх лимита: {simultaneous_excess}"}, "user", "u",
            {"simultaneous_excess": None},
        )
    assert "Сверх лимита: —" in notify.await_args.kwargs["telegram_card"].to_html()

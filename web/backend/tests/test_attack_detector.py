"""Тесты детектора атаки на канал ноды.

Главное, что здесь проверяется, — детектор не кричит на обычную нагрузку.
Ложная тревога дороже пропуска: админ, которому панель раз в неделю пишет
«нода под атакой» на вечернем пике, перестаёт читать эти уведомления вообще.
"""
import pytest

from web.backend.core.attack_detector import (
    Baseline,
    NetSample,
    Thresholds,
    Verdict,
    _open_or_touch,
    assess,
)

CFG = Thresholds()
CALM = Baseline(rx_bps=2_000_000, rx_pps=1_500, samples=200)


def sample(**over) -> NetSample:
    """Срез ноды в норме; в тестах переопределяем только значимое поле."""
    base = dict(
        node_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        name="NL-1",
        rx_bps=2_100_000,
        rx_pps=1_600,
        rx_drop_ps=0,
        tcp_syncookies_ps=0,
        tcp_listen_drop_ps=0,
        conntrack_count=None,
        conntrack_max=None,
    )
    base.update(over)
    return NetSample(**base)


# ── Тишина там, где тишина ───────────────────────────────────────


def test_normal_traffic_is_silent():
    assert assess(sample(), CALM, CFG) is None


def test_evening_peak_is_not_an_attack():
    """Трафик втрое выше обычного, но пакеты крупные и стек не страдает."""
    peak = sample(rx_bps=6_500_000, rx_pps=5_200)
    assert assess(peak, CALM, CFG) is None


def test_spike_without_symptoms_is_not_an_attack():
    """Даже пятикратный рост сам по себе не приговор: бывает и легальный.

    Пакеты по 1250 байт — так выглядит скачивание, а не флуд.
    """
    spike = sample(rx_bps=12_000_000, rx_pps=9_600)
    assert assess(spike, CALM, CFG) is None


def test_quiet_node_noise_does_not_trigger():
    """На пустой ноде рост «в двадцать раз» — это шум в несколько сотен пакетов."""
    quiet = Baseline(rx_bps=20_000, rx_pps=40, samples=200)
    noise = sample(rx_bps=400_000, rx_pps=800, tcp_syncookies_ps=5)

    assert assess(noise, quiet, CFG) is None


def test_no_verdict_without_baseline():
    """Пока история не набралась, сравнивать не с чем — молчим."""
    fresh = Baseline(rx_bps=0, rx_pps=0, samples=3)
    flood = sample(rx_pps=90_000, rx_bps=9_000_000, tcp_syncookies_ps=4_000)

    assert assess(flood, fresh, CFG) is None


def test_disabled_detector_stays_quiet():
    flood = sample(rx_pps=90_000, rx_bps=9_000_000, tcp_syncookies_ps=4_000)
    assert assess(flood, CALM, Thresholds(enabled=False)) is None


# ── Атаки, которые обязаны быть замечены ─────────────────────────


def test_syn_flood_is_critical():
    """Много мелких пакетов и syncookies — классический SYN-флуд."""
    flood = sample(rx_pps=90_000, rx_bps=5_400_000, tcp_syncookies_ps=4_000)

    verdict = assess(flood, CALM, CFG)

    assert verdict is not None
    assert verdict.severity == "critical"
    assert "syn_flood" in verdict.reasons
    assert "small_packets" in verdict.reasons  # 60 байт на пакет


def test_volumetric_attack_detected_by_bandwidth():
    """Пакеты крупные, но канал забит и карта роняет пакеты."""
    flood = sample(rx_bps=940_000_000, rx_pps=80_000, rx_drop_ps=1_200)

    verdict = assess(flood, CALM, CFG)

    assert verdict is not None
    assert verdict.severity == "critical"
    assert verdict.reasons == ["nic_drops"]


def test_accept_queue_overflow_detected():
    flood = sample(rx_pps=60_000, rx_bps=36_000_000, tcp_listen_drop_ps=800)

    verdict = assess(flood, CALM, CFG)

    assert verdict is not None
    assert "listen_drops" in verdict.reasons


def test_conntrack_exhaustion_detected():
    flood = sample(rx_pps=70_000, rx_bps=42_000_000, conntrack_count=250_000, conntrack_max=262_144)

    verdict = assess(flood, CALM, CFG)

    assert verdict is not None
    assert "conntrack_full" in verdict.reasons


def test_conntrack_with_room_left_is_not_a_reason():
    flood = sample(rx_pps=70_000, rx_bps=42_000_000, conntrack_count=1_000, conntrack_max=262_144)
    assert assess(flood, CALM, CFG) is None


def test_small_packets_alone_are_only_a_warning():
    """Стек ещё справляется, но поток из мелких пакетов подозрителен сам по себе."""
    flood = sample(rx_pps=80_000, rx_bps=8_000_000)  # 100 байт на пакет

    verdict = assess(flood, CALM, CFG)

    assert verdict is not None
    assert verdict.severity == "warning"
    assert verdict.reasons == ["small_packets"]


def test_ratio_is_reported_for_the_alert_text():
    flood = sample(rx_pps=15_000, rx_bps=1_200_000, tcp_syncookies_ps=100)

    verdict = assess(flood, CALM, CFG)

    assert verdict is not None
    assert verdict.ratio_pps == pytest.approx(10.0)


# ── Состояние события ────────────────────────────────────────────


class FakeConn:
    """Подменяет два запроса _open_or_touch: чтение прошлой severity и upsert."""

    def __init__(self, previous: str | None, inserted: bool):
        self.previous = previous
        self.inserted = inserted

    async def fetchval(self, sql: str, *args):
        return self.previous if "SELECT severity" in sql else self.inserted


async def _touch(previous: str | None, inserted: bool, severity: str):
    verdict = Verdict(severity=severity, reasons=["syn_flood"], ratio_pps=9.0, ratio_bps=3.0)
    return await _open_or_touch(FakeConn(previous, inserted), sample(), verdict, CALM)


@pytest.mark.asyncio
async def test_new_attack_reports_start():
    assert await _touch(None, True, "critical") == (True, False)


@pytest.mark.asyncio
async def test_ongoing_attack_stays_silent():
    """Событие уже открыто — второй раз о том же не пишем."""
    assert await _touch("critical", False, "critical") == (False, False)


@pytest.mark.asyncio
async def test_escalation_breaks_the_silence():
    """Было больно — стало очень больно. Об этом сказать обязаны."""
    assert await _touch("warning", False, "critical") == (False, True)


@pytest.mark.asyncio
async def test_no_escalation_notice_when_severity_drops():
    assert await _touch("critical", False, "warning") == (False, False)


def test_baseline_of_zero_does_not_divide_by_zero():
    """Нода только что поднялась после простоя: базлайн нулевой."""
    idle = Baseline(rx_bps=0, rx_pps=0, samples=100)
    flood = sample(rx_pps=90_000, rx_bps=5_400_000, tcp_syncookies_ps=4_000)

    verdict = assess(flood, idle, CFG)

    assert verdict is not None
    assert verdict.ratio_pps == float("inf")

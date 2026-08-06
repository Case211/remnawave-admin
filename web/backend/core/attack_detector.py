"""Детект атаки на канал ноды.

Панель видит трафик глазами Xray — то есть только тот, что прошёл через прокси.
Атака бьёт по интерфейсу, до Xray не доходит и в статистике не появляется:
нода выглядит просто опустевшей, будто её заблокировали. Сырые счётчики хоста
от агента (1.3.0+) показывают разницу — при блокировке приём падает, при атаке
растёт.

Вердикт ставится только когда совпало двое: приём заметно выше собственного
базлайна ноды И это не похоже на полезную нагрузку — стек захлёбывается или
пакеты подозрительно мелкие. Один лишь всплеск трафика поводом не считаем:
вечерний пик тоже всплеск.
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from shared.db_schema import (
    NODE_ATTACK_EVENTS_TABLE,
    NODE_METRICS_SNAPSHOTS_TABLE,
    NODES_TABLE,
)

logger = logging.getLogger(__name__)

_TICK_SECONDS = 60
_STARTUP_DELAY = 120

# Метрики старше этого возраста считаем протухшими: агент молчит или нода легла
_SAMPLE_MAX_AGE_MINUTES = 3

# Окно базлайна и «слепая зона» перед текущим моментом: без неё атака
# поднимала бы собственный базлайн и через полчаса переставала быть аномалией
_BASELINE_WINDOW_HOURS = 6
_BASELINE_LAG_MINUTES = 15

# Через сколько тишины считаем, что атака закончилась
_RECOVERY_MINUTES = 10

_CONNTRACK_FULL_RATIO = 0.9

# Признаки, по которым всплеск считается атакой. Первые четыре означают, что
# ноде уже больно; small_packets — что трафик не похож на полезный.
REASON_LABELS: dict[str, str] = {
    "syn_flood": "SYN-флуд (ядро отвечает syncookies)",
    "listen_drops": "очередь входящих соединений переполнена",
    "nic_drops": "сетевая карта роняет пакеты",
    "conntrack_full": "таблица соединений почти заполнена",
    "small_packets": "поток из мелких пакетов",
}

_PAINFUL = ("syn_flood", "listen_drops", "nic_drops", "conntrack_full")


@dataclass(frozen=True)
class Thresholds:
    """Пороги детекта (правятся в настройках)."""

    enabled: bool = True
    pps_ratio: float = 4.0
    bps_ratio: float = 4.0
    min_pps: int = 5_000
    min_bps: int = 12_500_000          # 100 Мбит/с
    min_samples: int = 20              # меньше — базлайну нельзя верить
    small_packet_bytes: int = 300


@dataclass(frozen=True)
class NetSample:
    """Текущий сетевой срез ноды."""

    node_uuid: str
    name: str
    rx_bps: int
    rx_pps: int
    rx_drop_ps: int
    tcp_syncookies_ps: int
    tcp_listen_drop_ps: int
    conntrack_count: Optional[int] = None
    conntrack_max: Optional[int] = None


@dataclass(frozen=True)
class Baseline:
    """Спокойное состояние той же ноды: медиана за окно наблюдения."""

    rx_bps: float
    rx_pps: float
    samples: int


@dataclass(frozen=True)
class Verdict:
    severity: str          # warning | critical
    reasons: list[str]
    ratio_pps: float
    ratio_bps: float


def _ratio(value: float, baseline: float) -> float:
    """Во сколько раз выше базлайна. Пустой базлайн — считаем ростом с нуля."""
    if baseline <= 0:
        return float("inf") if value > 0 else 1.0
    return value / baseline


def assess(sample: NetSample, baseline: Baseline, cfg: Thresholds) -> Optional[Verdict]:
    """Поставить вердикт по одному срезу. None — поводов нет."""
    if not cfg.enabled or baseline.samples < cfg.min_samples:
        return None

    ratio_pps = _ratio(sample.rx_pps, baseline.rx_pps)
    ratio_bps = _ratio(sample.rx_bps, baseline.rx_bps)

    # Абсолютный минимум обязателен: на пустой ночной ноде рост «в десять раз»
    # получается из шума в пару сотен пакетов
    spike = (
        (sample.rx_pps >= cfg.min_pps and ratio_pps >= cfg.pps_ratio)
        or (sample.rx_bps >= cfg.min_bps and ratio_bps >= cfg.bps_ratio)
    )
    if not spike:
        return None

    reasons: list[str] = []
    if sample.tcp_syncookies_ps > 0:
        reasons.append("syn_flood")
    if sample.tcp_listen_drop_ps > 0:
        reasons.append("listen_drops")
    if sample.rx_drop_ps > 0:
        reasons.append("nic_drops")
    if (
        sample.conntrack_count is not None
        and sample.conntrack_max
        and sample.conntrack_count >= sample.conntrack_max * _CONNTRACK_FULL_RATIO
    ):
        reasons.append("conntrack_full")
    if sample.rx_pps > 0 and sample.rx_bps / sample.rx_pps < cfg.small_packet_bytes:
        reasons.append("small_packets")

    # Всплеск без единого признака — это просто нагрузка, а не атака
    if not reasons:
        return None

    severity = "critical" if any(r in _PAINFUL for r in reasons) else "warning"
    return Verdict(severity=severity, reasons=reasons, ratio_pps=ratio_pps, ratio_bps=ratio_bps)


# ── Загрузка данных ──────────────────────────────────────────────


def load_thresholds() -> Thresholds:
    from shared.config_service import config_service

    def _num(key: str, default: float) -> float:
        try:
            return float(config_service.get(key, default) or default)
        except (TypeError, ValueError):
            return default

    return Thresholds(
        enabled=bool(config_service.get("attack_detect_enabled", True)),
        pps_ratio=_num("attack_pps_ratio", 4.0),
        bps_ratio=_num("attack_bps_ratio", 4.0),
        min_pps=int(_num("attack_min_pps", 5_000)),
        min_bps=int(_num("attack_min_bps", 12_500_000)),
        min_samples=int(_num("attack_min_samples", 20)),
        small_packet_bytes=int(_num("attack_small_packet_bytes", 300)),
    )


async def _fetch_samples(conn) -> list[NetSample]:
    """Свежие сетевые срезы включённых нод."""
    rows = await conn.fetch(
        f"""
        SELECT uuid, name, net_rx_bps, net_rx_pps, net_rx_drop_ps,
               tcp_syncookies_ps, tcp_listen_drop_ps, conntrack_count, conntrack_max
        FROM {NODES_TABLE}
        WHERE is_disabled = false
          AND net_rx_pps IS NOT NULL
          AND metrics_updated_at > NOW() - make_interval(mins => $1)
        """,
        _SAMPLE_MAX_AGE_MINUTES,
    )
    return [
        NetSample(
            node_uuid=str(r["uuid"]),
            name=r["name"] or str(r["uuid"])[:8],
            rx_bps=r["net_rx_bps"] or 0,
            rx_pps=r["net_rx_pps"] or 0,
            rx_drop_ps=r["net_rx_drop_ps"] or 0,
            tcp_syncookies_ps=r["tcp_syncookies_ps"] or 0,
            tcp_listen_drop_ps=r["tcp_listen_drop_ps"] or 0,
            conntrack_count=r["conntrack_count"],
            conntrack_max=r["conntrack_max"],
        )
        for r in rows
    ]


async def _fetch_baselines(conn) -> dict[str, Baseline]:
    """Медиана приёма по каждой ноде за окно наблюдения."""
    rows = await conn.fetch(
        f"""
        SELECT node_uuid,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY net_rx_bps) AS rx_bps,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY net_rx_pps) AS rx_pps,
               COUNT(*) AS samples
        FROM {NODE_METRICS_SNAPSHOTS_TABLE}
        WHERE net_rx_pps IS NOT NULL
          AND created_at >= NOW() - make_interval(hours => $1)
          AND created_at <= NOW() - make_interval(mins => $2)
        GROUP BY node_uuid
        """,
        _BASELINE_WINDOW_HOURS,
        _BASELINE_LAG_MINUTES,
    )
    return {
        str(r["node_uuid"]): Baseline(
            rx_bps=float(r["rx_bps"] or 0),
            rx_pps=float(r["rx_pps"] or 0),
            samples=int(r["samples"] or 0),
        )
        for r in rows
    }


# ── Состояние атак ───────────────────────────────────────────────


async def _open_or_touch(
    conn, sample: NetSample, verdict: Verdict, baseline: Baseline
) -> tuple[bool, bool]:
    """Завести событие или продлить идущее.

    Возвращает (началась, усилилась). Второе — переход warning → critical:
    ноде стало по-настоящему больно, и молчать об этом нельзя, хотя событие
    то же самое.
    """
    reasons = ",".join(verdict.reasons)
    previous = await conn.fetchval(
        f"SELECT severity FROM {NODE_ATTACK_EVENTS_TABLE} "
        "WHERE node_uuid = $1::uuid AND ended_at IS NULL",
        sample.node_uuid,
    )
    started = await conn.fetchval(
        f"""
        INSERT INTO {NODE_ATTACK_EVENTS_TABLE} (
            node_uuid, severity, reasons, peak_rx_bps, peak_rx_pps,
            baseline_rx_bps, baseline_rx_pps
        )
        VALUES ($1::uuid, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (node_uuid) WHERE ended_at IS NULL DO UPDATE SET
            last_seen_at = NOW(),
            severity = CASE WHEN EXCLUDED.severity = 'critical'
                            THEN 'critical' ELSE node_attack_events.severity END,
            reasons = EXCLUDED.reasons,
            peak_rx_bps = GREATEST(node_attack_events.peak_rx_bps, EXCLUDED.peak_rx_bps),
            peak_rx_pps = GREATEST(node_attack_events.peak_rx_pps, EXCLUDED.peak_rx_pps)
        RETURNING (xmax = 0) AS inserted
        """,
        sample.node_uuid, verdict.severity, reasons,
        sample.rx_bps, sample.rx_pps,
        int(baseline.rx_bps), int(baseline.rx_pps),
    )
    escalated = (
        not started and previous == "warning" and verdict.severity == "critical"
    )
    return bool(started), escalated


async def _close_finished(conn) -> list[dict[str, Any]]:
    """Закрыть события, по которым давно тихо. Возвращает закрытые."""
    rows = await conn.fetch(
        f"""
        UPDATE {NODE_ATTACK_EVENTS_TABLE} e
        SET ended_at = last_seen_at
        FROM nodes n
        WHERE n.uuid = e.node_uuid
          AND e.ended_at IS NULL
          AND e.last_seen_at < NOW() - make_interval(mins => $1)
        RETURNING e.node_uuid, n.name, e.started_at, e.last_seen_at,
                  e.peak_rx_bps, e.peak_rx_pps, e.severity
        """,
        _RECOVERY_MINUTES,
    )
    return [dict(r) for r in rows]


# ── Уведомления ──────────────────────────────────────────────────


def _fmt_speed(bps: int) -> str:
    mbit = bps * 8 / 1_000_000
    return f"{mbit:.0f} Мбит/с" if mbit >= 1 else f"{bps * 8 / 1000:.0f} Кбит/с"


def _fmt_int(value: int) -> str:
    """Разряды через неразрывный пробел: «1 200 000»."""
    return f"{value:,}".replace(",", " ")


def _fmt_duration(started: datetime, ended: datetime) -> str:
    minutes = max(1, int((ended - started).total_seconds() // 60))
    if minutes < 60:
        return f"{minutes} мин"
    return f"{minutes // 60} ч {minutes % 60} мин"


async def _notify_started(
    sample: NetSample, verdict: Verdict, baseline: Baseline, escalated: bool = False
) -> None:
    from web.backend.core.notification_service import create_notification

    reasons = "\n".join(f"   • {REASON_LABELS[r]}" for r in verdict.reasons)
    body = (
        f"<b>Нода:</b> {sample.name}\n"
        f"<b>Приём:</b> {_fmt_speed(sample.rx_bps)} · {_fmt_int(sample.rx_pps)} пакетов/с\n"
        f"<b>Обычно:</b> {_fmt_speed(int(baseline.rx_bps))} · "
        f"{_fmt_int(int(baseline.rx_pps))} пакетов/с\n"
        f"<b>Признаки:</b>\n{reasons}"
    )

    # Отдельный group_key для эскалации: иначе дедуп примет её за повтор
    # начального алерта и проглотит ровно то сообщение, которое важнее
    prefix = "Атака усилилась" if escalated else "Нода под атакой"
    key = "node_attack_critical" if escalated else "node_attack"

    await create_notification(
        title=f"{prefix}: {sample.name}",
        body=body,
        type="alert",
        severity=verdict.severity,
        channels=["in_app", "telegram", "push"],
        topic_type="nodes",
        source="attack_detector",
        source_id=sample.node_uuid,
        group_key=f"{key}:{sample.node_uuid}",
        link="/fleet",
    )


async def _notify_finished(event: dict[str, Any]) -> None:
    from web.backend.core.notification_service import create_notification

    started, ended = event["started_at"], event["last_seen_at"]
    body = (
        f"<b>Нода:</b> {event['name']}\n"
        f"<b>Длилась:</b> {_fmt_duration(started, ended)}\n"
        f"<b>Пик приёма:</b> {_fmt_speed(event['peak_rx_bps'] or 0)}"
    )

    await create_notification(
        title=f"Атака закончилась: {event['name']}",
        body=body,
        type="alert",
        severity="info",
        channels=["in_app", "telegram"],
        topic_type="nodes",
        source="attack_detector",
        source_id=str(event["node_uuid"]),
        group_key=f"node_attack_end:{event['node_uuid']}",
        link="/fleet",
    )


# ── Цикл ─────────────────────────────────────────────────────────


async def run_once() -> int:
    """Один проход детектора. Возвращает число нод с вердиктом."""
    from shared.database import db_service

    if not db_service.is_connected:
        return 0

    cfg = load_thresholds()
    if not cfg.enabled:
        return 0

    hits = 0
    async with db_service.acquire() as conn:
        samples = await _fetch_samples(conn)
        if not samples:
            return 0

        baselines = await _fetch_baselines(conn)
        empty = Baseline(rx_bps=0.0, rx_pps=0.0, samples=0)

        for sample in samples:
            baseline = baselines.get(sample.node_uuid, empty)
            verdict = assess(sample, baseline, cfg)
            if verdict is None:
                continue

            hits += 1
            started, escalated = await _open_or_touch(conn, sample, verdict, baseline)
            if started or escalated:
                logger.warning(
                    "Node under attack: %s (rx %d pps, x%.1f baseline, %s)",
                    sample.name, sample.rx_pps, verdict.ratio_pps, ",".join(verdict.reasons),
                )
                await _notify_started(sample, verdict, baseline, escalated=escalated)

        for event in await _close_finished(conn):
            logger.info("Attack ended on node %s", event["name"])
            await _notify_finished(event)

    return hits


async def attack_detector_loop() -> None:
    """Фоновый цикл: раз в минуту смотрит свежие метрики нод."""
    await asyncio.sleep(_STARTUP_DELAY)
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("Attack detector tick failed: %s", e)
        await asyncio.sleep(_TICK_SECONDS)

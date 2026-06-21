"""Unit-харнесс по всем 7 анализаторам IntelligentViolationDetector.

Гоняет НАСТОЯЩИЙ детектор с синтетическими входами (моки БД/GeoIP, prefetched-данные —
чтобы не ходить в реальную БД), по сценарию на каждый анализатор. Заодно фиксирует
поведение фиксов аудита:
  - H2 strong-signal bypass (geo impossible-travel создаёт нарушение на ПЕРВОМ срабатывании)
  - C2 HWID per_account_abuse (мультитариф детектится)
  - H3 HWID floor 80 при score>=85
  - device-анализатор подтверждённо мёртв (всегда 0 — нет UA в данных коллектора)

Это первые unit-тесты детектора в проекте (раньше их не было вообще).
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from shared.analyzers.detector import IntelligentViolationDetector
from shared.connection_monitor import ActiveConnection
from shared.geoip import IPMetadata


# ── Хелперы ───────────────────────────────────────────────────────

def meta(ip, **kw) -> IPMetadata:
    return IPMetadata(ip=ip, **kw)


class FakeGeoip:
    """Подменяет GeoIPService: отдаёт заранее заданные метаданные по IP."""
    def __init__(self, mapping):
        self.mapping = mapping

    async def lookup_batch(self, ips):
        return {ip: self.mapping[ip] for ip in ips if ip in self.mapping}

    async def lookup(self, ip):
        return self.mapping.get(ip)


def make_detector(geo_map, recent_violations=3):
    """Детектор с моками. recent_violations: 0 = первое срабатывание (consistency ×0.3),
    3+ = устойчивый паттерн (consistency ×1.0)."""
    db = AsyncMock()
    db.is_connected = True
    db.get_recent_violations_count = AsyncMock(return_value=recent_violations)
    db.get_connection_history = AsyncMock(return_value=[])
    db.get_user_baseline = AsyncMock(return_value=None)
    db.get_user_devices_count = AsyncMock(return_value=1)
    monitor = AsyncMock()
    return IntelligentViolationDetector(db, monitor, geoip_service=FakeGeoip(geo_map))


def conn(ip, sec_ago=480, ua=None):
    """ActiveConnection. sec_ago=480 (8 мин) — для temporal даёт максимум overlap-скора."""
    c = ActiveConnection(
        connection_id=1, user_uuid="u", ip_address=ip, node_uuid="n",
        connected_at=datetime.utcnow() - timedelta(seconds=sec_ago), device_info=None,
    )
    if ua is not None:
        c.user_agent = ua  # коллектор такого не пишет — для проверки device-анализатора
    return c


async def run_check(det, conns, *, history=None, shared=None, srh=None, baseline=None, devices=1):
    return await det.check_user(
        "u",
        prefetched_device_count=devices,
        prefetched_active_connections=conns,
        prefetched_history_30d=history or [],
        prefetched_baseline=baseline,
        prefetched_shared_hwids=shared or [],
        prefetched_srh_records=srh or [],
    )


# ── GEO ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_geo_impossible_travel_creates_violation_on_first_hit():
    """2 IP разных стран одновременно -> geo=90. H2 strong-signal bypass должен создать
    нарушение ДАЖЕ на первом срабатывании (consistency ×0.3), а не утопить в no_action."""
    geo_map = {
        "1.1.1.1": meta("1.1.1.1", country_code="RU", city="Moscow", latitude=55.7, longitude=37.6,
                        asn=1, asn_org="ISP-A", connection_type="residential"),
        "2.2.2.2": meta("2.2.2.2", country_code="DE", city="Berlin", latitude=52.5, longitude=13.4,
                        asn=2, asn_org="ISP-B", connection_type="residential"),
    }
    det = make_detector(geo_map, recent_violations=0)  # ПЕРВОЕ срабатывание
    res = await run_check(det, [conn("1.1.1.1", 60), conn("2.2.2.2", 60)])
    assert res is not None
    assert res.breakdown["geo"].score == 90.0
    assert res.breakdown["geo"].impossible_travel_detected is True
    assert res.total >= 50.0, "H2 strong-signal bypass: geo=90 должен дать нарушение"
    assert res.recommended_action.value in ("warn", "soft_block", "temp_block", "hard_block")


# ── TEMPORAL ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_temporal_simultaneous_ips_scores():
    """Несколько IP одного юзера одновременно (не мобильные, разные ASN) -> temporal > 0."""
    geo_map = {
        f"{i}.{i}.{i}.{i}": meta(f"{i}.{i}.{i}.{i}", country_code="RU", city="Moscow",
                                 latitude=55.7, longitude=37.6, asn=100 + i, asn_org=f"ISP-{i}",
                                 connection_type="residential")
        for i in range(1, 7)
    }
    det = make_detector(geo_map, recent_violations=3)
    conns = [conn(f"{i}.{i}.{i}.{i}", 480 + i * 5) for i in range(1, 7)]
    res = await run_check(det, conns)
    assert res.breakdown["temporal"].score > 0.0
    assert res.breakdown["temporal"].simultaneous_connections_count >= 2


# ── ASN ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_asn_datacenter_scores():
    """Подключение через датацентр -> asn > 0."""
    geo_map = {
        "5.5.5.5": meta("5.5.5.5", country_code="DE", city="Frankfurt", latitude=50.1, longitude=8.6,
                        asn=24940, asn_org="Hetzner", connection_type="datacenter"),
    }
    det = make_detector(geo_map, recent_violations=3)
    res = await run_check(det, [conn("5.5.5.5", 60)])
    assert res.breakdown["asn"].score > 0.0
    assert res.breakdown["asn"].is_datacenter is True


# ── HWID ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hwid_cross_account_creates_violation():
    """3 разных telegram-аккаунта делят 1 HWID -> hwid=85, qualifies, floor 80 (H3)."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", asn=1, asn_org="ISP",
                               connection_type="residential")}
    shared = [{
        "hwid": "HW1", "self_telegram_id": 100,
        "other_users": [
            {"uuid": "U1", "telegram_id": 201, "username": "a", "status": "ACTIVE"},
            {"uuid": "U2", "telegram_id": 202, "username": "b", "status": "ACTIVE"},
        ],
    }]
    det = make_detector(geo_map, recent_violations=0)
    res = await run_check(det, [conn("1.1.1.1", 60)], shared=shared)
    assert res.breakdown["hwid"].score >= 85.0
    assert res.breakdown["hwid"].other_accounts_count >= 1
    assert res.total >= 50.0


@pytest.mark.asyncio
async def test_hwid_multitariff_creates_violation():
    """C2: один telegram_id с 11 подписками на 1 HWID -> per_account_abuse, нарушение.
    other_accounts_count=0, поэтому раньше floor не срабатывал и нарушения не было."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", asn=1, asn_org="ISP",
                               connection_type="residential")}
    shared = [{
        "hwid": "HW1", "self_telegram_id": 100,
        "other_users": [{"uuid": f"U{i}", "telegram_id": 100, "username": f"s{i}", "status": "ACTIVE"}
                        for i in range(1, 12)],
    }]
    det = make_detector(geo_map, recent_violations=0)
    res = await run_check(det, [conn("1.1.1.1", 60)], shared=shared)
    assert res.breakdown["hwid"].per_account_abuse is True
    assert res.breakdown["hwid"].other_accounts_count == 0
    assert res.total >= 50.0, "C2: мультитариф должен создавать нарушение"


# ── DEVICE (подтверждаем, что мёртв) ──────────────────────────────

@pytest.mark.asyncio
async def test_device_analyzer_is_dead():
    """Находка аудита: device всегда 0, т.к. коллектор не пишет user_agent в подключения.
    Даже 5 разных IP при лимите 1 -> device score 0 (fingerprint всегда пустой)."""
    geo_map = {f"{i}.{i}.{i}.{i}": meta(f"{i}.{i}.{i}.{i}", country_code="RU", asn=1,
                                        asn_org="ISP", connection_type="residential")
               for i in range(1, 6)}
    det = make_detector(geo_map, recent_violations=3)
    conns = [conn(f"{i}.{i}.{i}.{i}", 60) for i in range(1, 6)]
    res = await run_check(det, conns, devices=1)
    assert res.breakdown["device"].score == 0.0, "device-анализатор мёртв (нет UA в данных)"


# ── USER-AGENT ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_user_agent_link_in_ua_floor():
    """Ссылка подписки (vless://) в User-Agent = двойной туннель -> ua link floor (>=70)."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", asn=1, asn_org="ISP",
                               connection_type="residential")}
    srh = [{"request_id": 1, "user_agent": "vless://abc@host:443?type=tcp", "request_ip": "1.1.1.1",
            "request_at": datetime.utcnow()}]
    det = make_detector(geo_map, recent_violations=0)
    res = await run_check(det, [conn("1.1.1.1", 60)], srh=srh)
    assert res.breakdown["user_agent"].has_link_in_ua is True
    assert res.total >= 70.0, "ua link floor"


# ── PROFILE ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_profile_ip_count_deviation():
    """Резкий рост числа IP против baseline -> profile > 0 (числовая часть профиля жива)."""
    geo_map = {f"{i}.{i}.{i}.{i}": meta(f"{i}.{i}.{i}.{i}", country_code="RU", asn=100 + i,
                                        asn_org=f"ISP-{i}", connection_type="residential")
               for i in range(1, 7)}
    baseline = {
        "typical_countries": [], "typical_cities": [], "typical_regions": [], "typical_asns": [],
        "known_ips": [], "avg_daily_unique_ips": 1.0, "max_daily_unique_ips": 1,
        "typical_hours": [], "avg_session_duration_minutes": 0, "data_points": 10,
    }
    det = make_detector(geo_map, recent_violations=3)
    conns = [conn(f"{i}.{i}.{i}.{i}", 60) for i in range(1, 7)]  # 6 IP против baseline 1/день
    res = await run_check(det, conns, baseline=baseline)
    assert res.breakdown["profile"].score > 0.0


# ── SANITY: чистый юзер ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_clean_user_no_violation():
    """Один IP, одна страна, без HWID/UA-проблем -> нарушения нет (no_action)."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", city="Moscow", latitude=55.7,
                               longitude=37.6, asn=1, asn_org="ISP", connection_type="residential")}
    det = make_detector(geo_map, recent_violations=0)
    res = await run_check(det, [conn("1.1.1.1", 60)])
    assert res.total < 50.0
    assert res.recommended_action.value in ("no_action", "monitor")


# ── M2: temporal не душится overlap-dampening при массовом шаринге ──

@pytest.mark.asyncio
async def test_temporal_strong_sharing_reaches_100():
    """M2: 6 IP при лимите 1 устройства (не мобильные) — явный массовый шаринг.
    overlap-dampening НЕ применяется -> temporal=100 (раньше потолок был 70)."""
    geo_map = {
        f"{i}.{i}.{i}.{i}": meta(f"{i}.{i}.{i}.{i}", country_code="RU", city="Moscow",
                                 latitude=55.7, longitude=37.6, asn=100 + i, asn_org=f"ISP-{i}",
                                 connection_type="residential")
        for i in range(1, 7)
    }
    det = make_detector(geo_map, recent_violations=3)
    conns = [conn(f"{i}.{i}.{i}.{i}", 60 + i) for i in range(1, 7)]  # свежие, но strong_sharing перебивает
    res = await run_check(det, conns, devices=1)
    assert res.breakdown["temporal"].score == 100.0, "M2: массовый шаринг даёт 100, не дампится"


# ── M3: мобильный оператор защищён CGNAT-буфером + floor_suppression ──

@pytest.mark.asyncio
async def test_mobile_carrier_not_false_positive():
    """M3: те же 6 IP, но мобильный оператор (connection_type=mobile) — CGNAT-буфер
    поднимает порог, floor_suppressed гасит temporal-floor -> нарушения НЕТ."""
    geo_map = {
        f"{i}.{i}.{i}.{i}": meta(f"{i}.{i}.{i}.{i}", country_code="RU", city="Moscow",
                                 latitude=55.7, longitude=37.6, asn=100 + i, asn_org=f"MegaFon-{i}",
                                 connection_type="mobile", is_mobile=True)
        for i in range(1, 7)
    }
    det = make_detector(geo_map, recent_violations=3)
    conns = [conn(f"{i}.{i}.{i}.{i}", 60 + i) for i in range(1, 7)]
    res = await run_check(det, conns, devices=1)
    assert res.total < 50.0, "M3: мобильный оператор не должен ловить ложное нарушение"


def test_mobile_carriers_list_covers_major_operators():
    """M3: расширенный MOBILE_CARRIERS покрывает основных операторов
    (разные варианты названий, как в MaxMind/RIPE)."""
    from shared.geoip import GeoIPService
    carriers = GeoIPService.MOBILE_CARRIERS
    for org in ["MegaFon", "MTS PJSC", "Mobile TeleSystems", "VimpelCom",
                "T2 Mobile", "Scartel", "Kyivstar", "Kcell"]:
        low = org.lower()
        assert any(c in low for c in carriers), f"{org} не распознаётся как мобильный оператор"


@pytest.mark.asyncio
async def test_profile_geo_baseline_revived_via_geoip():
    """Группа 3 #2: build_baseline резолвит typical_countries по known_ips через GeoIP
    (раньше всегда пусто — история подключений не содержит country)."""
    from shared.analyzers.profile import UserProfileAnalyzer
    geo_map = {"77.88.8.8": meta("77.88.8.8", country_code="RU", asn_org="Yandex LLC")}
    db = AsyncMock()
    db.is_connected = True
    db.get_user_baseline = AsyncMock(return_value=None)
    db.save_user_baseline = AsyncMock()
    pa = UserProfileAnalyzer(db, geoip_service=FakeGeoip(geo_map))
    history = [{"ip_address": "77.88.8.8", "connected_at": datetime.utcnow() - timedelta(days=1)}]
    bl = await pa.build_baseline("u", days=30, connection_history=history)
    assert "RU" in bl["typical_countries"], "гео-baseline должен резолвиться через GeoIP по known_ips"

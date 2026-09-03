"""Unit-харнесс по всем 7 анализаторам IntelligentViolationDetector.

Гоняет НАСТОЯЩИЙ детектор с синтетическими входами (моки БД/GeoIP, prefetched-данные —
чтобы не ходить в реальную БД), по сценарию на каждый анализатор. Заодно фиксирует
поведение фиксов аудита:
  - H2 strong-signal bypass (geo impossible-travel создаёт нарушение на ПЕРВОМ срабатывании)
  - C2 HWID per_account_abuse (мультитариф детектится)
  - H3 HWID floor 80 при score>=85
  - device-анализатор оживлён по SRH-UA (M6): платформы устройств, разные ОС = шаринг

Это первые unit-тесты детектора в проекте (раньше их не было вообще).
"""
from datetime import datetime, timedelta, timezone
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
async def test_hwid_mass_cross_account_hard_blocks():
    """7 разных аккаунтов на одном HWID >= порога violations_hard_block_hwid_accounts (5)
    -> extreme abuse, score=100, hard_block (раньше потолком был floor 80 = temp_block,
    и автоблок не срабатывал никогда)."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", asn=1, asn_org="ISP",
                               connection_type="residential")}
    shared = [{
        "hwid": "HW1", "self_telegram_id": 100,
        "other_users": [{"uuid": f"U{i}", "telegram_id": 200 + i, "username": f"tg{i}", "status": "DISABLED"}
                        for i in range(1, 7)],
    }]
    det = make_detector(geo_map, recent_violations=0)
    res = await run_check(det, [conn("1.1.1.1", 60)], shared=shared)
    assert res.breakdown["hwid"].max_accounts_per_hwid == 7
    assert res.total == 100.0
    assert res.recommended_action.value == "hard_block"
    assert any("аккаунтов на одном HWID" in r for r in res.reasons)


@pytest.mark.asyncio
async def test_hwid_below_hard_block_accounts_stays_temp_block():
    """4 аккаунта на HWID — выше порога анализатора (нарушение есть), но ниже порога
    жёсткой блокировки (5): floor 80, temp_block, автоблока нет."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", asn=1, asn_org="ISP",
                               connection_type="residential")}
    shared = [{
        "hwid": "HW1", "self_telegram_id": 100,
        "other_users": [{"uuid": f"U{i}", "telegram_id": 200 + i, "username": f"tg{i}", "status": "ACTIVE"}
                        for i in range(1, 4)],
    }]
    det = make_detector(geo_map, recent_violations=0)
    res = await run_check(det, [conn("1.1.1.1", 60)], shared=shared)
    assert res.breakdown["hwid"].max_accounts_per_hwid == 4
    assert 80.0 <= res.total < 95.0
    assert res.recommended_action.value != "hard_block"


@pytest.mark.asyncio
async def test_hwid_email_grouping_keeps_multitariff_clean():
    """Мультитариф без Telegram: две подписки одного email на общем устройстве — это
    ОДИН аккаунт, нарушения быть не должно. До группировки по email каждый UUID без
    telegram_id считался отдельным аккаунтом, и легальный апгрейд выглядел как
    кросс-аккаунт."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", asn=1, asn_org="ISP",
                               connection_type="residential")}
    shared = [{
        "hwid": "HW1", "self_telegram_id": None, "self_email": "Dacx@Mail.Ru",
        "self_is_trial": False, "self_is_active": True,
        "other_users": [
            {"uuid": "U1", "telegram_id": None, "email": "dacx@mail.ru", "username": "dacx-trial",
             "status": "EXPIRED", "is_trial": True, "is_active": False},
        ],
    }]
    det = make_detector(geo_map, recent_violations=0)
    res = await run_check(det, [conn("1.1.1.1", 60)], shared=shared)
    assert res.breakdown["hwid"].max_accounts_per_hwid == 1
    assert res.breakdown["hwid"].score == 0.0


@pytest.mark.asyncio
async def test_hwid_parallel_active_trials_hard_blocks():
    """Два РАЗНЫХ аккаунта с живым триалом на одном устройстве -> extreme abuse,
    hard_block. Порога по числу аккаунтов (дефолт 2) двух аккаунтов не хватает —
    срабатывает именно триальная проверка."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", asn=1, asn_org="ISP",
                               connection_type="residential")}
    shared = [{
        "hwid": "HW1", "self_telegram_id": 7948421388, "self_email": None,
        "self_is_trial": True, "self_is_active": True,
        "other_users": [
            {"uuid": "U1", "telegram_id": 6283030269, "email": None, "username": "trial2",
             "status": "ACTIVE", "is_trial": True, "is_active": True},
        ],
    }]
    det = make_detector(geo_map, recent_violations=0)
    res = await run_check(det, [conn("1.1.1.1", 60)], shared=shared)
    assert res.breakdown["hwid"].max_active_trials_per_hwid == 2
    assert res.breakdown["hwid"].max_accounts_per_hwid == 2
    assert res.total == 100.0
    assert res.recommended_action.value == "hard_block"
    # Ровно одна строка: анализатор и детектор формулируют находку одинаково,
    # дедупликация причин схлопывает их в одну — админ не должен видеть дубль
    assert len([r for r in res.reasons if "активным триалом" in r]) == 1


@pytest.mark.asyncio
async def test_hwid_trial_abuse_collects_accomplices():
    """В соучастники попадают только чужие подписки с ЖИВЫМ триалом на том же HWID:
    их блокируют вместе с проверяемым, иначе связка остаётся рабочей. Платный и
    истёкший аккаунты рядом на устройстве под блокировку не идут."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", asn=1, asn_org="ISP",
                               connection_type="residential")}
    shared = [{
        "hwid": "HW1", "self_telegram_id": 100, "self_email": None,
        "self_is_trial": True, "self_is_active": True,
        "other_users": [
            {"uuid": "U-trial", "telegram_id": 201, "email": None, "username": "trial2",
             "status": "ACTIVE", "is_trial": True, "is_active": True},
            {"uuid": "U-paid", "telegram_id": 202, "email": None, "username": "payer",
             "status": "ACTIVE", "is_trial": False, "is_active": True},
            {"uuid": "U-old", "telegram_id": 203, "email": None, "username": "old",
             "status": "EXPIRED", "is_trial": True, "is_active": False},
        ],
    }]
    det = make_detector(geo_map, recent_violations=0)
    res = await run_check(det, [conn("1.1.1.1", 60)], shared=shared)
    assert res.breakdown["hwid"].active_trial_accomplices == ["U-trial"]
    assert res.recommended_action.value == "hard_block"
    assert any("Связанные аккаунты" in r for r in res.reasons)


@pytest.mark.asyncio
async def test_hwid_no_accomplices_when_threshold_not_hit():
    """Порог не пробит — список соучастников пуст, блокировать некого."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", asn=1, asn_org="ISP",
                               connection_type="residential")}
    shared = [{
        "hwid": "HW1", "self_telegram_id": 100, "self_email": None,
        "self_is_trial": True, "self_is_active": True,
        "other_users": [
            {"uuid": "U-paid", "telegram_id": 202, "email": None, "username": "payer",
             "status": "ACTIVE", "is_trial": False, "is_active": True},
        ],
    }]
    det = make_detector(geo_map, recent_violations=0)
    res = await run_check(det, [conn("1.1.1.1", 60)], shared=shared)
    assert not res.breakdown["hwid"].active_trial_accomplices


@pytest.mark.asyncio
async def test_hwid_expired_trial_next_to_active_is_clean():
    """Истёкший триал рядом с живой подпиской — обычный жизненный цикл, а не абуз:
    живой триал на устройстве один, порог не пробит."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", asn=1, asn_org="ISP",
                               connection_type="residential")}
    shared = [{
        "hwid": "HW1", "self_telegram_id": 100, "self_email": None,
        "self_is_trial": True, "self_is_active": True,
        "other_users": [
            {"uuid": "U1", "telegram_id": 201, "email": None, "username": "paid",
             "status": "ACTIVE", "is_trial": False, "is_active": True},
            {"uuid": "U2", "telegram_id": 201, "email": None, "username": "old-trial",
             "status": "DISABLED", "is_trial": True, "is_active": False},
        ],
    }]
    det = make_detector(geo_map, recent_violations=0)
    res = await run_check(det, [conn("1.1.1.1", 60)], shared=shared)
    assert res.breakdown["hwid"].max_active_trials_per_hwid == 1
    assert res.breakdown["hwid"].score == 0.0
    assert res.recommended_action.value != "hard_block"


@pytest.mark.asyncio
async def test_hwid_second_trial_under_own_telegram_is_abuse():
    """Обход, пойманный 22.08: человек с истёкшим триалом удаляет устройство,
    заводит вторую подписку через email, цепляет к ней тот же HWID и привязывает
    свой же telegram_id. После привязки аккаунт для детектора снова один, живой
    триал один, подписок две из десяти разрешённых — все прежние пороги молчат.
    Ловит только счёт пробных подписок одного аккаунта на устройстве."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", asn=1, asn_org="ISP",
                               connection_type="residential")}
    shared = [{
        "hwid": "HW1", "self_telegram_id": 100, "self_email": None,
        "self_is_trial": True, "self_is_active": True,
        "other_users": [
            {"uuid": "U1", "telegram_id": 100, "email": None, "username": "old-trial",
             "status": "DISABLED", "is_trial": True, "is_active": False,
             "removed_at": datetime.now(timezone.utc)},
        ],
    }]
    det = make_detector(geo_map, recent_violations=0)
    res = await run_check(det, [conn("1.1.1.1", 60)], shared=shared)
    hwid = res.breakdown["hwid"]
    assert hwid.max_active_trials_per_hwid == 1, "живой триал один — старые пороги слепы"
    assert hwid.max_accounts_per_hwid == 1, "после привязки telegram_id аккаунт один"
    assert hwid.per_account_abuse is False, "две подписки из десяти разрешённых"
    assert hwid.max_trial_subs_per_hwid == 2
    assert hwid.score == 100.0
    assert res.recommended_action.value == "hard_block"


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


# ── DEVICE (оживлён по SRH-UA, M6) ────────────────────────────────

@pytest.mark.asyncio
async def test_device_zero_without_srh():
    """Без SRH device падает на connection-based fingerprint (UA нет) -> 0."""
    geo_map = {f"{i}.{i}.{i}.{i}": meta(f"{i}.{i}.{i}.{i}", country_code="RU", asn=1,
                                        asn_org="ISP", connection_type="residential")
               for i in range(1, 6)}
    det = make_detector(geo_map, recent_violations=3)
    conns = [conn(f"{i}.{i}.{i}.{i}", 60) for i in range(1, 6)]
    res = await run_check(det, conns, devices=1)  # srh пуст
    assert res.breakdown["device"].score == 0.0


@pytest.mark.asyncio
async def test_device_scores_different_platforms_from_srh():
    """M6: iOS + Android в SRH-UA при лимите 1 устройство -> device > 0 (разные платформы)."""
    geo_map = {"1.1.1.1": meta("1.1.1.1", country_code="RU", asn=1, asn_org="ISP",
                               connection_type="residential")}
    det = make_detector(geo_map, recent_violations=3)
    srh = [
        {"user_agent": "Happ/1.9.0", "request_ip": "1.1.1.1", "request_at": datetime.utcnow(), "request_id": 1},
        {"user_agent": "v2rayNG/1.8.5", "request_ip": "2.2.2.2", "request_at": datetime.utcnow(), "request_id": 2},
    ]
    res = await run_check(det, [conn("1.1.1.1", 60)], srh=srh, devices=1)
    assert res.breakdown["device"].score > 0.0
    assert res.breakdown["device"].different_os_count >= 2


class TestDeviceAnalyzeSrh:
    """Unit-тесты analyze_srh напрямую на анализаторе."""

    def _analyzer(self):
        from shared.analyzers.detector import DeviceFingerprintAnalyzer
        return DeviceFingerprintAnalyzer()

    def _srh(self, *uas):
        return [{"user_agent": ua, "request_at": datetime.utcnow(), "request_ip": None, "request_id": i}
                for i, ua in enumerate(uas)]

    def test_single_platform_zero(self):
        res = self._analyzer().analyze_srh(self._srh("Happ/1.9", "Happ/2.0", "Shadowrocket/2.2"), user_device_count=1)
        # все iOS -> одна платформа -> 0
        assert res.different_os_count == 1
        assert res.score == 0.0

    def test_two_platforms_over_limit(self):
        res = self._analyzer().analyze_srh(self._srh("Happ/1.9", "v2rayNG/1.8"), user_device_count=1)
        assert res.different_os_count == 2
        assert res.score >= 25.0

    def test_three_platforms_strong(self):
        res = self._analyzer().analyze_srh(
            self._srh("Happ/1.9", "v2rayNG/1.8", "v2rayN/6.0"), user_device_count=1)
        assert res.different_os_count == 3
        assert res.score == 40.0

    def test_two_platforms_within_limit(self):
        # лимит 2 устройства, 2 платформы -> в пределах, 0
        res = self._analyzer().analyze_srh(self._srh("Happ/1.9", "v2rayNG/1.8"), user_device_count=2)
        assert res.score == 0.0

    def test_cross_platform_client_ignored(self):
        # Hiddify кроссплатформенный -> платформа не определяется, не считается разной ОС
        res = self._analyzer().analyze_srh(self._srh("Happ/1.9", "Hiddify/2.0"), user_device_count=1)
        assert res.different_os_count == 1  # только iOS от Happ

    def test_explicit_os_marker_wins(self):
        # явный маркер ОС в UA (даже у кроссплатформенного клиента)
        res = self._analyzer().analyze_srh(
            self._srh("ClashMetaForAndroid/2.0 (Android 13)", "FlClash/1.0 (Windows NT 10)"),
            user_device_count=1)
        assert res.different_os_count == 2

    def test_old_records_outside_window_ignored(self):
        old = datetime.utcnow() - timedelta(days=30)
        recs = [
            {"user_agent": "Happ/1.9", "request_at": datetime.utcnow(), "request_ip": None, "request_id": 1},
            {"user_agent": "v2rayNG/1.8", "request_at": old, "request_ip": None, "request_id": 2},
        ]
        res = self._analyzer().analyze_srh(recs, user_device_count=1, window_days=7)
        assert res.different_os_count == 1  # старый Android отброшен

    def test_empty_srh_zero(self):
        res = self._analyzer().analyze_srh([], user_device_count=1)
        assert res.score == 0.0


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
    """M3: те же 6 IP, но один мобильный оператор (connection_type=mobile) — CGNAT-буфер
    поднимает порог, floor_suppressed гасит temporal-floor -> нарушения НЕТ.

    Оператор один: шесть адресов из шести разных сетей за минуту — это уже не
    CGNAT одного телефона, а толпа, и её детектор обязан ловить (см. ниже)."""
    geo_map = {
        f"{i}.{i}.{i}.{i}": meta(f"{i}.{i}.{i}.{i}", country_code="RU", city="Moscow",
                                 latitude=55.7, longitude=37.6, asn=31133, asn_org="PJSC MegaFon",
                                 connection_type="mobile", is_mobile=True)
        for i in range(1, 7)
    }
    det = make_detector(geo_map, recent_violations=3)
    conns = [conn(f"{i}.{i}.{i}.{i}", 60 + i) for i in range(1, 7)]
    res = await run_check(det, conns, devices=1)
    assert res.total < 50.0, "M3: мобильный оператор не должен ловить ложное нарушение"


def _crowd(n, mobile_every=None):
    """n адресов из n разных сетей и провайдеров; каждый mobile_every-й — мобильный."""
    geo_map, conns = {}, []
    for i in range(1, n + 1):
        ip = f"{80 + i}.{10 + i}.{20 + i}.{30 + i}"
        mobile = bool(mobile_every) and i % mobile_every == 0
        geo_map[ip] = meta(ip, country_code="RU", city="Moscow", latitude=55.7, longitude=37.6,
                           asn=1000 + i, asn_org="PJSC MegaFon" if mobile else f"ISP-{i}",
                           connection_type="mobile" if mobile else "residential", is_mobile=mobile)
        conns.append(conn(ip, 60 + i))
    return geo_map, conns


@pytest.mark.asyncio
async def test_mass_sharing_survives_one_mobile_address():
    """Живой случай: один мобильный адрес среди восьми сетей обнулял нарушение целиком."""
    geo_map, conns = _crowd(8, mobile_every=8)
    res = await run_check(make_detector(geo_map, recent_violations=3), conns, devices=1)
    assert res.breakdown["temporal"].strong_sharing
    assert res.total >= 50.0


@pytest.mark.asyncio
async def test_crowd_of_operators_half_mobile_is_a_violation():
    """Скрин из чата: шестнадцать адресов из шестнадцати сетей, половина мобильных."""
    geo_map, conns = _crowd(16, mobile_every=2)
    res = await run_check(make_detector(geo_map, recent_violations=3), conns, devices=1)
    assert res.total >= 50.0


@pytest.mark.asyncio
async def test_two_operators_stay_a_network_switch():
    """Домашний провайдер плюс мобильный — переключение сети, а не шаринг."""
    geo_map, conns = _crowd(2, mobile_every=2)
    res = await run_check(make_detector(geo_map, recent_violations=3), conns, devices=1)
    assert res.total < 50.0


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


# ── CGNAT: пул оператора считается источниками, а не адресами ──────

@pytest.mark.asyncio
async def test_cgnat_pool_does_not_look_like_sharing():
    """Жалоба из чата: CGNAT раздал одному клиенту пачку адресов.

    Двенадцать адресов МегаФона и двенадцать Билайна — по логам это был
    один человек, открывший соединения к одному хосту. По адресам детектор
    видел «24 разных», по источникам видит два.
    """
    geo_map = {}
    conns = []
    for i in range(2, 14):
        ip = f"178.177.22.{i}"
        geo_map[ip] = meta(ip, country_code="RU", city="Moscow", latitude=55.7, longitude=37.6,
                           asn=31133, asn_org="PJSC MegaFon", connection_type="residential")
        conns.append(conn(ip, 60 + i))
    for i in range(179, 191):
        ip = f"81.9.21.{i}"
        geo_map[ip] = meta(ip, country_code="RU", city="Moscow", latitude=55.7, longitude=37.6,
                           asn=16345, asn_org="PVimpelCom", connection_type="residential")
        conns.append(conn(ip, 60 + i))

    det = make_detector(geo_map, recent_violations=3)
    res = await run_check(det, conns, devices=2)

    assert res.breakdown["temporal"].score == 0.0, "два источника при двух устройствах — не шаринг"
    assert res.recommended_action.value in ("no_action", "monitor")


@pytest.mark.asyncio
async def test_real_sharing_through_hosting_still_caught():
    """Обратная сторона: у хостера соседние адреса — разные машины.

    Схлопывание там не применяется, иначе прокси-пул на одном /24
    превратился бы в «одного человека» и шаринг стал бы невидим.
    """
    geo_map = {}
    conns = []
    for i in range(1, 7):
        ip = f"5.9.10.{i}"
        geo_map[ip] = meta(ip, country_code="DE", city="Nuremberg", latitude=49.4, longitude=11.0,
                           asn=24940, asn_org="Hetzner Online GmbH", connection_type="hosting")
        conns.append(conn(ip, 60 + i))

    det = make_detector(geo_map, recent_violations=3)
    res = await run_check(det, conns, devices=1)

    assert res.breakdown["temporal"].score == 100.0, "шесть машин хостера — это шаринг"


@pytest.mark.asyncio
async def test_violation_text_names_sources_and_addresses():
    """Разбирать инцидент нужно по числам: сколько источников и сколько адресов."""
    geo_map = {}
    conns = []
    for i in range(1, 9):
        ip = f"178.177.22.{i}"
        geo_map[ip] = meta(ip, country_code="RU", city="Moscow", latitude=55.7, longitude=37.6,
                           asn=31133, asn_org="PJSC MegaFon", connection_type="residential")
        conns.append(conn(ip, 60 + i))
    # девятый адрес из чужой сети — источников станет два, порог при одном
    # устройстве это уже превышает
    geo_map["203.0.113.7"] = meta("203.0.113.7", country_code="RU", city="Moscow",
                                  latitude=55.7, longitude=37.6, asn=64500,
                                  asn_org="Some ISP", connection_type="fixed")
    conns.append(conn("203.0.113.7", 70))

    det = make_detector(geo_map, recent_violations=3)
    res = await run_check(det, conns, devices=1)

    reasons = " ".join(res.breakdown["temporal"].reasons)
    assert "источник" in reasons and "адрес" in reasons, reasons

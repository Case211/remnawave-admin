"""Карта в аналитике: область на карте по названию региона из GeoIP и разбивка /geo по регионам."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from shared.geo_regions import RU_REGIONS, has_region_map, locate, resolve_region
from web.backend.api.v2 import advanced_analytics as aa

GEO_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "geo"
GEO_DATA = GEO_DIR / "geo-data.json"
ALIASES = Path(__file__).resolve().parents[3] / "shared" / "assets" / "geo_regions.json"

# Названия, которые реально пишут MaxMind, ip-api и база ASN (выборка с живой панели)
OBSERVED = {
    "Moscow": "RU-MOW", "Москва": "RU-MOW", "Moscow Oblast": "RU-MOS", "St.-Petersburg": "RU-SPE",
    "Leningrad Oblast": "RU-LEN", "Tatarstan Republic": "RU-TA", "Bashkortostan Republic": "RU-BA",
    "Krasnodar Krai": "RU-KDA", "Stavropol Kray": "RU-STA", "Primorye": "RU-PRI", "Khabarovsk": "RU-KHA",
    "Kamchatka": "RU-KAM", "Transbaikal Territory": "RU-ZAB", "Sakha": "RU-SA", "Republic of Tyva": "RU-TY",
    "North Ossetia–Alania": "RU-SE", "Ingushetiya Republic": "RU-IN", "Kabardino-Balkariya Republic": "RU-KB",
    "Kalmykiya Republic": "RU-KL", "Khakasiya Republic": "RU-KK", "Udmurtiya Republic": "RU-UD",
    "Buryatiya Republic": "RU-BU", "Mariy-El Republic": "RU-ME", "Adygeya Republic": "RU-AD",
    "Khanty-Mansia": "RU-KHM", "Yamalo-Nenets": "RU-YAN", "Nenets": "RU-NEN", "Arkhangelskaya": "RU-ARK",
    "Murmansk": "RU-MUR", "Karelia": "RU-KR", "Komi": "RU-KO", "Oryol oblast": "RU-ORL",
    "Nizhny Novgorod Oblast": "RU-NIZ", "Chechnya": "RU-CE", "Dagestan": "RU-DA", "Altai Krai": "RU-ALT",
    "Crimea": "RU-CR",
}


@pytest.mark.parametrize("name,code", OBSERVED.items())
def test_observed_names(name, code):
    assert resolve_region("RU", name) == code


def test_every_official_name_resolves_to_its_subject():
    for code, names in RU_REGIONS.items():
        for name in names:
            assert resolve_region("ru", name) == code, name


def test_moscow_and_its_oblast_stay_apart():
    # Без родовых слов оба сводятся к «moscow» — такой ключ не должен работать
    assert resolve_region("RU", "Moscow City") == "RU-MOW"
    assert resolve_region("RU", "Московская обл.") == "RU-MOS"
    assert resolve_region("RU", "г. Москва") == "RU-MOW"


@pytest.mark.parametrize("name,code", [
    ("Ямало-Ненецкий АО", "RU-YAN"), ("Ханты-Мансийский АО", "RU-KHM"), ("Чукотский АО", "RU-CHU"),
    ("Пермский кр.", "RU-PER"), ("Забайкальский край", "RU-ZAB"),
])
def test_russian_abbreviations(name, code):
    # «й» сворачивается в «и» — родовые слова должны сворачиваться так же
    assert resolve_region("RU", name) == code


def test_unknown_regions():
    assert resolve_region("RU", None) is None
    assert resolve_region("RU", "") is None
    assert resolve_region("RU", "Atlantis Oblast") is None
    assert resolve_region("DE", "Moscow") is None
    assert resolve_region(None, "Moscow") is None
    assert resolve_region("VA", "Vatican") is None      # страна без регионов на карте
    assert not has_region_map("VA")


@pytest.mark.parametrize("cc,name,code", [
    ("DE", "Bavaria", "DE-BY"), ("DE", "Bayern", "DE-BY"), ("DE", "Hesse", "DE-HE"),
    ("NL", "North Holland", "NL-NH"), ("NL", "Limburg", "NL-LI"), ("FI", "Uusimaa", "FI-18"),
    ("CZ", "Prague", "CZ-PR"), ("CZ", "Usti nad Labem", "CZ-US"), ("US", "California", "US-CA"),
    ("TR", "İstanbul", "TR-34"), ("EE", "Harjumaa", "EE-37"),
    # Столица и одноимённая область у Natural Earth делят названия — разведены явно
    ("UA", "Kyiv City", "UA-30"), ("UA", "Kyiv Oblast", "UA-32"),
    ("BY", "Minsk City", "BY-HM"), ("BY", "Minsk", "BY-MI"),
    ("KZ", "Almaty", "KAZ-4829"), ("KZ", "Almaty Oblast", "KAZ-3207"),
    ("UZ", "Tashkent", "UZ-TK"), ("UZ", "Tashkent Region", "UZ-TO"),
    ("MX", "Mexico City", "MX-DIF"), ("MX", "México", "MX-MEX"),
    ("US", "Washington", "US-WA"), ("US", "District of Columbia", "US-DC"),
    ("AE", "Dubai", "AE-DU"), ("AU", "New South Wales", "AUS-2654"),
    # woe_name у NE переносит имя на соседей: без него Рига и Дублин находятся
    ("LV", "Riga", "LV-RIX"), ("IE", "Dublin", "IRL-5575"), ("MK", "Skopje", "MK-85"),
])
def test_other_countries_from_natural_earth(cc, name, code):
    assert has_region_map(cc)
    assert resolve_region(cc, name) == code


def test_codes_match_map_geometry():
    topo = json.loads(GEO_DATA.read_text(encoding="utf-8"))
    ids = {g["properties"]["id"] for g in topo["objects"]["regions"]["geometries"]}
    assert ids == set(RU_REGIONS)

    # Написания для бэкенда и геометрия стран собираются одним скриптом — id совпадают
    aliases = json.loads(ALIASES.read_text(encoding="utf-8"))
    files = {p.stem for p in (GEO_DIR / "countries").glob("*.json")}
    assert set(aliases) == files and "RU" not in files
    for cc in ("DE", "UA", "US"):
        topo = json.loads((GEO_DIR / "countries" / f"{cc}.json").read_text(encoding="utf-8"))
        assert {g["properties"]["id"] for g in topo["objects"]["regions"]["geometries"]} == set(aliases[cc])
    # Крым и Севастополь — субъекты РФ, у Украины их на карте нет
    assert {"RU-CR", "RU-SEV"} <= ids
    assert not {"UA-43", "UA-40"} & set(aliases["UA"])


@pytest.mark.parametrize("cc,name,expected", [
    # GeoIP отдаёт их Украине (написания с живой панели) — на карте они в России
    ("UA", "Crimea", ("RU", "RU-CR")), ("UA", "Sebastopol City", ("RU", "RU-SEV")),
    ("ua", "Republic of Crimea", ("RU", "RU-CR")),
    ("RU", "Crimea", ("RU", "RU-CR")), ("RU", "Севастополь", ("RU", "RU-SEV")),
    # Остальная Украина остаётся Украиной
    ("UA", "Kyiv City", ("UA", "UA-30")), ("UA", "Atlantis", ("UA", None)),
    (None, "Crimea", ("", None)),
])
def test_crimea_and_sevastopol_are_in_russia(cc, name, expected):
    assert locate(cc, name) == expected


class _Conn:
    def __init__(self, rows, nodes):
        self.rows, self.nodes = rows, nodes

    async def fetch(self, sql, *args):
        return self.nodes if "FROM nodes" in sql else self.rows


class _Db:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


def _row(uuid, region, city, ips, nodes, connections=1, country="RU", name="Russia"):
    return {
        "uuid": uuid, "username": f"user-{uuid}", "status": "ACTIVE",
        "city": city, "region": region, "country_name": name, "country_code": country,
        "latitude": 55.75, "longitude": 37.62, "connections": connections,
        "ips": ips, "nodes": nodes,
    }


@pytest.mark.asyncio
async def test_geo_groups_users_by_subject():
    rows = [
        # Один юзер под двумя написаниями Москвы — в субъекте он один
        _row("u1", "Moscow", "Moscow", ["1.1.1.1"], ["n1"], connections=5),
        _row("u1", "Москва", "Москва", ["1.1.1.2"], ["n2"], connections=3),
        _row("u2", "Moscow", "Moscow", ["1.1.1.3"], ["n1"]),
        _row("u3", "Moscow Oblast", "Ramenskoye", ["2.2.2.2"], None),
        # Регион не назван — не выдумываем, считаем отдельно
        _row("u4", None, None, ["3.3.3.3", "3.3.3.4"], ["n1"]),
        _row("u5", "Limburg", "Eygelshoven", ["4.4.4.4"], ["n1"], country="NL", name="The Netherlands"),
        # Другое имя той же страны у другого провайдера GeoIP
        _row("u6", "Tatarstan Republic", "Kazan", ["5.5.5.5"], ["n1"], name="Russian Federation"),
    ]
    nodes = [{"uuid": "n1", "name": "Москва — вход"}, {"uuid": "n2", "name": "Стокгольм"}]
    with patch.object(aa, "_db", return_value=_Db(_Conn(rows, nodes))):
        data = await aa._geo("7d", None, None, None)

    regions = {r["code"]: r for r in data["regions"]}
    assert set(regions) == {"RU-MOW", "RU-MOS", "RU-TA", "NL-LI"}
    mow = regions["RU-MOW"]
    assert mow["count"] == 2
    assert mow["unique_ips"] == 3
    assert mow["users"][0] == {"uuid": "u1", "username": "user-u1", "status": "ACTIVE", "connections": 8}
    assert mow["nodes"] == [
        {"uuid": "n1", "name": "Москва — вход", "count": 2},
        {"uuid": "n2", "name": "Стокгольм", "count": 1},
    ]
    assert regions["RU-MOS"]["nodes"] == []
    assert regions["RU-MOS"]["cities"] == [{"city": "Ramenskoye", "count": 1}]
    assert data["regions_unknown"] == [{"country_code": "RU", "count": 1, "unique_ips": 2}]

    countries = {c["country_code"]: c for c in data["countries"]}
    assert countries["RU"]["count"] == 5
    assert countries["NL"]["count"] == 1


@pytest.mark.asyncio
async def test_geo_counts_crimea_in_russia():
    rows = [
        _row("u1", "Crimea", "Simferopol", ["6.6.6.6"], ["n1"], country="UA", name="Ukraine"),
        _row("u2", "Sebastopol City", "Sevastopol", ["6.6.6.7"], ["n1"], country="UA", name="Ukraine"),
        _row("u3", "Kyiv City", "Kyiv", ["7.7.7.7"], ["n1"], country="UA", name="Ukraine"),
    ]
    with patch.object(aa, "_db", return_value=_Db(_Conn(rows, [{"uuid": "n1", "name": "Вход"}]))):
        data = await aa._geo("7d", None, None, None)

    countries = {c["country_code"]: c for c in data["countries"]}
    assert countries["RU"]["count"] == 2 and countries["RU"]["country"] == "Russia"
    assert countries["UA"]["count"] == 1
    assert {r["code"]: r["country_code"] for r in data["regions"]} == {
        "RU-CR": "RU", "RU-SEV": "RU", "UA-30": "UA",
    }
    assert {c["city"]: c["country"] for c in data["cities"]}["Simferopol"] == "Russia"


def test_node_breakdown_is_cut_after_scope_filter():
    nodes = [{"uuid": f"n{i}", "name": f"node {i}", "count": 100 - i} for i in range(15)]
    data = {"regions": [{"code": "RU-MOW", "nodes": nodes}]}
    assert len(aa._geo_visible_nodes(data, None)["regions"][0]["nodes"]) == 10
    # Нода админа — двенадцатая по числу юзеров, но он её видит
    assert aa._geo_visible_nodes(data, ["n12"])["regions"][0]["nodes"] == [nodes[12]]


def test_node_breakdown_respects_node_scope():
    data = {"countries": [], "cities": [], "regions_unknown": [], "regions": [
        {"code": "RU-MOW", "nodes": [{"uuid": "n1", "name": "a", "count": 2}, {"uuid": "n2", "name": "b", "count": 1}]},
    ]}
    assert aa._geo_visible_nodes(data, None)["regions"][0]["nodes"] == data["regions"][0]["nodes"]
    scoped = aa._geo_visible_nodes(data, ["n2"])
    assert scoped["regions"][0]["nodes"] == [{"uuid": "n2", "name": "b", "count": 1}]
    assert data["regions"][0]["nodes"][0]["uuid"] == "n1"   # кэш не тронут


@pytest.mark.asyncio
async def test_geo_endpoint_filters_nodes_for_scoped_admin(client):
    data = {"countries": [], "cities": [], "regions_unknown": [], "regions": [
        {"code": "RU-MOW", "country_code": "RU", "count": 1, "unique_ips": 1, "cities": [], "users": [],
         "nodes": [{"uuid": "n1", "name": "a", "count": 1}, {"uuid": "n2", "name": "b", "count": 1}]},
    ]}
    with patch.object(aa, "_user_scope", AsyncMock(return_value=None)), \
            patch.object(aa, "_node_scope", AsyncMock(return_value=["n1"])), \
            patch.object(aa, "_compute_geo", AsyncMock(return_value=data)):
        resp = await client.get("/api/v2/analytics/advanced/geo?period=7d")
    assert resp.status_code == 200, resp.text
    assert [n["uuid"] for n in resp.json()["regions"][0]["nodes"]] == ["n1"]

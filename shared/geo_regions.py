"""Регион для карты в аналитике: id области на карте по названию региона из GeoIP.

Названия приходят вразнобой: MaxMind и ip-api пишут по-английски, причём
каждый по-своему («Moscow Oblast», «St.-Petersburg», «Primorye»,
«Transbaikal Territory»), локальная база ASN — по-русски («Москва»).
Сопоставляем по нормализованному имени. Не узнали — регион неизвестен:
по координатам не угадываем, у адреса без региона MaxMind ставит точку
в центре страны, и такие юзеры все оказались бы в одной области.

Субъекты РФ — вручную ниже (коды ISO 3166-2). Крым и Севастополь — тоже
субъекты РФ (RU-CR, RU-SEV), как фактически; GeoIP отдаёт их Украине, и
``locate`` переносит такие адреса в Россию. Остальные страны — из
shared/assets/geo_regions.json: его пишет вместе с геометрией карты
web/frontend/scripts/build-geo.mjs (написания из Natural Earth, в том числе
имена GeoNames — их отдаёт MaxMind), так что id совпадают с картой.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Tuple

# Код → известные написания. Первым — английское название, вторым — русское;
# дальше варианты из MaxMind GeoLite2, ip-api, ipwho.is и базы ASN.
RU_REGIONS: Dict[str, Tuple[str, ...]] = {
    "RU-AD": ("Adygea", "Адыгея", "Republic of Adygea", "Adygeya Republic", "Adygeya", "Республика Адыгея"),
    "RU-AL": ("Altai Republic", "Республика Алтай", "Altay Republic", "Gorno-Altay", "Altai Rep"),
    "RU-ALT": ("Altai Krai", "Алтайский край", "Altay Krai", "Altai Territory", "Altayskiy Kray"),
    "RU-AMU": ("Amur Oblast", "Амурская область", "Amurskaya Oblast"),
    "RU-ARK": ("Arkhangelsk Oblast", "Архангельская область", "Arkhangelskaya", "Arkhangel'sk Oblast"),
    "RU-AST": ("Astrakhan Oblast", "Астраханская область", "Astrakhanskaya Oblast"),
    "RU-BA": ("Bashkortostan", "Башкортостан", "Bashkortostan Republic", "Republic of Bashkortostan",
              "Bashkiria", "Республика Башкортостан", "Башкирия"),
    "RU-BEL": ("Belgorod Oblast", "Белгородская область"),
    "RU-BRY": ("Bryansk Oblast", "Брянская область"),
    "RU-BU": ("Buryatia", "Бурятия", "Buryatiya Republic", "Republic of Buryatia", "Республика Бурятия"),
    "RU-CE": ("Chechnya", "Чечня", "Chechen Republic", "Chechnya Republic", "Чеченская Республика"),
    "RU-CHE": ("Chelyabinsk Oblast", "Челябинская область"),
    "RU-CHU": ("Chukotka", "Чукотский автономный округ", "Chukotka Autonomous Okrug",
               "Chukotskiy Avtonomnyy Okrug", "Чукотка"),
    "RU-CR": ("Crimea", "Республика Крым", "Republic of Crimea", "Autonomous Republic of Crimea", "Krym",
              "Respublika Krym", "Avtonomna Respublika Krym", "Крым"),
    "RU-CU": ("Chuvashia", "Чувашия", "Chuvash Republic", "Chuvashiya", "Чувашская Республика"),
    "RU-DA": ("Dagestan", "Дагестан", "Republic of Dagestan", "Республика Дагестан"),
    "RU-IN": ("Ingushetia", "Ингушетия", "Ingushetiya Republic", "Republic of Ingushetia",
              "Республика Ингушетия"),
    "RU-IRK": ("Irkutsk Oblast", "Иркутская область"),
    "RU-IVA": ("Ivanovo Oblast", "Ивановская область"),
    "RU-KAM": ("Kamchatka Krai", "Камчатский край", "Kamchatka"),
    "RU-KB": ("Kabardino-Balkaria", "Кабардино-Балкария", "Kabardino-Balkariya Republic",
              "Kabardino-Balkarian Republic", "Кабардино-Балкарская Республика"),
    "RU-KC": ("Karachay-Cherkessia", "Карачаево-Черкесия", "Karachayevo-Cherkesiya Republic",
              "Karachay-Cherkess Republic", "Карачаево-Черкесская Республика"),
    "RU-KDA": ("Krasnodar Krai", "Краснодарский край", "Krasnodarskiy Kray", "Kuban"),
    "RU-KEM": ("Kemerovo Oblast", "Кемеровская область", "Kuzbass", "Кузбасс"),
    "RU-KGD": ("Kaliningrad Oblast", "Калининградская область"),
    "RU-KGN": ("Kurgan Oblast", "Курганская область"),
    "RU-KHA": ("Khabarovsk Krai", "Хабаровский край", "Khabarovsk", "Khabarovskiy Kray"),
    "RU-KHM": ("Khanty-Mansi Autonomous Okrug", "Ханты-Мансийский автономный округ", "Khanty-Mansia",
               "Khanty-Mansiysk", "Yugra", "Khanty-Mansiyskiy Avtonomnyy Okrug-Yugra",
               "Ханты-Мансийский автономный округ — Югра", "Югра", "ХМАО"),
    "RU-KIR": ("Kirov Oblast", "Кировская область"),
    "RU-KK": ("Khakassia", "Хакасия", "Khakasiya Republic", "Republic of Khakassia", "Республика Хакасия"),
    "RU-KL": ("Kalmykia", "Калмыкия", "Kalmykiya Republic", "Republic of Kalmykia", "Республика Калмыкия"),
    "RU-KLU": ("Kaluga Oblast", "Калужская область"),
    "RU-KO": ("Komi Republic", "Республика Коми", "Komi", "Коми"),
    "RU-KOS": ("Kostroma Oblast", "Костромская область"),
    "RU-KR": ("Karelia", "Карелия", "Republic of Karelia", "Республика Карелия"),
    "RU-KRS": ("Kursk Oblast", "Курская область"),
    "RU-KYA": ("Krasnoyarsk Krai", "Красноярский край", "Krasnoyarskiy Kray"),
    "RU-LEN": ("Leningrad Oblast", "Ленинградская область", "Leningradskaya Oblast'"),
    "RU-LIP": ("Lipetsk Oblast", "Липецкая область"),
    "RU-MAG": ("Magadan Oblast", "Магаданская область"),
    "RU-ME": ("Mari El", "Марий Эл", "Mariy-El Republic", "Mari El Republic", "Республика Марий Эл"),
    "RU-MO": ("Mordovia", "Мордовия", "Mordoviya Republic", "Republic of Mordovia", "Республика Мордовия"),
    "RU-MOS": ("Moscow Oblast", "Московская область", "Moskovskaya Oblast", "Подмосковье"),
    "RU-MOW": ("Moscow", "Москва", "Moskva", "Moscow City", "город Москва"),
    "RU-MUR": ("Murmansk Oblast", "Мурманская область", "Murmansk"),
    "RU-NEN": ("Nenets Autonomous Okrug", "Ненецкий автономный округ", "Nenets", "Nenetskiy Avtonomnyy Okrug"),
    "RU-NGR": ("Novgorod Oblast", "Новгородская область"),
    "RU-NIZ": ("Nizhny Novgorod Oblast", "Нижегородская область", "Nizhegorodskaya Oblast"),
    "RU-NVS": ("Novosibirsk Oblast", "Новосибирская область"),
    "RU-OMS": ("Omsk Oblast", "Омская область"),
    "RU-ORE": ("Orenburg Oblast", "Оренбургская область"),
    "RU-ORL": ("Oryol Oblast", "Орловская область", "Orel Oblast", "Orlovskaya Oblast"),
    "RU-PER": ("Perm Krai", "Пермский край", "Perm", "Permskiy Kray"),
    "RU-PNZ": ("Penza Oblast", "Пензенская область"),
    "RU-PRI": ("Primorsky Krai", "Приморский край", "Primorye", "Primorskiy (Maritime) Kray",
               "Primorskiy Krai", "Приморье"),
    "RU-PSK": ("Pskov Oblast", "Псковская область"),
    "RU-ROS": ("Rostov Oblast", "Ростовская область"),
    "RU-RYA": ("Ryazan Oblast", "Рязанская область"),
    "RU-SA": ("Sakha (Yakutia)", "Якутия", "Sakha", "Sakha Republic", "Yakutia",
              "Republic of Sakha (Yakutia)", "Республика Саха (Якутия)", "Республика Саха"),
    "RU-SAK": ("Sakhalin Oblast", "Сахалинская область"),
    "RU-SAM": ("Samara Oblast", "Самарская область"),
    "RU-SAR": ("Saratov Oblast", "Саратовская область"),
    "RU-SE": ("North Ossetia–Alania", "Северная Осетия — Алания", "North Ossetia", "North Ossetia-Alania",
              "Republic of North Ossetia-Alania", "Республика Северная Осетия — Алания", "Северная Осетия"),
    "RU-SEV": ("Sevastopol", "Севастополь", "Sevastopol City", "City of Sevastopol", "Sebastopol",
               "Sebastopol City", "Misto Sevastopol", "город Севастополь"),
    "RU-SMO": ("Smolensk Oblast", "Смоленская область"),
    "RU-SPE": ("Saint Petersburg", "Санкт-Петербург", "St.-Petersburg", "St Petersburg", "Sankt-Peterburg",
               "Petersburg", "Петербург"),
    "RU-STA": ("Stavropol Krai", "Ставропольский край", "Stavropol Kray", "Stavropol'skiy Kray"),
    "RU-SVE": ("Sverdlovsk Oblast", "Свердловская область"),
    "RU-TA": ("Tatarstan", "Татарстан", "Tatarstan Republic", "Republic of Tatarstan", "Республика Татарстан"),
    "RU-TAM": ("Tambov Oblast", "Тамбовская область"),
    "RU-TOM": ("Tomsk Oblast", "Томская область"),
    "RU-TUL": ("Tula Oblast", "Тульская область"),
    "RU-TVE": ("Tver Oblast", "Тверская область"),
    "RU-TY": ("Tuva", "Тыва", "Republic of Tyva", "Tyva Republic", "Tuva Republic", "Республика Тыва", "Тува"),
    "RU-TYU": ("Tyumen Oblast", "Тюменская область"),
    "RU-UD": ("Udmurtia", "Удмуртия", "Udmurtiya Republic", "Udmurt Republic", "Удмуртская Республика"),
    "RU-ULY": ("Ulyanovsk Oblast", "Ульяновская область"),
    "RU-VGG": ("Volgograd Oblast", "Волгоградская область"),
    "RU-VLA": ("Vladimir Oblast", "Владимирская область"),
    "RU-VLG": ("Vologda Oblast", "Вологодская область"),
    "RU-VOR": ("Voronezh Oblast", "Воронежская область"),
    "RU-YAN": ("Yamalo-Nenets Autonomous Okrug", "Ямало-Ненецкий автономный округ", "Yamalo-Nenets",
               "Yamal-Nenets", "Yamalo-Nenetskiy Avtonomnyy Okrug", "ЯНАО"),
    "RU-YAR": ("Yaroslavl Oblast", "Ярославская область"),
    "RU-YEV": ("Jewish Autonomous Oblast", "Еврейская автономная область", "Yevreyskaya Avtonomnaya Oblast'",
               "Jewish Autonomous Region"),
    "RU-ZAB": ("Zabaykalsky Krai", "Забайкальский край", "Transbaikal Territory",
               "Zabaykalskiy (Transbaikal) Kray", "Zabaykalskiy Kray"),
}

_ASSET = Path(__file__).with_name("assets") / "geo_regions.json"

# Родовые слова: без них «Tomsk Oblast», «Томская обл.» и «Tomsk» сводятся
# к одному ключу. Если после выброса две области совпали (Москва и Московская
# область → «moscow»), такой ключ не используется. Слова записаны так, как их
# оставляет _norm: без диакритики, «й» → «и» («краи», «автономныи»).
_GENERIC = re.compile(
    r"\b(?:oblast|krai|kray|territory|republic|respublika|rep|autonomous|avtonomnyy|avtonomnaya|"
    r"okrug|region|province|federal|city|of|the|county|state|district|prefecture|department|"
    r"governorate|voivodeship|municipality|provincie|provincia|provinz|maakond|"
    r"область|обл|краи|кр|республика|респ|автономныи|автономная|округ|ао|город|г)\b"
)


def _norm(name: str) -> str:
    # Без диакритики: «Rīga» = «Riga», «Île-de-France» = «Ile-de-France» (й → и тоже — с обеих сторон)
    s = "".join(c for c in unicodedata.normalize("NFKD", name.lower()) if not unicodedata.combining(c))
    s = re.sub(r"[.'’ʼ`]", "", s)          # St.-Petersburg, Arkhangel'sk
    s = re.sub(r"[^\w]+", " ", s)          # дефисы, тире, скобки
    return " ".join(s.split())


def _strip(norm: str) -> str:
    return " ".join(_GENERIC.sub(" ", norm).split())


def _build(regions: Mapping[str, Iterable[str]]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Точные и «без родовых слов» ключи → id; ключ двух разных областей не годится."""
    exact: Dict[str, Optional[str]] = {}
    loose: Dict[str, Optional[str]] = {}
    for code, names in regions.items():
        for name in names:
            for table, key in ((exact, _norm(name)), (loose, _strip(_norm(name)))):
                if key:
                    table[key] = code if table.get(key, code) == code else None
    return ({k: v for k, v in exact.items() if v}, {k: v for k, v in loose.items() if v})


@lru_cache(maxsize=1)
def _assets() -> Dict[str, Dict[str, list]]:
    return json.loads(_ASSET.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _tables(country_code: str) -> Optional[Tuple[Dict[str, str], Dict[str, str]]]:
    if country_code == "RU":
        return _build(RU_REGIONS)
    regions = _assets().get(country_code)
    return _build(regions) if regions else None


def has_region_map(country_code: Optional[str]) -> bool:
    """Есть ли у страны карта регионов (во фронте и здесь)."""
    cc = (country_code or "").upper()
    return cc == "RU" or cc in _assets()


def resolve_region(country_code: Optional[str], region: Optional[str]) -> Optional[str]:
    """Id области на карте по стране и названию региона из GeoIP; None — не узнали."""
    if not region:
        return None
    tables = _tables((country_code or "").upper())
    if not tables:
        return None
    exact, loose = tables
    key = _norm(region)
    return exact.get(key) or loose.get(_strip(key))


# Субъекты РФ, которые GeoIP (MaxMind и др.) отдаёт Украине
_FROM_UA = frozenset({"RU-CR", "RU-SEV"})


def locate(country_code: Optional[str], region: Optional[str]) -> Tuple[str, Optional[str]]:
    """(Код страны, id области на карте) для адреса из GeoIP; id None — регион не узнали.

    Крым и Севастополь переносятся в Россию и на карте мира, и в субъектах —
    иначе юзеры оттуда считались бы в Украине.
    """
    cc = (country_code or "").upper()
    if cc == "UA":
        code = resolve_region("RU", region)
        if code in _FROM_UA:
            return "RU", code
    return cc, resolve_region(cc, region)

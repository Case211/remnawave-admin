"""Опознание сети абонента: мобильный оператор и «источник» подключения.

Детектор шаринга считал уникальные адреса — и на мобильных абонентах это
давало ложные срабатывания. У операторского CGNAT один клиент получает
разные публичные адреса из пула на каждое соединение: четыре потока к
одному хосту за полмиллисекунды приходят с четырёх разных IP. По адресам
это «четверо», по сути — один человек.

Здесь два ответа на эту беду:

1. :func:`is_mobile_network` — честный признак мобильной сети. Раньше он
   брался из ``connection_type``/``is_mobile`` метаданных GeoIP, но те
   почти всегда врут: у МТС из 39 393 известных адресов мобильными
   помечены три. Зато имя организации (``asn_org``) приходит нормальным —
   «MTS», «PJSC MegaFon», «T2 Mobile LLC», — и по нему оператор
   опознаётся уверенно.

2. :func:`source_key` — «источник» вместо адреса. Адреса одной сети,
   лежащие в одном узком префиксе, схлопываются в один источник: пул
   оператора перестаёт выглядеть толпой. Пороги детектора считаются по
   источникам, а число адресов остаётся в тексте нарушения, иначе
   разбирать инциденты будет нечем.

Хостинг, датацентры и VPN не схлопываются никогда: там соседние адреса —
это разные машины, и как раз в них живёт настоящий шаринг.
"""
from __future__ import annotations

import ipaddress
from typing import Any, Dict, Iterable, Optional, Tuple

#: Признаки операторского пула прямо в имени сети.
CGNAT_HINTS = ("cgnat", "lte", "gprs", "cellular", "mobile network", "мобильн")

#: Кэш списка операторов: geoip тянет за собой БД и MaxMind, поэтому
#: импортируем его лениво и только один раз.
_CARRIERS_CACHE: Optional[frozenset] = None


def _mobile_carriers() -> frozenset:
    """Имена мобильных операторов — из ``GeoIPService.MOBILE_CARRIERS``.

    Там уже собраны РФ, СНГ и мир, и на тот список есть тест. Свой второй
    список жил бы своей жизнью и неизбежно разошёлся бы с первым.
    """
    global _CARRIERS_CACHE
    if _CARRIERS_CACHE is None:
        try:
            from shared.geoip import GeoIPService

            _CARRIERS_CACHE = frozenset(GeoIPService.MOBILE_CARRIERS)
        except Exception:  # pragma: no cover — geoip недоступен в изоляции
            _CARRIERS_CACHE = frozenset()
    return _CARRIERS_CACHE

#: Типы сетей, где соседние адреса принадлежат разным машинам.
NON_COLLAPSIBLE_TYPES = frozenset({"hosting", "datacenter", "vpn"})

#: Типы, которые сами по себе означают мобильную сеть.
MOBILE_TYPES = frozenset({"mobile", "mobile_isp"})

#: Ширина сети, в пределах которой адреса считаются одним источником.
#: /24 закрывает типичный пул оператора и при этом не склеивает в одну
#: «личность» пол-региона: брать шире опасно — двое реально шарящих
#: абонентов одного оператора слились бы в одного.
DEFAULT_V4_PREFIX = 24
#: Абоненту IPv6 выдают /64 целиком, так что это его собственная сеть.
DEFAULT_V6_PREFIX = 64


def is_mobile_network(
    asn_org: Optional[str] = None,
    connection_type: Optional[str] = None,
) -> bool:
    """Мобильная ли это сеть (значит, за адресами может стоять CGNAT).

    ``connection_type`` спрашиваем первым, но не полагаемся на него: в
    ``ip_metadata`` он проставлен один раз при первой встрече адреса и с
    тех пор не пересматривался — у МТС из 39 393 известных адресов
    мобильными помечены три. Имя организации надёжнее.
    """
    if connection_type and connection_type.lower() in MOBILE_TYPES:
        return True
    if not asn_org:
        return False
    org = asn_org.lower()
    return any(carrier in org for carrier in _mobile_carriers()) or any(
        hint in org for hint in CGNAT_HINTS
    )


def is_collapsible(connection_type: Optional[str] = None) -> bool:
    """Можно ли схлопывать соседние адреса этой сети в один источник."""
    return not (connection_type and connection_type.lower() in NON_COLLAPSIBLE_TYPES)


def source_key(
    ip: str,
    asn: Optional[int] = None,
    asn_org: Optional[str] = None,
    connection_type: Optional[str] = None,
    *,
    v4_prefix: int = DEFAULT_V4_PREFIX,
    v6_prefix: int = DEFAULT_V6_PREFIX,
) -> str:
    """Ключ источника подключения — то, что детектор считает «одним местом».

    Возвращает либо ``asn:сеть`` (адреса одного пула склеиваются), либо сам
    адрес, если схлопывать нельзя или сеть непонятна. Ключ строковый и
    сравнимый — большего от него не требуется.
    """
    # Без ASN схлопывать нельзя: соседние адреса вполне могут принадлежать
    # разным провайдерам, и, склеив их, детектор ослеп бы ровно тогда, когда
    # GeoIP не ответил.
    if asn is None or not is_collapsible(connection_type):
        return ip
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        # Не адрес вовсе — пусть останется как есть, чем потеряется.
        return ip

    prefix = v6_prefix if address.version == 6 else v4_prefix
    network = ipaddress.ip_network(f"{address}/{prefix}", strict=False)
    # ASN в ключе обязателен: один и тот же /24 у разных операторов —
    # это разные сети.
    return f"{asn}:{network}"


def _meta_of(meta: Any) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """(asn, asn_org, connection_type) из метаданных любого вида."""
    if meta is None:
        return None, None, None
    if isinstance(meta, dict):
        return meta.get("asn"), meta.get("asn_org"), meta.get("connection_type")
    return (
        getattr(meta, "asn", None),
        getattr(meta, "asn_org", None),
        getattr(meta, "connection_type", None),
    )


def source_map(ips: Iterable[str], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """``адрес → ключ источника`` для набора адресов.

    Без метаданных каждый адрес остаётся сам себе источником: гадать по
    одному лишь виду адреса, чей это пул, нельзя.
    """
    metadata = metadata or {}
    out: Dict[str, str] = {}
    for ip in ips:
        if not ip:
            continue
        asn, asn_org, connection_type = _meta_of(metadata.get(ip))
        out[ip] = source_key(ip, asn, asn_org, connection_type)
    return out


def count_sources(ips: Iterable[str], metadata: Optional[Dict[str, Any]] = None) -> int:
    """Сколько независимых источников стоит за набором адресов."""
    mapping = source_map(ips, metadata)
    return len({mapping[ip] for ip in mapping})


def has_mobile_network(metadata: Optional[Dict[str, Any]]) -> bool:
    """Есть ли среди адресов хоть один из мобильной сети."""
    for meta in (metadata or {}).values():
        _, asn_org, connection_type = _meta_of(meta)
        if is_mobile_network(asn_org, connection_type):
            return True
    return False

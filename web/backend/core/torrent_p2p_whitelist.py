"""Отсев легального P2P из торрент-вердиктов.

nDPI опознаёт протокол, а не намерение. Игровые лаунчеры раздают обновления
по самому настоящему BitTorrent — Gaijin (War Thunder) первым делом, — и
вердикт по ним верный: это действительно torrent. Отличить такую раздачу от
пиратской качалки по трафику невозможно, различие только в том, КУДА идёт
обмен: у лаунчера это адреса самого издателя, у роя — случайные абоненты.

Поэтому фильтруем по организации-владельцу адреса. Сюда же попадают ложные
срабатывания эвристики на шифрованном потоке: пойманный случай — сервер
Kaspersky, которому приписали BitTorrent.
"""
from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)

#: Ключ настройки со списком маркеров (подстроки имени организации, через запятую).
SETTING_KEY = "torrent_asn_whitelist"

#: Кто раздаёт обновления по P2P или ловится эвристикой на шифрованном
#: потоке. Сравнение по вхождению и без регистра: имена организаций в базах
#: пишутся вразнобой («Kaspersky Lab Switzerland GmbH», «Valve Corp.»).
DEFAULT_MARKERS = (
    "kaspersky", "gaijin", "blizzard", "valve", "wargaming",
    "microsoft", "epic games", "riot games", "steam",
)


def markers() -> tuple[str, ...]:
    """Маркеры из настройки; пустая настройка — дефолтный список."""
    try:
        from shared.config_service import config_service

        raw = config_service.get(SETTING_KEY, "") or ""
    except Exception:
        logger.debug("torrent whitelist: настройка недоступна", exc_info=True)
        raw = ""
    custom = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    return custom or DEFAULT_MARKERS


def is_whitelisted_org(asn_org: str | None) -> bool:
    if not asn_org:
        return False
    org = asn_org.lower()
    return any(marker in org for marker in markers())


async def filter_destinations(destinations: Iterable[str]) -> list[str]:
    """Оставить адреса, которые НЕ принадлежат легальным P2P-раздачам.

    Адрес приходит как ``ip:port`` — в том же виде, в каком его пишет Xray.
    Резолв идёт только здесь, на последнем шаге перед нарушением: гонять
    geoip на каждое событие батча было бы дорого и незачем.
    """
    targets = [str(d) for d in destinations if d]
    if not targets:
        return []

    by_ip = {d: d.rsplit(":", 1)[0].strip("[]") for d in targets}
    try:
        from shared.geoip import get_geoip_service

        found = await get_geoip_service().lookup_batch(list(set(by_ip.values())))
    except Exception:
        # Без геобазы отсеивать нечем: пропускаем всё дальше, а не хороним
        # нарушение молча — ложный пропуск дешевле ложного обвинения только
        # тогда, когда мы знаем, кого пропускаем.
        logger.warning("torrent whitelist: geoip недоступен, фильтр пропущен", exc_info=True)
        return targets

    kept: list[str] = []
    for destination, ip in by_ip.items():
        info = found.get(ip)
        asn_org = getattr(info, "asn_org", None) if info else None
        if is_whitelisted_org(asn_org):
            logger.info("Torrent: адрес %s принадлежит %s — легальный P2P, пропускаем",
                        destination, asn_org)
            continue
        kept.append(destination)
    return kept

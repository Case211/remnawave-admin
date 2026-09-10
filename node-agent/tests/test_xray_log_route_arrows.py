"""Тег инбаунда не зависит от того, как Xray выбрал аутбаунд.

Xray пишет между тегами разные стрелки: `>>` — аутбаунд по умолчанию,
`->` / `==>` — выбран правилом роутинга, `=>` / `->` — балансером
(app/dispatcher/default.go, обозначения менялись между версиями). Раньше
парсер знал только `>>`, и у ноды, где весь трафик идёт по правилам
(каскады, WARP, блокировки), тег инбаунда терялся, а торрент-тег из
правила роутинга не распознавался.

    cd node-agent && python -m pytest
"""
import os

import pytest

os.environ.setdefault("AGENT_NODE_UUID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
os.environ.setdefault("AGENT_COLLECTOR_URL", "http://collector.test")
os.environ.setdefault("AGENT_AUTH_TOKEN", "token")

from src.collectors.xray_log import LOG_PATTERN_EXTENDED, _parse_lines

NODE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def line(detour, user="4", ip="91.79.39.214", dest="scontent-hel3-1.cdninstagram.com:443"):
    return "2026/09/10 18:00:50.618700 from %s:0 accepted tcp:%s [%s] email: %s" % (ip, dest, detour, user)


@pytest.mark.parametrize("detour, outbound", [
    ("Moscow CDN >> DIRECT", "DIRECT"),    # аутбаунд по умолчанию
    ("Moscow CDN -> casc-fi", "casc-fi"),  # правило роутинга (Xray 25.x–26.x)
    ("Moscow CDN ==> casc-fi", "casc-fi"), # правило роутинга (новее)
    ("Moscow CDN => casc-fi", "casc-fi"),  # балансер
    ("Moscow CDN->casc-fi", "casc-fi"),    # без пробелов
])
def test_inbound_tag_survives_any_arrow(detour, outbound):
    m = LOG_PATTERN_EXTENDED.search(line(detour))
    assert m is not None
    assert m.group(5) == "Moscow CDN"
    assert m.group(6) == outbound


def test_connection_keeps_inbound_tag_when_routed_by_rule():
    conns, torrents, _, accepted, matched = _parse_lines([line("Moscow CDN -> casc-fi")], NODE)
    assert accepted == matched == 1
    assert torrents == []
    assert len(conns) == 1
    assert conns[0].inbound_tag == "Moscow CDN"
    assert conns[0].user_email == "user_4"


def test_torrent_tag_detected_when_routed_by_rule():
    # Торрент-аутбаунд выбирается ТОЛЬКО правилом роутинга, значит в логе он
    # никогда не бывает с `>>` — до правки такие события не ловились вовсе.
    conns, torrents, _, _, _ = _parse_lines([line("inbound -> TORRENT", dest="tracker.example.com:6881")], NODE)
    assert conns == []
    assert len(torrents) == 1
    assert torrents[0].outbound_tag == "TORRENT"
    assert torrents[0].inbound_tag == "inbound"

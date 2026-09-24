"""Источник с префиксом сети: `from tcp:203.0.113.10:1334`.

Для подсоединений внутри mux-сессии Xray кладёт в AccessMessage.From не
net.Addr, а свой net.Destination (common/mux/server.go), и тот печатается с
сетью впереди: `tcp:203.0.113.10:1334`, `udp:…`, для IPv6 —
`tcp:[2001:db8::1]:1334`. В mux (XUDP) VLESS-клиент заворачивает UDP — с flow
Vision весь, без него всё, кроме портов 53 и 443
(proxy/vless/outbound/outbound.go), — так что на практике это строки с
UDP-целями вроде QUIC. Раньше шаблон источника префикса не допускал, и такая
строка не подходила ни под один паттерн — подключение терялось целиком.

    cd node-agent && python -m pytest
"""
import os

import pytest

os.environ.setdefault("AGENT_NODE_UUID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
os.environ.setdefault("AGENT_COLLECTOR_URL", "http://collector.test")
os.environ.setdefault("AGENT_AUTH_TOKEN", "token")

from src.collectors.xray_log import LOG_PATTERN_BASIC, LOG_PATTERN_EXTENDED, _parse_lines

NODE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def line(source, detour="[Sweden1 >> DIRECT] "):
    return "2026/09/19 10:50:02.095960 from %s accepted udp:198.51.100.7:443 %semail: 42" % (source, detour)


SOURCES = [
    ("203.0.113.10:1334", "203.0.113.10"),      # прежний формат
    ("[2001:db8::1]:1334", "2001:db8::1"),      # прежний формат, IPv6
    ("tcp:203.0.113.10:1334", "203.0.113.10"),  # mux/XUDP поверх TCP-инбаунда
    ("udp:203.0.113.10:1334", "203.0.113.10"),  # то же поверх UDP-инбаунда
    ("tcp:[2001:db8::1]:1334", "2001:db8::1"),
]


@pytest.mark.parametrize("source, ip", SOURCES)
def test_extended_pattern_takes_ip_without_network_prefix(source, ip):
    m = LOG_PATTERN_EXTENDED.search(line(source))
    assert m is not None
    assert m.group(2) == ip
    assert m.group(3) == "1334"
    assert m.group(5) == "Sweden1"


@pytest.mark.parametrize("source, ip", SOURCES)
def test_basic_pattern_takes_ip_without_network_prefix(source, ip):
    m = LOG_PATTERN_BASIC.search(line(source, detour=""))  # строка без скобок роутинга
    assert m is not None
    assert m.group(2) == ip
    assert m.group(3) == "1334"


def test_prefixed_and_plain_lines_are_one_connection():
    # Один человек с одного адреса: обычная строка и строка с префиксом должны
    # сойтись в один ключ (user, ip) — иначе в админке это два разных IP.
    conns, torrents, _, accepted, matched = _parse_lines(
        [line("203.0.113.10:1334"), line("tcp:203.0.113.10:1335")], NODE,
    )
    assert accepted == matched == 2
    assert torrents == []
    assert len(conns) == 1
    assert conns[0].ip_address == "203.0.113.10"
    assert conns[0].user_email == "user_42"
    assert conns[0].inbound_tag == "Sweden1"

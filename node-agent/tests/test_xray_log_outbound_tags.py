"""Агент передаёт аутбаунды, которые Xray выбрал для подключения.

Вторая половина скобок `[inbound -> outbound]` в access.log раньше разбиралась
и выбрасывалась: наверх уходил только тег инбаунда. За кусок лога один
пользователь уходит в несколько веток сразу, поэтому аутбаунды копятся
множеством и отдаются отсортированным списком.

    cd node-agent && python -m pytest
"""
import os

os.environ.setdefault("AGENT_NODE_UUID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
os.environ.setdefault("AGENT_COLLECTOR_URL", "http://collector.test")
os.environ.setdefault("AGENT_AUTH_TOKEN", "token")

from src.collectors.xray_log import _parse_lines
from src.models import ConnectionReport

NODE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def line(detour, t="18:00:50.618700", user="4", ip="91.79.39.214", dest="example.com:443"):
    return "2026/09/10 %s from %s:0 accepted tcp:%s [%s] email: %s" % (t, ip, dest, detour, user)


def basic(t="18:00:59.000000", user="4", ip="91.79.39.214"):
    return "2026/09/10 %s from %s:0 accepted tcp:example.com:443 email: %s" % (t, ip, user)


def test_outbounds_accumulate_sorted_and_unique():
    conns, _, _, _, _ = _parse_lines([
        line("Moscow CDN -> casc-fi", t="18:00:50.000000"),
        line("Moscow CDN >> DIRECT", t="18:00:51.000000"),
        line("Moscow CDN -> casc-fi", t="18:00:49.000000"),   # раньше и с повтором
    ], NODE)
    assert len(conns) == 1
    assert conns[0].outbound_tags == ["DIRECT", "casc-fi"]
    assert conns[0].inbound_tag == "Moscow CDN"


def test_outbounds_are_per_user_and_ip():
    conns, _, _, _, _ = _parse_lines([
        line("in -> warp-out", ip="91.79.39.214"),
        line("in >> DIRECT", ip="10.20.30.40"),
        line("in -> BLOCK", user="5"),
    ], NODE)
    got = {(c.user_email, c.ip_address): c.outbound_tags for c in conns}
    assert got == {
        ("user_4", "91.79.39.214"): ["warp-out"],
        ("user_4", "10.20.30.40"): ["DIRECT"],
        ("user_5", "91.79.39.214"): ["BLOCK"],
    }


def test_line_without_tags_keeps_inbound_and_outbounds():
    # Базовый regex тегов не знает: более поздняя строка обновляет время,
    # но не затирает то, что уже известно о подключении.
    conns, _, _, _, _ = _parse_lines([line("Moscow CDN -> casc-fi"), basic()], NODE)
    assert len(conns) == 1
    assert conns[0].inbound_tag == "Moscow CDN"
    assert conns[0].outbound_tags == ["casc-fi"]
    assert conns[0].connected_at.second == 59


def test_torrent_outbound_is_not_a_connection_outbound():
    conns, torrents, _, _, _ = _parse_lines([
        line("in >> DIRECT"),
        line("in -> TORRENT", dest="tracker.example.com:6881"),
    ], NODE)
    assert len(torrents) == 1
    assert conns[0].outbound_tags == ["DIRECT"]


class _Oracle:
    def __init__(self, dest):
        self.dest = dest

    def is_torrent(self, destination):
        return destination == self.dest


def test_ndpi_candidate_returned_to_connections_keeps_its_outbound():
    # Два человека ходили к одному адресу — обвинять некого, кандидаты
    # возвращаются в обычные подключения и не теряют выбранный аутбаунд.
    dest = "cdn.example.com:443"
    conns, torrents, _, _, _ = _parse_lines([
        line("in -> warp-out", user="4", dest=dest),
        line("in >> DIRECT", user="5", dest=dest),
    ], NODE, torrent_oracle=_Oracle(dest))
    assert torrents == []
    assert {c.user_email: c.outbound_tags for c in conns} == {"user_4": ["warp-out"], "user_5": ["DIRECT"]}


def test_report_without_outbounds_defaults_to_empty_list():
    r = ConnectionReport(user_email="user_1", ip_address="1.2.3.4", node_uuid=NODE,
                         connected_at="2026-09-10T18:00:50")
    assert r.outbound_tags == []

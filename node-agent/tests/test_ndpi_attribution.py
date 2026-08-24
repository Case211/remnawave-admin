"""Связка вердикта nDPI с пользователем.

Вердикт висит на адресе назначения, а за популярным адресом стоит не один
человек — здесь проверяется, что обвинение не размазывается по всем.

    cd node-agent && python -m pytest
"""
import os

os.environ.setdefault("AGENT_NODE_UUID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
os.environ.setdefault("AGENT_COLLECTOR_URL", "http://collector.test")
os.environ.setdefault("AGENT_AUTH_TOKEN", "token")

from src.collectors.xray_log import _parse_lines

NODE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class Oracle:
    """Окно вердиктов: отвечает «да» на перечисленные адреса."""

    def __init__(self, *destinations):
        self._destinations = set(destinations)

    def is_torrent(self, destination):
        return destination in self._destinations


def line(user, client_ip, destination, at="2026/08/24 18:03:14"):
    return (
        "%s from %s:51234 accepted tcp:%s [inbound >> direct] email: %s"
        % (at, client_ip, destination, user)
    )


def parse(lines, oracle):
    return _parse_lines(lines, NODE, torrent_oracle=oracle)


class TestNdpiAttribution:
    def test_single_user_on_address_is_accused(self):
        connections, events, *_ = parse(
            [line("101", "10.0.0.1", "203.0.113.7:51413")],
            Oracle("203.0.113.7:51413"),
        )
        assert [e.user_email for e in events] == ["user_101"]
        assert [e.detected_by for e in events] == ["ndpi"]
        assert connections == []

    def test_address_shared_by_two_users_accuses_nobody(self):
        """Адрес мессенджера: один вердикт не делает нарушителями обоих."""
        connections, events, *_ = parse(
            [
                line("101", "10.0.0.1", "57.144.105.33:443"),
                line("202", "10.0.0.2", "57.144.105.33:443"),
            ],
            Oracle("57.144.105.33:443"),
        )
        assert events == []
        assert sorted(c.user_email for c in connections) == ["user_101", "user_202"]

    def test_shared_address_does_not_hide_the_other_one(self):
        """Общий адрес отброшен, а личный пир того же юзера — засчитан."""
        connections, events, *_ = parse(
            [
                line("101", "10.0.0.1", "57.144.105.33:443"),
                line("202", "10.0.0.2", "57.144.105.33:443"),
                line("101", "10.0.0.1", "198.51.100.9:6881"),
            ],
            Oracle("57.144.105.33:443", "198.51.100.9:6881"),
        )
        assert [e.destination for e in events] == ["198.51.100.9:6881"]

    def test_xray_tag_is_not_affected_by_the_rule(self):
        """Тег роутинга стоит на самом соединении — привязка точная."""
        tagged = (
            "2026/08/24 18:03:14 from 10.0.0.1:51234 accepted tcp:57.144.105.33:443 "
            "[inbound >> TORRENT] email: 101"
        )
        _, events, *_ = parse([tagged, line("202", "10.0.0.2", "57.144.105.33:443")], Oracle("57.144.105.33:443"))
        assert [(e.user_email, e.detected_by) for e in events] == [("user_101", "xray_routing")]

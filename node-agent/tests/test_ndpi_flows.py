"""Разбор вердиктов nDPI: что считается торрентом, а что нет.

Гоняется в наборе агента — пакет здесь зовётся ``src`` и в одном процессе
с тестами бэкенда конкурировал бы за это имя:

    cd node-agent && python -m pytest
"""
import json
import os

os.environ.setdefault("AGENT_NODE_UUID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
os.environ.setdefault("AGENT_COLLECTOR_URL", "http://collector.test")
os.environ.setdefault("AGENT_AUTH_TOKEN", "token")

from src.collectors.ndpi_flows import (
    NdpiTorrentWatcher,
    confidence_of,
    destination_of,
    is_torrent,
    iter_messages,
)


def verdict(proto, *, name="detected", confidence="DPI", dst="1.2.3.4", port=6881):
    """Сообщение nDPIsrvd в том виде, в каком его шлёт живой демон."""
    ndpi = {"proto": proto}
    if confidence is not None:
        ndpi["confidence"] = {"6": confidence}
    return {"flow_event_name": name, "dst_ip": dst, "dst_port": port, "ndpi": ndpi}


def framed(event):
    body = (json.dumps(event) + chr(10)).encode()
    return b"%05d" % len(body) + body


class TestIsTorrent:
    def test_plain_verdict_counts(self):
        assert is_torrent(verdict("BitTorrent"))

    def test_dns_lookup_of_tracker_does_not_count(self):
        """DNS.BitTorrent — спрошенное имя трекера, обмена по нему ещё не было."""
        assert not is_torrent(verdict("DNS.BitTorrent", dst="1.1.1.1", port=53))

    def test_encrypted_lookup_does_not_count(self):
        """Тот же резолв, только через DoH: адрес и порт выглядят как HTTPS."""
        assert not is_torrent(verdict("DoH_DoT.BitTorrent", dst="1.1.1.1", port=443))

    def test_torrent_over_tls_does_not_count(self):
        """TLS.BitTorrent — соединение с трекером по HTTPS, обмена ещё нет.

        На проде такие вердикты прилетали на адреса Meta и делали
        нарушителями всех, кто в это окно туда ходил.
        """
        assert not is_torrent(verdict("TLS.BitTorrent", dst="57.144.105.33", port=443))

    def test_guess_does_not_count(self):
        assert not is_torrent(verdict("BitTorrent", confidence="Match by port"))
        assert not is_torrent(verdict("BitTorrent", confidence="Match by IP"))
        assert not is_torrent(verdict("BitTorrent", confidence="Guessed"))

    def test_first_packet_has_no_verdict_yet(self):
        assert not is_torrent(verdict("BitTorrent", name="new"))

    def test_verdict_without_confidence_counts(self):
        """nDPId постарше поля не шлёт — отбрасывать такие вердикты нельзя."""
        assert is_torrent(verdict("BitTorrent", confidence=None))

    def test_torrent_as_master_counts(self):
        assert is_torrent(verdict("BitTorrent.Gnutella"))

    def test_web_ports_are_not_peers(self):
        """443/80/5222 — это веб и мессенджеры, пиров там не бывает."""
        assert not is_torrent(verdict("BitTorrent", port=443))
        assert not is_torrent(verdict("BitTorrent", port=80))
        assert not is_torrent(verdict("BitTorrent", port=5222))

    def test_privileged_ports_are_not_peers(self):
        """Ниже 1024 нужен root на той стороне — торрент-клиенты так не делают."""
        assert not is_torrent(verdict("BitTorrent", port=554))
        assert not is_torrent(verdict("BitTorrent", port=477))

    def test_high_ports_count(self):
        assert is_torrent(verdict("BitTorrent", port=51413))
        assert is_torrent(verdict("BitTorrent", port=27607))

    def test_unknown_port_is_not_a_reason_to_drop(self):
        event = verdict("BitTorrent")
        event.pop("dst_port")
        assert is_torrent(event)

    def test_other_protocols_ignored(self):
        assert not is_torrent(verdict("TLS"))
        assert not is_torrent(verdict("DNS", port=53))


class TestFields:
    def test_confidence_from_object(self):
        assert confidence_of(verdict("BitTorrent")) == "dpi"

    def test_confidence_absent(self):
        assert confidence_of({"ndpi": {"proto": "BitTorrent"}}) == ""

    def test_destination_matches_xray_format(self):
        assert destination_of(verdict("BitTorrent", dst="5.6.7.8", port=51413)) == "5.6.7.8:51413"

    def test_destination_needs_both_halves(self):
        assert destination_of({"dst_ip": "5.6.7.8"}) is None


class TestFraming:
    def test_reads_messages_and_keeps_unfinished_tail(self):
        stream = framed(verdict("BitTorrent")) + framed(verdict("TLS")) + b"001"
        events, rest = iter_messages(stream)
        assert [e["ndpi"]["proto"] for e in events] == ["BitTorrent", "TLS"]
        assert rest == b"001"

    def test_broken_prefix_drops_buffer(self):
        events, rest = iter_messages(b"xxxxx{}")
        assert list(events) == []
        assert rest == b""


class TestWindow:
    def test_verdict_expires_with_window(self):
        watcher = NdpiTorrentWatcher("/tmp/nonexistent.sock", window_seconds=30)
        watcher.remember("1.2.3.4:6881", at=100.0)
        assert watcher.is_torrent("1.2.3.4:6881", at=120.0)
        assert not watcher.is_torrent("1.2.3.4:6881", at=140.0)

    def test_unknown_destination(self):
        watcher = NdpiTorrentWatcher("/tmp/nonexistent.sock")
        assert not watcher.is_torrent("9.9.9.9:6881", at=1.0)
        assert not watcher.is_torrent("", at=1.0)

"""Вердикты nDPI в агенте: разбор сокета, окно и связка с пользователем.

Xray ставит тег TORRENT только на открытое рукопожатие BitTorrent —
шифрованный поток, DHT и uTP проходят мимо. nDPI их видит, но не знает,
чей это клиент: трафик он наблюдает уже после NAT, от имени ноды. Связка
делается по адресу назначения, который есть и у него, и в логе Xray.
"""
import json
import sys
from pathlib import Path

import pytest

# Агент живёт отдельным пакетом и в панель не импортируется — добавляем
# его каталог в путь, как это делает сам агент при запуске.
AGENT_ROOT = Path(__file__).resolve().parents[3] / "node-agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src.collectors.ndpi_flows import (  # noqa: E402
    NdpiTorrentWatcher,
    destination_of,
    is_torrent,
    iter_messages,
    protocol_of,
)


def frame(event: dict) -> bytes:
    """Сообщение в том виде, в каком его шлёт nDPIsrvd."""
    payload = json.dumps(event).encode() + b"\n"
    return f"{len(payload):05d}".encode() + payload


TORRENT_FLOW = {
    "flow_event_name": "detected",
    "src_ip": "10.0.0.5", "src_port": 44321,
    "dst_ip": "203.0.113.9", "dst_port": 51413,
    "l4_proto": "tcp",
    "ndpi.proto": "BitTorrent",
    "ndpi.category": "Download-FileTransfer-FileSharing",
}


# ── разбор потока ─────────────────────────────────────────────────

def test_message_is_read_whole():
    events, rest = iter_messages(frame(TORRENT_FLOW))
    events = list(events)
    assert len(events) == 1
    assert events[0]["ndpi.proto"] == "BitTorrent"
    assert rest == b""


def test_several_messages_in_one_chunk():
    chunk = frame(TORRENT_FLOW) + frame({"flow_event_name": "end", "ndpi.proto": "TLS"})
    events, rest = iter_messages(chunk)
    assert len(list(events)) == 2 and rest == b""


def test_half_message_waits_for_the_rest():
    """Сокет режет поток где попало — недочитанное должно дожидаться."""
    whole = frame(TORRENT_FLOW)
    events, rest = iter_messages(whole[:20])
    assert list(events) == []
    events, rest = iter_messages(rest + whole[20:])
    assert len(list(events)) == 1 and rest == b""


def test_broken_length_prefix_drops_buffer():
    # После сломанного префикса границы сообщений неизвестны — читать
    # дальше нечего, буфер сбрасывается целиком.
    events, rest = iter_messages(b"xxxxx{}")
    assert list(events) == [] and rest == b""


def test_unreadable_message_does_not_break_the_stream():
    garbage = b"00006" + b"nojson"
    events, rest = iter_messages(garbage + frame(TORRENT_FLOW))
    assert len(list(events)) == 1, "следующее сообщение должно прочитаться"


# ── что считаем торрентом ─────────────────────────────────────────

def test_torrent_detected_by_protocol_name():
    assert is_torrent(TORRENT_FLOW) is True


def test_nested_protocol_object_also_understood():
    event = {"flow_event_name": "detected", "ndpi": {"proto": "BitTorrent"}}
    assert protocol_of(event) == "BitTorrent"
    assert is_torrent(event) is True


def test_torrent_must_be_the_protocol_of_the_flow():
    """У составного «master.app» сам поток — это master, а app лишь то, к
    чему он относится. `TLS.BitTorrent` — соединение с трекером по HTTPS,
    `DNS.BitTorrent` — спрошенное имя: обмена не было ни там, ни там. Пока
    такие вердикты считались, на проде за один поток к адресу Meta
    нарушителями становились все, кто в то же окно туда ходил.
    """
    assert is_torrent({"flow_event_name": "update", "ndpi.proto": "TLS.BitTorrent"}) is False
    assert is_torrent({"flow_event_name": "update", "ndpi.proto": "DNS.BitTorrent"}) is False
    assert is_torrent({"flow_event_name": "update", "ndpi.proto": "BitTorrent.Gnutella"}) is True


def test_other_protocols_are_not_torrent():
    for proto in ("TLS", "HTTP", "QUIC", "WireGuard"):
        assert is_torrent({"flow_event_name": "detected", "ndpi.proto": proto}) is False, proto


def test_new_flow_verdict_is_ignored():
    """На первом пакете протокол ещё не определён — это не вердикт."""
    assert is_torrent({"flow_event_name": "new", "ndpi.proto": "BitTorrent"}) is False


def test_destination_matches_xray_log_format():
    assert destination_of(TORRENT_FLOW) == "203.0.113.9:51413"
    assert destination_of({"dst_ip": "1.1.1.1"}) is None


# ── окно вердиктов ────────────────────────────────────────────────

def test_verdict_lives_inside_the_window_and_expires():
    watcher = NdpiTorrentWatcher("/tmp/none.sock", window_seconds=60)
    watcher.remember("203.0.113.9:51413", at=100.0)

    assert watcher.is_torrent("203.0.113.9:51413", at=130.0) is True
    assert watcher.is_torrent("203.0.113.9:51413", at=200.0) is False


def test_repeated_verdict_refreshes_the_window():
    watcher = NdpiTorrentWatcher("/tmp/none.sock", window_seconds=60)
    watcher.remember("203.0.113.9:51413", at=100.0)
    watcher.remember("203.0.113.9:51413", at=150.0)
    # Первая запись протухла, вторая ещё жива — адрес не должен пропасть.
    assert watcher.is_torrent("203.0.113.9:51413", at=190.0) is True


def test_unknown_destination_is_not_torrent():
    watcher = NdpiTorrentWatcher("/tmp/none.sock", window_seconds=60)
    assert watcher.is_torrent("198.51.100.1:443") is False
    assert watcher.is_torrent("") is False


# ── связка с пользователем ────────────────────────────────────────

class _Oracle:
    """Заглушка nDPI: знает про один адрес."""

    def __init__(self, destination: str) -> None:
        self.destination = destination

    def is_torrent(self, destination: str, at=None) -> bool:
        return destination == self.destination


LOG_LINE = (
    "2026/08/17 05:12:33.123456 from 10.0.0.5:44321 accepted tcp:203.0.113.9:51413 "
    "[vless_tls >> direct] email: 42"
)


def test_ndpi_verdict_turns_a_plain_line_into_a_torrent_event():
    """Соединение без тега TORRENT, но с вердиктом nDPI — это торрент.

    Именно так выглядит шифрованный BitTorrent: Xray видит обычный поток,
    роутинг тега не ставит, и без второго источника событие терялось.
    """
    from src.collectors.xray_log import _parse_lines

    connections, torrent_events, *_ = _parse_lines(
        [LOG_LINE], "node-1", torrent_tag="TORRENT",
        torrent_oracle=_Oracle("203.0.113.9:51413"),
    )

    assert len(torrent_events) == 1
    event = torrent_events[0]
    assert event.user_email == "user_42"
    assert event.destination == "203.0.113.9:51413"
    assert event.detected_by == "ndpi"
    # Событие ушло в торренты и не задваивается обычным подключением
    assert connections == []


def test_without_oracle_line_stays_an_ordinary_connection():
    from src.collectors.xray_log import _parse_lines

    connections, torrent_events, *_ = _parse_lines([LOG_LINE], "node-1")
    assert torrent_events == []
    assert len(connections) == 1


def test_xray_tag_still_wins_and_is_marked_as_such():
    from src.collectors.xray_log import _parse_lines

    tagged = LOG_LINE.replace(">> direct]", ">> TORRENT]")
    _, torrent_events, *_ = _parse_lines([tagged], "node-1", torrent_tag="TORRENT")

    assert len(torrent_events) == 1
    assert torrent_events[0].detected_by == "xray_routing"
    assert torrent_events[0].outbound_tag == "TORRENT"


# ── включение из панели ───────────────────────────────────────────

def test_command_shape_matches_agent_contract():
    """Панель шлёт ровно то, что агент разбирает."""
    from web.backend.core import ndpi_rollout
    from src.command_runner import ALLOWED_COMMAND_TYPES

    command = ndpi_rollout.build_command(True)
    assert command["type"] in ALLOWED_COMMAND_TYPES
    assert command["enabled"] is True
    # Путь сокета и окно остаются на ноде: у разных нод они могут
    # отличаться, и панели незачем это знать.
    assert set(command) == {"type", "enabled"}


@pytest.mark.asyncio
async def test_agent_answers_with_state_not_just_ok(monkeypatch):
    """Ответ должен отличать «работает» от «включено, но демона нет».

    Иначе тумблер в панели врёт: чтение сокета включается всегда, а
    nDPId на ноде может быть не установлен.
    """
    from src.command_runner import CommandRunner

    sent = []

    async def _send(msg):
        sent.append(msg)
        return True

    async def _control(enabled, socket_path=None, window_seconds=None):
        return {"enabled": enabled, "connected": False, "socket_path": "/tmp/x.sock"}

    class _Settings:
        ws_secret_key = ""
        auth_token = ""

    runner = CommandRunner(_Settings(), _send, ndpi_control=_control)
    monkeypatch.setattr("src.command_runner.verify_signature", lambda *a, **k: True)

    await runner.handle({"type": "set_ndpi", "enabled": True, "command_id": "c1", "_sig": "x"})

    assert len(sent) == 1
    assert sent[0]["status"] == "completed"
    assert "connected" in sent[0]["output"]


@pytest.mark.asyncio
async def test_agent_without_ndpi_support_answers_honestly(monkeypatch):
    from src.command_runner import CommandRunner

    sent = []

    async def _send(msg):
        sent.append(msg)
        return True

    class _Settings:
        ws_secret_key = ""
        auth_token = ""

    runner = CommandRunner(_Settings(), _send)  # без контроллера
    monkeypatch.setattr("src.command_runner.verify_signature", lambda *a, **k: True)

    await runner.handle({"type": "set_ndpi", "enabled": True, "command_id": "c2", "_sig": "x"})

    assert sent[0]["status"] == "error"


# ── демон внутри агента ───────────────────────────────────────────

def test_default_interface_is_the_one_with_default_route(tmp_path, monkeypatch):
    """Слушать надо интерфейс маршрута по умолчанию, а не «any».

    «any» у nDPId ловит в том числе loopback — разбирать собственный
    трафик агента незачем.
    """
    from src.collectors import ndpi_daemon

    route = tmp_path / "route"
    route.write_text(
        "Iface\tDestination\tGateway\tFlags\n"
        "lo\t0000007F\t00000000\t0001\n"
        "eth0\t00000000\t0100A8C0\t0003\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ndpi_daemon, "Path", lambda _p: route)
    assert ndpi_daemon.default_interface() == "eth0"


@pytest.mark.asyncio
async def test_daemon_says_plainly_when_binaries_are_missing(monkeypatch):
    """Агент старой сборки не должен делать вид, что всё включилось."""
    from src.collectors.ndpi_daemon import NdpiDaemon

    monkeypatch.setattr("src.collectors.ndpi_daemon.binaries_available", lambda: False)
    state = await NdpiDaemon("/tmp/none.sock", interface="eth0").start()

    assert state["started"] is False
    assert "образе" in state["reason"]


@pytest.mark.asyncio
async def test_daemon_needs_an_interface(monkeypatch):
    from src.collectors.ndpi_daemon import NdpiDaemon

    monkeypatch.setattr("src.collectors.ndpi_daemon.binaries_available", lambda: True)
    monkeypatch.setattr("src.collectors.ndpi_daemon.default_interface", lambda: None)
    state = await NdpiDaemon("/tmp/none.sock").start()

    assert state["started"] is False
    assert "интерфейс" in state["reason"]

"""Штрафы шейпера: разбор дампа карты и отправка событий панели.

    cd node-agent && python -m pytest
"""
import asyncio
import json
import os
import struct

os.environ.setdefault("AGENT_NODE_UUID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
os.environ.setdefault("AGENT_COLLECTOR_URL", "http://collector.test")
os.environ.setdefault("AGENT_AUTH_TOKEN", "token")

from unittest.mock import AsyncMock, MagicMock

import pytest

from src import shaper
from src.command_runner import CommandRunner


def dump(*entries):
    """Вывод `bpftool -j map dump`: ключ и значение — списки байтов «0x..»."""
    items = []
    for ip, start, until, total in entries:
        key = shaper.client_key(ip)
        value = struct.pack("<3Q", start, until, total)
        items.append({"key": [f"0x{b:02x}" for b in key], "value": [f"0x{b:02x}" for b in value]})
    return json.dumps(items)


class TestParse:
    def test_monotonic_time_becomes_wall_time(self):
        now_mono, now_wall = 1_000 * 10**9, 1_700_000_000.0
        events = shaper.parse_penalties(
            dump(("1.2.3.4", 940 * 10**9, 1_840 * 10**9, 3 * 1024**3)), now_mono, now_wall)
        assert events == [{
            "ip": "1.2.3.4",
            "start_ns": 940 * 10**9,
            "started_at": now_wall - 60,
            "until": now_wall + 840,
            "bytes": 3 * 1024**3,
        }]

    def test_ipv6_client_keeps_its_address(self):
        events = shaper.parse_penalties(dump(("2001:db8::7", 1, 2, 3)), 10, 100.0)
        assert events[0]["ip"] == "2001:db8::7"

    @pytest.mark.parametrize("output", ["", "not json", "{}", json.dumps([{"key": ["0xzz"]}])])
    def test_garbage_is_ignored(self, output):
        assert shaper.parse_penalties(output, 10, 100.0) == []


def runner(dump_output, penalty_mb=100):
    r = CommandRunner.__new__(CommandRunner)
    r._settings = MagicMock(host_mode=False)
    r._shaper_general = shaper.ShaperConfig(enabled=True, ports=(443,), penalty_mb=penalty_mb,
                                            penalty_window_sec=60, penalty_kbit=2000, penalty_minutes=5)
    r._shaper_personal = {}
    r._shaper_loaded = True
    r._penalties_seen = {}
    r._communicate = AsyncMock(return_value=(dump_output, 0))
    r._send = AsyncMock(return_value=True)
    return r


class TestCollect:
    @pytest.mark.asyncio
    async def test_nothing_is_read_while_penalty_mode_is_off(self):
        r = runner(dump(("1.2.3.4", 1, 2, 3)), penalty_mb=0)
        assert await r.collect_penalties() == []
        r._communicate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_event_is_reported_once(self):
        r = runner(dump(("1.2.3.4", 5 * 10**9, 10**15, 3)))
        shutdown = asyncio.Event()

        async def stop_after_two_rounds(msg):
            if r._send.await_count >= 1:
                shutdown.set()
            return True
        r._send.side_effect = stop_after_two_rounds

        task = asyncio.create_task(r.watch_penalties(shutdown, interval=0.01))
        await asyncio.sleep(0.1)
        shutdown.set()
        await task

        assert r._send.await_count == 1
        message = r._send.await_args.args[0]
        assert message["type"] == "shaper_penalties"
        assert message["events"][0]["ip"] == "1.2.3.4"
        assert await r.collect_penalties() == []

    @pytest.mark.asyncio
    async def test_unsent_event_is_tried_again(self):
        """Связь оборвалась — событие не теряется, уйдёт в следующий раз."""
        r = runner(dump(("1.2.3.4", 5 * 10**9, 10**15, 3)))
        r._send = AsyncMock(return_value=False)
        shutdown = asyncio.Event()

        task = asyncio.create_task(r.watch_penalties(shutdown, interval=0.01))
        await asyncio.sleep(0.05)
        shutdown.set()
        await task

        assert r._send.await_count >= 2
        assert len(await r.collect_penalties()) == 1

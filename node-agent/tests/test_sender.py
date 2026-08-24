"""Тесты отправки батчей: сжатие, дробление на куски, деградация на старый коллектор.

Гоняются отдельно от остальных наборов — пакет агента называется ``src``
и в одном процессе с тестами бота или бэкенда конкурировал бы за это имя:

    cd node-agent && python -m pytest
"""
import os

os.environ.setdefault("AGENT_NODE_UUID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
os.environ.setdefault("AGENT_COLLECTOR_URL", "http://collector.test")
os.environ.setdefault("AGENT_AUTH_TOKEN", "token")

import gzip
import json
from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from src.config import Settings
from src.models import ConnectionReport, SystemMetrics
from src.sender import CollectorSender

NODE_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def make_settings(**overrides) -> Settings:
    defaults = {"send_chunk_gap_seconds": 0.0}
    defaults.update(overrides)
    return Settings(**defaults)


def make_connections(count: int) -> list[ConnectionReport]:
    return [
        ConnectionReport(
            user_email=f"user_{i}",
            ip_address=f"10.0.{i // 256}.{i % 256}",
            node_uuid=NODE_UUID,
            connected_at=datetime(2026, 8, 23, 5, 0, 0),
        )
        for i in range(count)
    ]


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("POST", "http://collector.test"),
                response=self,  # type: ignore[arg-type]
            )


class TestEncode:
    def test_large_body_is_compressed(self):
        sender = CollectorSender(make_settings())
        payload = {"connections": [{"user_email": f"user_{i}"} for i in range(500)]}

        body, headers = sender._encode(payload)

        assert headers["Content-Encoding"] == "gzip"
        assert json.loads(gzip.decompress(body)) == payload
        assert len(body) < len(json.dumps(payload))

    def test_small_body_stays_plain(self):
        sender = CollectorSender(make_settings())

        body, headers = sender._encode({"connections": []})

        assert "Content-Encoding" not in headers
        assert json.loads(body) == {"connections": []}

    def test_compression_is_skipped_once_collector_refused(self):
        sender = CollectorSender(make_settings())
        sender._gzip_ok = False
        payload = {"connections": [{"user_email": f"user_{i}"} for i in range(500)]}

        _, headers = sender._encode(payload)

        assert "Content-Encoding" not in headers


class TestGzipFallback:
    @pytest.mark.asyncio
    async def test_switches_to_plain_json_when_collector_rejects_gzip(self):
        """Коллектор старее агента отвечает 415 — агент дошлёт то же несжатым."""
        sender = CollectorSender(make_settings(send_gzip_min_bytes=1))
        seen: list[bool] = []

        async def post(url, content=None, headers=None):
            compressed = "Content-Encoding" in (headers or {})
            seen.append(compressed)
            return _FakeResponse(415 if compressed else 200)

        client = AsyncMock()
        client.post = post
        sender._get_client = AsyncMock(return_value=client)

        assert await sender.send_batch(make_connections(3)) is True
        assert seen == [True, False]
        assert sender._gzip_ok is False


class TestSendInChunks:
    @pytest.mark.asyncio
    async def test_splits_by_chunk_size(self):
        sender = CollectorSender(make_settings(send_chunk_size=2))
        sender.send_batch = AsyncMock(return_value=True)

        sent, _ = await sender.send_in_chunks(make_connections(5))

        assert sent == 5
        assert sender.send_batch.await_count == 3
        assert [len(c.args[0]) for c in sender.send_batch.await_args_list] == [2, 2, 1]

    @pytest.mark.asyncio
    async def test_metrics_ride_only_with_first_chunk(self):
        """Метрики относятся к моменту съёма — дублировать их по кускам незачем."""
        sender = CollectorSender(make_settings(send_chunk_size=2))
        sender.send_batch = AsyncMock(return_value=True)

        await sender.send_in_chunks(make_connections(4), system_metrics=SystemMetrics())

        with_metrics = [
            c.kwargs["system_metrics"] is not None
            for c in sender.send_batch.await_args_list
        ]
        assert with_metrics == [True, False]

    @pytest.mark.asyncio
    async def test_reports_progress_when_a_chunk_fails(self):
        """Обрыв на середине стоит остатка, а не всего накопленного."""
        sender = CollectorSender(make_settings(send_chunk_size=2))
        sender.send_batch = AsyncMock(side_effect=[True, False, True])

        sent, _ = await sender.send_in_chunks(make_connections(6))

        assert sent == 2
        assert sender.send_batch.await_count == 2

    @pytest.mark.asyncio
    async def test_metrics_without_connections_still_go(self):
        sender = CollectorSender(make_settings(send_chunk_size=2))
        sender.send_batch = AsyncMock(return_value=True)

        sent, _ = await sender.send_in_chunks([], system_metrics=SystemMetrics())

        assert sent == 0
        assert sender.send_batch.await_count == 1

    @pytest.mark.asyncio
    async def test_nothing_counted_when_first_chunk_fails(self):
        sender = CollectorSender(make_settings(send_chunk_size=2))
        sender.send_batch = AsyncMock(return_value=False)

        sent, events = await sender.send_in_chunks(make_connections(4), torrent_events=[])

        assert (sent, events) == (0, 0)

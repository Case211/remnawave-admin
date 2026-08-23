"""
Отправка батчей подключений в Collector API (Web Backend).
"""
import asyncio
import gzip
import json
import logging
from datetime import datetime, timezone

import httpx

from .config import Settings
from .models import BatchReport, ConnectionReport, NetworkMetrics, SystemMetrics, TorrentEvent

logger = logging.getLogger(__name__)


class CollectorSender:
    """HTTP-клиент для отправки данных в Collector."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._url = f"{settings.collector_url.rstrip('/')}/api/v2/collector/batch"
        self._health_url = f"{settings.collector_url.rstrip('/')}/api/v2/collector/health"
        self._headers = {"Authorization": f"Bearer {settings.auth_token}"}
        self._client: httpx.AsyncClient | None = None
        # Коллектор старее агента сжатия не понимает. Узнаём это по первому
        # отказу и дальше шлём как есть — агент не должен требовать, чтобы
        # панель обновили раньше него.
        self._gzip_ok: bool = True

    async def _get_client(self) -> httpx.AsyncClient:
        """Возвращает переиспользуемый httpx клиент."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers=self._headers,
                limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
            )
        return self._client

    async def close(self) -> None:
        """Закрывает HTTP клиент. Вызывать при завершении работы."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _encode(self, payload: dict) -> tuple[bytes, dict[str, str]]:
        """Тело запроса и заголовки к нему.

        Батч подключений — это одни и те же ключи, соседние адреса и близкие
        отметки времени, поэтому gzip снимает с него примерно 11-кратный
        объём. На мелких телах выигрыш не окупает процессор, там шлём как есть.
        """
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if self._gzip_ok and len(raw) >= self.settings.send_gzip_min_bytes:
            return gzip.compress(raw, 6), {
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
            }
        return raw, {"Content-Type": "application/json"}

    async def check_connectivity(self) -> bool:
        """Проверяет связь с Collector API при старте."""
        try:
            client = await self._get_client()
            resp = await client.get(self._health_url)
            resp.raise_for_status()
            logger.info("Collector API OK: %s", self._health_url)
            return True
        except Exception as e:
            logger.warning("Collector API unreachable: %s", e)
            return False

    async def send_batch(
        self,
        connections: list[ConnectionReport],
        torrent_events: list[TorrentEvent] | None = None,
        system_metrics: SystemMetrics | None = None,
        network_metrics: NetworkMetrics | None = None,
    ) -> bool:
        """Отправить батч подключений, торрент-событий и метрик. Возвращает True при успехе."""
        if not connections and not system_metrics and not torrent_events:
            return True

        from .version import AGENT_VERSION

        report = BatchReport(
            node_uuid=self.settings.node_uuid,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
            connections=connections,
            torrent_events=torrent_events or [],
            system_metrics=system_metrics,
            network_metrics=network_metrics,
            agent_version=AGENT_VERSION,
        )
        payload = report.model_dump(mode="json")
        body, headers = self._encode(payload)

        for attempt in range(1, self.settings.send_max_retries + 1):
            try:
                client = await self._get_client()
                resp = await client.post(self._url, content=body, headers=headers)
                resp.raise_for_status()
                # Любой 2xx после raise_for_status = успех
                logger.debug("Batch sent: %d connections, %s metrics",
                             len(connections), "with" if system_metrics else "no")
                return True
            except httpx.HTTPStatusError as e:
                if (
                    self._gzip_ok
                    and "Content-Encoding" in headers
                    and e.response.status_code in (400, 415, 422)
                ):
                    # Коллектор не разобрал сжатое тело — он старее агента.
                    # Пересобираем без сжатия и пробуем сразу, без паузы.
                    self._gzip_ok = False
                    body, headers = self._encode(payload)
                    logger.info(
                        "Collector rejected gzip (%s), switching to plain JSON",
                        e.response.status_code,
                    )
                    continue
                logger.warning(
                    "Collector %s (attempt %d/%d)",
                    e.response.status_code, attempt, self.settings.send_max_retries,
                )
            except Exception as e:
                logger.warning(
                    "Send failed (attempt %d/%d): %s",
                    attempt, self.settings.send_max_retries, e,
                )

            if attempt < self.settings.send_max_retries:
                await asyncio.sleep(self.settings.send_retry_delay_seconds)

        logger.error("Batch failed after %d attempts (%d connections lost)",
                      self.settings.send_max_retries, len(connections))
        return False

    async def send_in_chunks(
        self,
        connections: list[ConnectionReport],
        torrent_events: list[TorrentEvent] | None = None,
        system_metrics: SystemMetrics | None = None,
        network_metrics: NetworkMetrics | None = None,
    ) -> tuple[int, int]:
        """Отправить накопленное кусками по ``send_chunk_size``.

        Возвращает, сколько подключений и торрент-событий коллектор принял —
        считая с начала списков. Куски подтверждаются по отдельности, поэтому
        обрыв на середине стоит остатка, а не всего накопленного: вызывающий
        выбрасывает из буфера ровно принятое и досылает хвост следующим витком.

        Метрики и торрент-события уезжают с первым куском: они относятся к
        моменту съёма, дробить их по кускам смысла нет.
        """
        chunk = max(1, self.settings.send_chunk_size)
        sent_connections = 0
        sent_events = 0
        first = True

        # max(len, 1) — пустой список подключений всё равно должен доехать
        # один раз, если с ним едут метрики или торрент-события.
        for start in range(0, max(len(connections), 1), chunk):
            part = connections[start:start + chunk]
            ok = await self.send_batch(
                part,
                torrent_events=torrent_events if first else None,
                system_metrics=system_metrics if first else None,
                network_metrics=network_metrics if first else None,
            )
            if not ok:
                break

            sent_connections += len(part)
            if first:
                sent_events = len(torrent_events or [])
                first = False
            if start + chunk < len(connections):
                await asyncio.sleep(self.settings.send_chunk_gap_seconds)

        return sent_connections, sent_events

"""
Отправка батчей подключений в Collector API (Web Backend).
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx

from .config import Settings
from .models import BatchReport, ConnectionReport, SystemMetrics

logger = logging.getLogger(__name__)


class CollectorSender:
    """HTTP-клиент для отправки данных в Collector."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._url = f"{settings.collector_url.rstrip('/')}/api/v2/collector/batch"
        self._health_url = f"{settings.collector_url.rstrip('/')}/api/v2/collector/health"
        self._headers = {"Authorization": f"Bearer {settings.auth_token}"}
        self._client: httpx.AsyncClient | None = None

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
        system_metrics: SystemMetrics | None = None,
    ) -> bool:
        """Отправить батч подключений и метрик. Возвращает True при успехе."""
        if not connections and not system_metrics:
            return True

        report = BatchReport(
            node_uuid=self.settings.node_uuid,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
            connections=connections,
            system_metrics=system_metrics,
        )
        payload = report.model_dump(mode="json")

        for attempt in range(1, self.settings.send_max_retries + 1):
            try:
                client = await self._get_client()
                resp = await client.post(self._url, json=payload)
                resp.raise_for_status()
                # Любой 2xx после raise_for_status = успех
                logger.info("Batch sent: %d connections, %s metrics",
                            len(connections), "with" if system_metrics else "no")
                return True
            except httpx.HTTPStatusError as e:
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

"""
Отправка батчей подключений в Collector API (Admin Bot).
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx

from .config import Settings
from .models import BatchReport, ConnectionReport

logger = logging.getLogger(__name__)


class CollectorSender:
    """HTTP-клиент для отправки данных в Collector."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._url = f"{settings.collector_url.rstrip('/')}/api/v1/connections/batch"
        self._health_url = f"{settings.collector_url.rstrip('/')}/api/v1/connections/health"
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
        """
        Проверяет связь с Collector API при старте.
        Возвращает True если API доступен.
        """
        try:
            client = await self._get_client()
            resp = await client.get(self._health_url)
            resp.raise_for_status()
            logger.info("Collector API connectivity check passed: %s", self._health_url)
            return True
        except Exception as e:
            logger.warning("Collector API connectivity check failed (%s): %s", self._health_url, e)
            return False

    async def send_batch(self, connections: list[ConnectionReport]) -> bool:
        """Отправить батч подключений. Возвращает True при успехе."""
        if not connections:
            return True

        report = BatchReport(
            node_uuid=self.settings.node_uuid,
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
            connections=connections,
        )
        payload = report.model_dump(mode="json")

        for attempt in range(1, self.settings.send_max_retries + 1):
            try:
                client = await self._get_client()
                resp = await client.post(self._url, json=payload)
                resp.raise_for_status()

                # Проверяем, что ответ не пустой и содержит JSON
                response_text = resp.text
                if not response_text or not response_text.strip():
                    logger.warning(
                        "Collector returned empty response on attempt %s (status %s)",
                        attempt,
                        resp.status_code
                    )
                    # Если статус 200 и ответ пустой, считаем успехом (может быть особенность API)
                    if resp.status_code == 200:
                        logger.info(
                            "Batch sent successfully: %s connections (empty response accepted)",
                            len(connections)
                        )
                        return True
                    continue

                try:
                    response_data = resp.json()
                    logger.info(
                        "Batch sent successfully: %s connections, response: %s",
                        len(connections),
                        response_data,
                    )
                    return True
                except ValueError:
                    logger.warning(
                        "Collector returned non-JSON response on attempt %s: %s (status %s)",
                        attempt,
                        response_text[:200],
                        resp.status_code
                    )
                    # Если статус 200, но не JSON - всё равно считаем успехом
                    if resp.status_code == 200:
                        logger.info(
                            "Batch sent successfully: %s connections (non-JSON response accepted)",
                            len(connections)
                        )
                        return True
                    continue
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "Collector returned %s on attempt %s: %s",
                    e.response.status_code,
                    attempt,
                    e.response.text[:500] if e.response.text else "(empty)",
                )
            except Exception as e:
                logger.warning("Send attempt %s failed: %s", attempt, e, exc_info=True)

            if attempt < self.settings.send_max_retries:
                await asyncio.sleep(self.settings.send_retry_delay_seconds)

        logger.error("Failed to send batch after %s attempts", self.settings.send_max_retries)
        return False

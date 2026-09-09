"""Свои серверы в мониторинге: связь = свежие метрики агента.

У ноды панели флаг is_connected ведёт панель. У внешнего сервера панели нет:
коллектор поднимает флаг каждым батчем с метриками (update_node_metrics),
а этот цикл опускает его, когда агент молчит дольше STALE_MINUTES — дальше
alert_engine и Fleet видят сервер офлайн так же, как ноду.
"""
import asyncio
import logging

from shared.database import db_service

logger = logging.getLogger(__name__)

STALE_MINUTES = 5
_TICK_SECONDS = 60


async def external_servers_sweep_loop() -> None:
    """Фоновый цикл: гасит is_connected у своих серверов без свежих метрик."""
    while True:
        try:
            await asyncio.sleep(_TICK_SECONDS)
            if not db_service.is_connected:
                continue
            marked = await db_service.mark_stale_external_nodes_offline(STALE_MINUTES)
            if marked:
                logger.info(
                    "External servers marked offline (agent silent > %d min): %d",
                    STALE_MINUTES, marked,
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("External servers sweep error: %s", e, exc_info=True)

"""Событие для вебхуков из любого процесса — бота, планировщиков, веб-бэкенда.

Доставкой занимается веб-бэкенд (webhook_security), а бот живёт в другом
процессе и до него не дотягивается. Событие кладётся в очередь доставки
webhook_retry_queue по одной строке на каждую активную подписку; воркер
веб-бэкенда разбирает её раз в несколько секунд — с подписью, ретраями и
журналом доставок, как у любого другого события.
"""
import json
import logging

logger = logging.getLogger(__name__)

# Столько попыток даёт и webhook_security (WEBHOOK_MAX_ATTEMPTS)
_MAX_ATTEMPTS = 3


async def enqueue_event(event: str, payload: dict) -> int:
    """Поставить событие в очередь доставки. Возвращает число подписок."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return 0
        async with db_service.acquire() as conn:
            result = await conn.execute(
                """
                INSERT INTO webhook_retry_queue (webhook_id, event, payload, attempt, max_attempts, next_try_at)
                SELECT id, $1, $2::jsonb, 1, $3, NOW()
                FROM webhook_subscriptions
                WHERE is_active = true AND $1 = ANY(events)
                """,
                event, json.dumps(payload, default=str), _MAX_ATTEMPTS,
            )
        return int(result.split()[-1]) if result else 0
    except Exception as e:
        logger.warning("enqueue_event(%s) failed: %s", event, e)
        return 0

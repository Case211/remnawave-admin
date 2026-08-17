"""Раскатка настройки nDPI на агенты нод.

Демон nDPId стоит на самой ноде, но включать его чтение через .env на
каждой ноде отдельно — работа руками там, где у нас уже есть канал команд.
Панель держит один тумблер и рассылает его состояние агентам: при
переключении — всем подключённым, при подключении агента — только ему
(иначе после перезапуска нода молча вернулась бы к прежнему поведению).

Ответ агента говорит больше, чем «принято»: чтение сокета можно включить
всегда, а вот демона на ноде может не быть вовсе. Панель должна отличать
«включено и работает» от «включено, но сокета нет», иначе тумблер врёт.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

#: Ключ настройки в bot_config.
SETTING_KEY = "ndpi_detection_enabled"


def _is_enabled() -> bool:
    try:
        from shared.config_service import config_service

        return bool(config_service.get(SETTING_KEY, False))
    except Exception:
        logger.debug("ndpi: настройка недоступна, считаем выключенной", exc_info=True)
        return False


def build_command(enabled: bool) -> dict:
    """Тело команды агенту. Путь сокета и окно остаются на стороне агента:
    у ноды они могут отличаться, и панели незачем это знать."""
    return {"type": "set_ndpi", "enabled": bool(enabled)}


async def push_to_node(node_uuid: str, token: str, enabled: Optional[bool] = None) -> bool:
    """Отправить состояние одному агенту. ``token`` нужен для подписи."""
    from web.backend.core.agent_hmac import sign_command_with_ts
    from web.backend.core.agent_manager import agent_manager

    state = _is_enabled() if enabled is None else enabled
    payload, signature = sign_command_with_ts(build_command(state), token)
    payload["_sig"] = signature
    return await agent_manager.send_command(node_uuid, payload)


async def push_to_all(enabled: Optional[bool] = None) -> int:
    """Разослать состояние всем подключённым агентам; вернуть число отправок.

    Токен у каждой ноды свой, поэтому подпись собирается на каждую
    отдельно. Нода без токена пропускается: подписать команду нечем, а
    неподписанную агент справедливо отвергнет.
    """
    from shared.database import db_service
    from web.backend.core.agent_manager import agent_manager

    state = _is_enabled() if enabled is None else enabled
    sent = 0
    for node_uuid in list(agent_manager.connected_nodes()):
        token = None
        try:
            async with db_service.acquire() as conn:
                token = await conn.fetchval(
                    "SELECT agent_token FROM nodes WHERE uuid = $1::uuid", node_uuid
                )
        except Exception:
            logger.warning("ndpi: не удалось получить токен ноды %s", node_uuid, exc_info=True)
        if not token:
            continue
        if await push_to_node(node_uuid, token, state):
            sent += 1
    logger.info("ndpi: настройка (%s) разослана на %d агентов", state, sent)
    return sent

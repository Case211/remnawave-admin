"""Раскладка ограничений скорости по нодам.

Ограничение вешается на адрес пользователя правилами tc, а адреса он меняет
часто — медиана четыре за сутки. Поэтому правила не ставятся один раз, а
пересобираются по живым подключениям: появился новый адрес — уехал на ту
ноду, где человек сейчас сидит.

Ноде отправляется её полный список, целиком заменяющий прежний. Из этого
следует главное: слать нужно и пустые списки — иначе снятое ограничение
останется висеть на ноде навсегда.
"""
import asyncio
import json
import logging
from typing import Dict, List

from shared.config_service import config_service
from shared.database import db_service
from shared.db_query import select_sql
from shared.db_schema import NODES_TABLE

logger = logging.getLogger(__name__)

_TICK_SECONDS = 60

# Что каждой ноде уже отправлено: {node_uuid: отпечаток списка}. Применение
# правил снимает и заново ставит корневую дисциплину интерфейса, а это
# кратковременно задевает весь трафик ноды — дёргать её незачем, пока список
# не изменился.
_pushed: Dict[str, str] = {}


def _fingerprint(rules: List[dict]) -> str:
    return json.dumps(sorted((r["ip"], r["rate_kbit"]) for r in rules), separators=(",", ":"))


def forget_node(node_uuid: str) -> None:
    """Забыть отправленное: агент переподключился и мог потерять правила."""
    _pushed.pop(node_uuid, None)


async def push_throttles(only_node: str | None = None) -> int:
    """Разослать ограничения подключённым агентам. Возвращает число нод, которым ушло."""
    from web.backend.core.agent_manager import agent_manager
    from web.backend.core.agent_hmac import sign_command_with_ts

    try:
        by_node = await db_service.get_throttle_rules_by_node()
    except Exception as e:
        logger.warning("Failed to collect throttle rules: %s", e)
        return 0

    connected = agent_manager.connected_nodes()
    targets = [only_node] if only_node else list(connected)

    sent = 0
    for node_uuid in targets:
        if node_uuid not in connected:
            continue
        rules = by_node.get(node_uuid, [])
        mark = _fingerprint(rules)
        if _pushed.get(node_uuid) == mark:
            continue

        try:
            async with db_service.acquire() as conn:
                row = await conn.fetchrow(
                    select_sql(NODES_TABLE, "agent_token", "WHERE uuid = $1"), node_uuid
                )
            if not row or not row["agent_token"]:
                continue

            cmd = {"type": "sync_throttled_ips", "rules": rules}
            payload, sig = sign_command_with_ts(cmd, row["agent_token"])
            payload["_sig"] = sig
            if await agent_manager.send_command(node_uuid, payload):
                _pushed[node_uuid] = mark
                sent += 1
        except Exception as e:
            logger.warning("Failed to push throttles to %s: %s", node_uuid, e)

    if sent:
        total = sum(len(v) for v in by_node.values())
        # Пустой список при подключении агента — рутина, а не событие:
        # после рестарта панели так отчитывается каждая нода
        log = logger.debug if only_node and not total else logger.info
        log("Throttles pushed to %d node(s), %d address(es) total", sent, total)
    return sent


async def throttle_sync_loop() -> None:
    """Фоновый цикл: снимает истёкшие ограничения и догоняет сменившиеся адреса."""
    while True:
        try:
            await asyncio.sleep(_TICK_SECONDS)
            if not config_service.get("throttle_enabled", True):
                continue
            expired = await db_service.cleanup_expired_throttles()
            if expired:
                logger.info("Throttles expired and lifted: %d", expired)
            await push_throttles()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Throttle sync loop error: %s", e, exc_info=True)

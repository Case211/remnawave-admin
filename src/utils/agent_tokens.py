"""
Утилиты для работы с токенами Node Agent.

Токен агента — секретный ключ для аутентификации агента перед Collector API.
Каждая нода имеет свой уникальный токен, который генерируется в Admin Bot.
"""
import secrets
from typing import Optional

from src.services.database import DatabaseService
from src.utils.logger import logger


def generate_agent_token() -> str:
    """
    Генерирует новый токен агента (32 байта в hex = 64 символа).
    
    Пример: 'a1b2c3d4e5f6...' (64 символа)
    """
    return secrets.token_urlsafe(32)


async def get_node_by_token(db: DatabaseService, token: str) -> Optional[str]:
    """
    Находит node_uuid по токену агента.
    Возвращает UUID ноды или None если токен не найден/невалиден.
    """
    if not db.is_connected or not token:
        return None
    
    try:
        async with db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT uuid FROM nodes WHERE agent_token = $1",
                token
            )
            if row:
                return str(row["uuid"])
    except Exception as e:
        logger.error("Error looking up node by token: %s", e)
    
    return None


async def set_node_agent_token(
    db: DatabaseService,
    node_uuid: str,
    token: Optional[str] = None
) -> Optional[str]:
    """
    Устанавливает токен агента для ноды.
    
    Если token=None, генерирует новый токен.
    Возвращает установленный токен или None при ошибке.
    """
    if not db.is_connected:
        return None
    
    if token is None:
        token = generate_agent_token()
    
    try:
        async with db.acquire() as conn:
            await conn.execute(
                "UPDATE nodes SET agent_token = $1 WHERE uuid = $2",
                token,
                node_uuid
            )
            logger.info("Agent token set for node %s", node_uuid)
            return token
    except Exception as e:
        logger.error("Error setting agent token for node %s: %s", node_uuid, e)
        return None


async def revoke_node_agent_token(db: DatabaseService, node_uuid: str) -> bool:
    """
    Удаляет токен агента у ноды (отзывает доступ).
    """
    if not db.is_connected:
        return False
    
    try:
        async with db.acquire() as conn:
            await conn.execute(
                "UPDATE nodes SET agent_token = NULL WHERE uuid = $1",
                node_uuid
            )
            logger.info("Agent token revoked for node %s", node_uuid)
            return True
    except Exception as e:
        logger.error("Error revoking agent token for node %s: %s", node_uuid, e)
        return False

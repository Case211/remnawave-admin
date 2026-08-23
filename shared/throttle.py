"""Постановка и снятие «мягкой блокировки».

Мера состоит из двух половин, и обе живут здесь, чтобы бот, веб-API и
автоматика делали одно и то же:

* правило tc на ноде режет скорость к адресу пользователя;
* если настроен резервный сквад для нарушителей, человек переезжает туда.

Вторая половина обратима только при одном условии: прежний состав сквадов
нужно запомнить ДО переключения. Панель хранит лишь текущий, и без снимка
снять наказание было бы некуда — пользователь остался бы в резервном сквадe
навсегда.

Раскладку правил по нодам делает веб-бэкенд: WebSocket-каналы к агентам
держит он. Бот пишет решение в базу, и синхронизатор подхватывает его в
пределах минуты.
"""
import json
from datetime import datetime
from typing import List, Optional

from shared.config_service import config_service
from shared.database import db_service
from shared.logger import logger


def _squad_uuid() -> Optional[str]:
    """UUID резервного сквада для нарушителей. Пусто — сквады не трогаем."""
    value = config_service.get("throttle_squad_uuid", "") or ""
    value = str(value).strip()
    return value or None


async def _current_squads(user_uuid: str) -> Optional[List[str]]:
    """Сквады пользователя сейчас. None — если панель не ответила."""
    from shared.api_client import api_client
    from shared.data_access import resolve_panel_user_id

    try:
        panel_id = await resolve_panel_user_id(user_uuid)
        result = await api_client.get_user_by_id(panel_id)
        user = result.get("response", result) if isinstance(result, dict) else {}
        squads = user.get("activeInternalSquads") or []
        # Панель отдаёт то объекты сквадов, то голые uuid — берём и так, и так.
        return [s.get("uuid") if isinstance(s, dict) else str(s) for s in squads]
    except Exception as e:
        logger.warning("Cannot read squads of %s: %s", user_uuid, e)
        return None


async def _set_squads(user_uuid: str, squads: List[str]) -> bool:
    from shared.api_client import api_client
    from shared.data_access import resolve_panel_user_id

    try:
        panel_id = await resolve_panel_user_id(user_uuid)
        await api_client.update_user(uuid=panel_id, active_internal_squads=squads)
        return True
    except Exception as e:
        logger.warning("Cannot move %s between squads: %s", user_uuid, e)
        return False


async def apply_throttle(
    user_uuid: str,
    rate_kbit: int,
    reason: Optional[str] = None,
    admin_id: Optional[int] = None,
    admin_username: Optional[str] = None,
    until: Optional[datetime] = None,
) -> tuple:
    """Урезать скорость и, если настроено, увести в резервный сквад.

    Returns:
        (success: bool, error: Optional[str], moved: bool)
    """
    squad = _squad_uuid()
    prev_squads: Optional[List[str]] = None
    moved = False

    if squad:
        prev_squads = await _current_squads(user_uuid)
        if prev_squads is not None and prev_squads != [squad]:
            moved = await _set_squads(user_uuid, [squad])
            if not moved:
                # Скорость всё равно урежем: половина меры лучше, чем ничего,
                # а неудачный переезд не должен отменять решение админа.
                logger.warning("Throttle for %s applied without squad move", user_uuid)
        elif prev_squads is not None:
            # Уже сидит в резервном — прежний состав перетирать нечем.
            prev_squads = None

    success, error = await db_service.add_user_throttle(
        user_uuid=user_uuid,
        rate_kbit=rate_kbit,
        reason=reason,
        admin_id=admin_id,
        admin_username=admin_username,
        until=until,
        prev_squads=prev_squads if moved else None,
    )
    return (success, error, moved)


async def lift_throttle(user_uuid: str) -> tuple:
    """Снять ограничение и вернуть пользователя в его прежние сквады.

    Returns:
        (removed: bool, restored: bool)
    """
    record = await db_service.get_user_throttle(user_uuid)
    prev_squads = None
    if record:
        raw = record.get("prev_squads")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = None
        if isinstance(raw, list) and raw:
            prev_squads = [str(s) for s in raw]

    removed = await db_service.remove_user_throttle(user_uuid)

    restored = False
    if removed and prev_squads:
        restored = await _set_squads(user_uuid, prev_squads)
        if not restored:
            # Запись уже удалена, а вернуть не смогли — говорим об этом
            # громко: молча оставить человека в резервном сквадe хуже всего.
            logger.error(
                "Throttle lifted for %s but squads NOT restored (%s)",
                user_uuid, ", ".join(prev_squads),
            )

    return (removed, restored)

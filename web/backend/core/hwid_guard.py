"""Сторож чёрного списка HWID: держит помеченные устройства отключёнными.

Периодический скан в коллекторе идёт от устройств, которые прислали ноды, и
срабатывает один раз — отключил и забыл. Этого мало: подписку может поднять
что угодно уже после блокировки. Случай 22.08: абузер привязал свой telegram_id
к заведённой через email подписке, и та ожила сама — DISABLED сменился на
ACTIVE, срок уехал на три недели вперёд.

Этот цикл ходит с другой стороны — от чёрного списка, а не от нод:

  * берёт все записи списка и всех, кого на этих устройствах видели, включая
    тех, кто устройство уже отвязал (``removed_at`` его помнит);
  * если подписка ожила — гасит её снова и говорит об этом.

Записи с действием ``alert`` остаются наблюдением: про такие только сообщаем,
не трогая подписку — админ выбрал не блокировать.
"""
import asyncio
from typing import Any, Dict, List, Set, Tuple

from shared.logger import logger

# (hwid, user_uuid), про которые уже сообщили в режиме alert. Цикл ходит раз в
# несколько минут, и без этой памяти одно и то же наблюдение уезжало бы админу
# бесконечно. Живёт до перезапуска — потери не страшны, максимум один повтор.
_alerted: Set[Tuple[str, str]] = set()


async def _active_connection_count(user_uuid: str) -> int:
    """Сколько подключений юзера живо прямо сейчас (0, если монитор недоступен)."""
    try:
        # тот же экземпляр, что у коллектора: он уже сидит на общем пуле БД
        from web.backend.api.v2.collector import connection_monitor
        conns = await connection_monitor.get_user_active_connections(
            user_uuid, max_age_minutes=5,
        )
        return len(conns or [])
    except Exception as e:  # noqa: BLE001
        logger.debug("hwid_guard: не удалось получить подключения %s: %s", user_uuid, e)
        return 0


async def _disable(user_uuid: str) -> bool:
    """Погасить подписку в панели. True — получилось."""
    from shared.api_client import api_client
    from web.backend.api.v2.users import _resolve_user_key
    try:
        await api_client.disable_user(await _resolve_user_key(user_uuid))
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("hwid_guard: не удалось отключить %s: %s", user_uuid, e)
        return False


def _describe(user: Dict[str, Any], conns: int) -> str:
    """Строка про одного юзера для уведомления."""
    name = user.get("username") or str(user.get("user_uuid", "?"))
    parts = [name]
    if user.get("removed_at"):
        parts.append("устройство отвязано")
    if conns:
        parts.append("подключений сейчас: %d" % conns)
    return "%s (%s)" % (parts[0], ", ".join(parts[1:])) if len(parts) > 1 else parts[0]


async def run_once() -> int:
    """Один проход сторожа. Возвращает число погашенных подписок."""
    from shared.config_service import config_service
    from shared.database import db_service
    from shared.db.network import _subscription_is_active

    if not config_service.get("hwid_blacklist_guard_enabled", True):
        return 0
    if not db_service.is_connected:
        return 0

    try:
        entries = await db_service.get_hwid_blacklist()
    except Exception as e:  # noqa: BLE001
        logger.warning("hwid_guard: чёрный список недоступен: %s", e)
        return 0
    if not entries:
        return 0

    disabled_total = 0
    for entry in entries:
        hwid = entry.get("hwid")
        if not hwid:
            continue
        try:
            users = await db_service.find_users_by_hwid(hwid)
        except Exception as e:  # noqa: BLE001
            logger.warning("hwid_guard: не удалось найти юзеров по %s: %s", hwid, e)
            continue

        alive = [u for u in users
                 if _subscription_is_active(u.get("expire_at"), u.get("status"))]
        # Кто перестал быть активным — забываем, иначе о рецидиве промолчим
        alive_keys = {(hwid, str(u.get("user_uuid"))) for u in alive}
        _alerted.difference_update({k for k in _alerted
                                    if k[0] == hwid and k not in alive_keys})
        if not alive:
            continue

        block = str(entry.get("action") or "").lower() == "block"
        touched: List[str] = []
        for user in alive:
            uuid = str(user.get("user_uuid"))
            conns = await _active_connection_count(uuid)
            if block:
                if await _disable(uuid):
                    disabled_total += 1
                    touched.append(_describe(user, conns))
                    logger.warning(
                        "hwid_guard: подписка %s ожила на HWID %s из чёрного списка — отключена",
                        user.get("username") or uuid, hwid[:16],
                    )
            elif (hwid, uuid) not in _alerted:
                _alerted.add((hwid, uuid))
                touched.append(_describe(user, conns))

        if touched:
            await _notify(hwid, entry, touched, blocked=block)

    return disabled_total


async def _notify(hwid: str, entry: Dict[str, Any], touched: List[str], blocked: bool) -> None:
    from web.backend.core.notification_service import create_notification
    reason = entry.get("reason") or "причина не указана"
    title = ("Чёрный список HWID: подписка ожила и снова отключена" if blocked
             else "Чёрный список HWID: живая подписка на помеченном устройстве")
    try:
        await create_notification(
            title=title,
            body=("HWID %s...\n%s\nПричина в списке: %s" % (
                hwid[:16], "\n".join("• " + t for t in touched), reason)),
            type="alert",
            severity="critical" if blocked else "warning",
            link="/violations",
            source="hwid_blacklist_guard",
            source_id=hwid,
            channels=["in_app", "telegram", "push"],
            topic_type="violations",
            # своё событие, не общий hwid_blacklist: воскресшая подписка —
            # отдельный повод, и отключать его хочется отдельно от остальных
            event="violation.hwid_blacklist_revived",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("hwid_guard: уведомление не ушло: %s", e)


async def loop() -> None:
    """Фоновый цикл сторожа."""
    from shared.config_service import config_service

    await asyncio.sleep(120)  # даём подняться синку и коллектору
    while True:
        try:
            disabled = await run_once()
            if disabled:
                logger.info("hwid_guard: отключено подписок: %d", disabled)
        except Exception as e:  # noqa: BLE001
            logger.warning("hwid_guard: проход не удался: %s", e)
        minutes = config_service.get("hwid_blacklist_guard_interval_minutes", 5)
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            minutes = 5
        await asyncio.sleep(max(1, minutes) * 60)

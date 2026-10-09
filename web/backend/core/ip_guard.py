"""Сторож адресов: несколько пробных подписок с одного IP.

HWID подделывается — его называет сам клиент в заголовке, и абузеру достаточно
прислать другую строку. Адрес так просто не сменить: он выдаётся провайдером, и
чтобы получить новый, нужно как минимум переключиться на мобильный интернет или
поднять VPN. Поэтому связка «несколько пробных подписок с одного адреса» —
сигнал более устойчивый, хотя и не абсолютный.

Считаем только пробные подписки: за адресом домашнего провайдера живёт целая
квартира, а за адресом оператора — целый район. Мобильным адресам порог
поднимается отдельно: там CGNAT, и несколько разных людей за одним адресом —
норма, а не совпадение.

Уведомление несёт кнопки быстрых действий (``ipact:``): заблокировать адрес,
посмотреть аккаунты, отложить сигнал.
"""
from typing import Any, Dict, List, Sequence

from shared.i18n import tr
from shared.logger import logger
from shared.tg_card import Button, Card, code, i, join, when
from web.backend.core.hwid_cards import connections_cell, people_table

NOTIFY_SOURCE = "ip_trial_reuse"
# Отметка «разобрано» из кнопки под уведомлением — см. src/handlers/ip_actions.py
MUTED_SOURCE = "ip_trial_muted"
MUTED_DAYS = 30


def _tone(group: Dict[str, Any]) -> str:
    """Насколько сигнал весомый: мобильный адрес сам по себе ничего не доказывает."""
    if group.get("is_mobile"):
        return "warning"
    return "critical" if group.get("accounts", 0) >= 3 else "warning"


def _network_note(group: Dict[str, Any]) -> str:
    """Чем известен адрес — оператор, хостинг, прокси."""
    kinds = [kind for kind in ("mobile", "hosting", "proxy") if group.get(f"is_{kind}")]
    return ", ".join(tr(f"notify.ip_trial.network.{kind}") for kind in kinds)


def ip_buttons(ip: str) -> List[List[Button]]:
    """Кнопки по адресу, а не по одному аккаунту: блок — красная, аккаунты — синяя."""
    return [
        [Button(tr("notify.ip_trial.btn.block"), f"ipact:block:{ip}", style="danger"),
         Button(tr("notify.ip_trial.btn.users"), f"ipact:users:{ip}", style="primary")],
        [Button(tr("notify.ip_trial.btn.mute"), f"ipact:mute:{ip}")],
    ]


def build_card(group: Dict[str, Any], users: Sequence[Dict[str, Any]]) -> Card:
    """Карточка: адрес, чем он известен, и пробные аккаунты таблицей."""
    provider = group.get("asn_org")
    card = Card(tr("notify.ip_trial.title"), emoji="🌐")
    card.text(i(tr("notify.ip_trial.subtitle.mobile" if group.get("is_mobile")
                   else "notify.ip_trial.subtitle.plain")))
    card.section(tr("notify.ip_trial.address"))
    card.fields([
        (tr("notify.ip_trial.field.ip"), code(group["ip"])),
        (tr("notify.ip_trial.field.provider"), join(provider, group.get("country_code")) if provider else None),
        (tr("notify.ip_trial.field.network"), _network_note(group) or None),
    ])
    card.section(tr("notify.ip_trial.trials", count=len(users)))
    people_table(card, users, extra=[
        (tr("notify.people.col.conns"), connections_cell),
        (tr("notify.people.col.created"), lambda u: when(u.get("created_at"), "d")),
    ])
    card.buttons(*ip_buttons(group["ip"]))
    return card.stamp()


async def _recently_notified(ip: str, hours: int) -> bool:
    """Молчим, если про адрес недавно говорили или админ отметил его разобранным.

    История берётся из таблицы уведомлений: отдельная таблица ради двух отметок
    не нужна, а решение админа так переживает перезапуск.
    """
    from shared.database import db_service
    try:
        async with db_service.acquire() as conn:
            found = await conn.fetchval(
                "SELECT 1 FROM notifications "
                " WHERE source_id = $1 "
                "   AND ((source = $2 AND created_at > NOW() - ($4 || ' hours')::interval) "
                "     OR (source = $3 AND created_at > NOW() - ($5 || ' days')::interval)) "
                " LIMIT 1",
                ip, NOTIFY_SOURCE, MUTED_SOURCE, str(hours), str(MUTED_DAYS),
            )
            return found is not None
    except Exception as e:  # noqa: BLE001
        logger.debug("ip_guard: проверка истории уведомлений не удалась: %s", e)
        return False


def _int_setting(key: str, default: int) -> int:
    from shared.config_service import config_service
    try:
        return int(config_service.get(key, default))
    except (TypeError, ValueError):
        return default


async def run_once() -> int:
    """Один проход. Возвращает число адресов, о которых сообщили."""
    from shared.config_service import config_service
    from shared.database import db_service

    if not config_service.get("violations_ip_trial_guard_enabled", True):
        return 0
    if not db_service.is_connected:
        return 0

    threshold = _int_setting("violations_ip_trial_accounts", 2)
    mobile_threshold = _int_setting("violations_ip_trial_accounts_mobile", 4)
    window_days = _int_setting("violations_ip_trial_window_days", 30)
    repeat_hours = _int_setting("violations_ip_trial_repeat_hours", 24)
    if threshold <= 0:
        return 0

    # Берём по нижнему порогу, мобильные отсеиваем после — их порог выше
    groups = await db_service.get_shared_ip_accounts(
        min_accounts=min(threshold, mobile_threshold), days=window_days, limit=50,
    )
    if not groups:
        return 0

    reported = 0
    for group in groups:
        users = [u for u in group.get("users", []) if u.get("is_trial")]
        limit = mobile_threshold if group.get("is_mobile") else threshold
        if len(users) < limit:
            continue
        ip = group["ip"]
        if await _recently_notified(ip, repeat_hours):
            continue

        users.sort(key=lambda u: u.get("conns") or 0, reverse=True)
        await _notify(group, users)
        reported += 1
        logger.warning(
            "ip_guard: %d пробных подписок с адреса %s (%s)",
            len(users), ip, group.get("asn_org") or "провайдер неизвестен",
        )
    return reported


async def _notify(group: Dict[str, Any], users: List[Dict[str, Any]]) -> None:
    from web.backend.core.notification_service import create_notification
    ip = group["ip"]
    try:
        card = build_card(group, users)
        await create_notification(
            title=card.title_text(),
            body=card.body_text(),
            telegram_card=card,
            type="alert",
            severity=_tone({**group, "accounts": len(users)}),
            link=f"/violations?ip={ip}",
            source=NOTIFY_SOURCE,
            source_id=ip,
            channels=["in_app", "telegram", "push"],
            topic_type="violations",
            event="violation.ip_trial_reuse",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("ip_guard: уведомление не ушло: %s", e)


async def loop() -> None:
    """Фоновый цикл сторожа адресов."""
    import asyncio

    await asyncio.sleep(300)  # даём коллектору набрать подключения
    while True:
        try:
            reported = await run_once()
            if reported:
                logger.info("ip_guard: адресов с повторными пробными: %d", reported)
        except Exception as e:  # noqa: BLE001
            logger.warning("ip_guard: проход не удался: %s", e)
        minutes = _int_setting("violations_ip_trial_interval_minutes", 60)
        await asyncio.sleep(max(5, minutes) * 60)

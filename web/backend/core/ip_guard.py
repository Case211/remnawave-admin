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

from shared.logger import logger
from web.backend.core.hwid_cards import esc, fmt_dt

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
    bits = []
    if group.get("is_mobile"):
        bits.append("мобильный оператор (CGNAT)")
    if group.get("is_hosting"):
        bits.append("хостинг")
    if group.get("is_proxy"):
        bits.append("прокси")
    return ", ".join(bits)


def build_card(group: Dict[str, Any], users: Sequence[Dict[str, Any]]) -> str:
    """Карточка уведомления в том же каноне, что и HWID-карточки."""
    lines = [
        "\U0001f310 <b>Несколько пробных подписок с одного адреса</b>",
        "",
        "\U0001f4a1 %s" % esc(
            "Адрес сменить труднее, чем HWID, — но за мобильным оператором может стоять весь район"
            if group.get("is_mobile")
            else "С этого адреса пробную подписку брали несколько раз"
        ),
        "",
        "\U0001f4cd <b>Адрес</b>",
        f"   \U0001f5a7 <code>{esc(group['ip'])}</code>",
    ]
    provider = group.get("asn_org")
    if provider:
        country = group.get("country_code")
        lines.append("   \U0001f3e2 %s%s" % (esc(provider), f" ({esc(country)})" if country else ""))
    note = _network_note(group)
    if note:
        lines.append(f"   ⚠️ {esc(note)}")
    lines.append("")

    lines.append(f"\U0001f465 <b>Пробные подписки ({len(users)})</b>")
    for index, user in enumerate(users[:5]):
        if index:
            lines.append("")
        name = user.get("username") or str(user.get("uuid") or "")[:8]
        lines.append(f"   \U0001f464 <code>{esc(name)}</code>")
        if user.get("telegram_id"):
            lines.append(f"   \U0001f4f1 TG ID: <code>{esc(user['telegram_id'])}</code>")
        if user.get("email"):
            lines.append(f"   \U0001f4e7 <code>{esc(user['email'])}</code>")
        lines.append(
            "   \U0001f50c Подключений: <b>%d</b>, последнее %s"
            % (int(user.get("conns") or 0), esc(fmt_dt(user.get("last_seen"))))
        )
        created = fmt_dt(user.get("created_at"))
        if created:
            lines.append(f"   \U0001f195 Аккаунт создан: {esc(created)}")
        if user.get("is_active"):
            lines.append("   \U0001f7e2 Подписка сейчас активна")
    tail = users[5:]
    if tail:
        names = ", ".join(esc(u.get("username") or str(u.get("uuid") or "")[:8]) for u in tail)
        lines.append(f"<blockquote expandable>И ещё {len(tail)}: {names}</blockquote>")
    return "\n".join(lines).rstrip()


def build_keyboard(ip: str) -> Dict[str, Any]:
    """Кнопки под уведомлением: действие по адресу, а не по одному аккаунту."""
    return {
        "inline_keyboard": [
            [
                {"text": "\U0001f6ab Заблокировать IP", "callback_data": f"ipact:block:{ip}"},
                {"text": "\U0001f465 Аккаунты", "callback_data": f"ipact:users:{ip}"},
            ],
            [
                {"text": "\U0001f507 Не напоминать", "callback_data": f"ipact:mute:{ip}"},
            ],
        ]
    }


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
        await create_notification(
            title="Несколько пробных подписок с одного адреса",
            body=build_card(group, users),
            type="alert",
            severity=_tone({**group, "accounts": len(users)}),
            link=f"/violations?ip={ip}",
            source=NOTIFY_SOURCE,
            source_id=ip,
            channels=["in_app", "telegram", "push"],
            topic_type="violations",
            event="violation.ip_trial_reuse",
            reply_markup=build_keyboard(ip),
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

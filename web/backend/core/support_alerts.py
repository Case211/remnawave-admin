"""Алерты поддержки: новое обращение и просроченный первый ответ.

Два повода дёрнуть оператора, и у каждого своя цена ошибки. О новом обращении
лучше сказать сразу — клиент ждёт. О просрочке нельзя говорить дважды: тикет
висит часами, и алерт на каждом круге превратился бы в шум, поэтому дедуп идёт
по ``group_key`` уведомления и по отметке в памяти процесса.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from shared import timefmt
from shared.i18n import tr
from shared.tg_card import CAPTION_LIMIT, Button, Card, b, code, link, tg_user, when

logger = logging.getLogger(__name__)

SLA_CHECK_INTERVAL_SECONDS = 60
DEFAULT_SLA_MINUTES = 30

# Тикеты, по которым просрочка уже объявлена. Сбрасывается при рестарте — тогда
# уведомление повторится один раз, что лучше молчания.
_sla_alerted: set[int] = set()

# Ответы клиента, о которых уже сказали: ключ по времени сообщения, поэтому
# событие бота и догоняющий синк не дадут двух уведомлений об одном и том же.
_reply_alerted: set[tuple[int, str]] = set()
_REPLY_MEMORY_LIMIT = 5000
FRESH_REPLY_MINUTES = 30


def sla_minutes() -> int:
    from shared.config_service import config_service

    try:
        return max(1, int(config_service.get("support_sla_minutes", DEFAULT_SLA_MINUTES) or DEFAULT_SLA_MINUTES))
    except (TypeError, ValueError):
        return DEFAULT_SLA_MINUTES


def sla_enabled() -> bool:
    """Контроль срока ответа целиком: очередь, подсветка, алерты о просрочке.

    Выключатель отдельный от алертов: кому-то нужны уведомления о новых
    обращениях, но не нужна гонка за таймером.
    """
    from shared.config_service import config_service

    return bool(config_service.get("support_sla_enabled", True))


def alerts_enabled() -> bool:
    from shared.config_service import config_service

    return bool(config_service.get("support_alerts_enabled", True))


def new_message_alerts_enabled() -> bool:
    from shared.config_service import config_service

    return alerts_enabled() and bool(config_service.get("support_alert_new_message", True))


def new_ticket_alerts_enabled() -> bool:
    from shared.config_service import config_service

    return alerts_enabled() and bool(config_service.get("support_alert_new_ticket", True))


def _panel_base() -> str:
    """Адрес панели для кнопок-ссылок; пусто — ссылок не будет.

    Внутрипанельный путь в чате бесполезен — нужен абсолютный адрес, а его
    знает только настройка «Публичный URL панели». Telegram принимает в кнопке
    исключительно https и отклоняет всё сообщение целиком, если адрес не
    подошёл, поэтому на пустой или http-настройке ссылок просто нет: лучше
    уведомление без них, чем молчание.
    """
    from shared.config_service import config_service

    base = str(config_service.get("web_panel_public_url", "") or "").strip().rstrip("/")
    return base if base.startswith("https://") else ""


def ticket_buttons(
    ticket_id: int,
    *,
    bot_user_id: int | None = None,
    username: str | None = None,
) -> list[list[Button]]:
    """Кнопки карточки: куда перейти и что можно сделать не переходя.

    Ссылки ведут в панель, действия обрабатывает бот админки (``sact:``) — тем
    же RBAC, что и веб-интерфейс. Без публичного адреса панели остаются одни
    действия: они работают и без ссылок.
    """
    base = _panel_base()
    links: list[Button] = []
    if base:
        links.append(Button(tr("notify.support.btn.open"), url=f"{base}/support?ticket={ticket_id}", style="primary"))
        if bot_user_id:
            links.append(Button(tr("notify.support.btn.profile"), url=f"{base}/bedolaga/customers/{bot_user_id}"))
    if username:
        # Личка открывается только по имени: у клиента без username Telegram
        # ссылку не примет и отклонит всё сообщение.
        links.append(Button(tr("notify.support.btn.write"), url=f"https://t.me/{username.lstrip('@')}"))
    rows = [links[n:n + 2] for n in range(0, len(links), 2)]
    rows.append([Button(tr("notify.support.btn.take"), f"sact:take:{ticket_id}", style="success"),
                 Button(tr("notify.support.btn.snooze"), f"sact:snooze:{ticket_id}")])
    rows.append([Button(tr("notify.support.btn.close"), f"sact:close:{ticket_id}", style="danger")])
    return rows


async def _send_with_media(card: Card, ticket_id: int, attachment: dict) -> bool:
    """Отправить карточку вместе со скриншотом (видео, файлом) клиента.

    Вложение встраивается в саму карточку, а если rich не прошёл — уходит
    файлом с подписью: в чате одно сообщение, а не картинка следом за
    текстом. Файл качаем через API бота: file_id принадлежит его боту и
    нашим токеном не отправляется, поэтому пересылаем байтами.
    """
    from shared import tg_rich
    from web.backend.core.notification_service import _get_global_telegram_config

    bot_token, chat_id, topic_id = _get_global_telegram_config("support")
    if not bot_token or not chat_id:
        return False
    try:
        return await tg_rich.send_rich_or_html(
            bot_token, chat_id, card.to_html(limit=CAPTION_LIMIT),
            blocks=card.to_blocks(),
            message_thread_id=int(topic_id) if topic_id and str(topic_id) != "0" else None,
            fallback_markup=card.keyboard(),
            media=(_media_kind(attachment), attachment.get("name") or "attachment", attachment["content"]),
        )
    except Exception as exc:  # noqa: BLE001 — сеть до Telegram: обойдёмся текстом
        logger.warning("Support alert: вложение не ушло (%s): %s", ticket_id, exc)
        return False


def _media_kind(attachment: dict) -> str:
    kind = attachment.get("kind")
    return kind if kind in ("photo", "video") else "document"


async def _notify(
    card: Card,
    body: str,
    *,
    severity: str,
    group_key: str,
    ticket_id: int,
    attachment: dict | None = None,
    bot_user_id: int | None = None,
    username: str | None = None,
) -> None:
    try:
        from web.backend.core.notification_service import create_notification

        if attachment:
            card.media(_media_kind(attachment))
        card.buttons(*ticket_buttons(ticket_id, bot_user_id=bot_user_id, username=username))
        card.stamp()
        # Карточка с вложением уходит отдельным вызовом: файл не проходит
        # через общую трубу уведомлений. Не получилось — шлём её обычным путём.
        sent_with_file = bool(attachment) and await _send_with_media(card, ticket_id, attachment)

        await create_notification(
            title=card.title_text(),
            body=body,
            type="alert",
            severity=severity,
            channels=["in_app"] if sent_with_file else ["in_app", "telegram"],
            # Обращения идут своим топиком, иначе тонут среди сервисных сообщений.
            topic_type="support",
            source="support",
            source_id=str(ticket_id),
            group_key=group_key,
            link=f"/support?ticket={ticket_id}",
            telegram_card=card,
        )
    except Exception as exc:  # noqa: BLE001 — алерт не должен ронять синк
        logger.warning("Support alert не отправлен (%s): %s", group_key, exc)


def _short(text: str, limit: int = 300) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def _ticket_row(ticket_id: int) -> dict:
    """Строка проекции: событие бота приносит не все поля, которые нужны в письме."""
    from shared.database import db_service

    if not db_service.is_connected:
        return {}
    try:
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT t.*,
                       (SELECT COUNT(*) FROM support_ticket_messages m
                         WHERE m.ticket_id = t.id AND m.has_media) AS attachments
                FROM support_tickets t WHERE t.id = $1
                """,
                ticket_id,
            )
        return dict(row) if row else {}
    except Exception as exc:  # noqa: BLE001 — уведомление важнее полноты карточки
        logger.debug("Support alert: проекция по %s не прочиталась: %s", ticket_id, exc)
        return {}


async def _last_message(ticket_id: int) -> dict:
    """Сообщение, из-за которого пришёл алерт: оно же последнее в переписке."""
    from shared.database import db_service

    if not db_service.is_connected:
        return {}
    try:
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, text, has_media, media_type, media_items, is_from_admin
                FROM support_ticket_messages
                WHERE ticket_id = $1
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                ticket_id,
            )
        return dict(row) if row else {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("Support alert: сообщение по %s не прочиталось: %s", ticket_id, exc)
        return {}


async def _attachment(ticket_id: int, message: dict) -> dict | None:
    """Первый файл сообщения байтами — для пересылки в чат."""
    if not message or not message.get("has_media"):
        return None
    from shared.bedolaga_client import bedolaga_client
    from web.backend.core import support_media_cache as media_cache

    file_id = None
    kind = str(message.get("media_type") or "document")
    raw = message.get("media_items")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if isinstance(raw, list) and raw:
        first = raw[0] or {}
        file_id = first.get("file_id")
        kind = str(first.get("type") or kind)

    try:
        if not file_id:
            info = await bedolaga_client.get_ticket_message_media(ticket_id, int(message["id"]))
            file_id = (info or {}).get("media_file_id")
            kind = str((info or {}).get("media_type") or kind)
        if not file_id:
            return None
        content = media_cache.read(file_id)
        if content is None:
            content = await bedolaga_client.download_media(file_id)
            media_cache.write(file_id, content)
    except Exception as exc:  # noqa: BLE001 — бот не отдал файл: уведомим текстом
        logger.warning("Support alert: вложение %s не скачалось: %s", ticket_id, exc)
        return None

    extension = {"photo": "jpg", "video": "mp4"}.get(kind, "bin")
    return {"content": content, "kind": kind, "name": f"ticket-{ticket_id}.{extension}"}


def _ticket_card(title: str, emoji: str, customer: str, subject: str = "", text: str = "",
                 fields: Sequence = ()) -> Card:
    """Карточка обращения: кто и о чём, слова клиента — цитатой с его именем.

    Числа вложений в карточке нет: сам файл встроен в неё, и строка
    «вложений столько-то» повторяла бы то, что и так видно.
    """
    card = Card(title, emoji=emoji)
    card.lead(b(customer), subject)
    card.quote(text, credit=customer)
    card.fields(fields)
    return card


async def _customer_fields(bot_user_id: int) -> tuple[list[tuple[str, Any]], dict]:
    """Контакты, подписка и баланс — всё, с чем оператор решает, что делать.

    Контакты нужны, чтобы написать человеку не заходя в панель, а подписка с
    балансом — то, чего в уведомлении бота нет: повторять его карточку смысла
    не было бы, ценность нашей в том, что мы видим панель.
    """
    if not bot_user_id:
        return [], {}
    from shared.bedolaga_client import bedolaga_client

    try:
        user = await bedolaga_client.get_user(bot_user_id)
    except Exception as exc:  # noqa: BLE001 — бот недоступен: обойдёмся без контекста
        logger.debug("Support alert: клиент %s не прочитался: %s", bot_user_id, exc)
        return [], {}

    user = user or {}
    username = str(user.get("username") or "").lstrip("@")
    telegram_id = user.get("telegram_id")
    email = str(user.get("email") or "")

    subscription = user.get("subscription") or {}
    if subscription:
        status = str(subscription.get("actual_status") or subscription.get("status") or "")
        label = tr(f"notify.support.sub.status.{status}") if status else "—"
        parts = [status if label == f"notify.support.sub.status.{status}" else label]
        end_date = str(subscription.get("end_date") or "")[:10]
        if end_date:
            parts.append(tr("notify.support.sub.until", date=timefmt.fmt_date(end_date) or end_date))
        if subscription.get("is_trial"):
            parts.append(tr("notify.support.sub.trial"))
        if subscription.get("device_limit"):
            parts.append(tr("notify.support.sub.devices", count=subscription["device_limit"]))
        sub_text = " · ".join(parts)
    else:
        sub_text = tr("notify.support.sub.none")

    balance = user.get("balance_rubles")
    fields = [
        (tr("notify.support.field.username"), link(f"@{username}", f"https://t.me/{username}") if username else None),
        (tr("notify.support.field.telegram"), tg_user(str(telegram_id), telegram_id) if telegram_id else None),
        (tr("notify.support.field.email"), code(email) if email else None),
        (tr("notify.support.field.subscription"), sub_text),
        (tr("notify.support.field.balance"), b(f"{balance} ₽") if balance is not None else None),
    ]
    return fields, {"username": username, "telegram_id": telegram_id}


async def notify_new_ticket(ticket: dict) -> None:
    """Клиент создал обращение — сказать сразу, пока он ещё в чате.

    В чат уходит карточка: кто написал, о чём, с чем пришёл и что у него с
    подпиской. Одной строки «имя: тема» оператору не хватало — чтобы понять,
    срочное ли это, всё равно приходилось открывать панель.
    """
    if not new_ticket_alerts_enabled():
        return
    ticket_id = int(ticket.get("id") or 0)
    if not ticket_id:
        return

    row = await _ticket_row(ticket_id)
    data = {**ticket, **row}
    customer = str(data.get("customer_name") or "") or f"#{data.get('bot_user_id') or '—'}"
    title = str(data.get("title") or tr("notify.support.no_subject"))
    message = await _last_message(ticket_id)

    bot_user_id = int(data.get("bot_user_id") or 0)
    contacts, meta = await _customer_fields(bot_user_id)
    channel = tr("notify.support.channel.telegram" if data.get("telegram_id") else "notify.support.channel.cabinet")

    card = _ticket_card(tr("notify.support.new_ticket", id=ticket_id), "🆘", customer, title,
                        _short(data.get("last_message_text") or "", 800),
                        [(tr("notify.support.field.channel"), channel), *contacts])

    await _notify(
        card,
        f"{customer}: {title}",
        severity="info",
        group_key=f"support_new_{ticket_id}",
        ticket_id=ticket_id,
        attachment=await _attachment(ticket_id, message),
        bot_user_id=bot_user_id,
        username=meta.get("username"),
    )


async def notify_auto_reply(ticket_id: int, customer: str) -> None:
    """Робот ответил за оператора — сказать об этом, но не тревожным тоном.

    Уведомление уходит обычным порядком: спящий телефон его всё равно не
    покажет, а утром в ленте видно, что клиент не остался в тишине.
    """
    if not alerts_enabled():
        return
    who = customer or tr("notify.support.customer")
    card = Card(tr("notify.support.auto_reply", id=ticket_id), emoji="🤖")
    card.lead(b(who))
    card.text(tr("notify.support.auto_reply_text"))
    await _notify(
        card,
        f"{who}: {tr('notify.support.auto_reply_text')}",
        severity="info",
        group_key=f"support_auto_{ticket_id}",
        ticket_id=ticket_id,
    )


async def notify_customer_reply(ticket: dict) -> None:
    """Клиент дописал в открытое обращение.

    Уведомление о новом обращении приходило, а дальше переписка шла молча:
    оператор узнавал об ответе, только когда сам заходил в раздел. Шлём то же,
    что и по новому обращению, но короче — контекст клиента он уже видел.
    """
    if not new_message_alerts_enabled():
        return
    ticket_id = int(ticket.get("id") or 0)
    if not ticket_id:
        return

    row = await _ticket_row(ticket_id)
    data = {**ticket, **row}
    if str(data.get("status") or "") == "closed":
        return
    # Ответ оператора — не повод дёргать оператора.
    if str(data.get("last_message_from") or "") != "user":
        return

    stamp = str(data.get("last_message_at") or "")
    if not stamp:
        return
    # Догоняющий синк после простоя переберёт всю очередь: уведомляем только о
    # том, что написано только что, иначе оператор получит пачку старых ответов.
    written = data.get("last_message_at")
    if isinstance(written, str):
        try:
            written = datetime.fromisoformat(written.replace("Z", "+00:00"))
        except ValueError:
            written = None
    if isinstance(written, datetime):
        if written.tzinfo is None:
            written = written.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - written > timedelta(minutes=FRESH_REPLY_MINUTES):
            return
    mark = (ticket_id, stamp)
    if mark in _reply_alerted:
        return
    if len(_reply_alerted) >= _REPLY_MEMORY_LIMIT:
        _reply_alerted.clear()
    _reply_alerted.add(mark)

    customer = str(data.get("customer_name") or "") or f"#{data.get('bot_user_id') or '—'}"
    title = str(data.get("title") or tr("notify.support.no_subject"))
    message = await _last_message(ticket_id)
    text = _short(data.get("last_message_text") or "", 800)
    bot_user_id = int(data.get("bot_user_id") or 0)
    # Контакты нужны и здесь: решение «ответить сейчас или позже» принимают по
    # тому же, по чему и на новом обращении.
    contacts, meta = await _customer_fields(bot_user_id)
    card = _ticket_card(tr("notify.support.reply", id=ticket_id), "💬", customer, title, text, contacts)

    await _notify(
        card,
        f"{customer}: {_short(text or title, 120)}",
        severity="info",
        group_key=f"support_reply_{ticket_id}_{stamp}",
        ticket_id=ticket_id,
        attachment=await _attachment(ticket_id, message),
        bot_user_id=bot_user_id,
        username=meta.get("username"),
    )


async def check_sla_breaches() -> int:
    """Найти обращения, где клиент ждёт дольше порога, и предупредить один раз."""
    from shared.database import db_service

    if not sla_enabled() or not alerts_enabled() or not db_service.is_connected:
        return 0

    threshold = datetime.now(timezone.utc) - timedelta(minutes=sla_minutes())
    alerted = list(_sla_alerted)
    async with db_service.acquire() as conn:
        # Уже объявленные отсекаем в SQL: иначе полсотни старых висяков занимали
        # бы всю страницу, и свежая просрочка не дождалась бы алерта никогда.
        rows = await conn.fetch(
            """
            SELECT t.id, t.title, t.customer_name, t.waiting_since
            FROM support_tickets t
            LEFT JOIN support_snoozes s ON s.ticket_id = t.id
            WHERE t.status <> 'closed'
              AND t.waiting_since IS NOT NULL
              AND t.waiting_since < $1
              AND (s.snooze_to IS NULL OR s.snooze_to <= NOW())
              AND NOT (t.id = ANY($2::bigint[]))
            ORDER BY t.waiting_since ASC
            LIMIT 50
            """,
            threshold, alerted,
        )
        # Отметку снимаем только с тех, кто перестал ждать — по всему списку
        # объявленных, а не по одной странице выборки.
        still_waiting = await conn.fetch(
            """
            SELECT t.id
            FROM support_tickets t
            WHERE t.id = ANY($1::bigint[])
              AND t.status <> 'closed'
              AND t.waiting_since IS NOT NULL
            """,
            alerted,
        ) if alerted else []

    _sla_alerted.intersection_update({int(r["id"]) for r in still_waiting})

    sent = 0
    for row in rows:
        ticket_id = int(row["id"])
        waited = int((datetime.now(timezone.utc) - row["waiting_since"]).total_seconds() // 60)
        customer = row["customer_name"] or tr("notify.support.customer")
        subject = row["title"] or tr("notify.support.no_subject")
        card = _ticket_card(tr("notify.support.sla", id=ticket_id, minutes=waited), "⏰", customer, subject,
                            fields=[(tr("notify.support.field.waiting"), when(row["waiting_since"]))])
        await _notify(
            card,
            f"{customer}: {subject}",
            severity="warning",
            group_key=f"support_sla_{ticket_id}",
            ticket_id=ticket_id,
        )
        _sla_alerted.add(ticket_id)
        sent += 1

    return sent


async def support_alerts_loop() -> None:
    """Раз в минуту проверяем просрочки. Падение круга не убивает цикл."""
    while True:
        try:
            await check_sla_breaches()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Support alerts: круг проверки упал: %s", exc, exc_info=True)
        await asyncio.sleep(SLA_CHECK_INTERVAL_SECONDS)

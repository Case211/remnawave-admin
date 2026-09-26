"""Предупреждение клиенту о нарушении: шаблоны и отправка через бота.

Решение всегда за человеком. Детектор ошибается — гео-анализатор срабатывает
на переезде, HWID на переустановке системы, — поэтому автоматика сама клиенту
не пишет: оператор смотрит нарушение и жмёт «Предупредить», либо применяет
меру, и тогда предупреждение уходит вместе с ней (иначе доступ просто
перестанет работать без объяснений).

Текст зависит от того, что сработало: раздавшему подписку и качающему торренты
надо сказать разное. Шаблон свой на каждый вид, со своим порогом скора и
выключателем; чего не нашлось — берётся ``default``.

Клиенту не сообщают, ЧТО именно увидел детектор: ни стран, ни числа устройств,
ни скоринга. Это инструкция по обходу — человек просто разнесёт подключения.
Наружу идут факт и последствие, подробности остаются в панели.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Порядок важен: сюда же смотрит интерфейс шаблонов.
NOTICE_KINDS = (
    "default", "temporal", "geo", "asn", "profile",
    "device", "hwid", "user_agent", "torrent", "traffic_rate",
)

_TEMPLATE_FIELDS = (
    "kind", "enabled", "min_score", "send_email",
    "subject_ru", "body_ru", "subject_en", "body_en", "updated_at", "updated_by",
)


async def list_templates() -> list[dict]:
    """Все шаблоны, включая ещё не тронутые оператором."""
    from shared.database import db_service

    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            # Общий шаблон первым: с него начинают, остальные — уточнения к нему.
            f"SELECT id, {', '.join(_TEMPLATE_FIELDS)} FROM violation_notice_templates "
            "ORDER BY (kind = 'default') DESC, kind"
        )
    return [dict(row) for row in rows]


async def update_template(kind: str, data: dict, *, updated_by: str | None = None) -> Optional[dict]:
    """Правка шаблона. Возвращает обновлённую строку либо None, если вида нет."""
    from shared.database import db_service

    if kind not in NOTICE_KINDS or not db_service.is_connected:
        return None

    allowed = ("enabled", "min_score", "send_email", "subject_ru", "body_ru", "subject_en", "body_en")
    updates = {key: data[key] for key in allowed if key in data}
    if not updates:
        return None

    columns = ", ".join(f"{key} = ${i + 2}" for i, key in enumerate(updates))
    args = [kind, *updates.values()]
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE violation_notice_templates
               SET {columns}, updated_at = NOW(), updated_by = ${len(args) + 1}
             WHERE kind = $1
            RETURNING id, {', '.join(_TEMPLATE_FIELDS)}
            """,
            *args,
            updated_by,
        )
    return dict(row) if row else None


def violation_kind(violation: dict) -> str:
    """Вид нарушения — по анализатору, давшему наибольший вклад.

    Тот же выбор, что у кнопок белого списка под уведомлением: сработал HWID —
    и текст про устройства, а не общий про раздачу доступа.
    """
    from shared.analyzers.models import dominant_analyzer

    raw = violation.get("raw_breakdown") or violation.get("raw_data")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if isinstance(raw, dict):
        breakdown = raw.get("breakdown") if isinstance(raw.get("breakdown"), dict) else raw
        dominant = dominant_analyzer(breakdown)
        if dominant in NOTICE_KINDS:
            return dominant

    reasons = " ".join(violation.get("reasons") or []).lower()
    if "торрент" in reasons or "torrent" in reasons:
        return "torrent"
    return "default"


async def pick_template(
    kind: str, score: float | None, *, respect_threshold: bool = False
) -> Optional[dict]:
    """Шаблон под вид нарушения; None — предупреждать не надо.

    Порог скора смотрим только при автоотправке. Нажатие «Предупредить» — уже
    решение человека, и отказывать ему из-за слабого скора значит спорить с
    оператором, который видит нарушение целиком.
    """
    from shared.database import db_service

    if not db_service.is_connected:
        return None
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM violation_notice_templates WHERE kind = $1", kind
        )
        if row is None or not row["enabled"]:
            # Своего шаблона нет или он выключен — пробуем общий.
            row = await conn.fetchrow(
                "SELECT * FROM violation_notice_templates WHERE kind = 'default'"
            )
    if row is None or not row["enabled"]:
        return None

    template = dict(row)
    if respect_threshold and score is not None and float(score) < float(template["min_score"] or 0):
        return None
    if not (template.get("body_ru") or "").strip():
        return None
    return template


async def already_notified(violation_id: int) -> bool:
    from shared.database import db_service

    if not db_service.is_connected:
        return False
    async with db_service.acquire() as conn:
        return bool(await conn.fetchval(
            "SELECT 1 FROM violation_notices WHERE violation_id = $1", violation_id
        ))


async def send_notice(
    violation: dict,
    *,
    sent_by: str | None = None,
    force: bool = False,
    auto: bool = False,
) -> dict:
    """Отправить клиенту предупреждение по конкретному нарушению.

    Возвращает результат доставки по каналам: ``{"sent": bool, "telegram": …,
    "email": …, "reason": …}``. Ошибка доставки не откатывает ничего — писать
    повторно решает оператор.

    ``auto`` — отправка без отдельного решения человека: тогда действует порог
    скора из шаблона, иначе он не применяется.
    """
    from shared.database import db_service

    violation_id = int(violation.get("id") or 0)
    telegram_id = violation.get("telegram_id")
    email = str(violation.get("email") or "").strip()
    if not violation_id:
        return {"sent": False, "reason": "no_violation"}
    if not telegram_id and not email:
        return {"sent": False, "reason": "no_recipient"}
    if not force and await already_notified(violation_id):
        return {"sent": False, "reason": "already_notified"}

    kind = violation_kind(violation)
    template = await pick_template(kind, violation.get("score"), respect_threshold=auto)
    if not template:
        return {"sent": False, "reason": "no_template", "kind": kind}

    body = str(template.get("body_ru") or "")
    subject = str(template.get("subject_ru") or "Использование подписки")
    html = "<p>" + body.replace("\n\n", "</p><p>").replace("\n", "<br>") + "</p>"
    want_email = bool(template.get("send_email"))

    # Сначала бот Bedolaga: Telegram от сервисного бота и письмо её почтой
    result, reason = await _deliver_via_bedolaga(
        violation_id, telegram_id, email, want_email, subject, body, html,
    )
    telegram_ok = bool(((result or {}).get("telegram") or {}).get("sent"))
    email_ok = bool(((result or {}).get("email") or {}).get("sent"))
    email_result = (result or {}).get("email")

    # Главное — чтобы дошло письмо, если у клиента есть почта. Бот не доставил
    # ничего (не настроен, без ручки /notify, клиента не нашёл) — пишем своим
    # почтовым сервером любому клиенту с email; доставил только Telegram, а
    # шаблон просит «и на почту» — досылаем письмо сами.
    if email and not email_ok and (not telegram_ok or want_email):
        if await _send_own_email(email, subject, body, html):
            email_ok = True
            email_result = {"sent": True, "via": "mail_server"}
        elif not telegram_ok:
            reason = "mail_failed"

    delivered = [name for name, ok in (("telegram", telegram_ok), ("email", email_ok)) if ok]

    if delivered and db_service.is_connected:
        async with db_service.acquire() as conn:
            # Текст храним снимком: шаблон потом правят, а клиенту показывать
            # надо ровно то, что он получил.
            await conn.execute(
                """
                INSERT INTO violation_notices
                    (violation_id, user_uuid, telegram_id, kind, channels, sent_by, subject, body)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (violation_id) DO UPDATE
                   SET channels = EXCLUDED.channels, sent_at = NOW(), sent_by = EXCLUDED.sent_by,
                       subject = EXCLUDED.subject, body = EXCLUDED.body
                """,
                violation_id,
                str(violation.get("user_uuid")),
                int(telegram_id) if telegram_id else None,
                kind,
                delivered,
                sent_by,
                subject,
                body,
            )

    logger.info(
        "Предупреждение по нарушению %s: telegram=%s email=%s (вид %s)",
        violation_id, telegram_ok, email_ok, kind,
    )
    return {
        "sent": bool(delivered),
        "kind": kind,
        "telegram": (result or {}).get("telegram"),
        "email": email_result,
        "reason": None if delivered else (reason or "not_delivered"),
    }


async def _deliver_via_bedolaga(
    violation_id: int, telegram_id, email: str, want_email: bool, subject: str, body: str, html: str,
) -> tuple[Optional[dict], Optional[str]]:
    """Доставка ботом Bedolaga. Возвращает (ответ бота или None, причина неудачи или None)."""
    from shared.bedolaga_client import bedolaga_client
    from web.backend.api.v2.bedolaga import ensure_configured

    try:
        ensure_configured()
    except Exception as exc:  # noqa: BLE001 — Bedolaga не настроена
        logger.info("Bedolaga не настроена — предупреждение %s без бота: %s", violation_id, exc)
        return None, "bedolaga_not_configured"

    try:
        if telegram_id:
            user = await bedolaga_client.get_user_by_telegram(int(telegram_id))
        else:
            user = await bedolaga_client.get_user_by_email(email)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Клиент нарушения %s в боте не найден: %s", violation_id, exc)
        return None, "user_not_found"

    bot_user_id = int((user or {}).get("id") or 0)
    if not bot_user_id:
        return None, "user_not_found"

    if telegram_id:
        channels = ["telegram", "email"] if want_email else ["telegram"]
    else:
        # Без Telegram письмо — единственный канал
        channels = ["email"]
    try:
        result = await bedolaga_client.notify_user(
            bot_user_id, text=body, channels=channels, email_subject=subject, email_html=html,
        )
    except Exception as exc:  # noqa: BLE001 — бот недоступен или без ручки /notify (#3270)
        logger.warning("Предупреждение по нарушению %s ботом не доставлено: %s", violation_id, exc)
        return None, "delivery_failed"
    return result, None


async def _send_own_email(to_email: str, subject: str, body_text: str, body_html: str) -> bool:
    """Письмо нашим почтовым сервером. False — сервер не настроен (нет домена отправки) или сбой."""
    try:
        from web.backend.core.mail.mail_service import mail_service

        queue_id = await mail_service.send_email(
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            category="violation_notice",
            priority=1,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Письмо-предупреждение нашим сервером не ушло: %s", exc)
        return False
    return bool(queue_id)


async def notice_for(violation_id: int) -> Optional[dict]:
    """Когда и чем предупреждали по этому нарушению."""
    from shared.database import db_service

    if not db_service.is_connected:
        return None
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT violation_id, kind, channels, sent_by, sent_at, subject, body "
            "FROM violation_notices WHERE violation_id = $1",
            violation_id,
        )
    return dict(row) if row else None


async def last_notice_for_user(telegram_id: int, *, days: int = 14) -> Optional[dict]:
    """Последнее предупреждение клиента — то, что показывает ему кабинет.

    Ограничение по сроку важнее, чем кажется: плашка «вы нарушили» не должна
    висеть у человека вечно. Аннулированные нарушения не в счёт — оператор
    признал их ошибкой детектора, и напоминать о них незачем.
    """
    from shared.database import db_service

    if not telegram_id or not db_service.is_connected:
        return None
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT n.violation_id, n.kind, n.subject, n.body, n.sent_at
              FROM violation_notices n
              JOIN violations v ON v.id = n.violation_id
             WHERE n.telegram_id = $1
               AND n.sent_at >= NOW() - ($2 || ' days')::interval
               AND (v.action_taken IS NULL OR v.action_taken <> 'annulled')
             ORDER BY n.sent_at DESC
             LIMIT 1
            """,
            telegram_id,
            str(days),
        )
    return dict(row) if row else None

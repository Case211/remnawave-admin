"""Напоминания о предстоящих и просроченных платежах: списаниях и ожидаемых поступлениях.

Суточная логика с защитой от дублей через finance_items.last_reminded_at:
одно напоминание на запись в день, только на порогах finance_reminder_days
(например 7/3/1 дней до списания) и при просрочке.

«День» и час отправки считаются в зоне отображения (display_timezone), а не
по часам контейнера: иначе сутки сменяются в 00:00 UTC, напоминания уходят
первой же проверкой после этого — среди ночи по местному времени, — а
«сегодня» и «завтра» в тексте до утра расходятся с календарём админа.
Час задаёт finance_reminder_hour. Кнопки в Telegram:
«Оплачено» (платёж + сдвиг цикла) и «Пропустить цикл» (сдвиг без платежа) —
обрабатываются ботом (fin:paid / fin:skip).
"""
import asyncio
import logging
from datetime import date, datetime
from typing import Dict, List, Optional

from shared.i18n import tr
from shared.tg_card import Button, Card, b, i

logger = logging.getLogger(__name__)

# Проверяем раз в четверть часа, шлём максимум раз в день: от шага зависит,
# насколько точно напоминание попадёт в назначенный час.
CHECK_INTERVAL_SECONDS = 900
DEFAULT_REMINDER_HOUR = 10


def _reminder_hour() -> int:
    """Час отправки (0–23) в зоне отображения; мусор в настройке — час по умолчанию."""
    from shared.config_service import config_service
    try:
        hour = int(config_service.get("finance_reminder_hour", DEFAULT_REMINDER_HOUR))
    except (TypeError, ValueError):
        return DEFAULT_REMINDER_HOUR
    return hour if 0 <= hour <= 23 else DEFAULT_REMINDER_HOUR


def is_send_time(now_local: datetime, hour: int) -> bool:
    """Пора ли слать: местное время дошло до назначенного часа.

    После этого часа и до конца суток — «пора»: если панель в назначенный
    час была выключена, напоминание уйдёт при первой проверке после старта,
    а не потеряется. От повторов защищает last_reminded_at.
    """
    return now_local.hour >= hour


def _reminder_days() -> List[int]:
    from shared.config_service import config_service
    raw = str(config_service.get("finance_reminder_days", "7,3,1") or "7,3,1")
    days = []
    for part in raw.split(","):
        try:
            days.append(int(part.strip()))
        except ValueError:
            continue
    return sorted(set(d for d in days if d >= 0), reverse=True)


def _fmt_amount(item: Dict) -> str:
    return f"{item['amount']:,.2f}".replace(",", " ") + f" {item['currency']}"


def _fmt_date(iso: Optional[str]) -> str:
    try:
        return date.fromisoformat(iso or "").strftime("%d.%m.%Y")
    except ValueError:
        return iso or ""


def reminder_card(item: Dict, title_key: str, when: str, emoji: str) -> Card:
    """Сумма и срок — сводкой, где и за что — полями, кнопки — прямо в сообщении."""
    card = Card(tr(title_key, name=item["name"]), emoji=emoji)
    amount = b(_fmt_amount(item)) if item.get("amount") else i(tr("notify.finance.no_amount"))
    card.lead(amount, when)
    card.fields([
        (tr("notify.finance.field.date"), _fmt_date(item.get("next_due_at"))),
        (tr("notify.finance.field.provider"), item.get("provider_name")),
        (tr("notify.finance.field.category"), item.get("category_name")),
    ])
    income = item.get("kind") == "income"
    card.buttons(
        [Button(tr("notify.finance.btn.received" if income else "notify.finance.btn.paid"),
                f"fin:paid:{item['id']}", style="success"),
         Button(tr("notify.finance.btn.skip"), f"fin:skip:{item['id']}")],
        [Button(tr("notify.finance.btn.open"), url=item["url"], style="primary")] if item.get("url") else [],
    )
    return card.stamp()


async def check_and_send_reminders(today: Optional[date] = None) -> int:
    """Один проход: найти записи на порогах/просроченные, отправить, отметить.

    ``today`` — сегодняшняя дата в зоне отображения; по умолчанию берётся из
    ``shared.timefmt``.
    """
    from shared import timefmt
    from shared.database import db_service
    from shared.config_service import config_service
    from web.backend.core.notification_service import create_notification

    if not config_service.get("finance_reminders_enabled", True):
        return 0
    if not db_service.is_connected:
        return 0

    thresholds = set(_reminder_days())
    if today is None:
        today = timefmt.now().date()
    sent = 0

    horizon = max(thresholds) if thresholds else 7
    for item in await db_service.upcoming_finance_payments(days=horizon, today=today):
        days_left = item["days_left"]
        overdue = item["is_overdue"]
        if not overdue and days_left not in thresholds:
            continue
        if item.get("last_reminded_at") == today.isoformat():
            continue  # уже напоминали сегодня

        # Доход ждут, а не платят: «скоро списание» про ожидаемое поступление
        # пугало и сбивало с толку — формулировка зависит от вида записи.
        kind = "income" if item.get("kind") == "income" else "expense"
        if overdue:
            title_key, emoji = f"notify.finance.overdue.{kind}", "⚠️"
            when = tr("notify.finance.when.late" if kind == "income" else "notify.finance.when.overdue",
                      days=abs(days_left))
            severity = "critical"
        else:
            title_key, emoji = f"notify.finance.due.{kind}", "💰" if kind == "income" else "💸"
            when = (
                tr("notify.finance.when.today") if days_left == 0
                else tr("notify.finance.when.tomorrow") if days_left == 1
                else tr("notify.finance.when.in_days", days=days_left)
            )
            severity = "warning" if days_left <= 1 else "info"
        card = reminder_card(item, title_key, when, emoji)

        try:
            await create_notification(
                title=card.title_text(),
                body=card.body_text(),
                telegram_card=card,
                type="finance",
                severity=severity,
                source="finance",
                source_id=str(item["id"]),
                link="/finance",
                group_key=f"finance:{item['id']}",
                channels=["telegram", "in_app"],
                topic_type="finance",
                event="finance.payment_due",
            )
            await db_service.update_finance_item(item["id"], last_reminded_at=today)
            sent += 1
        except Exception as e:
            logger.warning("Finance reminder failed for item %s: %s", item["id"], e)

    if sent:
        logger.info("Finance reminders sent: %d", sent)
    return sent


async def reminders_loop() -> None:
    """Цикл напоминаний (запускается в lifespan)."""
    from shared import timefmt

    await asyncio.sleep(300)
    while True:
        try:
            now_local = timefmt.now()
            if is_send_time(now_local, _reminder_hour()):
                await check_and_send_reminders(today=now_local.date())
        except Exception as e:
            logger.warning("Finance reminders loop failed: %s", e)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

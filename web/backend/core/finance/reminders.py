"""Напоминания о предстоящих и просроченных платежах: списаниях и ожидаемых поступлениях.

Суточная логика с защитой от дублей через finance_items.last_reminded_at:
одно напоминание на запись в день, только на порогах finance_reminder_days
(например 7/3/1 дней до списания) и при просрочке. Кнопки в Telegram:
«Оплачено» (платёж + сдвиг цикла) и «Пропустить цикл» (сдвиг без платежа) —
обрабатываются ботом (fin:paid / fin:skip).
"""
import asyncio
import logging
from datetime import date
from html import escape
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 3600  # проверяем каждый час, шлём максимум раз в день


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


def _item_keyboard(item: Dict) -> Dict:
    rows = [[
        {"text": "✅ Получено" if item.get("kind") == "income" else "✅ Оплачено", "callback_data": f"fin:paid:{item['id']}"},
        {"text": "⏭️ Пропустить", "callback_data": f"fin:skip:{item['id']}"},
    ]]
    if item.get("url"):
        rows.append([{"text": "🔗 Открыть кабинет", "url": item["url"]}])
    return {"inline_keyboard": rows}


def _fmt_amount(item: Dict) -> str:
    return f"{item['amount']:,.2f}".replace(",", " ") + f" {item['currency']}"


def _fmt_date(iso: Optional[str]) -> str:
    try:
        return date.fromisoformat(iso or "").strftime("%d.%m.%Y")
    except ValueError:
        return iso or ""


def _telegram_body(item: Dict, when: str) -> str:
    """HTML-карточка для Telegram: сумма/срок и мета в цитате."""
    amount = (
        f"<b>{escape(_fmt_amount(item))}</b>" if item.get("amount")
        else "<i>сумма не указана</i>"
    )
    lines = [f"💰 {amount} · {escape(when)} ({_fmt_date(item.get('next_due_at'))})"]
    meta = " · ".join(x for x in (
        f"🏢 {escape(item['provider_name'])}" if item.get("provider_name") else None,
        f"🗂 {escape(item['category_name'])}" if item.get("category_name") else None,
    ) if x)
    if meta:
        lines.append(meta)
    return "<blockquote>" + "\n".join(lines) + "</blockquote>"


async def check_and_send_reminders() -> int:
    """Один проход: найти записи на порогах/просроченные, отправить, отметить."""
    from shared.database import db_service
    from shared.config_service import config_service
    from web.backend.core.notification_service import create_notification

    if not config_service.get("finance_reminders_enabled", True):
        return 0
    if not db_service.is_connected:
        return 0

    thresholds = set(_reminder_days())
    today = date.today()
    sent = 0

    horizon = max(thresholds) if thresholds else 7
    for item in await db_service.upcoming_finance_payments(days=horizon):
        days_left = item["days_left"]
        overdue = item["is_overdue"]
        if not overdue and days_left not in thresholds:
            continue
        if item.get("last_reminded_at") == today.isoformat():
            continue  # уже напоминали сегодня

        # Доход ждут, а не платят: «скоро списание» про ожидаемое поступление
        # пугало и сбивало с толку — формулировка зависит от вида записи.
        income = item.get("kind") == "income"
        if overdue:
            if income:
                title = f"⚠️ Поступление задерживается — {item['name']}"
                when = f"ожидалось {abs(days_left)} дн. назад"
            else:
                title = f"⚠️ Просрочен платёж — {item['name']}"
                when = f"просрочен на {abs(days_left)} дн."
            severity = "critical"
        else:
            title = f"{'💰 Скоро поступление' if income else '💸 Скоро списание'} — {item['name']}"
            when = (
                "сегодня" if days_left == 0
                else "завтра" if days_left == 1
                else f"через {days_left} дн."
            )
            severity = "warning" if days_left <= 1 else "info"

        # плоский текст — в БД/in-app; HTML-карточка — в Telegram
        lines = [f"Сумма: {_fmt_amount(item)}", f"Дата: {item['next_due_at']} ({when})"]
        if item.get("provider_name"):
            lines.append(f"Провайдер: {item['provider_name']}")
        if item.get("category_name"):
            lines.append(f"Категория: {item['category_name']}")
        if item.get("url"):
            lines.append(f"Кабинет: {item['url']}")

        try:
            await create_notification(
                title=title,
                body="\n".join(lines),
                telegram_body=_telegram_body(item, when),
                type="finance",
                severity=severity,
                source="finance",
                source_id=str(item["id"]),
                group_key=f"finance:{item['id']}",
                channels=["telegram", "in_app"],
                topic_type="finance",
                reply_markup=_item_keyboard(item),
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
    """Часовой цикл напоминаний (запускается в lifespan)."""
    await asyncio.sleep(300)
    while True:
        try:
            await check_and_send_reminders()
        except Exception as e:
            logger.warning("Finance reminders loop failed: %s", e)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)

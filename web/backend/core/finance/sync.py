"""Автосинк балансов и услуг с клиентских API хостеров.

Раз в finance_autosync_interval_hours (и по кнопке «Синк сейчас»):
- баланс аккаунта -> finance_provider_accounts.balance + дневной снапшот;
- услуги -> finance_provider_accounts.services (JSONB), даты списаний
  совпадающих по имени finance_items подтягиваются к данным хостера;
- баланс ниже порога -> ТГ/панель-алерт (раз в день на аккаунт).
"""
import asyncio
import json
import logging
from datetime import date
from typing import Any, Dict, Optional

from shared.i18n import tr
from shared.tg_card import Button, Card, b

from web.backend.core.finance.adapters import AdapterError, get_adapter

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_HOURS = 6


def _fmt_money(amount: float, currency: Optional[str]) -> str:
    return f"{amount:,.2f}".replace(",", " ") + (f" {currency}" if currency else "")


async def _sync_due_dates(account: Dict[str, Any], services) -> int:
    """Подтянуть next_due_at записей провайдера к датам хостера (матч по имени)."""
    from shared.database import db_service

    updated = 0
    items = await db_service.list_finance_items(status="active")
    provider_items = {
        i["name"].strip().lower(): i for i in items
        if i.get("provider_id") == account["provider_id"]
    }
    for svc in services:
        if not svc.next_due_at:
            continue
        item = provider_items.get(svc.name.strip().lower())
        if not item or item.get("next_due_at") == svc.next_due_at:
            continue
        await db_service.update_finance_item(item["id"], next_due_at=svc.next_due_at)
        logger.info(
            "Finance sync: due date %s -> %s for item «%s» (from %s)",
            item.get("next_due_at"), svc.next_due_at, item["name"], account["provider_name"],
        )
        updated += 1
    return updated


async def _maybe_alert_low_balance(account: Dict[str, Any], balance: float, currency: Optional[str]) -> bool:
    """Алерт низкого баланса: порог per-account, антиспам раз в день."""
    from shared.database import db_service
    from web.backend.core.notification_service import create_notification

    threshold = account.get("low_balance_threshold")
    if threshold is None or balance >= float(threshold):
        return False
    if account.get("last_alerted_at") == date.today().isoformat():
        return False

    card = Card(tr("notify.finance.low_balance", provider=account["provider_name"]), emoji="🪫")
    card.fields([
        (tr("notify.finance.field.balance"), b(_fmt_money(balance, currency))),
        (tr("notify.finance.field.threshold"), _fmt_money(float(threshold), currency)),
    ])
    if account.get("provider_url"):
        card.buttons([Button(tr("notify.finance.btn.open"), url=account["provider_url"], style="primary")])
    card.stamp()
    try:
        await create_notification(
            title=card.title_text(),
            body=card.body_text(),
            telegram_card=card,
            type="finance",
            severity="warning",
            source="finance",
            source_id=str(account["id"]),
            link="/finance",
            group_key=f"finance:balance:{account['id']}",
            channels=["telegram", "in_app"],
            topic_type="finance",
            event="finance.low_balance",
        )
        await db_service.update_finance_account(account["id"], last_alerted_at=date.today())
        return True
    except Exception as e:
        logger.warning("Finance low-balance alert failed for account %s: %s", account["id"], e)
        return False


async def sync_account(account_id: int) -> Dict[str, Any]:
    """Синк одного аккаунта. Возвращает итог для API/лога."""
    from shared.database import db_service
    from web.backend.core.crypto import decrypt_field

    account = await db_service.get_finance_account(account_id)
    if not account:
        return {"status": "error", "error": "Account not found"}

    try:
        encrypted = await db_service.get_finance_account_credentials(account_id)
        credentials = json.loads(decrypt_field(encrypted or ""))
        adapter = get_adapter(account["adapter"])
        # имя хостера — контекстом во все строки адаптера (structlog
        # merge_contextvars): иначе «BILLmanager func=… недоступна» в логах
        # невозможно привязать к конкретному хостеру
        import structlog
        structlog.contextvars.bind_contextvars(hoster=account.get("name") or account["adapter"])
        try:
            result = await adapter.fetch(account.get("base_url"), credentials)
        finally:
            structlog.contextvars.unbind_contextvars("hoster")
    except (AdapterError, ValueError) as e:
        await db_service.set_finance_account_sync_result(account_id, ok=False, error=str(e))
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.warning("Finance sync failed for account %s: %s", account_id, e)
        await db_service.set_finance_account_sync_result(account_id, ok=False, error=str(e))
        return {"status": "error", "error": str(e)}

    await db_service.set_finance_account_sync_result(
        account_id, ok=True,
        balance=result.balance, currency=result.currency,
        services=[s.to_dict() for s in result.services],
    )

    alerted = False
    if result.balance is not None:
        await db_service.record_finance_balance_snapshot(
            account_id, result.balance, result.currency or "RUB",
        )
        alerted = await _maybe_alert_low_balance(account, result.balance, result.currency)

    due_updated = 0
    try:
        from shared.config_service import config_service
        if config_service.get("finance_autosync_update_due_dates", True):
            due_updated = await _sync_due_dates(account, result.services)
    except Exception as e:
        logger.warning("Finance sync: due-date sync failed for account %s: %s", account_id, e)

    return {
        "status": "ok",
        "balance": result.balance,
        "currency": result.currency,
        "services": len(result.services),
        "due_dates_updated": due_updated,
        "low_balance_alert": alerted,
    }


async def sync_all_accounts() -> Dict[str, Any]:
    """Один проход по всем auto_sync аккаунтам (последовательно, API щадим)."""
    from shared.database import db_service

    if not db_service.is_connected:
        return {"synced": 0, "errors": 0}

    synced = errors = 0
    for account in await db_service.list_finance_accounts(auto_sync_only=True):
        result = await sync_account(account["id"])
        if result.get("status") == "ok":
            synced += 1
        else:
            errors += 1
    if synced or errors:
        logger.info("Finance autosync: %d ok, %d errors", synced, errors)
    return {"synced": synced, "errors": errors}


async def autosync_loop() -> None:
    """Фоновый цикл автосинка (запускается в lifespan)."""
    from shared.config_service import config_service

    await asyncio.sleep(240)
    while True:
        try:
            if config_service.get("finance_autosync_enabled", True):
                await sync_all_accounts()
        except Exception as e:
            logger.warning("Finance autosync loop failed: %s", e)
        try:
            hours = float(config_service.get("finance_autosync_interval_hours", DEFAULT_INTERVAL_HOURS))
        except (TypeError, ValueError):
            hours = DEFAULT_INTERVAL_HOURS
        await asyncio.sleep(max(0.5, hours) * 3600)

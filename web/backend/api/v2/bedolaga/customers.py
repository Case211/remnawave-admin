"""Bedolaga customers — users, subscriptions, transactions, events."""
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request
from httpx import ConnectError, HTTPStatusError, TimeoutException
from pydantic import BaseModel, Field

from web.backend.api.deps import AdminUser, require_permission, get_client_ip
from web.backend.core.audit import write_audit_log
from shared.bedolaga_client import bedolaga_client

from web.backend.api.v2.bedolaga import ensure_configured, proxy_request

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──

class BalanceModifyRequest(BaseModel):
    amount_kopeks: int = Field(..., description="Amount in kopeks (positive=add, negative=subtract)")
    reason: Optional[str] = Field(None, max_length=500)


class SubscriptionCreateRequest(BaseModel):
    duration_days: int = Field(..., ge=1)
    traffic_limit_gb: Optional[float] = None
    device_limit: Optional[int] = None
    is_trial: bool = False


class SubscriptionExtendRequest(BaseModel):
    days: int = Field(..., ge=1)


class TrafficAddRequest(BaseModel):
    traffic_gb: float = Field(..., gt=0)


class DevicesAddRequest(BaseModel):
    count: int = Field(..., ge=1)


# ══════════════════════════════════════════════════════
# IMPORTANT: All static paths MUST come BEFORE /{user_id}
# otherwise FastAPI will try to parse "transactions" etc
# as an integer and return 422.
# ══════════════════════════════════════════════════════


# ── Users (list) ──

@router.get("")
async def list_users(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    promo_group_id: Optional[int] = Query(None),
    subscription_status: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
    order: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "view")),
):
    """Список клиентов Bedolaga Bot."""
    # Bedolaga API поддерживает только: limit, offset, status, promo_group_id, search
    # sort/order и subscription_status не поддерживаются — обрабатываем локально
    need_local = bool(subscription_status) or (sort and sort != "created_at") or (sort == "created_at" and order == "asc")

    if not need_local:
        return await proxy_request(lambda: bedolaga_client.list_users(
            limit=limit, offset=offset, status=status, search=search,
            promo_group_id=promo_group_id, sort=sort, order=order,
        ))

    # Bedolaga API не поддерживает subscription_status и некоторые sort поля —
    # забираем всех юзеров и обрабатываем на бэкенде
    all_items: list = []
    batch_size = 200
    batch_offset = 0
    while True:
        resp = await proxy_request(lambda o=batch_offset: bedolaga_client.list_users(
            limit=batch_size, offset=o, status=status, search=search,
            promo_group_id=promo_group_id,
        ))
        items = resp.get("items", []) if isinstance(resp, dict) else []
        all_items.extend(items)
        if len(items) < batch_size:
            break
        batch_offset += batch_size

    # Фильтрация по subscription status
    if subscription_status:
        def match_sub(user: dict) -> bool:
            sub = user.get("subscription")
            if subscription_status == "trial":
                return isinstance(sub, dict) and sub.get("is_trial") is True
            if subscription_status == "active":
                return isinstance(sub, dict) and sub.get("status") == "active" and not sub.get("is_trial")
            if subscription_status == "expired":
                return isinstance(sub, dict) and sub.get("status") == "expired"
            if subscription_status == "none":
                return not sub or not isinstance(sub, dict) or not sub.get("status")
            return True
        all_items = [u for u in all_items if match_sub(u)]

    # Сортировка
    if sort:
        reverse = order == "desc"
        if sort == "last_activity":
            all_items.sort(key=lambda u: u.get("last_activity") or "", reverse=reverse)
        elif sort == "balance":
            all_items.sort(key=lambda u: u.get("balance_kopeks") or 0, reverse=reverse)
        elif sort == "username":
            all_items.sort(key=lambda u: (u.get("username") or u.get("first_name") or "").lower(), reverse=reverse)
        elif sort == "created_at":
            all_items.sort(key=lambda u: u.get("created_at") or "", reverse=reverse)

    return {"items": all_items[offset:offset + limit], "total": len(all_items)}


# ── Transactions (static path — before /{user_id}) ──

@router.get("/transactions")
async def list_transactions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: Optional[int] = Query(None),
    transaction_type: Optional[str] = Query(None),
    payment_method: Optional[str] = Query(None),
    is_completed: Optional[bool] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "view")),
):
    """История транзакций."""
    return await proxy_request(lambda: bedolaga_client.list_transactions(
        limit=limit, offset=offset, user_id=user_id,
        transaction_type=transaction_type, payment_method=payment_method,
        is_completed=is_completed, date_from=date_from, date_to=date_to,
    ))


# ── Subscriptions list (static path — before /{user_id}) ──

@router.get("/subscriptions/list")
async def list_subscriptions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "view")),
):
    """Список подписок."""
    return await proxy_request(lambda: bedolaga_client.list_subscriptions(
        limit=limit, offset=offset, status=status, user_id=user_id,
    ))


@router.get("/subscriptions/{sub_id}")
async def get_subscription(
    sub_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "view")),
):
    """Детали подписки."""
    return await proxy_request(lambda: bedolaga_client.get_subscription(sub_id))


@router.post("/subscriptions/{sub_id}/extend")
async def extend_subscription(
    request: Request,
    sub_id: int = Path(...),
    data: SubscriptionExtendRequest = ...,
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "edit")),
):
    """Продлить подписку на N дней."""
    result = await proxy_request(lambda: bedolaga_client.extend_subscription(sub_id, data.model_dump()))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.subscription.extend", resource="bedolaga_customers",
        resource_id=str(sub_id), details=json.dumps(data.model_dump()),
        ip_address=get_client_ip(request),
    )
    return result


@router.post("/subscriptions/{sub_id}/traffic")
async def add_traffic(
    request: Request,
    sub_id: int = Path(...),
    data: TrafficAddRequest = ...,
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "edit")),
):
    """Добавить трафик к подписке."""
    result = await proxy_request(lambda: bedolaga_client.add_traffic(sub_id, data.model_dump()))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.subscription.traffic", resource="bedolaga_customers",
        resource_id=str(sub_id), details=json.dumps(data.model_dump()),
        ip_address=get_client_ip(request),
    )
    return result


@router.post("/subscriptions/{sub_id}/devices")
async def add_devices(
    request: Request,
    sub_id: int = Path(...),
    data: DevicesAddRequest = ...,
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "edit")),
):
    """Увеличить лимит устройств подписки."""
    result = await proxy_request(lambda: bedolaga_client.add_devices(sub_id, data.model_dump()))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.subscription.devices", resource="bedolaga_customers",
        resource_id=str(sub_id), details=json.dumps(data.model_dump()),
        ip_address=get_client_ip(request),
    )
    return result


@router.post("/subscriptions/{sub_id}/reset-devices")
async def reset_devices(
    request: Request,
    sub_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "edit")),
):
    """Сбросить устройства подписки."""
    result = await proxy_request(lambda: bedolaga_client.reset_devices(sub_id))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.subscription.reset_devices", resource="bedolaga_customers",
        resource_id=str(sub_id), details="{}",
        ip_address=get_client_ip(request),
    )
    return result


# ── User by telegram (static path — before /{user_id}) ──

@router.get("/by-telegram/{telegram_id}")
async def get_user_by_telegram(
    telegram_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "view")),
):
    """Найти клиента по Telegram ID."""
    return await proxy_request(lambda: bedolaga_client.get_user_by_telegram(telegram_id))


# ── Referrals (sub-paths of /{user_id} but defined before GET /{user_id}) ──
# Note: Bedolaga webapi doesn't have per-user referral endpoints.
# We fetch all users and filter by referred_by_id on our side.

# (referral endpoints removed — use /bedolaga/referrals/network for global graph)


# ── User detail (dynamic /{user_id} — MUST be last) ──

@router.get("/{user_id}")
async def get_user(
    user_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "view")),
):
    """Детальная информация о клиенте."""
    return await proxy_request(lambda: bedolaga_client.get_user(user_id))


@router.patch("/{user_id}")
async def update_user(
    request: Request,
    user_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "edit")),
):
    """Обновить данные клиента."""
    body = await request.json()
    result = await proxy_request(lambda: bedolaga_client.update_user(user_id, body))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.user.update", resource="bedolaga_customers",
        resource_id=str(user_id), details=json.dumps(body),
        ip_address=get_client_ip(request),
    )
    return result


# ── Balance ──

@router.post("/{user_id}/balance")
async def modify_balance(
    request: Request,
    user_id: int = Path(...),
    data: BalanceModifyRequest = ...,
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "edit")),
):
    """Изменить баланс клиента."""
    result = await proxy_request(lambda: bedolaga_client.modify_balance(user_id, data.model_dump()))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.user.balance", resource="bedolaga_customers",
        resource_id=str(user_id),
        details=json.dumps({"amount_kopeks": data.amount_kopeks, "reason": data.reason}),
        ip_address=get_client_ip(request),
    )
    return result


@router.post("/{user_id}/subscription")
async def create_subscription(
    request: Request,
    user_id: int = Path(...),
    data: SubscriptionCreateRequest = ...,
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "edit")),
):
    """Создать/заменить подписку клиента."""
    result = await proxy_request(lambda: bedolaga_client.create_subscription(user_id, data.model_dump()))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.subscription.create", resource="bedolaga_customers",
        resource_id=str(user_id), details=json.dumps(data.model_dump()),
        ip_address=get_client_ip(request),
    )
    return result


@router.delete("/{user_id}/subscription")
async def deactivate_subscription(
    request: Request,
    user_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "edit")),
):
    """Деактивировать подписку клиента."""
    result = await proxy_request(lambda: bedolaga_client.deactivate_subscription(user_id))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.subscription.deactivate", resource="bedolaga_customers",
        resource_id=str(user_id), details="{}",
        ip_address=get_client_ip(request),
    )
    return result


# ── Activity timeline (мягкая деградация на старых версиях бота) ──

# Лента активности появилась в боте отдельной ручкой Web API (BEDOLAGA-DEV#3266).
# На старой версии её нет, и запрос возвращает 404 — тогда раздел просто не
# показывается, вместо ошибки. Флаг кэшируем, чтобы не долбить бота на каждый
# просмотр карточки, и перепроверяем раз в 5 минут: обновили бота — заработало
# само, без правок у нас.
_ACTIVITY_RECHECK_SECONDS = 300
_activity_support = {"supported": True, "checked_at": 0.0}


def _activity_unavailable(limit: int, offset: int) -> dict:
    return {"items": [], "total": 0, "limit": limit, "offset": offset, "available": False}


def _is_user_not_found(response) -> bool:
    """404 про конкретного пользователя, а не про отсутствующую ручку."""
    try:
        detail = response.json().get("detail")
    except Exception:  # noqa: BLE001 — не JSON, значит и не наш detail
        return False
    return isinstance(detail, str) and "user not found" in detail.lower()


@router.get("/{user_id}/activity")
async def user_activity(
    user_id: int = Path(..., ge=1),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    types: Optional[str] = Query(None, description="CSV-фильтр по типам записей"),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "view")),
):
    """Лента активности клиента: платежи, подписка, действия в кабинете, входы."""
    ensure_configured()

    now = time.monotonic()
    if not _activity_support["supported"]:
        if now - _activity_support["checked_at"] < _ACTIVITY_RECHECK_SECONDS:
            return _activity_unavailable(limit, offset)
        _activity_support["supported"] = True

    try:
        data = await bedolaga_client.get_user_activity(user_id, limit=limit, offset=offset, types=types)
    except HTTPStatusError as e:
        if e.response.status_code == 404 and not _is_user_not_found(e.response):
            logger.info("Bedolaga: ручки активности нет — версия бота без неё, раздел скрыт")
            _activity_support.update({"supported": False, "checked_at": now})
            return _activity_unavailable(limit, offset)
        logger.warning("Bedolaga activity error: %s %s", e.response.status_code, e.response.text[:200])
        raise HTTPException(status_code=e.response.status_code, detail=f"Bedolaga API error: {e.response.status_code}")
    except (ConnectError, TimeoutException) as e:
        logger.warning("Bedolaga activity connection error: %s", e)
        raise HTTPException(status_code=502, detail="Cannot connect to Bedolaga API")

    _activity_support.update({"supported": True, "checked_at": now})
    return {**data, "available": True}

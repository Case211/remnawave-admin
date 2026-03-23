"""Bedolaga customers — users, subscriptions, transactions, events."""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Path, Request
from pydantic import BaseModel, Field

from web.backend.api.deps import AdminUser, require_permission, get_client_ip
from web.backend.core.rbac import write_audit_log
from shared.bedolaga_client import bedolaga_client

from web.backend.api.v2.bedolaga import proxy_request

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
    limit: int = Query(20, ge=1, le=100),
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
    return await proxy_request(lambda: bedolaga_client.list_users(
        limit=limit, offset=offset, status=status, search=search,
        promo_group_id=promo_group_id, subscription_status=subscription_status,
        sort=sort, order=order,
    ))


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


# ── Subscription Events (static path — before /{user_id}) ──

@router.get("/events")
async def list_events(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: Optional[int] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "view")),
):
    """События подписок (аудит)."""
    return await proxy_request(lambda: bedolaga_client.list_subscription_events(
        limit=limit, offset=offset, user_id=user_id,
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

@router.get("/{user_id}/referrals")
async def get_user_referrals(
    user_id: int = Path(...),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "view")),
):
    """Список рефералов пользователя."""
    return await proxy_request(lambda: bedolaga_client.get_user_referrals(user_id, limit=limit, offset=offset))


@router.get("/{user_id}/referral-stats")
async def get_user_referral_stats(
    user_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_customers", "view")),
):
    """Реферальная статистика пользователя."""
    return await proxy_request(lambda: bedolaga_client.get_user_referral_stats(user_id))


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

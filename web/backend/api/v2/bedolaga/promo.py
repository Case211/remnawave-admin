"""Bedolaga promo codes — CRUD, stats."""
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

class PromoCreateRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    type: str = "balance"
    balance_bonus_kopeks: int = 0
    subscription_days: int = 0
    max_uses: int = Field(default=1, ge=0)
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    is_active: bool = True


class PromoUpdateRequest(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    type: Optional[str] = None
    balance_bonus_kopeks: Optional[int] = None
    subscription_days: Optional[int] = None
    max_uses: Optional[int] = Field(None, ge=0)
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    is_active: Optional[bool] = None


# ── List / Get ──

@router.get("")
async def list_promos(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga_promo", "view")),
):
    """Список промокодов."""
    return await proxy_request(lambda: bedolaga_client.list_promos(
        limit=limit, offset=offset, is_active=is_active, search=search,
    ))


@router.get("/{promo_id}")
async def get_promo(
    promo_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_promo", "view")),
):
    """Детали промокода."""
    return await proxy_request(lambda: bedolaga_client.get_promo(promo_id))


@router.get("/{promo_id}/stats")
async def get_promo_stats(
    promo_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_promo", "view")),
):
    """Статистика использования промокода."""
    return await proxy_request(lambda: bedolaga_client.get_promo_stats(promo_id))


# ── Create / Update / Delete ──

@router.post("")
async def create_promo(
    request: Request,
    data: PromoCreateRequest,
    admin: AdminUser = Depends(require_permission("bedolaga_promo", "create")),
):
    """Создать промокод."""
    result = await proxy_request(lambda: bedolaga_client.create_promo(data.model_dump(exclude_none=True)))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.promo.create", resource="bedolaga_promo",
        resource_id=data.code, details=json.dumps(data.model_dump(exclude_none=True)),
        ip_address=get_client_ip(request),
    )
    return result


@router.patch("/{promo_id}")
async def update_promo(
    request: Request,
    promo_id: int = Path(...),
    data: PromoUpdateRequest = ...,
    admin: AdminUser = Depends(require_permission("bedolaga_promo", "edit")),
):
    """Обновить промокод."""
    payload = data.model_dump(exclude_none=True)
    result = await proxy_request(lambda: bedolaga_client.update_promo(promo_id, payload))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.promo.update", resource="bedolaga_promo",
        resource_id=str(promo_id), details=json.dumps(payload),
        ip_address=get_client_ip(request),
    )
    return result


@router.delete("/{promo_id}")
async def delete_promo(
    request: Request,
    promo_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_promo", "delete")),
):
    """Удалить промокод."""
    result = await proxy_request(lambda: bedolaga_client.delete_promo(promo_id))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.promo.delete", resource="bedolaga_promo",
        resource_id=str(promo_id), details="{}",
        ip_address=get_client_ip(request),
    )
    return result

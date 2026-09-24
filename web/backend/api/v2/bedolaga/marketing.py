"""Bedolaga marketing — campaigns (ad campaigns), broadcasts (bulk messages)."""
import json
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Path, Request
from pydantic import BaseModel, Field, model_validator

from web.backend.api.deps import AdminUser, require_permission, get_client_ip
from web.backend.core.audit import write_audit_log
from shared.bedolaga_client import bedolaga_client

from web.backend.api.v2.bedolaga import proxy_request

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──

# Поля — как у Bedolaga (CampaignCreateRequest / CampaignUpdateRequest).
# Раньше схема пропускала только имя, параметр и активность: тип бонуса и его
# размер отбрасывались, и Bedolaga отклоняла каждое создание кампании (422).
CampaignBonusType = Literal["balance", "subscription", "none", "tariff"]


class CampaignCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    start_parameter: str = Field(..., min_length=1, max_length=64)
    bonus_type: CampaignBonusType = "none"
    balance_bonus_kopeks: int = Field(0, ge=0)
    subscription_duration_days: Optional[int] = Field(None, ge=0)
    subscription_traffic_gb: Optional[int] = Field(None, ge=0)
    subscription_device_limit: Optional[int] = Field(None, ge=0)
    tariff_id: Optional[int] = Field(None, ge=1)
    tariff_duration_days: Optional[int] = Field(None, ge=1)
    is_active: bool = True

    @model_validator(mode="after")
    def _tariff_needs_id(self):
        # Бонус «тариф» без тарифа Бедолага примет, но клиент ничего не получит
        if self.bonus_type == "tariff" and not (self.tariff_id and self.tariff_duration_days):
            raise ValueError("tariff bonus needs tariff_id and tariff_duration_days")
        return self


class CampaignUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    start_parameter: Optional[str] = Field(None, max_length=64)
    bonus_type: Optional[CampaignBonusType] = None
    balance_bonus_kopeks: Optional[int] = Field(None, ge=0)
    subscription_duration_days: Optional[int] = Field(None, ge=0)
    subscription_traffic_gb: Optional[int] = Field(None, ge=0)
    subscription_device_limit: Optional[int] = Field(None, ge=0)
    tariff_id: Optional[int] = Field(None, ge=1)
    tariff_duration_days: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None


class BroadcastCreateRequest(BaseModel):
    target: str = Field(..., min_length=1, max_length=100)
    message_text: str = Field(..., min_length=1, max_length=4000)


# ── Campaigns ──

@router.get("/campaigns")
async def list_campaigns(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "view")),
):
    """Список рекламных кампаний."""
    return await proxy_request(lambda: bedolaga_client.list_campaigns(
        limit=limit, offset=offset,
    ))


@router.post("/campaigns")
async def create_campaign(
    request: Request,
    data: CampaignCreateRequest,
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "create")),
):
    """Создать кампанию."""
    result = await proxy_request(lambda: bedolaga_client.create_campaign(data.model_dump(exclude_none=True)))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.campaign.create", resource="bedolaga_marketing",
        resource_id=data.name, details=json.dumps(data.model_dump(exclude_none=True)),
        ip_address=get_client_ip(request),
    )
    return result


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(
    request: Request,
    campaign_id: int = Path(...),
    data: CampaignUpdateRequest = ...,
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "edit")),
):
    """Обновить кампанию."""
    payload = data.model_dump(exclude_none=True)
    result = await proxy_request(lambda: bedolaga_client.update_campaign(campaign_id, payload))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.campaign.update", resource="bedolaga_marketing",
        resource_id=str(campaign_id), details=json.dumps(payload),
        ip_address=get_client_ip(request),
    )
    return result


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    request: Request,
    campaign_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "delete")),
):
    """Удалить кампанию."""
    result = await proxy_request(lambda: bedolaga_client.delete_campaign(campaign_id))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.campaign.delete", resource="bedolaga_marketing",
        resource_id=str(campaign_id), details="{}",
        ip_address=get_client_ip(request),
    )
    return result


# ── Broadcasts ──

@router.get("/broadcasts")
async def list_broadcasts(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "view")),
):
    """Список рассылок."""
    return await proxy_request(lambda: bedolaga_client.list_broadcasts(
        limit=limit, offset=offset,
    ))


@router.post("/broadcasts")
async def create_broadcast(
    request: Request,
    data: BroadcastCreateRequest,
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "create")),
):
    """Создать рассылку."""
    result = await proxy_request(lambda: bedolaga_client.create_broadcast(data.model_dump()))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.broadcast.create", resource="bedolaga_marketing",
        resource_id=data.target, details=json.dumps(data.model_dump()),
        ip_address=get_client_ip(request),
    )
    return result


@router.post("/broadcasts/{broadcast_id}/stop")
async def stop_broadcast(
    request: Request,
    broadcast_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "edit")),
):
    """Остановить рассылку."""
    result = await proxy_request(lambda: bedolaga_client.stop_broadcast(broadcast_id))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.broadcast.stop", resource="bedolaga_marketing",
        resource_id=str(broadcast_id), details="{}",
        ip_address=get_client_ip(request),
    )
    return result


# ── Partners ──

@router.get("/partners")
async def list_partners(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "view")),
):
    """Список партнёров-рефереров."""
    return await proxy_request(lambda: bedolaga_client.list_partners(limit=limit, offset=offset))


@router.get("/partners/stats")
async def get_partner_stats(
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "view")),
):
    """Глобальная статистика партнёрской программы."""
    return await proxy_request(bedolaga_client.get_partner_global_stats)


@router.get("/partners/top")
async def get_top_referrers(
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "view")),
):
    """Топ-рефереры."""
    return await proxy_request(bedolaga_client.get_partner_top_referrers)


@router.get("/partners/{user_id}")
async def get_partner_detail(
    user_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "view")),
):
    """Детали партнёра с его рефералами."""
    return await proxy_request(lambda: bedolaga_client.get_partner(user_id))


@router.patch("/partners/{user_id}/commission")
async def update_partner_commission(
    request: Request,
    user_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "edit")),
):
    """Изменить комиссию партнёра."""
    body = await request.json()
    result = await proxy_request(lambda: bedolaga_client.update_partner_commission(user_id, body))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.partner.commission", resource="bedolaga_marketing",
        resource_id=str(user_id), details=json.dumps(body),
        ip_address=get_client_ip(request),
    )
    return result

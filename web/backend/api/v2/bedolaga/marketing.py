"""Bedolaga marketing — campaigns, mailings."""
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

class CampaignCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    message_text: str = Field(..., min_length=1, max_length=4096)
    target_audience: Optional[str] = Field(None, max_length=100)
    scheduled_at: Optional[str] = None
    promo_id: Optional[int] = None


class CampaignUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    message_text: Optional[str] = Field(None, min_length=1, max_length=4096)
    target_audience: Optional[str] = Field(None, max_length=100)
    scheduled_at: Optional[str] = None
    promo_id: Optional[int] = None


class MailingCreateRequest(BaseModel):
    subject: str = Field(..., min_length=1, max_length=200)
    message_text: str = Field(..., min_length=1, max_length=4096)
    target_audience: Optional[str] = Field(None, max_length=100)
    send_immediately: bool = False
    scheduled_at: Optional[str] = None


# ── Campaigns ──

@router.get("/campaigns")
async def list_campaigns(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "view")),
):
    """Список кампаний."""
    return await proxy_request(lambda: bedolaga_client.list_campaigns(
        limit=limit, offset=offset, status=status,
    ))


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "view")),
):
    """Детали кампании."""
    return await proxy_request(lambda: bedolaga_client.get_campaign(campaign_id))


@router.get("/campaigns/{campaign_id}/stats")
async def get_campaign_stats(
    campaign_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "view")),
):
    """Статистика кампании."""
    return await proxy_request(lambda: bedolaga_client.get_campaign_stats(campaign_id))


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


@router.post("/campaigns/{campaign_id}/send")
async def send_campaign(
    request: Request,
    campaign_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "edit")),
):
    """Запустить отправку кампании."""
    result = await proxy_request(lambda: bedolaga_client.send_campaign(campaign_id))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.campaign.send", resource="bedolaga_marketing",
        resource_id=str(campaign_id), details="{}",
        ip_address=get_client_ip(request),
    )
    return result


# ── Mailings ──

@router.get("/mailings")
async def list_mailings(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "view")),
):
    """Список рассылок."""
    return await proxy_request(lambda: bedolaga_client.list_mailings(
        limit=limit, offset=offset, status=status,
    ))


@router.get("/mailings/{mailing_id}")
async def get_mailing(
    mailing_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "view")),
):
    """Детали рассылки."""
    return await proxy_request(lambda: bedolaga_client.get_mailing(mailing_id))


@router.post("/mailings")
async def create_mailing(
    request: Request,
    data: MailingCreateRequest,
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "create")),
):
    """Создать рассылку."""
    result = await proxy_request(lambda: bedolaga_client.create_mailing(data.model_dump(exclude_none=True)))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.mailing.create", resource="bedolaga_marketing",
        resource_id=data.subject, details=json.dumps(data.model_dump(exclude_none=True)),
        ip_address=get_client_ip(request),
    )
    return result


@router.post("/mailings/{mailing_id}/cancel")
async def cancel_mailing(
    request: Request,
    mailing_id: int = Path(...),
    admin: AdminUser = Depends(require_permission("bedolaga_marketing", "edit")),
):
    """Отменить рассылку."""
    result = await proxy_request(lambda: bedolaga_client.cancel_mailing(mailing_id))
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="bedolaga.mailing.cancel", resource="bedolaga_marketing",
        resource_id=str(mailing_id), details="{}",
        ip_address=get_client_ip(request),
    )
    return result

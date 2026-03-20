"""Bedolaga dashboard — stats, health, status."""
from fastapi import APIRouter, Depends

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core.config import get_web_settings
from shared.bedolaga_client import bedolaga_client

from web.backend.api.v2.bedolaga import proxy_request

router = APIRouter()


@router.get("/overview")
async def get_overview(admin: AdminUser = Depends(require_permission("bedolaga", "view"))):
    """Общая статистика из Bedolaga Bot."""
    return await proxy_request(bedolaga_client.get_overview)


@router.get("/full")
async def get_full_stats(admin: AdminUser = Depends(require_permission("bedolaga", "view"))):
    """Полная статистика с историей."""
    return await proxy_request(bedolaga_client.get_full_stats)


@router.get("/health")
async def get_health(admin: AdminUser = Depends(require_permission("bedolaga", "view"))):
    """Статус здоровья Bedolaga Bot."""
    return await proxy_request(bedolaga_client.get_health)


@router.get("/status")
async def get_status(admin: AdminUser = Depends(require_permission("bedolaga", "view"))):
    """Проверить настроен ли Bedolaga API."""
    settings = get_web_settings()
    return {"configured": bool(settings.bedolaga_api_url and settings.bedolaga_api_token)}

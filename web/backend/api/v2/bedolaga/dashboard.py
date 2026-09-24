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


_capabilities_cache: dict = {}
_CAPABILITIES_TTL = 600


@router.get("/capabilities")
async def get_capabilities(admin: AdminUser = Depends(require_permission("bedolaga", "view"))):
    """Какие разделы админки работают на этой версии бота.

    Ленту активности клиента бот умеет только с недавних версий. Вместо 404 в
    карточке клиента дашборд сразу говорит, что именно недоступно.
    """
    import time
    cached = _capabilities_cache.get("data")
    if cached and time.monotonic() - cached[0] < _CAPABILITIES_TTL:
        return cached[1]
    from fastapi import HTTPException
    from web.backend.api.v2.bedolaga import customers
    activity = True
    try:
        result = await customers.user_activity(user_id=1, limit=1, offset=0, types=None, admin=admin)
        activity = bool(result.get("available", True))
    except HTTPException:
        # Ошибка про клиента (нет такого, бот недоступен) — не про версию:
        # отсутствующую ручку user_activity распознаёт сама и отвечает available=False
        pass
    data = {"activity": activity}
    _capabilities_cache["data"] = (time.monotonic(), data)
    return data


@router.get("/maintenance")
async def get_maintenance(admin: AdminUser = Depends(require_permission("bedolaga", "view"))):
    """Реальный статус техобслуживания Bedolaga Bot."""
    return await proxy_request(bedolaga_client.get_maintenance)


@router.get("/status")
async def get_status(admin: AdminUser = Depends(require_permission("bedolaga", "view"))):
    """Проверить настроен ли Bedolaga API."""
    settings = get_web_settings()
    return {"configured": bool(settings.bedolaga_api_url and settings.bedolaga_api_token)}

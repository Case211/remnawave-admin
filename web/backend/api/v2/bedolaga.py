"""Bedolaga Bot API proxy endpoints."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from httpx import HTTPStatusError, ConnectError, TimeoutException

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core.config import get_web_settings
from shared.bedolaga_client import bedolaga_client

logger = logging.getLogger(__name__)
router = APIRouter()


def _ensure_configured():
    """Lazily configure the Bedolaga client from settings."""
    if bedolaga_client.is_configured:
        return
    settings = get_web_settings()
    if not settings.bedolaga_api_url or not settings.bedolaga_api_token:
        raise HTTPException(
            status_code=503,
            detail="Bedolaga API is not configured. Set BEDOLAGA_API_URL and BEDOLAGA_API_TOKEN.",
        )
    bedolaga_client.configure(settings.bedolaga_api_url, settings.bedolaga_api_token)


async def _proxy_request(coro_fn):
    """Execute a Bedolaga API request with error handling."""
    _ensure_configured()
    try:
        return await coro_fn()
    except HTTPStatusError as e:
        logger.warning("Bedolaga API error: %s %s", e.response.status_code, e.response.text[:200])
        raise HTTPException(status_code=e.response.status_code, detail=f"Bedolaga API error: {e.response.status_code}")
    except (ConnectError, TimeoutException) as e:
        logger.warning("Bedolaga API connection error: %s", e)
        raise HTTPException(status_code=502, detail="Cannot connect to Bedolaga API")
    except Exception as e:
        logger.error("Bedolaga API unexpected error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error while contacting Bedolaga API")


@router.get("/overview")
async def get_overview(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Общая статистика из Bedolaga Bot."""
    data = await _proxy_request(bedolaga_client.get_overview)
    logger.info("Bedolaga overview keys: %s", list(data.keys()) if isinstance(data, dict) else type(data))
    for k, v in (data.items() if isinstance(data, dict) else []):
        if isinstance(v, dict):
            logger.info("  %s keys: %s", k, list(v.keys()))
    return data


@router.get("/full")
async def get_full_stats(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Полная статистика с историей из Bedolaga Bot."""
    return await _proxy_request(bedolaga_client.get_full_stats)


@router.get("/health")
async def get_health(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Статус здоровья Bedolaga Bot."""
    data = await _proxy_request(bedolaga_client.get_health)
    logger.info("Bedolaga health: %s", data)
    return data


@router.get("/status")
async def get_status(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Проверить настроен ли Bedolaga API."""
    settings = get_web_settings()
    return {
        "configured": bool(settings.bedolaga_api_url and settings.bedolaga_api_token),
    }

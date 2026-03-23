"""Bedolaga Bot API proxy — package root."""
import logging

from fastapi import APIRouter, HTTPException
from httpx import HTTPStatusError, ConnectError, TimeoutException

from web.backend.core.config import get_web_settings
from shared.bedolaga_client import bedolaga_client

logger = logging.getLogger(__name__)


def ensure_configured():
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


async def proxy_request(coro_fn):
    """Execute a Bedolaga API request with error handling."""
    ensure_configured()
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


# Import routers AFTER defining helpers (avoids circular import)
from .dashboard import router as dashboard_router  # noqa: E402
from .customers import router as customers_router  # noqa: E402
from .promo import router as promo_router  # noqa: E402
from .marketing import router as marketing_router  # noqa: E402

router = APIRouter()
router.include_router(dashboard_router, tags=["bedolaga-dashboard"])
router.include_router(customers_router, prefix="/customers", tags=["bedolaga-customers"])
router.include_router(promo_router, prefix="/promo", tags=["bedolaga-promo"])
router.include_router(marketing_router, prefix="/marketing", tags=["bedolaga-marketing"])

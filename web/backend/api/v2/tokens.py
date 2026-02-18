"""API tokens management — proxy to Remnawave Panel API.

NOTE: Remnawave Panel's /api/tokens endpoints are forbidden for API-key auth
and require admin JWT-token. We use local DB as primary source via data_access,
with graceful fallback when API is unavailable.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from web.backend.api.deps import AdminUser, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()


class TokenCreate(BaseModel):
    tokenName: str


@router.get("")
async def list_tokens(
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """List all API tokens. Uses local DB first, API fallback."""
    from shared.data_access import get_all_tokens

    tokens = await get_all_tokens()
    # Mask token values in list
    for t in tokens:
        if "token" in t and t["token"]:
            val = t["token"]
            t["token"] = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"
    return {"items": tokens, "total": len(tokens)}


@router.post("")
async def create_token(
    data: TokenCreate,
    admin: AdminUser = Depends(require_permission("resources", "create")),
):
    """Create a new API token."""
    try:
        from shared.api_client import api_client
        result = await api_client.create_token(data.tokenName)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to create token: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.delete("/{token_uuid}")
async def delete_token(
    token_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "delete")),
):
    """Delete an API token."""
    try:
        from shared.api_client import api_client
        await api_client.delete_token(token_uuid)
        return {"status": "ok"}
    except Exception as e:
        logger.error("Failed to delete token: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

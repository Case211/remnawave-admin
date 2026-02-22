"""Config profiles management — proxy to Remnawave Panel API."""
import logging

from fastapi import APIRouter, Depends, HTTPException

from web.backend.api.deps import AdminUser, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def list_config_profiles(
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """List all config profiles."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_config_profiles()
        payload = result.get("response", {})
        profiles = payload.get("configProfiles", []) if isinstance(payload, dict) else []
        return {"items": profiles, "total": len(profiles)}
    except Exception as e:
        logger.error("Failed to list config profiles: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/inbounds")
async def list_inbounds(
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """List all inbounds."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_all_inbounds()
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to list inbounds: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{profile_uuid}")
async def get_config_profile(
    profile_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """Get a single config profile."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_config_profile_by_uuid(profile_uuid)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to get config profile: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{profile_uuid}/computed-config")
async def get_computed_config(
    profile_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """Get the computed (expanded) config for a profile."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_config_profile_computed(profile_uuid)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to get computed config: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

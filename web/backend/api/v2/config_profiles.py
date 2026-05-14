"""Config profiles management — proxy to Remnawave Panel API."""
import json
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from web.backend.api.deps import AdminUser, get_client_ip, require_permission
from web.backend.core.rbac import write_audit_log

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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


@router.get("/{profile_uuid}/inbounds")
async def list_profile_inbounds(
    profile_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """List inbounds for a specific config profile."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_inbounds_by_profile_uuid(profile_uuid)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to list profile inbounds: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


@router.patch("/{profile_uuid}")
async def update_config_profile(
    profile_uuid: str,
    request: Request,
    config: dict = Body(...),
    admin: AdminUser = Depends(require_permission("resources", "edit")),
):
    """Patch a config profile's xray-config JSON (used by xray-editor page)."""
    try:
        from shared.api_client import api_client
        # Panel expects the JSON payload `{ uuid, config }` to PATCH /api/config-profiles.
        result = await api_client.update_config_profile({"uuid": profile_uuid, "config": config})
    except Exception as e:
        logger.error("Failed to update config profile %s: %s", profile_uuid, e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")

    try:
        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="config_profile.update",
            resource="resources",
            resource_id=profile_uuid,
            details=json.dumps({"keys": sorted(list(config.keys()))[:20]}) if isinstance(config, dict) else None,
            ip_address=get_client_ip(request),
        )
    except Exception as e:
        logger.warning("Audit log for config_profile.update failed: %s", e)

    return result.get("response", result)

"""Subscription templates management — proxy to Remnawave Panel API."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from web.backend.api.deps import AdminUser, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()


class TemplateCreate(BaseModel):
    name: str
    templateType: str  # XRAY_JSON, XRAY_BASE64, MIHOMO, STASH, CLASH, SINGBOX


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    templateJson: Optional[dict] = None


class ReorderItem(BaseModel):
    uuid: str
    viewPosition: int


class ReorderRequest(BaseModel):
    items: list[ReorderItem]


@router.get("")
async def list_templates(
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """List all subscription templates."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_templates()
        payload = result.get("response", {})
        templates = payload.get("subscriptionTemplates", []) if isinstance(payload, dict) else []
        return {"items": templates, "total": len(templates)}
    except Exception as e:
        logger.error("Failed to list templates: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/{template_uuid}")
async def get_template(
    template_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """Get a single template by UUID."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_template(template_uuid)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to get template: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("")
async def create_template(
    data: TemplateCreate,
    admin: AdminUser = Depends(require_permission("resources", "create")),
):
    """Create a new subscription template."""
    try:
        from shared.api_client import api_client
        result = await api_client.create_template(data.name, data.templateType)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to create template: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.patch("/{template_uuid}")
async def update_template(
    template_uuid: str,
    data: TemplateUpdate,
    admin: AdminUser = Depends(require_permission("resources", "edit")),
):
    """Update a subscription template."""
    try:
        from shared.api_client import api_client
        result = await api_client.update_template(
            uuid=template_uuid,
            name=data.name,
            template_json=data.templateJson,
        )
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to update template: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.delete("/{template_uuid}")
async def delete_template(
    template_uuid: str,
    admin: AdminUser = Depends(require_permission("resources", "delete")),
):
    """Delete a subscription template."""
    try:
        from shared.api_client import api_client
        await api_client.delete_template(template_uuid)
        return {"status": "ok"}
    except Exception as e:
        logger.error("Failed to delete template: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/reorder")
async def reorder_templates(
    data: ReorderRequest,
    admin: AdminUser = Depends(require_permission("resources", "edit")),
):
    """Reorder subscription templates."""
    try:
        from shared.api_client import api_client
        items = [{"uuid": item.uuid, "viewPosition": item.viewPosition} for item in data.items]
        result = await api_client.reorder_templates(items)
        return result.get("response", {"status": "ok"})
    except Exception as e:
        logger.error("Failed to reorder templates: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

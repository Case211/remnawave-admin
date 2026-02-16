"""Config snippets management — proxy to Remnawave Panel API."""
import logging
from typing import Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from web.backend.api.deps import AdminUser, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()


class SnippetCreate(BaseModel):
    name: str
    snippet: Union[list, dict]


class SnippetUpdate(BaseModel):
    name: str
    snippet: Union[list, dict]


class SnippetDelete(BaseModel):
    name: str


@router.get("")
async def list_snippets(
    admin: AdminUser = Depends(require_permission("resources", "view")),
):
    """List all config snippets."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_snippets()
        snippets = result.get("response", [])
        return {"items": snippets, "total": len(snippets)}
    except Exception as e:
        logger.error("Failed to list snippets: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("")
async def create_snippet(
    data: SnippetCreate,
    admin: AdminUser = Depends(require_permission("resources", "create")),
):
    """Create a new config snippet."""
    try:
        from shared.api_client import api_client
        result = await api_client.create_snippet(data.name, data.snippet)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to create snippet: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.patch("")
async def update_snippet(
    data: SnippetUpdate,
    admin: AdminUser = Depends(require_permission("resources", "edit")),
):
    """Update a config snippet."""
    try:
        from shared.api_client import api_client
        result = await api_client.update_snippet(data.name, data.snippet)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to update snippet: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.delete("")
async def delete_snippet(
    data: SnippetDelete,
    admin: AdminUser = Depends(require_permission("resources", "delete")),
):
    """Delete a config snippet."""
    try:
        from shared.api_client import api_client
        result = await api_client.delete_snippet(data.name)
        return {"status": "ok"}
    except Exception as e:
        logger.error("Failed to delete snippet: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

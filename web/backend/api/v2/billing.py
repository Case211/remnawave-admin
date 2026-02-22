"""Infrastructure billing management — proxy to Remnawave Panel API."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from web.backend.api.deps import AdminUser, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Providers ──────────────────────────────────────────────────


class ProviderCreate(BaseModel):
    name: str
    faviconLink: Optional[str] = None
    loginUrl: Optional[str] = None


class ProviderUpdate(BaseModel):
    uuid: str
    name: Optional[str] = None
    faviconLink: Optional[str] = None
    loginUrl: Optional[str] = None


@router.get("/providers")
async def list_providers(
    admin: AdminUser = Depends(require_permission("billing", "view")),
):
    """List all infrastructure providers."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_infra_providers()
        response = result.get("response", {})
        providers = response.get("providers", []) if isinstance(response, dict) else []
        return {"items": providers, "total": len(providers)}
    except Exception as e:
        logger.error("Failed to list providers: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/providers/{provider_uuid}")
async def get_provider(
    provider_uuid: str,
    admin: AdminUser = Depends(require_permission("billing", "view")),
):
    """Get a single provider."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_infra_provider(provider_uuid)
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to get provider: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/providers")
async def create_provider(
    data: ProviderCreate,
    admin: AdminUser = Depends(require_permission("billing", "create")),
):
    """Create a new infrastructure provider."""
    try:
        from shared.api_client import api_client
        result = await api_client.create_infra_provider(
            name=data.name,
            favicon_link=data.faviconLink,
            login_url=data.loginUrl,
        )
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to create provider: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.patch("/providers")
async def update_provider(
    data: ProviderUpdate,
    admin: AdminUser = Depends(require_permission("billing", "edit")),
):
    """Update an infrastructure provider."""
    try:
        from shared.api_client import api_client
        result = await api_client.update_infra_provider(
            uuid=data.uuid,
            name=data.name,
            favicon_link=data.faviconLink,
            login_url=data.loginUrl,
        )
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to update provider: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.delete("/providers/{provider_uuid}")
async def delete_provider(
    provider_uuid: str,
    admin: AdminUser = Depends(require_permission("billing", "delete")),
):
    """Delete an infrastructure provider."""
    try:
        from shared.api_client import api_client
        await api_client.delete_infra_provider(provider_uuid)
        return {"status": "ok"}
    except Exception as e:
        logger.error("Failed to delete provider: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


# ── Billing History ────────────────────────────────────────────


class BillingRecordCreate(BaseModel):
    providerUuid: str
    amount: float
    billedAt: str


@router.get("/history")
async def list_billing_history(
    admin: AdminUser = Depends(require_permission("billing", "view")),
):
    """List billing history records."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_infra_billing_history()
        response = result.get("response", {})
        records = response.get("records", []) if isinstance(response, dict) else []
        return {"items": records, "total": len(records)}
    except Exception as e:
        logger.error("Failed to list billing history: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/history")
async def create_billing_record(
    data: BillingRecordCreate,
    admin: AdminUser = Depends(require_permission("billing", "create")),
):
    """Create a billing history record."""
    try:
        from shared.api_client import api_client
        result = await api_client.create_infra_billing_record(
            provider_uuid=data.providerUuid,
            amount=data.amount,
            billed_at=data.billedAt,
        )
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to create billing record: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.delete("/history/{record_uuid}")
async def delete_billing_record(
    record_uuid: str,
    admin: AdminUser = Depends(require_permission("billing", "delete")),
):
    """Delete a billing history record."""
    try:
        from shared.api_client import api_client
        await api_client.delete_infra_billing_record(record_uuid)
        return {"status": "ok"}
    except Exception as e:
        logger.error("Failed to delete billing record: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


# ── Billing Nodes ──────────────────────────────────────────────


class BillingNodeCreate(BaseModel):
    providerUuid: str
    nodeUuid: str
    nextBillingAt: Optional[str] = None


class BillingNodeUpdate(BaseModel):
    uuids: list[str]
    nextBillingAt: str


@router.get("/nodes")
async def list_billing_nodes(
    admin: AdminUser = Depends(require_permission("billing", "view")),
):
    """List all billing nodes with stats."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_infra_billing_nodes()
        data = result.get("response", {})
        return data
    except Exception as e:
        logger.error("Failed to list billing nodes: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/nodes")
async def create_billing_node(
    data: BillingNodeCreate,
    admin: AdminUser = Depends(require_permission("billing", "create")),
):
    """Associate a node with billing."""
    try:
        from shared.api_client import api_client
        result = await api_client.create_infra_billing_node(
            provider_uuid=data.providerUuid,
            node_uuid=data.nodeUuid,
            next_billing_at=data.nextBillingAt,
        )
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to create billing node: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.patch("/nodes")
async def update_billing_nodes(
    data: BillingNodeUpdate,
    admin: AdminUser = Depends(require_permission("billing", "edit")),
):
    """Update billing nodes next billing date."""
    try:
        from shared.api_client import api_client
        result = await api_client.update_infra_billing_nodes(
            uuids=data.uuids,
            next_billing_at=data.nextBillingAt,
        )
        return result.get("response", result)
    except Exception as e:
        logger.error("Failed to update billing nodes: %s", e)
        raise HTTPException(status_code=502, detail=str(e))


@router.delete("/nodes/{record_uuid}")
async def delete_billing_node(
    record_uuid: str,
    admin: AdminUser = Depends(require_permission("billing", "delete")),
):
    """Remove a billing node association."""
    try:
        from shared.api_client import api_client
        await api_client.delete_infra_billing_node(record_uuid)
        return {"status": "ok"}
    except Exception as e:
        logger.error("Failed to delete billing node: %s", e)
        raise HTTPException(status_code=502, detail=str(e))

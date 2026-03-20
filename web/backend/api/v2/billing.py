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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


# ── Summary ────────────────────────────────────────────────────


@router.get("/summary")
async def billing_summary(
    admin: AdminUser = Depends(require_permission("billing", "view")),
):
    """Aggregated billing summary for Dashboard widget."""
    try:
        from shared.api_client import api_client

        # Fetch providers and billing nodes in parallel for stats
        providers_result = await api_client.get_infra_providers()
        providers_resp = providers_result.get("response", {})
        providers = providers_resp.get("providers", []) if isinstance(providers_resp, dict) else []

        nodes_result = await api_client.get_infra_billing_nodes()
        nodes_data = nodes_result.get("response", {})
        stats = nodes_data.get("stats", {}) if isinstance(nodes_data, dict) else {}
        billing_nodes = nodes_data.get("billingNodes", []) if isinstance(nodes_data, dict) else []

        # Find nearest next billing date
        next_payment_date = None
        if isinstance(billing_nodes, list):
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            for bn in billing_nodes:
                nba = bn.get("nextBillingAt")
                if nba:
                    try:
                        dt = datetime.fromisoformat(nba.replace("Z", "+00:00"))
                        if dt > now and (next_payment_date is None or dt < next_payment_date):
                            next_payment_date = dt
                    except (ValueError, TypeError):
                        pass

        return {
            "total_providers": len(providers),
            "current_month_payments": stats.get("currentMonthPayments", 0),
            "total_spent": stats.get("totalSpent", 0),
            "upcoming_nodes": stats.get("upcomingNodesCount", 0),
            "next_payment_date": next_payment_date.isoformat() if next_payment_date else None,
            "total_billing_nodes": len(billing_nodes) if isinstance(billing_nodes, list) else 0,
        }
    except Exception as e:
        logger.error("Failed to get billing summary: %s", e)
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


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
        raise HTTPException(status_code=502, detail="Service temporarily unavailable")


# ══════════════════════════════════════════════════════════════════
# Financial Analytics
# ══════════════════════════════════════════════════════════════════


@router.get("/analytics/overview")
async def billing_analytics_overview(
    admin: AdminUser = Depends(require_permission("billing", "view")),
):
    """Financial analytics overview: cost/user, cost/GB, monthly breakdown."""
    from shared.api_client import api_client
    from shared.database import db_service

    try:
        # Fetch billing data from Panel API
        history_result = await api_client.get_infra_billing_history()
        history_resp = history_result.get("response", {})
        records = history_resp.get("records", []) if isinstance(history_resp, dict) else []

        nodes_result = await api_client.get_infra_billing_nodes()
        nodes_resp = nodes_result.get("response", {})
        stats = nodes_resp.get("stats", {}) if isinstance(nodes_resp, dict) else {}
        billing_nodes = nodes_resp.get("billingNodes", []) if isinstance(nodes_resp, dict) else []

        # Get user counts from DB
        user_counts = {"total": 0, "active": 0}
        total_traffic = 0
        if db_service.is_connected:
            user_counts = await db_service.get_users_count_by_status()
            total_traffic = user_counts.get("total_used_traffic_bytes", 0)

        total_users = user_counts.get("total", 0)
        active_users = user_counts.get("active", 0)
        total_spent = float(stats.get("totalSpent", 0) or 0)
        monthly_cost = float(stats.get("currentMonthPayments", 0) or 0)

        # Cost per user
        cost_per_user = round(monthly_cost / active_users, 2) if active_users > 0 else 0
        cost_per_user_total = round(total_spent / active_users, 2) if active_users > 0 else 0

        # Cost per GB
        total_traffic_gb = float(total_traffic) / (1024 ** 3) if total_traffic else 0
        cost_per_gb = round(total_spent / total_traffic_gb, 4) if total_traffic_gb > 1 else 0

        # Monthly breakdown from billing history
        from datetime import datetime, timezone
        monthly_data = {}
        for rec in records:
            if not isinstance(rec, dict):
                continue
            amount = float(rec.get("amount", 0) or 0)
            billed_at = rec.get("billedAt") or rec.get("billed_at")
            if billed_at and amount:
                try:
                    dt = datetime.fromisoformat(str(billed_at).replace("Z", "+00:00"))
                    month_key = dt.strftime("%Y-%m")
                    monthly_data[month_key] = monthly_data.get(month_key, 0) + amount
                except (ValueError, TypeError):
                    pass

        # Sort monthly data and compute trend
        monthly_sorted = sorted(monthly_data.items())
        monthly_series = [{"month": m, "amount": round(a, 2)} for m, a in monthly_sorted]

        # Cost per node
        cost_per_node = round(monthly_cost / len(billing_nodes), 2) if billing_nodes else 0

        return {
            "total_spent": round(total_spent, 2),
            "monthly_cost": round(monthly_cost, 2),
            "cost_per_user": cost_per_user,
            "cost_per_user_total": cost_per_user_total,
            "cost_per_gb": cost_per_gb,
            "cost_per_node": cost_per_node,
            "total_users": total_users,
            "active_users": active_users,
            "total_traffic_gb": round(total_traffic_gb, 2),
            "total_billing_nodes": len(billing_nodes) if isinstance(billing_nodes, list) else 0,
            "monthly_series": monthly_series,
        }
    except Exception as e:
        logger.error("Billing analytics failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to compute billing analytics")


@router.get("/analytics/per-node")
async def billing_per_node(
    admin: AdminUser = Depends(require_permission("billing", "view")),
):
    """Cost and utilization per billing node."""
    from shared.api_client import api_client
    from shared.database import db_service

    try:
        nodes_result = await api_client.get_infra_billing_nodes()
        nodes_resp = nodes_result.get("response", {})
        billing_nodes = nodes_resp.get("billingNodes", []) if isinstance(nodes_resp, dict) else []

        providers_result = await api_client.get_infra_providers()
        providers_resp = providers_result.get("response", {})
        providers = providers_resp.get("providers", []) if isinstance(providers_resp, dict) else []
        provider_map = {p["uuid"]: p.get("name", "Unknown") for p in providers if isinstance(p, dict) and "uuid" in p}

        # Get node metrics from DB
        node_metrics = {}
        if db_service.is_connected:
            async with db_service.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT uuid::text, name, is_connected, is_disabled, "
                    "cpu_usage, memory_usage, disk_usage "
                    "FROM nodes"
                )
                node_metrics = {r["uuid"]: dict(r) for r in rows}

        items = []
        for bn in billing_nodes:
            if not isinstance(bn, dict):
                continue
            node_uuid = bn.get("nodeUuid") or bn.get("node_uuid", "")
            provider_uuid = bn.get("providerUuid") or bn.get("provider_uuid", "")
            metrics = node_metrics.get(node_uuid, {})

            items.append({
                "node_uuid": node_uuid,
                "node_name": metrics.get("name", "Unknown"),
                "provider": provider_map.get(provider_uuid, "Unknown"),
                "next_billing_at": bn.get("nextBillingAt"),
                "is_connected": metrics.get("is_connected", False),
                "cpu_usage": metrics.get("cpu_usage"),
                "memory_usage": metrics.get("memory_usage"),
                "disk_usage": metrics.get("disk_usage"),
                "users_online": metrics.get("users_online", 0),
            })

        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.error("Billing per-node failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to compute per-node billing")

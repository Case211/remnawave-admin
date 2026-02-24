"""
Bedolaga integration API router.

Hybrid approach:
  - Static data (stats, users, subscriptions, transactions) → from local DB cache
  - Dynamic data (tickets, promos, polls, partners) → real-time proxy to Bedolaga API

All endpoints require 'bedolaga:view' permission minimum.
Write operations require 'bedolaga:edit'.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core.errors import api_error, E

logger = logging.getLogger(__name__)
router = APIRouter()


def _ensure_configured():
    """Check that Bedolaga client is configured."""
    from shared.bedolaga_client import bedolaga_client
    if not bedolaga_client.is_configured:
        raise api_error(503, E.BEDOLAGA_NOT_CONFIGURED)


def _ensure_db():
    """Check that database is available."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)


# ── Status & Health ──────────────────────────────────────────────

@router.get("/status")
async def get_bedolaga_status(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get Bedolaga integration status and health."""
    from shared.bedolaga_client import bedolaga_client
    from shared.bedolaga_sync import bedolaga_sync_service

    result = {
        "enabled": bedolaga_client.is_configured,
        "connected": False,
        "base_url": bedolaga_client._base_url if bedolaga_client.is_configured else None,
        "bot_version": None,
        "sync_running": bedolaga_sync_service.is_running,
        "initial_sync_done": bedolaga_sync_service.initial_sync_done,
        "last_sync": None,
    }

    if bedolaga_client.is_configured:
        try:
            health = await bedolaga_client.get_health()
            result["connected"] = True
            result["bot_version"] = health.get("version")
        except Exception as e:
            logger.warning("Bedolaga health check failed: %s", e)

    # Get sync status
    sync_statuses = await bedolaga_sync_service.get_sync_status()
    result["sync_entities"] = sync_statuses

    return result


# ── Sync Control ─────────────────────────────────────────────────

@router.post("/sync")
async def trigger_sync(
    entity: Optional[str] = Query(None, description="Entity to sync: stats, users, subscriptions, transactions. Omit for full sync."),
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Trigger manual sync of Bedolaga data."""
    _ensure_configured()
    _ensure_db()

    from shared.bedolaga_sync import bedolaga_sync_service

    if entity:
        sync_map = {
            "stats": bedolaga_sync_service.sync_stats,
            "users": bedolaga_sync_service.sync_users,
            "subscriptions": bedolaga_sync_service.sync_subscriptions,
            "transactions": bedolaga_sync_service.sync_transactions,
        }
        fn = sync_map.get(entity)
        if not fn:
            raise api_error(400, E.BEDOLAGA_INVALID_ENTITY, f"Unknown entity: {entity}")
        count = await fn()
        return {"entity": entity, "records_synced": count, "status": "ok"}

    results = await bedolaga_sync_service.full_sync()
    return {"entities": results, "status": "ok"}


@router.get("/sync/status")
async def get_sync_status(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get sync status for all Bedolaga entities."""
    from shared.bedolaga_sync import bedolaga_sync_service
    statuses = await bedolaga_sync_service.get_sync_status()
    return {"entities": statuses}


# ══════════════════════════════════════════════════════════════════
# STATIC DATA — served from local DB cache
# ══════════════════════════════════════════════════════════════════

# ── Overview Stats ───────────────────────────────────────────────

@router.get("/overview")
async def get_overview(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get latest Bedolaga overview stats from cached snapshot."""
    _ensure_db()
    from shared.database import db_service

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT total_users, active_subscriptions, total_revenue,
                   total_transactions, open_tickets, raw_data, snapshot_at
            FROM bedolaga_stats_snapshots
            ORDER BY snapshot_at DESC
            LIMIT 1
            """
        )

    if not row:
        return {
            "total_users": 0, "active_subscriptions": 0,
            "total_revenue": 0.0, "total_transactions": 0,
            "open_tickets": 0, "snapshot_at": None,
        }

    return {
        "total_users": row["total_users"],
        "active_subscriptions": row["active_subscriptions"],
        "total_revenue": float(row["total_revenue"]),
        "total_transactions": row["total_transactions"],
        "open_tickets": row["open_tickets"],
        "snapshot_at": row["snapshot_at"].isoformat() if row["snapshot_at"] else None,
        "raw_data": json.loads(row["raw_data"]) if row["raw_data"] else None,
    }


@router.get("/overview/history")
async def get_overview_history(
    limit: int = Query(30, ge=1, le=365),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get historical stats snapshots for charts."""
    _ensure_db()
    from shared.database import db_service

    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT total_users, active_subscriptions, total_revenue,
                   total_transactions, open_tickets, snapshot_at
            FROM bedolaga_stats_snapshots
            ORDER BY snapshot_at DESC
            LIMIT $1
            """,
            limit,
        )

    return {
        "items": [
            {
                "total_users": r["total_users"],
                "active_subscriptions": r["active_subscriptions"],
                "total_revenue": float(r["total_revenue"]),
                "total_transactions": r["total_transactions"],
                "open_tickets": r["open_tickets"],
                "snapshot_at": r["snapshot_at"].isoformat() if r["snapshot_at"] else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


# ── Users (cached) ──────────────────────────────────────────────

@router.get("/users")
async def list_users(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List Bedolaga users from local cache."""
    _ensure_db()
    from shared.database import db_service

    conditions = []
    params = []
    idx = 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if search:
        conditions.append(f"(username ILIKE ${idx} OR first_name ILIKE ${idx} OR CAST(telegram_id AS TEXT) LIKE ${idx})")
        params.append(f"%{search}%")
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with db_service.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM bedolaga_users_cache {where}", *params
        )
        rows = await conn.fetch(
            f"""
            SELECT id, telegram_id, username, first_name, last_name, status,
                   balance_kopeks, referral_code, has_had_paid_subscription,
                   created_at, last_activity, synced_at
            FROM bedolaga_users_cache
            {where}
            ORDER BY id DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params, limit, offset,
        )

    return {
        "items": [
            {
                "id": r["id"],
                "telegram_id": r["telegram_id"],
                "username": r["username"],
                "first_name": r["first_name"],
                "last_name": r["last_name"],
                "status": r["status"],
                "balance_rubles": float(r["balance_kopeks"] or 0) / 100.0,
                "referral_code": r["referral_code"],
                "has_had_paid_subscription": r["has_had_paid_subscription"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "last_activity": r["last_activity"].isoformat() if r["last_activity"] else None,
                "synced_at": r["synced_at"].isoformat() if r["synced_at"] else None,
            }
            for r in rows
        ],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get Bedolaga user details. Falls back to real-time API if not in cache."""
    _ensure_db()
    from shared.database import db_service

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM bedolaga_users_cache WHERE id = $1", user_id,
        )

    if row:
        data = dict(row)
        data["balance_rubles"] = float(data.pop("balance_kopeks", 0) or 0) / 100.0
        if data.get("raw_data") and isinstance(data["raw_data"], str):
            data["raw_data"] = json.loads(data["raw_data"])
        return data

    # Fallback to real-time
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_user(user_id)


# ── Subscriptions (cached) ──────────────────────────────────────

@router.get("/subscriptions")
async def list_subscriptions(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    is_trial: Optional[bool] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List Bedolaga subscriptions from local cache."""
    _ensure_db()
    from shared.database import db_service

    conditions = []
    params = []
    idx = 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if user_id is not None:
        conditions.append(f"user_id = ${idx}")
        params.append(user_id)
        idx += 1
    if is_trial is not None:
        conditions.append(f"is_trial = ${idx}")
        params.append(is_trial)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with db_service.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM bedolaga_subscriptions_cache {where}", *params
        )
        rows = await conn.fetch(
            f"""
            SELECT id, user_id, user_telegram_id, plan_name, status, is_trial,
                   started_at, expires_at, traffic_limit_bytes, traffic_used_bytes,
                   payment_amount, payment_provider, synced_at
            FROM bedolaga_subscriptions_cache
            {where}
            ORDER BY id DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params, limit, offset,
        )

    return {
        "items": [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "user_telegram_id": r["user_telegram_id"],
                "plan_name": r["plan_name"],
                "status": r["status"],
                "is_trial": r["is_trial"],
                "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
                "traffic_limit_bytes": r["traffic_limit_bytes"],
                "traffic_used_bytes": r["traffic_used_bytes"],
                "payment_amount": float(r["payment_amount"]) if r["payment_amount"] else None,
                "payment_provider": r["payment_provider"],
                "synced_at": r["synced_at"].isoformat() if r["synced_at"] else None,
            }
            for r in rows
        ],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


# ── Transactions (cached) ───────────────────────────────────────

@router.get("/transactions")
async def list_transactions(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user_id: Optional[int] = Query(None),
    provider: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List Bedolaga transactions from local cache."""
    _ensure_db()
    from shared.database import db_service

    conditions = []
    params = []
    idx = 1

    if user_id is not None:
        conditions.append(f"user_id = ${idx}")
        params.append(user_id)
        idx += 1
    if provider:
        conditions.append(f"provider = ${idx}")
        params.append(provider)
        idx += 1
    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if type:
        conditions.append(f"type = ${idx}")
        params.append(type)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with db_service.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM bedolaga_transactions_cache {where}", *params
        )
        rows = await conn.fetch(
            f"""
            SELECT id, user_id, user_telegram_id, amount, currency,
                   provider, status, type, created_at, synced_at
            FROM bedolaga_transactions_cache
            {where}
            ORDER BY created_at DESC NULLS LAST
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params, limit, offset,
        )

    return {
        "items": [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "user_telegram_id": r["user_telegram_id"],
                "amount": float(r["amount"]) if r["amount"] else 0.0,
                "currency": r["currency"],
                "provider": r["provider"],
                "status": r["status"],
                "type": r["type"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "synced_at": r["synced_at"].isoformat() if r["synced_at"] else None,
            }
            for r in rows
        ],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/transactions/stats")
async def get_transaction_stats(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get transaction statistics computed from local cache."""
    _ensure_db()
    from shared.database import db_service

    async with db_service.acquire() as conn:
        totals = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(amount), 0) as total_amount,
                COUNT(*) as total_count
            FROM bedolaga_transactions_cache
            WHERE status = 'completed' OR status = 'success'
            """
        )

        by_provider = await conn.fetch(
            """
            SELECT provider, COALESCE(SUM(amount), 0) as amount, COUNT(*) as count
            FROM bedolaga_transactions_cache
            WHERE (status = 'completed' OR status = 'success') AND provider IS NOT NULL
            GROUP BY provider
            ORDER BY amount DESC
            """
        )

        daily = await conn.fetch(
            """
            SELECT DATE(created_at) as day, COALESCE(SUM(amount), 0) as amount, COUNT(*) as count
            FROM bedolaga_transactions_cache
            WHERE (status = 'completed' OR status = 'success') AND created_at IS NOT NULL
            GROUP BY DATE(created_at)
            ORDER BY day DESC
            LIMIT 30
            """
        )

    return {
        "total_amount": float(totals["total_amount"]) if totals else 0.0,
        "total_count": totals["total_count"] if totals else 0,
        "by_provider": {
            r["provider"]: {"amount": float(r["amount"]), "count": r["count"]}
            for r in by_provider
        },
        "by_day": [
            {
                "day": r["day"].isoformat() if r["day"] else None,
                "amount": float(r["amount"]),
                "count": r["count"],
            }
            for r in daily
        ],
    }


# ── Revenue Analytics (computed from cache) ──────────────────────

@router.get("/revenue")
async def get_revenue(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get revenue analytics computed from cached transaction data."""
    _ensure_db()
    from shared.database import db_service

    async with db_service.acquire() as conn:
        total = await conn.fetchval(
            """
            SELECT COALESCE(SUM(amount), 0) FROM bedolaga_transactions_cache
            WHERE status IN ('completed', 'success')
            """
        )
        today = await conn.fetchval(
            """
            SELECT COALESCE(SUM(amount), 0) FROM bedolaga_transactions_cache
            WHERE status IN ('completed', 'success')
              AND created_at >= CURRENT_DATE
            """
        )
        week = await conn.fetchval(
            """
            SELECT COALESCE(SUM(amount), 0) FROM bedolaga_transactions_cache
            WHERE status IN ('completed', 'success')
              AND created_at >= CURRENT_DATE - INTERVAL '7 days'
            """
        )
        month = await conn.fetchval(
            """
            SELECT COALESCE(SUM(amount), 0) FROM bedolaga_transactions_cache
            WHERE status IN ('completed', 'success')
              AND created_at >= CURRENT_DATE - INTERVAL '30 days'
            """
        )

        by_provider = await conn.fetch(
            """
            SELECT provider, COALESCE(SUM(amount), 0) as amount
            FROM bedolaga_transactions_cache
            WHERE status IN ('completed', 'success') AND provider IS NOT NULL
            GROUP BY provider ORDER BY amount DESC
            """
        )

        daily = await conn.fetch(
            """
            SELECT DATE(created_at) as day, COALESCE(SUM(amount), 0) as amount
            FROM bedolaga_transactions_cache
            WHERE status IN ('completed', 'success') AND created_at IS NOT NULL
            GROUP BY DATE(created_at)
            ORDER BY day DESC LIMIT 30
            """
        )

    return {
        "total_revenue": float(total or 0),
        "revenue_today": float(today or 0),
        "revenue_week": float(week or 0),
        "revenue_month": float(month or 0),
        "by_provider": {r["provider"]: float(r["amount"]) for r in by_provider},
        "daily_chart": [
            {"day": r["day"].isoformat() if r["day"] else None, "amount": float(r["amount"])}
            for r in daily
        ],
    }


# ══════════════════════════════════════════════════════════════════
# DYNAMIC DATA — proxied to Bedolaga API in real-time
# ══════════════════════════════════════════════════════════════════

# ── Tickets ──────────────────────────────────────────────────────

@router.get("/tickets")
async def list_tickets(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List support tickets (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_tickets(
        limit=limit, offset=offset, status=status,
        priority=priority, user_id=user_id,
    )


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get ticket with conversation (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_ticket(ticket_id)


@router.post("/tickets/{ticket_id}/status")
async def update_ticket_status(
    ticket_id: int,
    data: dict,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Update ticket status (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.update_ticket_status(ticket_id, data.get("status", ""))


@router.post("/tickets/{ticket_id}/priority")
async def update_ticket_priority(
    ticket_id: int,
    data: dict,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Update ticket priority (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.update_ticket_priority(ticket_id, data.get("priority", ""))


@router.post("/tickets/{ticket_id}/reply")
async def reply_to_ticket(
    ticket_id: int,
    data: dict,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Reply to a ticket (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.reply_to_ticket(ticket_id, data.get("text", ""))


# ── Promo Groups ─────────────────────────────────────────────────

@router.get("/promo-groups")
async def list_promo_groups(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List promo groups (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_promo_groups(limit=limit, offset=offset)


@router.post("/promo-groups")
async def create_promo_group(
    data: dict,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Create promo group (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.create_promo_group(data)


@router.patch("/promo-groups/{group_id}")
async def update_promo_group(
    group_id: int,
    data: dict,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Update promo group (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.update_promo_group(group_id, data)


@router.delete("/promo-groups/{group_id}")
async def delete_promo_group(
    group_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Delete promo group (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.delete_promo_group(group_id)


# ── Promo Codes ──────────────────────────────────────────────────

@router.get("/promo-codes")
async def list_promo_codes(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    is_active: Optional[bool] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List promo codes (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_promo_codes(limit=limit, offset=offset, is_active=is_active)


@router.get("/promo-codes/{promocode_id}")
async def get_promo_code(
    promocode_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get promo code details (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_promo_code(promocode_id)


@router.post("/promo-codes")
async def create_promo_code(
    data: dict,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Create promo code (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.create_promo_code(data)


@router.patch("/promo-codes/{promocode_id}")
async def update_promo_code(
    promocode_id: int,
    data: dict,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Update promo code (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.update_promo_code(promocode_id, data)


@router.delete("/promo-codes/{promocode_id}")
async def delete_promo_code(
    promocode_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Delete promo code (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.delete_promo_code(promocode_id)


# ── Promo Offers ─────────────────────────────────────────────────

@router.get("/promo-offers")
async def list_promo_offers(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List promo offers (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_promo_offers(
        limit=limit, offset=offset, user_id=user_id, is_active=is_active,
    )


@router.post("/promo-offers")
async def create_promo_offer(
    data: dict,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Create promo offer (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.create_promo_offer(data)


@router.get("/promo-offers/templates")
async def list_promo_offer_templates(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List promo offer templates (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_promo_offer_templates()


@router.get("/promo-offers/logs")
async def list_promo_offer_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List promo offer operation logs (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_promo_offer_logs(limit=limit, offset=offset)


# ── Polls ────────────────────────────────────────────────────────

@router.get("/polls")
async def list_polls(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List polls (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_polls(limit=limit, offset=offset)


@router.get("/polls/{poll_id}")
async def get_poll(
    poll_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get poll details (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_poll(poll_id)


@router.post("/polls")
async def create_poll(
    data: dict,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Create poll (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.create_poll(data)


@router.delete("/polls/{poll_id}")
async def delete_poll(
    poll_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Delete poll (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.delete_poll(poll_id)


@router.get("/polls/{poll_id}/stats")
async def get_poll_stats(
    poll_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get poll statistics (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_poll_stats(poll_id)


# ── Partners / Referrals ─────────────────────────────────────────

@router.get("/partners")
async def list_partners(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List partners/referrers (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_partners(limit=limit, offset=offset, search=search)


@router.get("/partners/stats")
async def get_partner_stats(
    days: int = Query(30, ge=1, le=365),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get partner program statistics (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_partner_stats(days=days)


@router.get("/partners/{user_id}")
async def get_partner(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """Get partner details (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_partner(user_id, limit=limit, offset=offset)


# ── Broadcasts ───────────────────────────────────────────────────

@router.get("/broadcasts")
async def list_broadcasts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List broadcasts (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_broadcasts(limit=limit, offset=offset)


@router.post("/broadcasts")
async def create_broadcast(
    data: dict,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Create broadcast (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.create_broadcast(data)


@router.post("/broadcasts/{broadcast_id}/stop")
async def stop_broadcast(
    broadcast_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Stop broadcast (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.stop_broadcast(broadcast_id)


# ── Settings ─────────────────────────────────────────────────────

@router.get("/settings")
async def list_bedolaga_settings(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List Bedolaga settings (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_settings()


@router.get("/settings/categories")
async def list_bedolaga_setting_categories(
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List Bedolaga setting categories (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_setting_categories()


@router.put("/settings/{key}")
async def update_bedolaga_setting(
    key: str,
    data: dict,
    admin: AdminUser = Depends(require_permission("bedolaga", "edit")),
):
    """Update Bedolaga setting (proxied to Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.update_setting(key, data.get("value"))


# ── Logs ─────────────────────────────────────────────────────────

@router.get("/logs/monitoring")
async def list_monitoring_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List Bedolaga monitoring logs (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_monitoring_logs(
        limit=limit, offset=offset, event_type=event_type,
    )


@router.get("/logs/support")
async def list_support_logs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("bedolaga", "view")),
):
    """List Bedolaga support audit logs (real-time from Bedolaga)."""
    _ensure_configured()
    from shared.bedolaga_client import bedolaga_client
    return await bedolaga_client.get_support_logs(
        limit=limit, offset=offset, action=action,
    )

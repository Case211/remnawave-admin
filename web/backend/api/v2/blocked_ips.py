"""Blocked IPs CRUD API — manage IP-level blocking on VPN nodes."""
import ipaddress
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from shared.db_schema import NODES_TABLE
from shared.db_query import select_sql

from web.backend.api.deps import (
    AdminUser,
    get_client_ip,
    get_db,
    require_permission,
)
from web.backend.core.errors import E, api_error
from web.backend.core.rate_limit import RATE_MUTATIONS, RATE_READ, limiter
from web.backend.core.audit import write_audit_log
from web.backend.schemas.blocked_ip import (
    BlockedIPBulkCreate,
    BlockedIPCreate,
    BlockedIPItem,
    BlockedIPListResponse,
    BlockedIPUsersResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────


def _enrich_geoip(ip_cidr: str) -> dict:
    """Try to get GeoIP info for a single IP (not subnets)."""
    try:
        net = ipaddress.ip_network(ip_cidr, strict=False)
        if net.num_addresses == 1:
            from shared.geoip import get_geoip_service
            info = get_geoip_service().lookup(str(net.network_address))
            if info:
                return {
                    "country_code": getattr(info, "country_code", None),
                    "asn_org": getattr(info, "asn_org", None),
                }
    except Exception:
        pass
    return {}


async def push_blocklist_to_agents() -> int:
    """Push full blocklist to all connected agents. Returns count of successful pushes."""
    try:
        from shared.database import db_service
        from web.backend.core.agent_manager import agent_manager
        from web.backend.core.agent_hmac import sign_command_with_ts

        blocked = await db_service.get_all_active_blocked_ips()

        connected = agent_manager.list_connected()
        if not connected:
            return 0

        success = 0
        for node_uuid in connected:
            try:
                async with db_service.acquire() as conn:
                    row = await conn.fetchrow(
                        select_sql(NODES_TABLE, "agent_token", "WHERE uuid = $1"), node_uuid
                    )
                if not row or not row["agent_token"]:
                    continue

                cmd = {
                    "type": "sync_blocked_ips",
                    "ips": blocked,
                    "mode": "replace",
                }
                payload, sig = sign_command_with_ts(cmd, row["agent_token"])
                payload["_sig"] = sig
                sent = await agent_manager.send_command(node_uuid, payload)
                if sent:
                    success += 1
            except Exception as e:
                logger.warning("Failed to push blocklist to %s: %s", node_uuid, e)

        logger.info("Blocklist pushed to %d/%d agents (%d IPs)", success, len(connected), len(blocked))
        return success
    except Exception as e:
        logger.error("Failed to push blocklist: %s", e)
        return 0


# ── Endpoints ────────────────────────────────────────────────


@router.get("", response_model=BlockedIPListResponse)
@limiter.limit(RATE_READ)
async def list_blocked_ips(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_expired: bool = Query(False),
    admin: AdminUser = Depends(require_permission("blocked_ips", "view")),
    db=Depends(get_db),
):
    """List blocked IPs with pagination."""
    items = await db.get_blocked_ips(limit=limit, offset=offset, include_expired=include_expired)
    total = await db.get_blocked_ips_count(include_expired=include_expired)
    return BlockedIPListResponse(
        items=[BlockedIPItem(**{**item, "ip_cidr": str(item["ip_cidr"])}) for item in items],
        total=total,
    )


@router.get("/count")
@limiter.limit(RATE_READ)
async def blocked_ips_count(
    request: Request,
    admin: AdminUser = Depends(require_permission("blocked_ips", "view")),
    db=Depends(get_db),
):
    """Get count of active blocked IPs."""
    count = await db.get_blocked_ips_count()
    return {"count": count}


@router.get("/{block_id}/users", response_model=BlockedIPUsersResponse)
@limiter.limit(RATE_READ)
async def blocked_ip_users(
    request: Request,
    block_id: int,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    admin: AdminUser = Depends(require_permission("blocked_ips", "view")),
    db=Depends(get_db),
):
    """Кто заходил с этого адреса за окно — чтобы видеть, кого задела запись."""
    entry = await db.get_blocked_ip_by_id(block_id)
    if not entry:
        raise api_error(404, E.BLOCKED_IP_NOT_FOUND)

    ip_cidr = str(entry["ip_cidr"])
    users = await db.get_users_by_blocked_ip(ip_cidr, days=days, limit=limit)
    return BlockedIPUsersResponse(ip_cidr=ip_cidr, users=users, total=len(users))


@router.post("", response_model=BlockedIPItem, status_code=201)
@limiter.limit(RATE_MUTATIONS)
async def add_blocked_ip(
    request: Request,
    data: BlockedIPCreate,
    admin: AdminUser = Depends(require_permission("blocked_ips", "create")),
    db=Depends(get_db),
):
    """Add an IP or CIDR to the blocklist."""
    geo = _enrich_geoip(data.ip_cidr)

    expires_at = None
    if data.expires_in_hours:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=data.expires_in_hours)

    row = await db.add_blocked_ip(
        ip_cidr=data.ip_cidr,
        reason=data.reason,
        admin_id=admin.account_id,
        admin_username=admin.username,
        country_code=geo.get("country_code"),
        asn_org=geo.get("asn_org"),
        expires_at=expires_at,
    )
    if not row:
        raise api_error(409, E.BLOCKED_IP_DUPLICATE)

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="blocked_ips.add",
        resource="blocked_ips",
        resource_id=data.ip_cidr,
        details=data.reason,
        ip_address=get_client_ip(request),
    )

    # Push to agents (fire-and-forget style, don't block response)
    pushed = 0
    try:
        pushed = await push_blocklist_to_agents()
    except Exception as e:
        logger.warning("Failed to push blocklist after add: %s", e)

    await _notify_ip_blocked(db, row, admin.username, pushed)

    return BlockedIPItem(**{**row, "ip_cidr": str(row["ip_cidr"])})


async def _notify_ip_blocked(db, row: dict, admin_username: str, pushed: int) -> None:
    """Сказать в чат, что адрес закрыт — и кого это задело.

    Блокировка адреса режет весь трафик с него на ноду, а не только VPN, и по
    подсети может задеть живых абонентов. Раньше это происходило молча: в
    журнале аудита строка есть, а в чате — ничего.
    """
    from web.backend.core.blocked_ip_cards import blocked_ip_card
    from web.backend.core.notification_service import create_notification

    ip_cidr = str(row["ip_cidr"])
    try:
        users = await db.get_users_by_blocked_ip(ip_cidr, days=30, limit=20)
    except Exception as e:  # noqa: BLE001
        logger.debug("blocked ip card: users lookup failed for %s: %s", ip_cidr, e)
        users = []

    try:
        await create_notification(
            title="Адрес заблокирован",
            body=blocked_ip_card(row, users, pushed_nodes=pushed, admin_username=admin_username),
            type="alert",
            severity="warning",
            link="/blocking?tab=ip",
            source="blocked_ip",
            source_id=ip_cidr,
            channels=["in_app", "telegram"],
            topic_type="violations",
            event="violation.ip_blocked",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("blocked ip notification failed: %s", e)


@router.post("/bulk")
@limiter.limit(RATE_MUTATIONS)
async def bulk_add_blocked_ips(
    request: Request,
    data: BlockedIPBulkCreate,
    admin: AdminUser = Depends(require_permission("blocked_ips", "create")),
    db=Depends(get_db),
):
    """Bulk add IPs to the blocklist."""
    expires_at = None
    if data.expires_in_hours:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=data.expires_in_hours)

    added = 0
    skipped = 0
    for ip in data.ips:
        geo = _enrich_geoip(ip)
        row = await db.add_blocked_ip(
            ip_cidr=ip,
            reason=data.reason,
            admin_id=admin.account_id,
            admin_username=admin.username,
            country_code=geo.get("country_code"),
            asn_org=geo.get("asn_org"),
            expires_at=expires_at,
        )
        if row:
            added += 1
        else:
            skipped += 1

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="blocked_ips.bulk_add",
        resource="blocked_ips",
        details=f"added={added}, skipped={skipped}",
        ip_address=get_client_ip(request),
    )

    try:
        agents = await push_blocklist_to_agents()
    except Exception:
        agents = 0

    return {"added": added, "skipped": skipped, "synced_agents": agents}


@router.delete("/{ip_id}")
@limiter.limit(RATE_MUTATIONS)
async def remove_blocked_ip(
    request: Request,
    ip_id: int,
    admin: AdminUser = Depends(require_permission("blocked_ips", "delete")),
    db=Depends(get_db),
):
    """Remove an IP from the blocklist."""
    deleted = await db.remove_blocked_ip(ip_id)
    if not deleted:
        raise api_error(404, E.BLOCKED_IP_NOT_FOUND)

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="blocked_ips.remove",
        resource="blocked_ips",
        resource_id=str(ip_id),
        ip_address=get_client_ip(request),
    )

    try:
        await push_blocklist_to_agents()
    except Exception as e:
        logger.warning("Failed to push blocklist after remove: %s", e)

    return {"ok": True}


@router.post("/sync")
@limiter.limit(RATE_MUTATIONS)
async def sync_blocklist(
    request: Request,
    admin: AdminUser = Depends(require_permission("blocked_ips", "create")),
):
    """Force re-sync blocklist to all connected agents."""
    count = await push_blocklist_to_agents()
    return {"synced_agents": count}

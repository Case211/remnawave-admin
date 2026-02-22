"""Fleet management API endpoints.

Provides endpoints for listing agent v2 connection status
and querying the command execution log.
"""
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from web.backend.api.deps import AdminUser, get_client_ip, require_permission
from web.backend.core.agent_manager import agent_manager
from web.backend.core.rate_limit import limiter, RATE_ANALYTICS
from web.backend.core.rbac import write_audit_log

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────

class FleetAgentItem(BaseModel):
    """Agent v2 connection status for a node."""
    uuid: str
    name: str = ''
    address: str = ''
    agent_v2_connected: bool = False
    agent_v2_last_ping: Optional[str] = None


class FleetAgentsResponse(BaseModel):
    nodes: List[FleetAgentItem] = []
    connected_count: int = 0
    total_count: int = 0


class CommandLogEntry(BaseModel):
    id: int
    node_uuid: str
    admin_username: Optional[str] = None
    command_type: str
    command_data: Optional[str] = None
    status: str = 'pending'
    output: Optional[str] = None
    exit_code: Optional[int] = None
    started_at: str
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None


class CommandLogResponse(BaseModel):
    entries: List[CommandLogEntry] = []
    total: int = 0
    page: int = 1
    per_page: int = 50


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/agents", response_model=FleetAgentsResponse)
@limiter.limit(RATE_ANALYTICS)
async def get_fleet_agents(
    request: Request,
    admin: AdminUser = Depends(require_permission("fleet", "view")),
):
    """List all nodes with agent v2 connection status."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return FleetAgentsResponse()

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT uuid, name, address,
                       COALESCE(agent_v2_connected, false) as agent_v2_connected,
                       agent_v2_last_ping
                FROM nodes
                ORDER BY agent_v2_connected DESC, name
                """
            )

        items = []
        connected = 0
        for row in rows:
            is_connected = bool(row["agent_v2_connected"])
            # Cross-check with live connection manager
            node_uuid = str(row["uuid"])
            is_live = agent_manager.is_connected(node_uuid)
            actual_connected = is_connected and is_live

            last_ping = row["agent_v2_last_ping"]
            items.append(FleetAgentItem(
                uuid=node_uuid,
                name=row["name"] or '',
                address=row["address"] or '',
                agent_v2_connected=actual_connected,
                agent_v2_last_ping=last_ping.isoformat() if last_ping else None,
            ))
            if actual_connected:
                connected += 1

        return FleetAgentsResponse(
            nodes=items,
            connected_count=connected,
            total_count=len(items),
        )
    except Exception as e:
        logger.error("Error getting fleet agents: %s", e)
        return FleetAgentsResponse()


@router.get("/command-log", response_model=CommandLogResponse)
@limiter.limit(RATE_ANALYTICS)
async def get_command_log(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    node_uuid: Optional[str] = Query(None),
    command_type: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("fleet", "view")),
):
    """Get paginated command execution log."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return CommandLogResponse()

        async with db_service.acquire() as conn:
            # Build WHERE clause
            conditions = []
            params = []
            idx = 1

            if node_uuid:
                conditions.append(f"node_uuid = ${idx}")
                params.append(node_uuid)
                idx += 1

            if command_type:
                conditions.append(f"command_type = ${idx}")
                params.append(command_type)
                idx += 1

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            # Count
            total = await conn.fetchval(
                f"SELECT COUNT(*) FROM node_command_log {where}",
                *params,
            )

            # Fetch page
            offset = (page - 1) * per_page
            rows = await conn.fetch(
                f"""
                SELECT id, node_uuid, admin_username, command_type,
                       command_data, status, output, exit_code,
                       started_at, finished_at, duration_ms
                FROM node_command_log
                {where}
                ORDER BY started_at DESC
                LIMIT ${idx} OFFSET ${idx + 1}
                """,
                *params, per_page, offset,
            )

            entries = []
            for row in rows:
                started = row["started_at"]
                finished = row["finished_at"]
                entries.append(CommandLogEntry(
                    id=row["id"],
                    node_uuid=row["node_uuid"],
                    admin_username=row["admin_username"],
                    command_type=row["command_type"],
                    command_data=row["command_data"],
                    status=row["status"],
                    output=row["output"],
                    exit_code=row["exit_code"],
                    started_at=started.isoformat() if started else '',
                    finished_at=finished.isoformat() if finished else None,
                    duration_ms=row["duration_ms"],
                ))

            return CommandLogResponse(
                entries=entries,
                total=total or 0,
                page=page,
                per_page=per_page,
            )

    except Exception as e:
        logger.error("Error getting command log: %s", e)
        return CommandLogResponse()

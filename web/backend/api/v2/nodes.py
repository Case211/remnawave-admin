"""Nodes API endpoints."""
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException, Request

# Add src to path for importing bot services
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from web.backend.api.deps import get_current_admin, AdminUser, require_permission, require_quota, get_client_ip
from web.backend.core.errors import api_error, E
from web.backend.core.rbac import write_audit_log
from web.backend.core.api_helper import (
    fetch_nodes_from_api, fetch_nodes_realtime_usage,
    fetch_nodes_usage_by_range, _normalize,
)
from web.backend.schemas.node import NodeListItem, NodeDetail, NodeCreate, NodeUpdate
from web.backend.schemas.common import PaginatedResponse, SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def _ensure_node_snake_case(node: dict) -> dict:
    """Ensure node dict has snake_case keys for pydantic schemas."""
    result = dict(node)
    mappings = {
        'isDisabled': 'is_disabled',
        'isConnected': 'is_connected',
        'isXrayRunning': 'is_xray_running',
        'xrayVersion': 'xray_version',
        'trafficLimitBytes': 'traffic_limit_bytes',
        'trafficUsedBytes': 'traffic_used_bytes',
        'trafficTotalBytes': 'traffic_total_bytes',
        'trafficTodayBytes': 'traffic_today_bytes',
        'usersOnline': 'users_online',
        'createdAt': 'created_at',
        'updatedAt': 'updated_at',
        'lastSeenAt': 'last_seen_at',
        'cpuUsage': 'cpu_usage',
        'memoryUsage': 'memory_usage',
        'uptimeSeconds': 'uptime_seconds',
        'downloadSpeedBps': 'download_speed_bps',
        'uploadSpeedBps': 'upload_speed_bps',
    }
    for camel, snake in mappings.items():
        if camel in result and snake not in result:
            result[snake] = result[camel]
    # Fallback: traffic_total_bytes = traffic_used_bytes if not present
    if 'traffic_total_bytes' not in result and 'traffic_used_bytes' in result:
        result['traffic_total_bytes'] = result['traffic_used_bytes']
    # Derive is_xray_running: Panel API doesn't provide this field,
    # but if node is connected and has xray_version, xray is running
    if not result.get('is_xray_running') and not result.get('isXrayRunning'):
        if bool(result.get('is_connected') or result.get('isConnected')):
            xv = result.get('xray_version') or result.get('xrayVersion')
            if xv:
                result['is_xray_running'] = True
    return result


async def _get_nodes_list():
    """Get nodes from DB (normalized), fall back to API."""
    try:
        from shared.database import db_service
        if db_service.is_connected:
            nodes = await db_service.get_all_nodes()
            if nodes:
                # Normalize raw_data: flatten nested objects, add snake_case aliases
                return [_normalize(n) for n in nodes]
    except Exception as e:
        logger.debug("DB nodes fetch failed: %s", e)
    return await fetch_nodes_from_api()


@router.get("", response_model=PaginatedResponse[NodeListItem])
async def list_nodes(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=500),
    search: Optional[str] = Query(None, description="Search by name"),
    is_connected: Optional[bool] = Query(None, description="Filter by connection status"),
    admin: AdminUser = Depends(require_permission("nodes", "view")),
):
    """List nodes with pagination and filtering."""
    try:
        nodes = await _get_nodes_list()
        nodes = [_ensure_node_snake_case(n) for n in nodes]

        # Enrich with per-node today traffic from date-range endpoint (persistent)
        try:
            now = datetime.utcnow()
            today_str = now.strftime('%Y-%m-%d')
            tomorrow_str = (now + timedelta(days=1)).strftime('%Y-%m-%d')
            resp = await fetch_nodes_usage_by_range(
                start=today_str, end=tomorrow_str,
            )
            if resp:
                top_nodes = resp.get('topNodes', [])
                if isinstance(top_nodes, list):
                    today_map = {}
                    for tn in top_nodes:
                        uid = tn.get('uuid')
                        if uid:
                            try:
                                today_map[uid] = int(tn.get('total', 0) or 0)
                            except (ValueError, TypeError):
                                pass
                    for n in nodes:
                        val = today_map.get(n.get('uuid'))
                        if val is not None:
                            n['traffic_today_bytes'] = val
        except Exception as e:
            logger.debug("Date-range today traffic fetch failed: %s", e)

        # Enrich with realtime data (speed + fallback today traffic)
        try:
            realtime = await fetch_nodes_realtime_usage()
            rt_map = {r.get('nodeUuid'): r for r in realtime}
            for n in nodes:
                rt = rt_map.get(n.get('uuid'))
                if rt:
                    n['download_speed_bps'] = int(rt.get('downloadSpeedBps') or 0)
                    n['upload_speed_bps'] = int(rt.get('uploadSpeedBps') or 0)
                    if not n.get('traffic_today_bytes'):
                        try:
                            n['traffic_today_bytes'] = int(rt.get('totalBytes') or 0)
                        except (ValueError, TypeError):
                            pass
        except Exception as e:
            logger.debug("Realtime bandwidth fetch failed: %s", e)

        # Filter
        if search:
            search_lower = search.lower()
            nodes = [
                n for n in nodes
                if search_lower in (n.get('name') or '').lower()
                or search_lower in (n.get('address') or '').lower()
            ]

        if is_connected is not None:
            nodes = [
                n for n in nodes
                if bool(n.get('is_connected')) == is_connected
            ]

        # Sort by name
        nodes.sort(key=lambda x: x.get('name') or '')

        # Paginate
        total = len(nodes)
        start = (page - 1) * per_page
        end = start + per_page
        items = nodes[start:end]

        # Convert to schema
        node_items = []
        for n in items:
            try:
                node_items.append(NodeListItem(**n))
            except Exception as e:
                logger.debug("Failed to parse node %s: %s", n.get('uuid', '?'), e)

        return PaginatedResponse(
            items=node_items,
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page if total > 0 else 1,
        )

    except Exception as e:
        logger.error("Error listing nodes: %s", e)
        return PaginatedResponse(
            items=[],
            total=0,
            page=page,
            per_page=per_page,
            pages=1,
        )


@router.get("/{node_uuid}", response_model=NodeDetail)
async def get_node(
    node_uuid: str,
    admin: AdminUser = Depends(require_permission("nodes", "view")),
):
    """Get detailed node information."""
    try:
        node_data = None
        try:
            from shared.database import db_service
            if db_service.is_connected:
                node_data = await db_service.get_node_by_uuid(node_uuid)
        except Exception as e:
            logger.debug("Non-critical: %s", e)

        if not node_data:
            from shared.api_client import api_client
            raw = await api_client.get_node(node_uuid)
            node_data = raw.get('response', raw) if isinstance(raw, dict) else raw

        if not node_data:
            raise api_error(404, E.NODE_NOT_FOUND)

        return NodeDetail(**_ensure_node_snake_case(node_data))

    except HTTPException:
        raise
    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)


@router.post("", response_model=NodeDetail)
async def create_node(
    data: NodeCreate,
    request: Request,
    admin: AdminUser = Depends(require_permission("nodes", "create")),
    _quota: None = Depends(require_quota("nodes")),
):
    """Create a new node."""
    try:
        from shared.api_client import api_client

        result = await api_client.create_node(
            name=data.name,
            address=data.address,
            port=data.port,
        )

        # Upstream API wraps data in 'response' key
        node = result.get('response', result) if isinstance(result, dict) else result

        # Increment quota usage counter
        if admin.account_id is not None:
            from web.backend.core.rbac import increment_usage_counter
            await increment_usage_counter(admin.account_id, "nodes_created")

        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="node.create",
            resource="nodes",
            resource_id=node.get('uuid', '') if isinstance(node, dict) else '',
            details=json.dumps({"name": data.name, "address": data.address, "port": data.port}),
            ip_address=get_client_ip(request),
        )

        return NodeDetail(**_ensure_node_snake_case(node))

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{node_uuid}", response_model=NodeDetail)
async def update_node(
    node_uuid: str,
    data: NodeUpdate,
    request: Request,
    admin: AdminUser = Depends(require_permission("nodes", "edit")),
):
    """Update node fields."""
    try:
        from shared.api_client import api_client

        update_data = data.model_dump(exclude_unset=True)
        result = await api_client.update_node(node_uuid, **update_data)

        # Upstream API wraps data in 'response' key
        node = result.get('response', result) if isinstance(result, dict) else result

        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="node.update",
            resource="nodes",
            resource_id=node_uuid,
            details=json.dumps({"fields": list(update_data.keys())}),
            ip_address=get_client_ip(request),
        )

        return NodeDetail(**_ensure_node_snake_case(node))

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{node_uuid}", response_model=SuccessResponse)
async def delete_node(
    node_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("nodes", "delete")),
):
    """Delete a node."""
    try:
        from shared.api_client import api_client

        await api_client.delete_node(node_uuid)

        # Also remove from local DB so UI updates immediately
        try:
            from shared.database import db_service
            if db_service.is_connected:
                await db_service.delete_node(node_uuid)
        except Exception as e:
            logger.debug("Non-critical: %s", e)

        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="node.delete",
            resource="nodes",
            resource_id=node_uuid,
            details=json.dumps({"node_uuid": node_uuid}),
            ip_address=get_client_ip(request),
        )

        return SuccessResponse(message="Node deleted")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{node_uuid}/restart", response_model=SuccessResponse)
async def restart_node(
    node_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("nodes", "edit")),
):
    """Restart a node."""
    try:
        from shared.api_client import api_client

        await api_client.restart_node(node_uuid)

        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="node.restart",
            resource="nodes",
            resource_id=node_uuid,
            details=json.dumps({"node_uuid": node_uuid}),
            ip_address=get_client_ip(request),
        )

        return SuccessResponse(message="Node restart initiated")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{node_uuid}/enable", response_model=SuccessResponse)
async def enable_node(
    node_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("nodes", "edit")),
):
    """Enable a disabled node."""
    try:
        from shared.api_client import api_client

        await api_client.enable_node(node_uuid)

        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="node.enable",
            resource="nodes",
            resource_id=node_uuid,
            details=json.dumps({"node_uuid": node_uuid}),
            ip_address=get_client_ip(request),
        )

        return SuccessResponse(message="Node enabled")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{node_uuid}/agent-token")
async def get_agent_token_status(
    node_uuid: str,
    admin: AdminUser = Depends(require_permission("nodes", "edit")),
):
    """Get agent token status for a node (masked)."""
    try:
        from shared.database import db_service
        if db_service.is_connected:
            token = await db_service.get_node_agent_token(node_uuid)
            if token:
                # Return masked token: first 8 + ... + last 4
                masked = token[:8] + '...' + token[-4:] if len(token) > 12 else '***'
                return {"has_token": True, "masked_token": masked}
            return {"has_token": False, "masked_token": None}
        raise api_error(503, E.DB_UNAVAILABLE)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting agent token status for %s: %s", node_uuid, e)
        raise api_error(500, E.INTERNAL_ERROR)


@router.post("/{node_uuid}/agent-token/generate")
async def generate_agent_token(
    node_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("nodes", "edit")),
):
    """Generate a new agent token for a node."""
    try:
        from shared.database import db_service
        from shared.agent_tokens import set_node_agent_token

        token = await set_node_agent_token(db_service, node_uuid)
        if token:
            await write_audit_log(
                admin_id=admin.account_id,
                admin_username=admin.username,
                action="node.generate_agent_token",
                resource="nodes",
                resource_id=node_uuid,
                details=json.dumps({"node_uuid": node_uuid}),
                ip_address=get_client_ip(request),
            )
            return {"success": True, "token": token}
        raise api_error(500, E.TOKEN_GENERATE_FAILED)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating agent token for %s: %s", node_uuid, e)
        raise api_error(500, E.INTERNAL_ERROR)


@router.post("/{node_uuid}/agent-token/revoke")
async def revoke_agent_token(
    node_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("nodes", "edit")),
):
    """Revoke agent token for a node."""
    try:
        from shared.database import db_service
        from shared.agent_tokens import revoke_node_agent_token

        success = await revoke_node_agent_token(db_service, node_uuid)
        if success:
            await write_audit_log(
                admin_id=admin.account_id,
                admin_username=admin.username,
                action="node.revoke_agent_token",
                resource="nodes",
                resource_id=node_uuid,
                details=json.dumps({"node_uuid": node_uuid}),
                ip_address=get_client_ip(request),
            )
            return {"success": True}
        raise api_error(500, E.TOKEN_REVOKE_FAILED)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error revoking agent token for %s: %s", node_uuid, e)
        raise api_error(500, E.INTERNAL_ERROR)


@router.post("/{node_uuid}/disable", response_model=SuccessResponse)
async def disable_node(
    node_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("nodes", "edit")),
):
    """Disable a node."""
    try:
        from shared.api_client import api_client

        await api_client.disable_node(node_uuid)

        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="node.disable",
            resource="nodes",
            resource_id=node_uuid,
            details=json.dumps({"node_uuid": node_uuid}),
            ip_address=get_client_ip(request),
        )

        return SuccessResponse(message="Node disabled")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

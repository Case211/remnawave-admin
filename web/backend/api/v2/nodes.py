"""Nodes API endpoints."""
import logging
import sys
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, HTTPException

# Add src to path for importing bot services
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from web.backend.api.deps import get_current_admin, AdminUser
from web.backend.core.api_helper import fetch_nodes_from_api, _normalize
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
    }
    for camel, snake in mappings.items():
        if camel in result and snake not in result:
            result[snake] = result[camel]
    # Fallback: traffic_total_bytes = traffic_used_bytes if not present
    if 'traffic_total_bytes' not in result and 'traffic_used_bytes' in result:
        result['traffic_total_bytes'] = result['traffic_used_bytes']
    return result


async def _get_nodes_list():
    """Get nodes from DB (normalized), fall back to API."""
    try:
        from src.services.database import db_service
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
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by name"),
    is_connected: Optional[bool] = Query(None, description="Filter by connection status"),
    admin: AdminUser = Depends(get_current_admin),
):
    """List nodes with pagination and filtering."""
    try:
        nodes = await _get_nodes_list()
        nodes = [_ensure_node_snake_case(n) for n in nodes]

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
    admin: AdminUser = Depends(get_current_admin),
):
    """Get detailed node information."""
    try:
        node_data = None
        try:
            from src.services.database import db_service
            if db_service.is_connected:
                node_data = await db_service.get_node_by_uuid(node_uuid)
        except Exception:
            pass

        if not node_data:
            from src.services.api_client import api_client
            node_data = await api_client.get_node(node_uuid)

        if not node_data:
            raise HTTPException(status_code=404, detail="Node not found")

        return NodeDetail(**_ensure_node_snake_case(node_data))

    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")


@router.post("", response_model=NodeDetail)
async def create_node(
    data: NodeCreate,
    admin: AdminUser = Depends(get_current_admin),
):
    """Create a new node."""
    try:
        from src.services.api_client import api_client

        node = await api_client.create_node(
            name=data.name,
            address=data.address,
            port=data.port,
        )

        return NodeDetail(**_ensure_node_snake_case(node))

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{node_uuid}", response_model=NodeDetail)
async def update_node(
    node_uuid: str,
    data: NodeUpdate,
    admin: AdminUser = Depends(get_current_admin),
):
    """Update node fields."""
    try:
        from src.services.api_client import api_client

        update_data = data.model_dump(exclude_unset=True)
        node = await api_client.update_node(node_uuid, **update_data)

        return NodeDetail(**_ensure_node_snake_case(node))

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{node_uuid}", response_model=SuccessResponse)
async def delete_node(
    node_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Delete a node."""
    try:
        from src.services.api_client import api_client

        await api_client.delete_node(node_uuid)
        return SuccessResponse(message="Node deleted")

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{node_uuid}/restart", response_model=SuccessResponse)
async def restart_node(
    node_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Restart a node."""
    try:
        from src.services.api_client import api_client

        await api_client.restart_node(node_uuid)
        return SuccessResponse(message="Node restart initiated")

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{node_uuid}/enable", response_model=SuccessResponse)
async def enable_node(
    node_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Enable a disabled node."""
    try:
        from src.services.api_client import api_client

        await api_client.enable_node(node_uuid)
        return SuccessResponse(message="Node enabled")

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{node_uuid}/disable", response_model=SuccessResponse)
async def disable_node(
    node_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Disable a node."""
    try:
        from src.services.api_client import api_client

        await api_client.disable_node(node_uuid)
        return SuccessResponse(message="Node disabled")

    except ImportError:
        raise HTTPException(status_code=503, detail="API service not available")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

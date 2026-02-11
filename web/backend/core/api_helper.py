"""Lightweight API helper for fetching data from Remnawave API.

This module provides direct API access without depending on the bot's Settings.
Uses WebSettings (API_BASE_URL, API_TOKEN) for configuration.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.config import get_web_settings

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None

# camelCase to snake_case mapping for common Remnawave API fields
_CAMEL_TO_SNAKE = {
    "shortUuid": "short_uuid",
    "subscriptionUuid": "subscription_uuid",
    "subscriptionUrl": "subscription_url",
    "telegramId": "telegram_id",
    "expireAt": "expire_at",
    "trafficLimitBytes": "traffic_limit_bytes",
    "trafficLimitStrategy": "traffic_limit_strategy",
    "usedTrafficBytes": "used_traffic_bytes",
    "hwidDeviceLimit": "hwid_device_limit",
    "createdAt": "created_at",
    "updatedAt": "updated_at",
    "onlineAt": "online_at",
    "subLastUserAgent": "sub_last_user_agent",
    "subLastOpenedAt": "sub_last_opened_at",
    "subRevokedAt": "sub_revoked_at",
    "lastTrafficResetAt": "last_traffic_reset_at",
    "isDisabled": "is_disabled",
    "isConnected": "is_connected",
    "isConnecting": "is_connecting",
    "isHidden": "is_hidden",
    "trafficUsedBytes": "traffic_used_bytes",
    "trafficTotalBytes": "traffic_total_bytes",
    "trafficTodayBytes": "traffic_today_bytes",
    "trafficResetDay": "traffic_reset_day",
    "isTrafficTrackingActive": "is_traffic_tracking_active",
    "usersOnline": "users_online",
    "isXrayRunning": "is_xray_running",
    "xrayVersion": "xray_version",
    "nodeVersion": "node_version",
    "xrayUptime": "xray_uptime",
    "lastSeenAt": "last_seen_at",
    "lastStatusChange": "last_status_change",
    "lastStatusMessage": "last_status_message",
    "lifetimeUsedTrafficBytes": "lifetime_used_traffic_bytes",
    "externalSquadUuid": "external_squad_uuid",
    "activeInternalSquads": "active_internal_squads",
    "countryCode": "country_code",
    "viewPosition": "view_position",
    "notifyPercent": "notify_percent",
    "consumptionMultiplier": "consumption_multiplier",
    "providerUuid": "provider_uuid",
    "firstConnectedAt": "first_connected_at",
    "lastConnectedNodeUuid": "last_connected_node_uuid",
    "securityLayer": "security_layer",
    "serverDescription": "server_description",
    "overrideSniFromAddress": "override_sni_from_address",
    "keepSniBlank": "keep_sni_blank",
    "allowInsecure": "allow_insecure",
    "vlessRouteId": "vless_route_id",
    "shuffleHost": "shuffle_host",
    "mihomoX25519": "mihomo_x25519",
    "xrayJsonTemplateUuid": "xray_json_template_uuid",
    "excludedInternalSquads": "excluded_internal_squads",
    "xHttpExtraParams": "x_http_extra_params",
    "muxParams": "mux_params",
    "sockoptParams": "sockopt_params",
    "lastTriggeredThreshold": "last_triggered_threshold",
}


def _normalize(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize API response dict: add snake_case aliases for camelCase keys.

    Preserves original keys and adds snake_case equivalents so the data
    works with both pydantic schemas (snake_case) and raw access (camelCase).
    Also flattens nested userTraffic object to root level.
    """
    result = dict(data)
    # Flatten nested userTraffic fields to root level
    user_traffic = result.get("userTraffic")
    if isinstance(user_traffic, dict):
        for key in ("usedTrafficBytes", "lifetimeUsedTrafficBytes", "onlineAt",
                     "firstConnectedAt", "lastConnectedNodeUuid"):
            if key in user_traffic and key not in result:
                result[key] = user_traffic[key]
    for camel, snake in _CAMEL_TO_SNAKE.items():
        if camel in result and snake not in result:
            result[snake] = result[camel]
    # Ensure traffic_total_bytes exists for nodes
    if 'traffic_total_bytes' not in result and 'traffic_used_bytes' in result:
        result['traffic_total_bytes'] = result['traffic_used_bytes']
    return result


def _get_client() -> httpx.AsyncClient:
    """Get or create the shared httpx client."""
    global _client
    if _client is None or _client.is_closed:
        settings = get_web_settings()
        base_url = str(settings.api_base_url).rstrip("/")
        headers = {"Content-Type": "application/json"}
        if settings.api_token:
            headers["Authorization"] = f"Bearer {settings.api_token}"
        # Add proxy headers for internal requests
        if base_url.startswith("http://"):
            headers["X-Forwarded-Proto"] = "https"
            headers["X-Forwarded-For"] = "127.0.0.1"
            headers["X-Real-IP"] = "127.0.0.1"
        _client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(connect=15.0, read=30.0, write=15.0, pool=10.0),
            follow_redirects=True,
        )
    return _client


async def api_get(path: str, params: dict = None) -> Optional[Dict[str, Any]]:
    """Make a GET request to the Remnawave API.

    Returns the parsed JSON response or None on error.
    """
    try:
        client = _get_client()
        resp = await client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning("API request failed: %s %s: %s", "GET", path, e)
        return None


async def fetch_users_from_api(size: int = 500) -> List[Dict[str, Any]]:
    """Fetch users list from the Remnawave API.

    Returns normalized dicts with both camelCase and snake_case keys.
    """
    all_users = []
    start = 0
    while True:
        data = await api_get("/api/users", params={"start": start, "size": size})
        if not data:
            break
        response = data.get("response", data)
        users = response.get("users", []) if isinstance(response, dict) else []
        if not users:
            break
        all_users.extend(_normalize(u) for u in users)
        total = response.get("total", 0)
        start += size
        if start >= total:
            break
    return all_users


async def fetch_nodes_from_api() -> List[Dict[str, Any]]:
    """Fetch nodes list from the Remnawave API.

    Returns normalized dicts with both camelCase and snake_case keys.
    """
    data = await api_get("/api/nodes")
    if not data:
        return []
    response = data.get("response", data)
    if isinstance(response, list):
        items = response
    elif isinstance(response, dict):
        items = response.get("nodes", response) if "nodes" in response else [response]
    else:
        return []
    return [_normalize(n) for n in items if isinstance(n, dict)]


async def fetch_hosts_from_api() -> List[Dict[str, Any]]:
    """Fetch hosts list from the Remnawave API.

    Returns normalized dicts with both camelCase and snake_case keys.
    """
    data = await api_get("/api/hosts")
    if not data:
        return []
    response = data.get("response", data)
    if isinstance(response, list):
        items = response
    elif isinstance(response, dict):
        items = response.get("hosts", response) if "hosts" in response else [response]
    else:
        return []
    return [_normalize(h) for h in items if isinstance(h, dict)]


async def fetch_bandwidth_stats() -> Optional[Dict[str, Any]]:
    """Fetch bandwidth statistics from the Remnawave API.

    Returns response with bandwidthLastTwoDays, bandwidthLastSevenDays,
    bandwidthLast30Days, bandwidthCalendarMonth, bandwidthCurrentYear.
    Each has 'current', 'previous', 'difference' (string byte values).
    """
    data = await api_get("/api/system/stats/bandwidth")
    if not data:
        return None
    return data.get("response", data)


async def fetch_nodes_usage_by_range(
    start: str, end: str, top_nodes_limit: int = 100
) -> Optional[Dict[str, Any]]:
    """Fetch per-node bandwidth usage for a date range from the Remnawave API.

    Parameters:
        start: ISO-8601 datetime string (e.g. '2025-01-01T00:00:00.000Z')
        end: ISO-8601 datetime string
        top_nodes_limit: max nodes to return (default 100)

    Returns response with topNodes (each with 'total' bytes), series, etc.
    """
    data = await api_get(
        "/api/bandwidth-stats/nodes",
        params={
            "start": start,
            "end": end,
            "topNodesLimit": top_nodes_limit,
        },
    )
    if not data:
        return None
    return data.get("response", data)


async def fetch_nodes_realtime_usage() -> List[Dict[str, Any]]:
    """Fetch real-time per-node bandwidth usage from the Remnawave API.

    Returns list of dicts with nodeUuid, nodeName, totalBytes,
    downloadBytes, uploadBytes, downloadSpeedBps, uploadSpeedBps, totalSpeedBps.
    """
    data = await api_get("/api/bandwidth-stats/nodes/realtime")
    if not data:
        return []
    response = data.get("response", data)
    if isinstance(response, list):
        return response
    return []


async def close_client():
    """Close the shared httpx client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None

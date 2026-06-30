"""Internal API client for bot → backend communication.

Two mutually exclusive modes:

1. Proxy mode (INTERNAL_API_SECRET set):
   Calls backend /api/v2/internal/proxy/* endpoint with X-Internal-Api-Secret.
   The backend proxies to the Panel API with RBAC, quota, and audit enforcement.

2. Direct mode (INTERNAL_API_SECRET unset):
   Calls the Remnawave Panel API directly using API_TOKEN (legacy behavior).
   Bot admin verified via ADMINS env var with full superadmin permissions.
   No RBAC, quota, or audit — same as original pre-proxy behavior.
"""
import os
import re
from contextvars import ContextVar
from typing import Any

from shared.exceptions import (
    ApiClientError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TimeoutError,
    UnauthorizedError,
    ValidationError,
)
from shared.http_client import BaseHttpClient
from shared.logger import logger


def snake_to_camel(snake_str: str) -> str:
    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


_admin_ctx: ContextVar[dict | None] = ContextVar("internal_api_admin", default=None)


BACKEND_URL = os.environ.get("INTERNAL_API_BACKEND_URL", "http://web-backend:8081")
PROXY_PREFIX = "/api/v2/internal/proxy/api"
PANEL_PREFIX = "/api"


# ── Route definitions ────────────────────────────────────────────
# Each entry generates an async method on BaseInternalApiClient.
#
# Keys:
#   name   — method name
#   method — HTTP method (GET/POST/PATCH/DELETE)
#   path   — URL template with {param} placeholders for path params
#   body   — body handling: None (no body), "kwargs" (snake_to_camel),
#            "update" (uuid+kwargs), "payload" (dict as-is)
#   body_id — for "update" type, which kwarg maps to body "uuid"

_ROUTE_DEFS: list[dict[str, Any]] = [
    # ── Users ──
    dict(name="get_user_by_username", method="GET", path="/users/by-username/{username}"),
    dict(name="get_user_by_telegram_id", method="GET", path="/users/by-telegram-id/{telegram_id}"),
    dict(name="get_user_by_uuid", method="GET", path="/users/{user_uuid}"),
    dict(name="get_user_by_short_uuid", method="GET", path="/users/by-short-uuid/{short_uuid}"),
    dict(name="get_user_by_id", method="GET", path="/users/by-id/{user_id}"),
    dict(name="get_users_by_email", method="GET", path="/users/by-email/{email}"),
    dict(name="resolve_user", method="POST", path="/users/resolve", body="kwargs"),
    dict(name="get_users_by_tag", method="GET", path="/users/by-tag/{tag}"),
    dict(name="get_all_user_tags", method="GET", path="/users/tags"),
    dict(name="create_user", method="POST", path="/users", body="kwargs"),
    dict(name="update_user", method="PATCH", path="/users", body="update", body_id="user_uuid"),
    dict(name="delete_user", method="DELETE", path="/users/{user_uuid}"),
    dict(name="enable_user", method="POST", path="/users/{user_uuid}/actions/enable"),
    dict(name="disable_user", method="POST", path="/users/{user_uuid}/actions/disable"),
    dict(name="reset_user_traffic", method="POST", path="/users/{user_uuid}/actions/reset-traffic"),
    dict(name="revoke_user_subscription", method="POST", path="/users/{user_uuid}/actions/revoke", body="kwargs"),
    dict(name="get_user_subscription_request_history", method="GET", path="/users/{user_uuid}/subscription-request-history"),
    dict(name="get_user_accessible_nodes", method="GET", path="/users/{user_uuid}/accessible-nodes"),
    # ── Nodes ──
    dict(name="get_nodes", method="GET", path="/nodes"),
    dict(name="get_node", method="GET", path="/nodes/{node_uuid}"),
    dict(name="create_node", method="POST", path="/nodes", body="kwargs"),
    dict(name="update_node", method="PATCH", path="/nodes", body="update", body_id="node_uuid"),
    dict(name="delete_node", method="DELETE", path="/nodes/{node_uuid}"),
    dict(name="enable_node", method="POST", path="/nodes/{node_uuid}/actions/enable"),
    dict(name="disable_node", method="POST", path="/nodes/{node_uuid}/actions/disable"),
    dict(name="restart_node", method="POST", path="/nodes/{node_uuid}/actions/restart", body="kwargs"),
    dict(name="reset_node_traffic", method="POST", path="/nodes/{node_uuid}/actions/reset-traffic"),
    dict(name="get_all_node_tags", method="GET", path="/nodes/tags"),
    # ── Hosts ──
    dict(name="get_hosts", method="GET", path="/hosts"),
    dict(name="get_host", method="GET", path="/hosts/{host_uuid}"),
    dict(name="create_host", method="POST", path="/hosts", body="kwargs"),
    dict(name="update_host", method="PATCH", path="/hosts", body="update", body_id="host_uuid"),
    dict(name="delete_host", method="DELETE", path="/hosts/{host_uuid}"),
    dict(name="get_all_host_tags", method="GET", path="/hosts/tags"),
    # ── Config Profiles ──
    dict(name="get_config_profiles", method="GET", path="/config-profiles"),
    dict(name="get_config_profile_computed", method="GET", path="/config-profiles/{profile_uuid}/computed-config"),
    dict(name="get_config_profile_by_uuid", method="GET", path="/config-profiles/{profile_uuid}"),
    dict(name="get_all_inbounds", method="GET", path="/config-profiles/inbounds"),
    dict(name="get_inbounds_by_profile_uuid", method="GET", path="/config-profiles/{profile_uuid}/inbounds"),

    dict(name="delete_config_profile", method="DELETE", path="/config-profiles/{profile_uuid}"),
    dict(name="reorder_config_profiles", method="POST", path="/config-profiles/actions/reorder", body="kwargs"),
    # ── Subscription Templates ──
    dict(name="get_templates", method="GET", path="/subscription-templates"),
    dict(name="get_template", method="GET", path="/subscription-templates/{template_uuid}"),
    dict(name="delete_template", method="DELETE", path="/subscription-templates/{template_uuid}"),
    # ── Snippets ──
    dict(name="get_snippets", method="GET", path="/snippets"),
    # ── Squads (Internal) ──
    dict(name="get_internal_squads", method="GET", path="/internal-squads"),
    dict(name="get_internal_squad_by_uuid", method="GET", path="/internal-squads/{squad_uuid}"),
    dict(name="create_internal_squad", method="POST", path="/internal-squads", body="kwargs"),
    dict(name="update_internal_squad", method="PATCH", path="/internal-squads", body="update", body_id="squad_uuid"),
    dict(name="delete_internal_squad", method="DELETE", path="/internal-squads/{squad_uuid}"),
    dict(name="get_internal_squad_accessible_nodes", method="GET", path="/internal-squads/{squad_uuid}/accessible-nodes"),
    dict(name="add_users_to_internal_squad", method="POST", path="/internal-squads/{squad_uuid}/bulk-actions/add-users"),
    dict(name="remove_users_from_internal_squad", method="DELETE", path="/internal-squads/{squad_uuid}/bulk-actions/remove-users"),
    dict(name="reorder_internal_squads", method="POST", path="/internal-squads/actions/reorder", body="kwargs"),
    # ── Squads (External) ──
    dict(name="get_external_squads", method="GET", path="/external-squads"),
    dict(name="get_external_squad_by_uuid", method="GET", path="/external-squads/{squad_uuid}"),
    dict(name="create_external_squad", method="POST", path="/external-squads", body="kwargs"),
    dict(name="update_external_squad", method="PATCH", path="/external-squads", body="update", body_id="squad_uuid"),
    dict(name="delete_external_squad", method="DELETE", path="/external-squads/{squad_uuid}"),
    dict(name="add_users_to_external_squad", method="POST", path="/external-squads/{squad_uuid}/bulk-actions/add-users"),
    dict(name="remove_users_from_external_squad", method="DELETE", path="/external-squads/{squad_uuid}/bulk-actions/remove-users"),
    dict(name="reorder_external_squads", method="POST", path="/external-squads/actions/reorder", body="kwargs"),
    # ── Billing / Infra ──
    dict(name="get_infra_billing_history", method="GET", path="/infra-billing/history"),
    dict(name="get_infra_providers", method="GET", path="/infra-billing/providers"),
    dict(name="get_infra_provider", method="GET", path="/infra-billing/providers/{provider_uuid}"),
    dict(name="delete_infra_provider", method="DELETE", path="/infra-billing/providers/{provider_uuid}"),
    dict(name="delete_infra_billing_record", method="DELETE", path="/infra-billing/history/{record_uuid}"),
    dict(name="get_infra_billing_nodes", method="GET", path="/infra-billing/nodes"),
    dict(name="delete_infra_billing_node", method="DELETE", path="/infra-billing/nodes/{record_uuid}"),
    # ── Subscriptions ──
    dict(name="get_subscription_info", method="GET", path="/sub/{short_uuid}/info"),
    dict(name="get_subscription_settings", method="GET", path="/subscription-settings"),

    # ── System ──
    dict(name="get_health", method="GET", path="/system/health"),
    dict(name="get_stats", method="GET", path="/system/stats"),
    dict(name="get_bandwidth_stats", method="GET", path="/system/stats/bandwidth"),
    dict(name="get_stats_recap", method="GET", path="/system/stats/recap"),
    dict(name="get_nodes_statistics", method="GET", path="/system/stats/nodes"),
    dict(name="get_nodes_metrics", method="GET", path="/system/nodes/metrics"),
    # ── HWID ──
    dict(name="get_hwid_devices_stats", method="GET", path="/hwid/devices/stats"),
    dict(name="get_user_hwid_devices", method="GET", path="/hwid/devices/{user_uuid}"),

    # ── Token Management ──
    dict(name="get_tokens", method="GET", path="/tokens"),
    dict(name="delete_token", method="DELETE", path="/tokens/{token_uuid}"),
    # ── Subscription Page Configs ──
    dict(name="get_subscription_page_configs", method="GET", path="/subscription-page-configs"),
    dict(name="get_subscription_page_config_by_uuid", method="GET", path="/subscription-page-configs/{config_uuid}"),
    dict(name="create_subscription_page_config", method="POST", path="/subscription-page-configs", body="kwargs"),
    dict(name="update_subscription_page_config", method="PATCH", path="/subscription-page-configs", body="update", body_id="config_uuid"),
    dict(name="delete_subscription_page_config", method="DELETE", path="/subscription-page-configs/{config_uuid}"),
    dict(name="reorder_subscription_page_configs", method="POST", path="/subscription-page-configs/actions/reorder", body="kwargs"),
    dict(name="clone_subscription_page_config", method="POST", path="/subscription-page-configs/actions/clone", body="kwargs"),
    # ── Protected Subscriptions ──
    dict(name="get_all_subscriptions", method="GET", path="/subscriptions"),
    dict(name="get_subscription_by_username", method="GET", path="/subscriptions/by-username/{username}"),
    dict(name="get_subscription_by_short_uuid_protected", method="GET", path="/subscriptions/by-short-uuid/{short_uuid}"),
    dict(name="get_subscription_by_uuid", method="GET", path="/subscriptions/by-uuid/{uuid}"),
    dict(name="get_raw_subscription_by_short_uuid", method="GET", path="/subscriptions/by-short-uuid/{short_uuid}/raw"),
    dict(name="get_subpage_config_by_short_uuid", method="GET", path="/subscriptions/subpage-config/{short_uuid}"),
    # ── Subscription Request History ──
    dict(name="get_subscription_request_history_stats", method="GET", path="/subscription-request-history/stats"),
    # ── Torrent Blocker ──
    dict(name="get_torrent_blocker_stats", method="GET", path="/node-plugins/torrent-blocker/stats"),
    # ── Keygen ──
    dict(name="generate_ssl_cert_key", method="GET", path="/keygen"),
    # ── IP Control ──
    dict(name="fetch_user_ips", method="POST", path="/ip-control/fetch-ips/{user_uuid}"),
    dict(name="get_fetch_ips_result", method="GET", path="/ip-control/fetch-ips/result/{job_id}"),
    dict(name="fetch_users_ips_by_node", method="POST", path="/ip-control/fetch-users-ips/{node_uuid}"),
    dict(name="get_fetch_users_ips_result", method="GET", path="/ip-control/fetch-users-ips/result/{job_id}"),
    dict(name="drop_connections", method="POST", path="/ip-control/drop-connections", body="kwargs"),
    # ── Bulk Users ──
    dict(name="bulk_reset_traffic_all_users", method="POST", path="/users/bulk/all/reset-traffic"),
    dict(name="bulk_update_users", method="POST", path="/users/bulk/update", body="kwargs"),
    dict(name="bulk_update_users_squads", method="POST", path="/users/bulk/update-squads", body="kwargs"),
    # ── Bulk Hosts ──
    dict(name="bulk_delete_hosts", method="POST", path="/hosts/bulk/delete", body="kwargs"),
    dict(name="bulk_update_hosts", method="PATCH", path="/hosts/bulk/update", body="kwargs"),
]


def _make_route(defn: dict[str, Any]):
    http_method = defn["method"].upper()
    path_template = defn["path"]
    body_type = defn.get("body")
    body_id = defn.get("body_id")
    path_param_names = re.findall(r"\{(\w+)\}", path_template)

    async def route(self, *args: Any, **kwargs: Any) -> dict:
        path = path_template
        for i, pp_name in enumerate(path_param_names):
            if i < len(args):
                path = path.replace(f"{{{pp_name}}}", str(args[i]))
            elif pp_name in kwargs:
                path = path.replace(f"{{{pp_name}}}", str(kwargs.pop(pp_name)))

        remaining_args = args[len(path_param_names):]
        json_body: dict | None = None

        if body_type == "kwargs":
            json_body = {}
            for k, v in kwargs.items():
                if v is not None:
                    json_body[snake_to_camel(k)] = v
        elif body_type == "update":
            json_body = {}
            if body_id and len(remaining_args) > 0 and not path_param_names:
                json_body["uuid"] = remaining_args[0]
            elif body_id and body_id in kwargs:
                json_body["uuid"] = kwargs.pop(body_id)
            for k, v in kwargs.items():
                if v is not None:
                    json_body[snake_to_camel(k)] = v
        elif body_type == "payload":
            json_body = dict(kwargs)

        if http_method == "GET":
            return await self._get(path)
        elif http_method == "POST":
            return await self._post(path, json=json_body)
        elif http_method == "PATCH":
            return await self._patch(path, json=json_body)
        elif http_method == "DELETE":
            return await self._delete(path, json=json_body)

    route.__name__ = defn["name"]
    route.__qualname__ = f"BaseInternalApiClient.{defn['name']}"
    return route


class BaseInternalApiClient(BaseHttpClient):
    proxy_mode = False

    def __init__(self, base_url: str, prefix: str, headers: dict[str, str]) -> None:
        super().__init__(base_url, prefix, headers)

    def _extra_headers(self) -> dict[str, str]:
        return {}

    # ── Explicit methods (complex body, query params, positional body args) ──

    async def get_users(self, start: int = 0, size: int = 100, admin_id: int | None = None) -> dict:
        params = {"start": start, "size": size}
        if admin_id is not None:
            params["admin_id"] = admin_id
        return await self._get("/users", params=params)

    async def get_user_traffic_stats(self, user_uuid: str, start: str, end: str, top_nodes_limit: int = 10) -> dict:
        return await self._get(f"/bandwidth-stats/users/{user_uuid}", params={"start": start, "end": end, "topNodesLimit": top_nodes_limit})

    async def get_user_traffic_stats_legacy(self, user_uuid: str, start: str, end: str) -> dict:
        return await self._get(f"/bandwidth-stats/users/{user_uuid}/legacy", params={"start": start, "end": end})

    async def get_nodes_usage_range(self, start: str, end: str, top_nodes_limit: int = 10) -> dict:
        return await self._get("/bandwidth-stats/nodes", params={"start": start, "end": end, "topNodesLimit": top_nodes_limit})

    async def get_node_users_usage(self, node_uuid: str, start: str, end: str, top_users_limit: int = 10) -> dict:
        return await self._get(f"/bandwidth-stats/nodes/{node_uuid}/users", params={"start": start, "end": end, "topUsersLimit": top_users_limit})

    async def restart_all_nodes(self, force_restart: bool = False) -> dict:
        # 2.8.0: restart-all требует body с обязательным forceRestart.
        return await self._post("/nodes/actions/restart-all", json={"forceRestart": force_restart})

    async def reorder_nodes(self, items: list[dict]) -> dict:
        return await self._post("/nodes/actions/reorder", json={"nodes": items})

    async def reorder_hosts(self, items: list[dict]) -> dict:
        return await self._post("/hosts/actions/reorder", json={"hosts": items})

    async def reorder_templates(self, uuids_in_order: list[str]) -> dict:
        items = [{"uuid": uuid, "viewPosition": idx + 1} for idx, uuid in enumerate(uuids_in_order)]
        return await self._post("/subscription-templates/actions/reorder", json={"items": items})

    async def create_template(self, name: str, template_type: str) -> dict:
        return await self._post("/subscription-templates", json={"name": name, "templateType": template_type})

    async def update_template(self, template_uuid: str, name: str | None = None, template_json: dict | None = None) -> dict:
        payload: dict = {"uuid": template_uuid}
        if name:
            payload["name"] = name
        if template_json is not None:
            payload["templateJson"] = template_json
        return await self._patch("/subscription-templates", json=payload)

    async def create_snippet(self, name: str, snippet: list[dict] | dict) -> dict:
        return await self._post("/snippets", json={"name": name, "snippet": snippet})

    async def update_snippet(self, name: str, snippet: list[dict] | dict) -> dict:
        return await self._patch("/snippets", json={"name": name, "snippet": snippet})

    async def delete_snippet(self, name: str) -> dict:
        return await self._delete("/snippets", json={"name": name})

    async def enable_hosts(self, host_uuids: list[str]) -> dict:
        return await self._post("/hosts/bulk/enable", json={"uuids": host_uuids})

    async def disable_hosts(self, host_uuids: list[str]) -> dict:
        return await self._post("/hosts/bulk/disable", json={"uuids": host_uuids})

    async def create_infra_provider(self, name: str, favicon_link: str | None = None, login_url: str | None = None) -> dict:
        payload: dict = {"name": name}
        if favicon_link:
            payload["faviconLink"] = favicon_link
        if login_url:
            payload["loginUrl"] = login_url
        return await self._post("/infra-billing/providers", json=payload)

    async def update_infra_provider(self, provider_uuid: str, name: str | None = None, favicon_link: str | None = None, login_url: str | None = None) -> dict:
        payload: dict = {"uuid": provider_uuid}
        if name:
            payload["name"] = name
        if favicon_link is not None:
            payload["faviconLink"] = favicon_link
        if login_url is not None:
            payload["loginUrl"] = login_url
        return await self._patch("/infra-billing/providers", json=payload)

    async def create_infra_billing_record(self, provider_uuid: str, amount: float, billed_at: str) -> dict:
        return await self._post("/infra-billing/history", json={"providerUuid": provider_uuid, "amount": amount, "billedAt": billed_at})

    async def create_infra_billing_node(self, provider_uuid: str, node_uuid: str, next_billing_at: str | None = None) -> dict:
        payload: dict = {"providerUuid": provider_uuid, "nodeUuid": node_uuid}
        if next_billing_at:
            payload["nextBillingAt"] = next_billing_at
        return await self._post("/infra-billing/nodes", json=payload)

    async def update_infra_billing_nodes(self, uuids: list[str], next_billing_at: str) -> dict:
        return await self._patch("/infra-billing/nodes", json={"uuids": uuids, "nextBillingAt": next_billing_at})

    async def get_all_hwid_devices(self, start: int = 0, size: int = 100) -> dict:
        return await self._get("/hwid/devices", params={"start": start, "size": size})

    async def create_user_hwid_device(self, user_uuid: str, hwid: str) -> dict:
        return await self._post("/hwid/devices", json={"userUuid": user_uuid, "hwid": hwid})

    async def delete_user_hwid_device(self, user_uuid: str, hwid: str) -> dict:
        return await self._post("/hwid/devices/delete", json={"userUuid": user_uuid, "hwid": hwid})

    async def delete_all_user_hwid_devices(self, user_uuid: str) -> dict:
        return await self._post("/hwid/devices/delete-all", json={"userUuid": user_uuid})

    async def get_top_users_by_hwid_devices(self, limit: int = 10) -> dict:
        return await self._get("/hwid/devices/top-users", params={"limit": limit})

    async def create_token(self, token_name: str) -> dict:
        return await self._post("/tokens", json={"tokenName": token_name})

    async def get_subscription_request_history(self, start: int = 0, size: int = 100) -> dict:
        return await self._get("/subscription-request-history", params={"start": start, "size": size})

    async def get_torrent_blocker_reports(self, start: int = 0, size: int = 100) -> dict:
        return await self._get("/node-plugins/torrent-blocker", params={"start": start, "size": size})

    async def bulk_delete_users_by_status(self, status: str) -> dict:
        return await self._post("/users/bulk/delete-by-status", json={"status": status})

    async def bulk_delete_users(self, uuids: list[str]) -> dict:
        return await self._post("/users/bulk/delete", json={"uuids": uuids})

    async def bulk_revoke_subscriptions(self, uuids: list[str]) -> dict:
        return await self._post("/users/bulk/revoke-subscription", json={"uuids": uuids})

    async def bulk_reset_traffic_users(self, uuids: list[str]) -> dict:
        return await self._post("/users/bulk/reset-traffic", json={"uuids": uuids})

    async def bulk_extend_users(self, uuids: list[str], days: int) -> dict:
        return await self._post("/users/bulk/extend-expiration-date", json={"uuids": uuids, "extendDays": days})

    async def bulk_extend_all_users(self, days: int) -> dict:
        return await self._post("/users/bulk/all/extend-expiration-date", json={"extendDays": days})

    async def bulk_update_users_status(self, uuids: list[str], status: str) -> dict:
        return await self._post("/users/bulk/update", json={"uuids": uuids, "fields": {"status": status}})

    async def bulk_update_all_users(self, fields: dict) -> dict:
        return await self._post("/users/bulk/all/update", json=fields)

    async def bulk_enable_hosts(self, uuids: list[str]) -> dict:
        return await self._post("/hosts/bulk/enable", json={"uuids": uuids})

    async def bulk_disable_hosts(self, uuids: list[str]) -> dict:
        return await self._post("/hosts/bulk/disable", json={"uuids": uuids})

    async def bulk_nodes_profile_modification(self, node_uuids: list[str], profile_uuid: str, inbound_uuids: list[str]) -> dict:
        return await self._post("/nodes/bulk-actions/profile-modification", json={
            "uuids": node_uuids,
            "configProfile": {"activeConfigProfileUuid": profile_uuid, "activeInbounds": inbound_uuids},
        })

    async def create_config_profile(self, payload: dict) -> dict:
        return await self._post("/config-profiles", json=payload)

    async def update_config_profile(self, payload: dict) -> dict:
        return await self._patch("/config-profiles", json=payload)

    async def update_subscription_settings(self, payload: dict) -> dict:
        return await self._patch("/subscription-settings", json=payload)

    async def close(self) -> None:
        return await super().close()


# Attach auto-generated routes to the class
for _defn in _ROUTE_DEFS:
    _route_method = _make_route(_defn)
    setattr(BaseInternalApiClient, _defn["name"], _route_method)


class ProxyInternalApiClient(BaseInternalApiClient):
    proxy_mode = True

    def __init__(self) -> None:
        secret = os.environ.get("INTERNAL_API_SECRET", "")
        headers = {
            "Content-Type": "application/json",
            "X-Internal-Api-Secret": secret,
        }
        super().__init__(BACKEND_URL, PROXY_PREFIX, headers)

    def _extra_headers(self) -> dict[str, str]:
        extra: dict[str, str] = {}
        admin = _admin_ctx.get()
        if admin:
            if admin.get("username"):
                extra["X-Admin-Username"] = admin["username"]
            if admin.get("account_id"):
                extra["X-Admin-Account-Id"] = str(admin["account_id"])
        return extra


class DirectInternalApiClient(BaseInternalApiClient):
    def __init__(self) -> None:
        from shared.config import get_shared_settings
        settings = get_shared_settings()
        base_url = str(settings.api_base_url).rstrip("/")

        headers = {"Content-Type": "application/json"}
        if settings.api_token:
            headers["Authorization"] = f"Bearer {settings.api_token}"
        if settings.panel_api_key:
            headers["X-API-Key"] = settings.panel_api_key
        if base_url.startswith("http://"):
            headers["X-Forwarded-Proto"] = "https"
            headers["X-Forwarded-For"] = "127.0.0.1"
            headers["X-Real-IP"] = "127.0.0.1"

        super().__init__(base_url, PANEL_PREFIX, headers)


def _create_client() -> BaseInternalApiClient:
    secret = os.environ.get("INTERNAL_API_SECRET", "")
    if secret:
        return ProxyInternalApiClient()
    return DirectInternalApiClient()


internal_api_client = _create_client()

"""Audit middleware — automatically logs all mutable API actions.

Intercepts POST/PUT/PATCH/DELETE requests, resolves the admin from the JWT,
determines the resource/action from the URL pattern, and writes to admin_audit_log.
Also broadcasts audit events via WebSocket for real-time notifications.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from web.backend.core.security import decode_token

logger = logging.getLogger(__name__)

# ── Fields to extract per resource type for audit details ─────
# Only these fields are captured from request bodies.
_EXTRACT_FIELDS: dict[str, set[str]] = {
    "users": {
        "username", "data_limit", "expire_date", "status", "note",
        "data_limit_reset_strategy", "on_hold_expire_duration",
        "on_hold_timeout", "inbound_tags",
    },
    "nodes": {"name", "address", "port"},
    "hosts": {"remark", "address", "port", "sni", "host", "is_disabled", "alpn", "fingerprint"},
    "settings": {"value"},
    "violations": {},
    "api_keys": {"name", "scopes", "expires_at", "description", "is_active"},
    "webhooks": {"name", "url", "events", "is_active", "signature_version", "description"},
}

# Sensitive fields that must never be logged
_SENSITIVE_FIELDS = {"password", "password_hash", "token", "secret", "api_key", "subscription_url"}

# ── URL → resource/action mapping ─────────────────────────────────
# Maps URL patterns to (resource, action) tuples.
# Order matters — first match wins.

_ROUTE_MAP: list[Tuple[str, str, str, str]] = [
    # (method, regex_pattern, resource, action)

    # Users
    ("POST", r"/api/v2/users/bulk/(enable|disable|delete|reset-traffic)", "users", "bulk_{1}"),
    ("POST", r"/api/v2/users/([^/]+)/enable$", "users", "enable"),
    ("POST", r"/api/v2/users/([^/]+)/disable$", "users", "disable"),
    ("POST", r"/api/v2/users/([^/]+)/reset-traffic$", "users", "reset_traffic"),
    ("POST", r"/api/v2/users/([^/]+)/revoke$", "users", "revoke"),
    ("POST", r"/api/v2/users/([^/]+)/sync-hwid-devices$", "users", "sync_hwid"),
    ("POST", r"/api/v2/users$", "users", "create"),
    ("PATCH", r"/api/v2/users/([^/]+)$", "users", "update"),
    ("DELETE", r"/api/v2/users/([^/]+)$", "users", "delete"),

    # Nodes
    ("POST", r"/api/v2/nodes/([^/]+)/restart$", "nodes", "restart"),
    ("POST", r"/api/v2/nodes/([^/]+)/enable$", "nodes", "enable"),
    ("POST", r"/api/v2/nodes/([^/]+)/disable$", "nodes", "disable"),
    ("POST", r"/api/v2/nodes/([^/]+)/agent-token$", "nodes", "generate_token"),
    ("DELETE", r"/api/v2/nodes/([^/]+)/agent-token$", "nodes", "revoke_token"),
    ("POST", r"/api/v2/nodes$", "nodes", "create"),
    ("PATCH", r"/api/v2/nodes/([^/]+)$", "nodes", "update"),
    ("DELETE", r"/api/v2/nodes/([^/]+)$", "nodes", "delete"),

    # Hosts
    ("POST", r"/api/v2/hosts/([^/]+)/enable$", "hosts", "enable"),
    ("POST", r"/api/v2/hosts/([^/]+)/disable$", "hosts", "disable"),
    ("POST", r"/api/v2/hosts$", "hosts", "create"),
    ("PATCH", r"/api/v2/hosts/([^/]+)$", "hosts", "update"),
    ("DELETE", r"/api/v2/hosts/([^/]+)$", "hosts", "delete"),

    # Violations
    ("POST", r"/api/v2/violations/([^/]+)/resolve$", "violations", "resolve"),

    # Settings
    ("PUT", r"/api/v2/settings/ip-whitelist$", "settings", "update_ip_whitelist"),
    ("POST", r"/api/v2/settings/sync$", "settings", "trigger_sync"),
    ("PUT", r"/api/v2/settings/([^/]+)$", "settings", "update"),
    ("DELETE", r"/api/v2/settings/([^/]+)$", "settings", "reset"),

    # Admins (already logged manually, but middleware catches any gaps)
    ("POST", r"/api/v2/admins$", "admins", "create"),
    ("PUT", r"/api/v2/admins/(\d+)$", "admins", "update"),
    ("DELETE", r"/api/v2/admins/(\d+)$", "admins", "delete"),

    # Roles
    ("POST", r"/api/v2/roles$", "roles", "create"),
    ("PUT", r"/api/v2/roles/(\d+)$", "roles", "update"),
    ("DELETE", r"/api/v2/roles/(\d+)$", "roles", "delete"),

    # API keys
    ("POST", r"/api/v2/api-keys/?$", "api_keys", "create"),
    ("POST", r"/api/v2/api-keys/(\d+)/rotate$", "api_keys", "rotate"),
    ("PATCH", r"/api/v2/api-keys/(\d+)$", "api_keys", "update"),
    ("DELETE", r"/api/v2/api-keys/(\d+)$", "api_keys", "delete"),

    # Webhooks
    ("POST", r"/api/v2/webhooks/?$", "webhooks", "create"),
    ("POST", r"/api/v2/webhooks/(\d+)/test$", "webhooks", "test"),
    ("PATCH", r"/api/v2/webhooks/(\d+)$", "webhooks", "update"),
    ("DELETE", r"/api/v2/webhooks/(\d+)$", "webhooks", "delete"),

    # Auth
    ("POST", r"/api/v2/auth/password$", "auth", "login"),
    ("POST", r"/api/v2/auth/telegram$", "auth", "login_telegram"),
    ("POST", r"/api/v2/auth/change-password$", "auth", "change_password"),
    ("POST", r"/api/v2/auth/logout$", "auth", "logout"),

    # Public API v3 (аутентификация по API-ключу) — те же resource/action
    ("POST", r"/api/v3/users/bulk/(enable|disable|delete|reset-traffic)", "users", "bulk_{1}"),
    ("POST", r"/api/v3/users/([^/]+)/enable$", "users", "enable"),
    ("POST", r"/api/v3/users/([^/]+)/disable$", "users", "disable"),
    ("POST", r"/api/v3/users/([^/]+)/reset-traffic$", "users", "reset_traffic"),
    ("POST", r"/api/v3/users$", "users", "create"),
    ("DELETE", r"/api/v3/users/([^/]+)$", "users", "delete"),
    ("POST", r"/api/v3/nodes/([^/]+)/enable$", "nodes", "enable"),
    ("POST", r"/api/v3/nodes/([^/]+)/disable$", "nodes", "disable"),
    ("POST", r"/api/v3/nodes/([^/]+)/restart$", "nodes", "restart"),
]

# Actions already logged manually in admins.py/roles.py/auth.py — skip to avoid duplicates
_SKIP_DUPLICATES = {
    ("admins", "create"),
    ("admins", "update"),
    ("admins", "delete"),
    ("roles", "create"),
    ("roles", "update"),
    ("roles", "delete"),
    ("auth", "login"),
    ("auth", "login_telegram"),
    ("auth", "logout"),
    ("auth", "change_password"),
}


def _match_route(method: str, path: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """Match a request to a (resource, action, resource_id) tuple."""
    for route_method, pattern, resource, action_tpl in _ROUTE_MAP:
        if method != route_method:
            continue
        m = re.match(pattern, path)
        if m:
            groups = m.groups()
            # Replace {1} placeholder in action with first capture group
            action = action_tpl.replace("{1}", groups[0]) if groups and "{1}" in action_tpl else action_tpl
            resource_id = groups[0] if groups else None
            return resource, action, resource_id
    return None


def _extract_token(request: Request) -> Optional[str]:
    """Extract JWT from the Authorization header or the session cookie.

    Веб-фронт живёт на httpOnly-cookie (rw_access), Bearer-заголовок он
    ставит, только пока access-токен лежит в памяти — после перезагрузки
    страницы остаётся одна cookie. Пока здесь читался лишь заголовок,
    аудит таких запросов писался с admin_id=None и именем «unknown», а
    в WebSocket-уведомлении это выглядело как «unknown: users.create:
    users». Порядок тот же, что в deps.get_current_admin.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]

    try:
        from web.backend.core.auth_cookies import ACCESS_COOKIE
    except ImportError:
        return None
    return request.cookies.get(ACCESS_COOKIE)


class AuditMiddleware(BaseHTTPMiddleware):
    """Middleware that automatically logs mutable actions to audit_log."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Only intercept mutable methods
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)

        path = request.url.path

        # Skip non-API paths and health checks (аудитим и v2, и публичный v3)
        if not (path.startswith("/api/v2/") or path.startswith("/api/v3/")) or path == "/api/v2/health":
            return await call_next(request)

        # Skip read-only POST endpoints (lookups, search, etc.)
        if any(path.endswith(suffix) for suffix in (
            "/lookup-ips", "/hwid-device-counts", "/meta/internal-squads",
            "/meta/external-squads", "/auth/refresh",
        )):
            return await call_next(request)

        # Match the route
        match = _match_route(request.method, path)
        if not match:
            return await call_next(request)

        resource, action, resource_id = match

        # Skip actions already logged manually
        if (resource, action) in _SKIP_DUPLICATES:
            return await call_next(request)

        # Capture request body before forwarding (body is cached by Starlette)
        request_body = None
        try:
            body_bytes = await request.body()
            if body_bytes:
                request_body = json.loads(body_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        except Exception as e:
            logging.getLogger(__name__).debug("Failed to read request body for audit: %s", e)

        # Execute the actual request
        response = await call_next(request)

        # Only log successful actions (2xx status codes)
        if 200 <= response.status_code < 300:
            # Fire-and-forget audit log write
            asyncio.create_task(
                _write_audit_entry(request, resource, action, resource_id, request_body)
            )

        return response


def _build_details(
    resource: str,
    action: str,
    resource_id: Optional[str],
    body: Optional[dict],
) -> Optional[str]:
    """Extract relevant fields from request body for audit details."""
    result: dict = {}

    # For settings, include the setting key from the URL
    if resource == "settings" and resource_id:
        result["setting"] = resource_id

    if body:
        allowed = _EXTRACT_FIELDS.get(resource)
        if allowed is not None:
            result.update({k: v for k, v in body.items() if k in allowed})
        else:
            # Unknown resource: capture all non-sensitive fields
            result.update({
                k: v for k, v in body.items()
                if k.lower() not in _SENSITIVE_FIELDS
            })

        # Always try to capture a name-like identifier
        for key in ("username", "name", "remark", "title"):
            if key in body and key not in result:
                result[key] = body[key]

    if not result:
        return None
    return json.dumps(result, ensure_ascii=False, default=str)


async def _write_audit_entry(
    request: Request,
    resource: str,
    action: str,
    resource_id: Optional[str],
    request_body: Optional[dict] = None,
) -> None:
    """Write an audit log entry from middleware context."""
    try:
        # Resolve admin from JWT
        token = _extract_token(request)
        admin_id = None
        admin_username = "unknown"

        if token:
            payload = decode_token(token, token_type=None)
            if payload:
                subject = payload.get("sub", "")
                admin_username = payload.get("username", subject)

                # Resolve account_id
                if subject.startswith("pwd:"):
                    username = subject[4:]
                    admin_username = username
                    try:
                        from web.backend.core.rbac import get_admin_account_by_username
                        account = await get_admin_account_by_username(username)
                        if account:
                            admin_id = account["id"]
                    except Exception:
                        pass
                else:
                    try:
                        telegram_id = int(subject)
                        from web.backend.core.rbac import get_admin_account_by_telegram_id
                        account = await get_admin_account_by_telegram_id(telegram_id)
                        if account:
                            admin_id = account["id"]
                            admin_username = account["username"]
                    except (ValueError, TypeError):
                        pass

        # v3 аутентифицируется API-ключом, а не JWT — актор берётся из ключа
        api_key_user = getattr(request.state, "api_key_user", None)
        if api_key_user is not None:
            admin_id = None
            admin_username = f"apikey:{getattr(api_key_user, 'key_name', None) or getattr(api_key_user, 'key_id', '?')}"

        # Get client IP (unified logic from deps.get_client_ip)
        from web.backend.api.deps import get_client_ip
        ip_address = get_client_ip(request)

        # Build details from request body
        details = _build_details(resource, action, resource_id, request_body)

        # Write to DB
        from web.backend.core.rbac import write_audit_log
        await write_audit_log(
            admin_id=admin_id,
            admin_username=admin_username,
            action=f"{resource}.{action}",
            resource=resource,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
        )

        # Broadcast via WebSocket for real-time notifications
        try:
            from web.backend.api.v2.websocket import broadcast_audit_event
            await broadcast_audit_event(
                admin_username=admin_username,
                action=f"{resource}.{action}",
                resource=resource,
                resource_id=resource_id,
            )
        except Exception:
            pass

    except Exception as e:
        logger.warning("Audit middleware failed: %s", e)

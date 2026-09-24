"""Audit middleware — automatically logs all mutable API actions.

Intercepts POST/PUT/PATCH/DELETE requests, resolves the admin from the JWT,
determines the resource/action from the URL pattern, and writes to admin_audit_log.
Also broadcasts audit events via WebSocket for real-time notifications.
"""
import asyncio
import json
import logging
import re
import time
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
# Ключ, в имени которого есть такая часть, тоже секрет: smtp_password,
# api_token, access_key, env_vars скрипта и т.п.
_SENSITIVE_PARTS = ("password", "secret", "token", "api_key", "private", "credential", "access_key", "env_vars", "otp")
_DETAILS_MAX = 4000
_VALUE_MAX = 300

# Общая запись аудита для маршрутов, которых нет в _ROUTE_MAP и чей обработчик
# сам ничего не пишет. Исключены чтения под видом POST и служебный шум
# (отметки «прочитано», присутствие в тикете, приём данных от агентов).
_GENERIC_SKIP_MODULES = {"collector", "me_devices"}
_GENERIC_SKIP = {
    ("logs", "ingest_frontend_logs"),
    ("users", "resolve_user"),
    ("users", "get_hwid_device_counts"),
    ("users", "fetch_user_ips"),
    ("users", "fetch_users_ips_by_node"),
    ("violations", "lookup_ips"),
    ("automations", "test_automation"),
    ("notifications", "mark_notifications_read"),
    ("notifications", "create_notification_endpoint"),
    ("support", "heartbeat"),
    ("support", "mark_read"),
    ("mailserver", "mark_inbox_read"),
    ("mailserver", "check_domain_dns"),
    ("scripts", "browse_github_repo"),
    ("bscheck", "preview"),
    ("bscheck", "scans_preview"),
    ("bscheck", "save_history"),
    ("reputation", "lookup"),
}
# Из auth — только то, что меняет способы входа; вход/выход пишутся отдельно
_GENERIC_AUTH_ONLY = {
    "wa_register_finish", "wa_delete_credential", "oauth_del_link",
    "totp_regen_backup", "totp_confirm_setup",
}
_JSON_BODY_MAX = 256 * 1024

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


# Разделы, где обработчики /api/v2 пишут аудит сами («user.delete» и т.п.).
# Мидлварь писала ту же операцию второй раз («users.delete»), а для настроек —
# ещё и со значением секретной настройки, которое обработчик маскирует.
# Исключения — действия, которые обработчик не пишет.
_HANDLER_LOGGED_V2 = {"users", "nodes", "hosts", "violations", "settings"}
_HANDLER_NOT_LOGGED = {("users", "sync_hwid")}


def _logged_by_handler(path: str, resource: str, action: str) -> bool:
    return (
        path.startswith("/api/v2/")
        and resource in _HANDLER_LOGGED_V2
        and (resource, action) not in _HANDLER_NOT_LOGGED
    )


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
        if not request.url.path.startswith("/api/v3/"):
            return await self._dispatch_audit(request, call_next)
        # Публичный API: каждый запрос ключа — в его журнал (метод, путь, код, IP)
        start = time.perf_counter()
        response = await self._dispatch_audit(request, call_next)
        api_key_user = getattr(request.state, "api_key_user", None)
        if api_key_user is not None:
            try:
                from web.backend.api.deps import get_client_ip
                from web.backend.core.api_key_usage import record_request
                record_request(
                    api_key_user.key_id, request.method, request.url.path, response.status_code,
                    get_client_ip(request), int((time.perf_counter() - start) * 1000),
                )
            except Exception as e:
                logger.debug("API key request log skipped: %s", e)
        return response

    async def _dispatch_audit(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
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
        if match:
            resource, action, _ = match
            # Skip actions already logged manually
            if (resource, action) in _SKIP_DUPLICATES or _logged_by_handler(path, resource, action):
                return await call_next(request)

        request_body = await _read_json_body(request)

        from web.backend.core.audit import request_audit_state
        state = {"written": False}
        token = request_audit_state.set(state)
        try:
            response = await call_next(request)
        finally:
            request_audit_state.reset(token)

        # Only log successful actions, and only if the handler wrote nothing itself
        if not 200 <= response.status_code < 300 or state["written"]:
            return response

        if match:
            resource, action, resource_id = match
            asyncio.create_task(
                _write_audit_entry(request, resource, action, resource_id, request_body)
            )
        else:
            target = _generic_target(request)
            if target:
                resource, action, resource_id = target
                asyncio.create_task(
                    _write_audit_entry(request, resource, action, resource_id, request_body, require_actor=True)
                )

        return response


async def _read_json_body(request: Request) -> Optional[dict]:
    """Тело запроса для деталей аудита — только небольшой JSON: загрузки
    файлов (бэкапы, плагины) в память целиком не читаем."""
    if "json" not in request.headers.get("content-type", ""):
        return None
    try:
        if int(request.headers.get("content-length") or 0) > _JSON_BODY_MAX:
            return None
        body_bytes = await request.body()
        if body_bytes:
            parsed = json.loads(body_bytes)
            return parsed if isinstance(parsed, dict) else {"items": parsed}
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        pass
    except Exception as e:
        logger.debug("Failed to read request body for audit: %s", e)
    return None


def _generic_target(request: Request) -> Optional[Tuple[str, str, Optional[str]]]:
    """(раздел, действие, id) для маршрута без собственного аудита — по
    обработчику FastAPI: «finance.create_payment», id — первый параметр пути."""
    endpoint = request.scope.get("endpoint")
    if endpoint is None:
        return None
    module_path = getattr(endpoint, "__module__", "") or ""
    module = module_path.rsplit(".", 1)[-1]
    name = getattr(endpoint, "__name__", "")
    if module in _GENERIC_SKIP_MODULES or (module, name) in _GENERIC_SKIP:
        return None
    if module == "auth" and name not in _GENERIC_AUTH_ONLY:
        return None
    resource = f"bedolaga_{module}" if ".bedolaga." in module_path else module
    params = request.scope.get("path_params") or {}
    resource_id = str(next(iter(params.values()))) if params else None
    return resource, name, resource_id


def _is_sensitive(key: str) -> bool:
    low = key.lower()
    return low in _SENSITIVE_FIELDS or any(part in low for part in _SENSITIVE_PARTS)


def _clip(value):
    if isinstance(value, str) and len(value) > _VALUE_MAX:
        return value[:_VALUE_MAX] + "…"
    if isinstance(value, list) and len(value) > 50:
        return value[:50] + [f"… +{len(value) - 50}"]
    return value


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
                k: _clip(v) for k, v in body.items()
                if not _is_sensitive(k)
            })

        # Always try to capture a name-like identifier
        for key in ("username", "name", "remark", "title"):
            if key in body and key not in result:
                result[key] = body[key]

    if not result:
        return None
    details = json.dumps(result, ensure_ascii=False, default=str)
    return details if len(details) <= _DETAILS_MAX else details[:_DETAILS_MAX] + "…"


async def _write_audit_entry(
    request: Request,
    resource: str,
    action: str,
    resource_id: Optional[str],
    request_body: Optional[dict] = None,
    require_actor: bool = False,
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

        # Общая запись — только за опознанного админа или ключ: запросы
        # агентов и анонимные ручки журнал не засоряют
        if require_actor and admin_id is None and api_key_user is None and admin_username == "unknown":
            return

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

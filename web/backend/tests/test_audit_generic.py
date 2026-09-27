"""Общая запись аудита: каждый мутирующий маршрут попадает в журнал ровно раз.

Маршрут без собственного аудита записывает мидлварь («finance.create_payment»);
маршрут, чей обработчик сам вызвал write_audit_log, второй записи не получает.
"""
import ast
import asyncio
import inspect
import json
import re
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from web.backend.core import audit_middleware
from web.backend.core.audit import write_audit_log


def _app():
    app = FastAPI()
    app.add_middleware(audit_middleware.AuditMiddleware)

    async def create_payment(item_id: int):
        return {"ok": True}

    async def delete_category(item_id: int):
        await write_audit_log(1, "root", "finance.category.delete", "finance", str(item_id))
        return {"ok": True}

    async def lookup():
        return {"ok": True}

    async def notify_violation_user(violation_id: int):
        return {"sent": False, "reason": "no_template"}

    for fn, path in ((create_payment, "/api/v2/finance/items/{item_id}/pay"),
                     (delete_category, "/api/v2/finance/categories/{item_id}")):
        fn.__module__ = "web.backend.api.v2.finance"
        app.add_api_route(path, fn, methods=["POST"])
    lookup.__module__ = "web.backend.api.v2.reputation"
    app.add_api_route("/api/v2/reputation/lookup", lookup, methods=["POST"])
    notify_violation_user.__module__ = "web.backend.api.v2.violations"
    app.add_api_route("/api/v2/violations/{violation_id}/notify", notify_violation_user, methods=["POST"])
    return app


@pytest.fixture
def written(monkeypatch):
    calls = []

    async def fake_entry(request, resource, action, resource_id, body=None, require_actor=False):
        calls.append((resource, action, resource_id, body, require_actor))

    monkeypatch.setattr(audit_middleware, "_write_audit_entry", fake_entry)
    return calls


async def _post(path, json=None):
    async with AsyncClient(transport=ASGITransport(app=_app()), base_url="http://t") as client:
        response = await client.post(path, json=json)
    await asyncio.sleep(0)
    return response


@pytest.mark.asyncio
async def test_route_without_own_audit_is_logged(written):
    await _post("/api/v2/finance/items/7/pay", json={"amount": 10, "api_token": "x"})
    assert written == [("finance", "create_payment", "7", {"amount": 10, "api_token": "x"}, True)]


@pytest.mark.asyncio
async def test_handler_audit_is_not_duplicated(written):
    await _post("/api/v2/finance/categories/3")
    assert written == []


@pytest.mark.asyncio
async def test_read_like_post_skipped(written):
    await _post("/api/v2/reputation/lookup")
    assert written == []


@pytest.mark.asyncio
async def test_unsent_client_warning_not_logged(written):
    """Не ушло — фиксировать нечего; ушедшее обработчик пишет сам (client_notified)."""
    await _post("/api/v2/violations/5/notify", json={})
    assert written == []


@pytest.mark.asyncio
async def test_audit_event_carries_author_account(monkeypatch):
    """По admin_id вкладка автора узнаёт своё действие: имя, под которым
    входили через Telegram, с именем аккаунта не совпадает."""
    from starlette.requests import Request

    from web.backend.api import deps
    from web.backend.api.v2 import websocket
    from web.backend.core import rbac

    sent = []

    async def fake_broadcast(**kwargs):
        sent.append(kwargs)

    async def fake_account(telegram_id):
        return {"id": 5, "username": "admin"}

    async def fake_write(**kwargs):
        pass

    monkeypatch.setattr(audit_middleware, "decode_token", lambda token, token_type=None: {"sub": "366945364"})
    monkeypatch.setattr(rbac, "get_admin_account_by_telegram_id", fake_account)
    monkeypatch.setattr(rbac, "write_audit_log", fake_write)
    monkeypatch.setattr(websocket, "broadcast_audit_event", fake_broadcast)
    monkeypatch.setattr(deps, "get_client_ip", lambda request: "127.0.0.1")

    request = Request({"type": "http", "method": "POST", "path": "/api/v2/finance/items/7/pay",
                       "headers": [(b"authorization", b"Bearer t")]})
    await audit_middleware._write_audit_entry(request, "finance", "create_payment", "7", require_actor=True)

    assert sent == [{"admin_username": "admin", "action": "finance.create_payment",
                     "resource": "finance", "resource_id": "7", "admin_id": 5}]


def test_sensitive_keys_dropped_from_details():
    details = audit_middleware._build_details(
        "finance", "create_account", None,
        {"name": "Aeza", "api_token": "t", "smtp_password": "p", "env_vars": {"A": "1"}, "note": "x" * 1000},
    )
    assert "api_token" not in details and "smtp_password" not in details and "env_vars" not in details
    assert "Aeza" in details
    assert len(details) < 500


def _app_endpoints():
    """(модуль, функция) всех ручек приложения.

    С 0.130 FastAPI держит включённые роутеры лениво, и обход app.routes видит
    только верхний уровень. Ручки собираются с самих роутеров модулей — после
    импорта приложения они все лежат в sys.modules.
    """
    from fastapi import APIRouter
    from web.backend.main import app

    routers = [app.router]
    for module in list(sys.modules.values()):
        if getattr(module, "__name__", "").startswith("web.backend."):
            routers += [value for value in vars(module).values() if isinstance(value, APIRouter)]
    endpoints = set()
    for router in routers:
        for route in router.routes:
            endpoint = getattr(route, "endpoint", None)
            if endpoint is not None:
                endpoints.add((endpoint.__module__.rsplit(".", 1)[-1], endpoint.__name__))
    return endpoints


def test_exclusions_point_to_real_routes():
    """Исключение без живого маршрута — опечатка, из-за которой шум попадёт в журнал."""
    endpoints = _app_endpoints()
    missing = [pair for pair in audit_middleware._GENERIC_SKIP if pair not in endpoints]
    assert missing == []
    auth_names = {name for module, name in endpoints if module == "auth"}
    assert audit_middleware._GENERIC_AUTH_ONLY <= auth_names


# ── Переводы: действие в журнале, ленте и тосте — человеческим текстом ──

_LOCALES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "locales"
# Как resourceKey в web/frontend/src/lib/auditFormat.ts
_NOT_PLURAL = {"settings", "dns", "analytics"}


def _resource_key(resource: str) -> str:
    if resource == "setting":
        return "settings"
    return resource[:-1] if resource.endswith("s") and resource not in _NOT_PLURAL else resource


def _audit_calls(tree):
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and getattr(node.func, "id", getattr(node.func, "attr", None)) == "write_audit_log"]


def _handler_actions() -> set:
    """Действия, которые обработчики пишут сами (строкой, не f-строкой)."""
    root = Path(__file__).resolve().parents[3]
    actions = set()
    for base in ("web/backend", "src", "shared"):
        for path in (root / base).rglob("*.py"):
            if "tests" in path.parts:
                continue
            for call in _audit_calls(ast.parse(path.read_text(encoding="utf-8"))):
                node = next((kw.value for kw in call.keywords if kw.arg == "action"),
                            call.args[2] if len(call.args) > 2 else None)
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    actions.add(node.value)
    return actions


def _route_map_actions() -> set:
    actions = set()
    for _, pattern, resource, action in audit_middleware._ROUTE_MAP:
        if "{1}" not in action:
            actions.add(f"{resource}.{action}")
            continue
        options = re.search(r"\(([^)]+)\)", pattern).group(1).split("|")
        actions |= {f"{resource}.{action.replace('{1}', option.replace('-', '_'))}" for option in options}
    return actions


def _generic_actions() -> set:
    """Имена, которые мидлварь пишет за обработчик: сам он аудит не пишет,
    _ROUTE_MAP маршрут не ловит, в исключениях его нет."""
    from fastapi import APIRouter
    from fastapi.routing import APIRoute
    from web.backend.main import app

    routers = [app.router]
    for module in list(sys.modules.values()):
        if getattr(module, "__name__", "").startswith("web.backend."):
            routers += [value for value in vars(module).values() if isinstance(value, APIRouter)]
    mw = audit_middleware
    actions = set()
    for router in routers:
        for route in router.routes:
            methods = (getattr(route, "methods", None) or set()) & {"POST", "PUT", "PATCH", "DELETE"}
            if not isinstance(route, APIRoute) or not methods or not route.path.startswith("/api/"):
                continue
            fn = route.endpoint
            module = fn.__module__.rsplit(".", 1)[-1]
            if module in mw._GENERIC_SKIP_MODULES or (module, fn.__name__) in mw._GENERIC_SKIP:
                continue
            if module == "auth" and fn.__name__ not in mw._GENERIC_AUTH_ONLY:
                continue
            if _audit_calls(ast.parse(textwrap.dedent(inspect.getsource(fn)))):
                continue
            sample = re.sub(r"\{[^}]+\}", "1", route.path)
            if all(mw._match_route(method, sample) for method in methods):
                continue
            resource = f"bedolaga_{module}" if ".bedolaga." in fn.__module__ else module
            actions.add(f"{resource}.{fn.__name__}")
    return actions


def _lookup(tree, dotted: str):
    for part in dotted.split("."):
        tree = tree.get(part) if isinstance(tree, dict) else None
    return tree


def test_every_audit_action_is_translated():
    """Без перевода журнал, лента и тост показывают сырой ключ вроде
    «violations.notify_violation_user: violations»."""
    actions = _handler_actions() | _route_map_actions() | _generic_actions()
    missing = []
    for lang in ("ru", "en"):
        audit = json.loads((_LOCALES / lang / "translation.json").read_text(encoding="utf-8"))["audit"]
        for full in sorted(a for a in actions if "." in a):
            prefix, verb = full.split(".", 1)
            rk = _resource_key(prefix)
            for section, key in (("resources", rk), ("actions", verb), ("descriptions", f"{verb}.{rk}")):
                if not isinstance(_lookup(audit[section], key), str):
                    missing.append(f"{lang}: audit.{section}.{key} ({full})")
    assert missing == []


def test_audit_changes_only_changed_fields_and_masks_secrets():
    from web.backend.core.audit import audit_changes
    before = {"trafficLimitBytes": 100, "status": "ACTIVE", "note": "a"}
    after = {"traffic_limit_bytes": 200, "status": "ACTIVE", "api_token": "new"}
    assert audit_changes(before, after) == {"traffic_limit_bytes": [100, 200], "api_token": [None, "***"]}


def test_audit_changes_without_previous_state():
    from web.backend.core.audit import audit_changes
    assert audit_changes(None, {"name": "n"}) == {"name": [None, "n"]}

"""Общая запись аудита: каждый мутирующий маршрут попадает в журнал ровно раз.

Маршрут без собственного аудита записывает мидлварь («finance.create_payment»);
маршрут, чей обработчик сам вызвал write_audit_log, второй записи не получает.
"""
import asyncio
import sys

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

    for fn, path in ((create_payment, "/api/v2/finance/items/{item_id}/pay"),
                     (delete_category, "/api/v2/finance/categories/{item_id}")):
        fn.__module__ = "web.backend.api.v2.finance"
        app.add_api_route(path, fn, methods=["POST"])
    lookup.__module__ = "web.backend.api.v2.reputation"
    app.add_api_route("/api/v2/reputation/lookup", lookup, methods=["POST"])
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


def test_audit_changes_only_changed_fields_and_masks_secrets():
    from web.backend.core.audit import audit_changes
    before = {"trafficLimitBytes": 100, "status": "ACTIVE", "note": "a"}
    after = {"traffic_limit_bytes": 200, "status": "ACTIVE", "api_token": "new"}
    assert audit_changes(before, after) == {"traffic_limit_bytes": [100, 200], "api_token": [None, "***"]}


def test_audit_changes_without_previous_state():
    from web.backend.core.audit import audit_changes
    assert audit_changes(None, {"name": "n"}) == {"name": [None, "n"]}

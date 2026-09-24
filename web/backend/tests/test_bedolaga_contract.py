"""Запросы в Bedolaga совпадают с её схемами.

Раньше админка слала поля под своими именами (traffic_gb, count, reason) —
Bedolaga отвечала 422 или молча теряла причину. 401/403 от Bedolaga уходили
админу как есть, и фронт разлогинивал его, приняв за истёкшую сессию.
"""
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from web.backend.api.v2 import bedolaga as bedolaga_pkg
from web.backend.api.v2.bedolaga import customers, marketing, promo

ADMIN = SimpleNamespace(account_id=1, username="root")


@pytest.fixture(autouse=True)
def _no_side_effects(monkeypatch):
    monkeypatch.setattr(bedolaga_pkg, "ensure_configured", lambda: None)

    async def no_audit(**kwargs):
        return None

    monkeypatch.setattr(customers, "write_audit_log", no_audit)
    monkeypatch.setattr(customers, "get_client_ip", lambda request: "127.0.0.1")


def _capture(monkeypatch, method):
    sent = {}

    async def fake(target_id, payload):
        sent["id"], sent["payload"] = target_id, payload
        return {"ok": True}

    monkeypatch.setattr(customers.bedolaga_client, method, fake)
    return sent


def test_upstream_auth_errors_become_502():
    assert bedolaga_pkg.upstream_status(401) == 502
    assert bedolaga_pkg.upstream_status(403) == 502
    assert bedolaga_pkg.upstream_status(404) == 404
    assert bedolaga_pkg.upstream_status(422) == 422


@pytest.mark.asyncio
async def test_proxy_does_not_pass_401_through():
    request = httpx.Request("GET", "http://bot/users")
    response = httpx.Response(401, json={"detail": "bad token"}, request=request)

    async def call():
        raise httpx.HTTPStatusError("boom", request=request, response=response)

    with pytest.raises(HTTPException) as exc:
        await bedolaga_pkg.proxy_request(call)
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_traffic_sent_as_gb(monkeypatch):
    sent = _capture(monkeypatch, "add_traffic")
    await customers.add_traffic(request=None, sub_id=5, data=customers.TrafficAddRequest(traffic_gb=50), admin=ADMIN)
    assert sent == {"id": 5, "payload": {"gb": 50}}


@pytest.mark.asyncio
async def test_devices_sent_as_devices(monkeypatch):
    sent = _capture(monkeypatch, "add_devices")
    await customers.add_devices(request=None, sub_id=5, data=customers.DevicesAddRequest(count=2), admin=ADMIN)
    assert sent == {"id": 5, "payload": {"devices": 2}}


@pytest.mark.asyncio
async def test_balance_reason_sent_as_description(monkeypatch):
    sent = _capture(monkeypatch, "modify_balance")
    data = customers.BalanceModifyRequest(amount_kopeks=-1500, reason="возврат")
    await customers.modify_balance(request=None, user_id=9, data=data, admin=ADMIN)
    assert sent["payload"] == {"amount_kopeks": -1500, "description": "возврат"}


def test_balance_limits_match_bedolaga():
    with pytest.raises(ValidationError):
        customers.BalanceModifyRequest(amount_kopeks=100_000_001)


@pytest.mark.asyncio
async def test_update_user_passes_only_whitelisted_fields(monkeypatch):
    sent = _capture(monkeypatch, "update_user")
    data = customers.UserUpdateRequest.model_validate({"first_name": "Иван", "balance_kopeks": 10**9, "status": "active"})
    await customers.update_user(request=None, user_id=3, data=data, admin=ADMIN)
    assert sent["payload"] == {"first_name": "Иван"}


@pytest.mark.asyncio
async def test_update_user_rejects_empty_body():
    with pytest.raises(HTTPException) as exc:
        await customers.update_user(request=None, user_id=3, data=customers.UserUpdateRequest(), admin=ADMIN)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("kind", ["balance", "subscription_days", "balance_and_days", "trial_subscription"])
def test_promo_types_accepted(kind):
    assert promo.PromoCreateRequest(code="X", type=kind).type == kind


@pytest.mark.parametrize("kind", ["subscription", "mixed"])
def test_promo_types_unknown_to_bedolaga_rejected(kind):
    with pytest.raises(ValidationError):
        promo.PromoCreateRequest(code="X", type=kind)


def test_campaign_keeps_bonus_fields():
    data = marketing.CampaignCreateRequest(
        name="Осень", start_parameter="autumn", bonus_type="balance", balance_bonus_kopeks=10000,
    ).model_dump()
    assert data["bonus_type"] == "balance"
    assert data["balance_bonus_kopeks"] == 10000


def test_campaign_requires_start_parameter():
    with pytest.raises(ValidationError):
        marketing.CampaignCreateRequest(name="Осень")


@pytest.mark.parametrize("url,expected", [
    ("https://sub.example.com/AbC123", "AbC123"),
    ("https://sub.example.com/api/sub/AbC123/", "AbC123"),
    ("https://sub.example.com/AbC123?client=clash", "AbC123"),
    (None, None),
    ("", None),
])
def test_short_uuid_from_subscription_url(url, expected):
    assert customers._short_uuid_from_url(url) == expected


def test_tariff_campaign_needs_tariff():
    with pytest.raises(ValidationError):
        marketing.CampaignCreateRequest(name="A", start_parameter="a", bonus_type="tariff")
    ok = marketing.CampaignCreateRequest(name="A", start_parameter="a", bonus_type="tariff", tariff_id=3, tariff_duration_days=30)
    assert ok.tariff_id == 3


def test_discount_promo_percent_bounds():
    assert promo.PromoCreateRequest(code="X", type="discount", balance_bonus_kopeks=15, subscription_days=24).type == "discount"
    with pytest.raises(ValidationError):
        promo.PromoCreateRequest(code="X", type="discount", balance_bonus_kopeks=150)


def test_dead_campaign_detail_route_removed():
    """У Бедолаги нет GET /campaigns/{id} — ручка всегда отвечала 404."""
    assert not any(
        route.path == "/campaigns/{campaign_id}" and "GET" in route.methods for route in marketing.router.routes
    )

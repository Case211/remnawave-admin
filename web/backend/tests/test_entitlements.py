"""Онлайн-лицензирование: верификация entitlements JWT, кэш, динамический гейт.

Сетевых вызовов нет — токены подписываются локально сгенерированной
Ed25519-парой, публичный ключ подсовывается через RWA_LICENSE_PUBKEY.
"""
from __future__ import annotations

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from web.backend.core import entitlements
from web.backend.core.plugins import (
    PluginManifest,
    PluginParts,
    _entitlement_gate,
    ui_license_state,
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@pytest.fixture()
def keypair(monkeypatch):
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    monkeypatch.setenv("RWA_LICENSE_PUBKEY", base64.b64encode(raw).decode())
    return private


def sign(private: Ed25519PrivateKey, payload: dict) -> str:
    header = _b64url(json.dumps({"alg": "EdDSA", "typ": "JWT"}).encode())
    body = _b64url(json.dumps(payload).encode())
    sig = private.sign(f"{header}.{body}".encode("ascii"))
    return f"{header}.{body}.{_b64url(sig)}"


def make_jwt(private, plugins: dict, *, exp_in: int = 3600) -> str:
    now = int(time.time())
    return sign(private, {
        "iss": "rwa-licensing", "sub": "test-instance",
        "iat": now, "exp": now + exp_in, "plugins": plugins,
    })


@pytest.fixture(autouse=True)
def clean_cache():
    entitlements._cache = entitlements.EntitlementsCache()
    yield
    entitlements._cache = entitlements.EntitlementsCache()


async def test_disconnect_clears_identity(keypair):
    # инстанс «подключён»
    entitlements._cache.instance_id = "inst-123"
    entitlements._cache.instance_token = "rwit_secret"
    entitlements._adopt_jwt(make_jwt(keypair, {"smart_support": {"state": "active"}}))
    assert entitlements.status_summary()["registered"] is True

    await entitlements.disconnect()  # db_service не подключён в тестах — только память

    summary = entitlements.status_summary()
    assert summary["registered"] is False
    assert summary["instance_id"] is None
    assert summary["plugins"] == {}


# ── верификация ──────────────────────────────────────────────────


def test_verify_ok(keypair):
    token = make_jwt(keypair, {"smart_support": {"state": "active"}})
    payload = entitlements.verify_entitlements_jwt(token)
    assert payload is not None
    assert payload["plugins"]["smart_support"]["state"] == "active"


def test_verify_rejects_bad_signature(keypair):
    other = Ed25519PrivateKey.generate()
    token = make_jwt(other, {"smart_support": {"state": "active"}})
    assert entitlements.verify_entitlements_jwt(token) is None


def test_verify_rejects_expired(keypair):
    token = make_jwt(keypair, {"x": {"state": "active"}}, exp_in=-10)
    assert entitlements.verify_entitlements_jwt(token) is None


def test_verify_rejects_wrong_alg(keypair):
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    body = _b64url(json.dumps({"iss": "rwa-licensing", "exp": 9999999999,
                               "plugins": {}}).encode())
    assert entitlements.verify_entitlements_jwt(f"{header}.{body}.") is None


# ── кэш и состояния ──────────────────────────────────────────────


def test_adopt_and_state(keypair):
    token = make_jwt(keypair, {
        "smart_support": {"state": "active", "tier": "standard",
                          "quota": {"period_limit": 500, "used": 3, "topup_left": 0}},
        "old_one": {"state": "expired"},
    })
    assert entitlements._adopt_jwt(token)
    assert entitlements.is_usable("smart_support")
    assert not entitlements.is_usable("old_one")
    assert not entitlements.is_usable("unknown")
    assert entitlements.plugin_state("smart_support")["quota"]["period_limit"] == 500


def test_stale_jwt_means_no_entitlements(keypair):
    token = make_jwt(keypair, {"smart_support": {"state": "active"}}, exp_in=1)
    assert entitlements._adopt_jwt(token)
    entitlements._cache.jwt_exp = int(time.time()) - 1  # сетевой грейс кончился
    assert entitlements.plugin_state("smart_support") is None
    assert not entitlements.is_usable("smart_support")


def test_ui_license_state(keypair):
    free = PluginManifest(id="f", name="F", version="1", billing="free")
    paid = PluginManifest(id="p", name="P", version="1", billing="subscription")
    assert ui_license_state(free) == "not_required"
    assert ui_license_state(paid) == "missing"

    entitlements._adopt_jwt(make_jwt(keypair, {"p": {"state": "grace"}}))
    assert ui_license_state(paid) == "valid"

    entitlements._adopt_jwt(make_jwt(keypair, {"p": {"state": "expired"}}))
    assert ui_license_state(paid) == "expired"


# ── динамический гейт ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gate_blocks_and_unblocks_without_restart(keypair):
    from fastapi import Depends

    app = FastAPI()
    r = APIRouter()

    @r.get("/hello")
    async def hello() -> dict:
        return {"hello": True}

    app.include_router(r, prefix="/api/v2/plugins/paid",
                       dependencies=[Depends(_entitlement_gate("paid"))])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        resp = await client.get("/api/v2/plugins/paid/hello")
        assert resp.status_code == 402
        assert resp.json()["detail"]["code"] == "license_required"

        # «Купили» подписку: свежий entitlements — роут ожил без ремонтирования
        entitlements._adopt_jwt(make_jwt(keypair, {"paid": {"state": "active"}}))
        resp = await client.get("/api/v2/plugins/paid/hello")
        assert resp.status_code == 200

        # Истекла: 402 с кодом продления
        entitlements._adopt_jwt(make_jwt(keypair, {"paid": {"state": "expired"}}))
        resp = await client.get("/api/v2/plugins/paid/hello")
        assert resp.status_code == 402
        assert resp.json()["detail"]["code"] == "license_expired"


# ── manifest v2 discovery ────────────────────────────────────────


def test_noop_plugin_discovery(monkeypatch, keypair):
    from web.backend.core import plugins as loader

    monkeypatch.setenv("RWA_DEV_PLUGINS", "scripts.plugin_noop:manifest")
    app = FastAPI()
    loaded = loader.register(app)
    assert [m.id for m in loaded] == ["noop"]
    assert loader.ui_license_state(loaded[0]) == "not_required"
    # Спрашиваем схему, а не обходим app.routes: с 0.130 FastAPI держит
    # включённые роутеры лениво (_IncludedRouter), и плоского списка
    # путей там больше нет — обход находил только /docs и /openapi.json,
    # хотя роут монтировался нормально.
    paths = set(app.openapi().get("paths") or {})
    assert "/api/v2/plugins/noop/ping" in paths

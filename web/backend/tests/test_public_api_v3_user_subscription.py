"""Ссылка подписки в ответах GET /api/v3/users и /api/v3/users/{uuid}."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from web.backend.core.config import get_web_settings
from web.backend.main import create_app


READ_KEY = {"id": 1, "name": "read-key", "scopes": ["users:read"]}
ROW = {
    "uuid": "u-1", "username": "alice", "status": "ACTIVE",
    "traffic_limit_bytes": 0, "used_traffic_bytes": 42,
    "expire_at": datetime(2026, 12, 1, tzinfo=timezone.utc),
    "short_uuid": "AbCdEf123", "subscription_url": "https://sub.example.com/AbCdEf123",
}


@pytest.fixture()
def v3_app(monkeypatch):
    monkeypatch.setenv("EXTERNAL_API_ENABLED", "true")
    get_web_settings.cache_clear()
    _app = create_app()
    yield _app
    _app.dependency_overrides.clear()
    get_web_settings.cache_clear()


@pytest_asyncio.fixture()
async def v3_client(v3_app):
    transport = ASGITransport(app=v3_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture()
def db():
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=ROW)
    conn.fetch = AsyncMock(return_value=[ROW])

    @asynccontextmanager
    async def acquire():
        yield conn

    service = MagicMock(is_connected=True, acquire=acquire)
    with patch("shared.database.db_service", service):
        yield conn


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=READ_KEY)
async def test_user_card_has_subscription(_v, v3_client, db):
    resp = await v3_client.get("/api/v3/users/u-1", headers={"X-API-Key": "rwa_test"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["short_uuid"] == "AbCdEf123"
    assert body["subscription_url"] == "https://sub.example.com/AbCdEf123"
    assert "raw_data->>'subscriptionUrl'" in db.fetchrow.await_args.args[0]


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=READ_KEY)
async def test_user_list_has_subscription(_v, v3_client, db):
    resp = await v3_client.get("/api/v3/users", headers={"X-API-Key": "rwa_test"})
    assert resp.status_code == 200
    assert resp.json()[0]["subscription_url"] == "https://sub.example.com/AbCdEf123"


WRITE_KEY = {"id": 2, "name": "write-key", "scopes": ["users:write"]}
PANEL_USER = {
    "uuid": "u-new", "username": "bob", "shortUuid": "Zz9",
    "subscriptionUrl": "https://sub.example.com/Zz9",
}


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=WRITE_KEY)
async def test_create_returns_subscription_and_stores_user(_v, v3_client):
    """Интегратор создаёт юзера и сразу выдаёт ссылку — без ожидания синка."""
    from shared.api_client import api_client

    service = MagicMock(is_connected=True, upsert_user=AsyncMock())
    with patch.object(api_client, "create_user", new_callable=AsyncMock,
                      return_value={"response": PANEL_USER}), \
            patch("shared.database.db_service", service):
        resp = await v3_client.post(
            "/api/v3/users", headers={"X-API-Key": "rwa_test"},
            json={"username": "bob", "expire_at": "2027-01-01T00:00:00Z"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["uuid"] == "u-new"
    assert body["short_uuid"] == "Zz9"
    assert body["subscription_url"] == "https://sub.example.com/Zz9"
    service.upsert_user.assert_awaited_once_with(PANEL_USER)


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=WRITE_KEY)
async def test_create_on_panel_3_takes_uuid_from_local_row(_v, v3_client):
    """Панель 3.x отвечает числовым id без uuid."""
    from shared.api_client import api_client

    service = MagicMock(is_connected=True, upsert_user=AsyncMock(),
                        get_user_uuid_by_panel_id=AsyncMock(return_value="u-local"))
    with patch.object(api_client, "create_user", new_callable=AsyncMock,
                      return_value={"response": {"id": 77, "username": "bob"}}), \
            patch("shared.database.db_service", service):
        resp = await v3_client.post(
            "/api/v3/users", headers={"X-API-Key": "rwa_test"},
            json={"username": "bob", "expire_at": "2027-01-01T00:00:00Z"},
        )
    assert resp.status_code == 201
    assert resp.json()["uuid"] == "u-local"
    service.get_user_uuid_by_panel_id.assert_awaited_once_with(77)


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=WRITE_KEY)
async def test_create_survives_local_db_failure(_v, v3_client):
    from shared.api_client import api_client

    service = MagicMock(is_connected=True, upsert_user=AsyncMock(side_effect=RuntimeError("db down")))
    with patch.object(api_client, "create_user", new_callable=AsyncMock,
                      return_value={"response": PANEL_USER}), \
            patch("shared.database.db_service", service):
        resp = await v3_client.post(
            "/api/v3/users", headers={"X-API-Key": "rwa_test"},
            json={"username": "bob", "expire_at": "2027-01-01T00:00:00Z"},
        )
    assert resp.status_code == 201
    assert resp.json()["subscription_url"] == "https://sub.example.com/Zz9"

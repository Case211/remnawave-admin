"""POST /api/v3/support-events — external support contact for delayed actions."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from web.backend.core.config import get_web_settings
from web.backend.main import create_app


USER_UUID = "11111111-2222-3333-4444-555555555555"
VALID_KEY = {"id": 7, "name": "support", "scopes": ["enforcement:support"]}
NO_SCOPE_KEY = {"id": 8, "name": "reader", "scopes": ["violations:read"]}


@pytest.fixture()
def v3_app(monkeypatch):
    monkeypatch.setenv("EXTERNAL_API_ENABLED", "true")
    get_web_settings.cache_clear()
    app = create_app()
    yield app
    app.dependency_overrides.clear()
    get_web_settings.cache_clear()


@pytest_asyncio.fixture()
async def v3_client(v3_app):
    transport = ASGITransport(app=v3_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def _db(*, duplicate=False, users=None, inserted=9):
    conn = AsyncMock()
    conn.fetchval = AsyncMock(side_effect=[1] if duplicate else [None, inserted])
    conn.fetch = AsyncMock(return_value=users if users is not None else [
        {"uuid": USER_UUID, "telegram_id": 123456789},
    ])
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=None)
    transaction.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=transaction)
    acquire = MagicMock()
    acquire.__aenter__ = AsyncMock(return_value=conn)
    acquire.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock(is_connected=True)
    db.acquire.return_value = acquire
    return db, conn


def _body():
    return {
        "source": "telegram-support",
        "kind": "customer_message",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "user": {"telegram_id": 123456789},
        "ticket_id": "ticket-42",
        "metadata": {"queue": "billing"},
    }


@pytest.mark.asyncio
async def test_requires_dedicated_scope(v3_client):
    with patch("web.backend.core.api_key_auth.validate_api_key", AsyncMock(return_value=NO_SCOPE_KEY)):
        response = await v3_client.post(
            "/api/v3/support-events", json=_body(),
            headers={"X-API-Key": "rwa_test", "Idempotency-Key": "evt-1"},
        )
    assert response.status_code == 403
    assert "enforcement:support" in response.json()["detail"]


@pytest.mark.asyncio
async def test_idempotency_key_is_required(v3_client):
    with patch("web.backend.core.api_key_auth.validate_api_key", AsyncMock(return_value=VALID_KEY)):
        response = await v3_client.post(
            "/api/v3/support-events", json=_body(), headers={"X-API-Key": "rwa_test"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_records_event_for_exact_user(v3_client):
    db, conn = _db()
    with patch("web.backend.core.api_key_auth.validate_api_key", AsyncMock(return_value=VALID_KEY)), \
            patch("shared.database.db_service", db):
        response = await v3_client.post(
            "/api/v3/support-events", json=_body(),
            headers={"X-API-Key": "rwa_test", "Idempotency-Key": "evt-1"},
        )
    assert response.status_code == 202
    assert response.json() == {"accepted": True, "duplicate": False}
    assert "telegram_id = $1" in conn.fetch.await_args.args[0]
    insert = conn.fetchval.await_args_list[1].args
    assert insert[1:5] == (7, "evt-1", "telegram-support", "customer_message")
    assert insert[5:7] == (USER_UUID, 123456789)


@pytest.mark.asyncio
async def test_duplicate_is_successful_noop(v3_client):
    db, conn = _db(duplicate=True)
    with patch("web.backend.core.api_key_auth.validate_api_key", AsyncMock(return_value=VALID_KEY)), \
            patch("shared.database.db_service", db):
        response = await v3_client.post(
            "/api/v3/support-events", json=_body(),
            headers={"X-API-Key": "rwa_test", "Idempotency-Key": "evt-1"},
        )
    assert response.status_code == 202
    assert response.json()["duplicate"] is True
    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("users,status", [([], 404), ([
    {"uuid": USER_UUID, "telegram_id": 1},
    {"uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "telegram_id": 1},
], 409)])
async def test_rejects_missing_or_ambiguous_identity(v3_client, users, status):
    db, _ = _db(users=users)
    with patch("web.backend.core.api_key_auth.validate_api_key", AsyncMock(return_value=VALID_KEY)), \
            patch("shared.database.db_service", db):
        response = await v3_client.post(
            "/api/v3/support-events", json=_body(),
            headers={"X-API-Key": "rwa_test", "Idempotency-Key": "evt-1"},
        )
    assert response.status_code == status

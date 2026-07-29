"""Integration tests for the Internal API proxy flow.

Tests RBAC, quota, audit, and counter operations in the
catch-all proxy endpoint (/api/v2/internal/proxy/...).
"""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from shared.api_client import api_client


pytestmark = pytest.mark.asyncio

RBAC_MODULE = "web.backend.core.rbac"
PROXY_MODULE = "web.backend.api.v2.internal"


# Именно setenv, а не setdefault: у разработчика в корневом .env лежит
# рабочий INTERNAL_API_SECRET, и приложение поднималось с ним, а тесты
# продолжали слать заголовок "test-secret" — весь файл отвечал 401. На
# чистой машине и в CI это не воспроизводится, поэтому тестовое окружение
# задаём принудительно и откатываем после теста.
TEST_ENV = {
    "INTERNAL_API_SECRET": "test-secret",
    "WEB_SECRET_KEY": "test-secret-key-for-proxy-tests",
    "BOT_TOKEN": "123:abc",
    "API_BASE_URL": "http://panel:3000",
}


@pytest.fixture
def app(monkeypatch):
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)

    from web.backend.core.config import get_web_settings
    get_web_settings.cache_clear()
    from web.backend.main import create_app

    yield create_app()

    # Настройки закэшированы с тестовым секретом — не оставляем их соседям.
    get_web_settings.cache_clear()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _auth_headers() -> dict:
    return {"X-Internal-Api-Secret": "test-secret"}


def _admin_headers(account_id: int = 1, username: str = "admin") -> dict:
    return {
        "X-Internal-Api-Secret": "test-secret",
        "X-Admin-Username": username,
        "X-Admin-Account-Id": str(account_id),
    }


# ── RBAC tests ───────────────────────────────────────────────────

async def test_rbac_allows_with_permission(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"response": {"users": []}}
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "admin", "role_id": 2}
            with patch("shared.rbac.has_permission", new_callable=AsyncMock) as mock_perm:
                mock_perm.return_value = True
                resp = await client.get("/api/v2/internal/proxy/api/users", headers=headers)
                assert resp.status_code == 200
                mock_req.assert_called_once()


async def test_rbac_denies_without_permission(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "viewer", "role_id": 3}
            with patch("shared.rbac.has_permission", new_callable=AsyncMock) as mock_perm:
                mock_perm.return_value = False
                resp = await client.get("/api/v2/internal/proxy/api/users", headers=headers)
                assert resp.status_code == 403
                mock_req.assert_not_called()


async def test_rbac_allows_superadmin(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"response": {"users": []}}
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "superadmin", "role_id": 1}
            resp = await client.get("/api/v2/internal/proxy/api/users", headers=headers)
            assert resp.status_code == 200
            mock_req.assert_called_once()


async def test_rbac_allows_unknown_resource(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"ok": True}
        resp = await client.get("/api/v2/internal/proxy/api/subscriptions", headers=headers)
        assert resp.status_code == 200
        mock_req.assert_called_once()


async def test_rbac_allows_legacy_admin_no_account_id(client, app):
    headers = _auth_headers()
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"response": {"users": []}}
        resp = await client.get("/api/v2/internal/proxy/api/users", headers=headers)
        assert resp.status_code == 200
        mock_req.assert_called_once()


# ── Quota tests ──────────────────────────────────────────────────

async def test_quota_allows_create_under_limit(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"response": {"uuid": "abc-123", "username": "test"}}
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "superadmin", "role_id": 1}
            with patch(f"{RBAC_MODULE}.check_quota", new_callable=AsyncMock) as mock_quota:
                mock_quota.return_value = (True, "")
                with patch(f"{RBAC_MODULE}.increment_usage_counter", new_callable=AsyncMock) as mock_inc:
                    mock_inc.return_value = True
                    resp = await client.post("/api/v2/internal/proxy/api/users", headers=headers, json={"username": "test"})
                    assert resp.status_code == 200
                    mock_req.assert_called_once()


async def test_quota_blocks_create_over_limit(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "superadmin", "role_id": 1}
            with patch(f"{RBAC_MODULE}.check_quota", new_callable=AsyncMock) as mock_quota:
                mock_quota.return_value = (False, "User quota exceeded")
                resp = await client.post("/api/v2/internal/proxy/api/users", headers=headers, json={"username": "test"})
                assert resp.status_code == 403
                mock_req.assert_not_called()


async def test_quota_race_rolls_back_created_resource(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"response": {"uuid": "abc-123", "username": "test"}}
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "superadmin", "role_id": 1}
            with patch(f"{RBAC_MODULE}.check_quota", new_callable=AsyncMock) as mock_quota:
                mock_quota.return_value = (True, "")
                with patch(f"{RBAC_MODULE}.increment_usage_counter", new_callable=AsyncMock) as mock_inc:
                    mock_inc.return_value = False
                    resp = await client.post("/api/v2/internal/proxy/api/users", headers=headers, json={"username": "test"})
                    assert resp.status_code == 409
                    assert mock_req.call_count >= 2


async def test_quota_decrement_on_delete(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"response": {}}
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "superadmin", "role_id": 1}
            with patch(f"{RBAC_MODULE}.increment_usage_counter", new_callable=AsyncMock) as mock_inc:
                mock_inc.return_value = True
                resp = await client.delete("/api/v2/internal/proxy/api/users/abc-123", headers=headers)
                assert resp.status_code == 200
                mock_inc.assert_called_once_with(1, "users_created", -1)


# ── Error mapping tests ──────────────────────────────────────────

async def test_validation_error_maps_to_400(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        from shared.api_client import ValidationError
        mock_req.side_effect = ValidationError("bad data")
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "superadmin", "role_id": 1}
            with patch(f"{RBAC_MODULE}.check_quota", new_callable=AsyncMock) as mock_q:
                mock_q.return_value = (True, "")
                with patch(f"{RBAC_MODULE}.increment_usage_counter", new_callable=AsyncMock) as mock_inc:
                    mock_inc.return_value = True
                    resp = await client.post("/api/v2/internal/proxy/api/users", headers=headers, json={"username": ""})
                    assert resp.status_code == 400


async def test_unauthorized_maps_to_401(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        from shared.api_client import UnauthorizedError
        mock_req.side_effect = UnauthorizedError("denied")
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "superadmin", "role_id": 1}
            resp = await client.get("/api/v2/internal/proxy/api/users", headers=headers)
            assert resp.status_code == 401


async def test_not_found_maps_to_404(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        from shared.api_client import NotFoundError
        mock_req.side_effect = NotFoundError("not found")
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "superadmin", "role_id": 1}
            resp = await client.get("/api/v2/internal/proxy/api/nodes/missing", headers=headers)
            assert resp.status_code == 404


async def test_rate_limit_maps_to_429(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        from shared.api_client import RateLimitError
        mock_req.side_effect = RateLimitError("too fast")
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "superadmin", "role_id": 1}
            resp = await client.get("/api/v2/internal/proxy/api/users", headers=headers)
            assert resp.status_code == 429


async def test_timeout_maps_to_504(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        from shared.api_client import TimeoutError
        mock_req.side_effect = TimeoutError("timed out")
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "superadmin", "role_id": 1}
            resp = await client.get("/api/v2/internal/proxy/api/users", headers=headers)
            assert resp.status_code == 504


async def test_server_error_maps_to_502(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        from shared.api_client import ServerError
        mock_req.side_effect = ServerError("boom", status_code=500)
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "superadmin", "role_id": 1}
            resp = await client.get("/api/v2/internal/proxy/api/users", headers=headers)
            assert resp.status_code == 502


# ── Action mapping tests ─────────────────────────────────────────

async def test_get_maps_to_view_action(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"response": {}}
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "admin", "role_id": 2}
            with patch("shared.rbac.has_permission", new_callable=AsyncMock) as mock_perm:
                mock_perm.return_value = True
                await client.get("/api/v2/internal/proxy/api/nodes", headers=headers)
                mock_perm.assert_called_once_with(2, "nodes", "view")


async def test_post_to_root_maps_to_create_action(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"response": {}}
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "admin", "role_id": 2}
            with patch("shared.rbac.has_permission", new_callable=AsyncMock) as mock_perm:
                mock_perm.return_value = True
                with patch(f"{RBAC_MODULE}.check_quota", new_callable=AsyncMock) as mock_quota:
                    mock_quota.return_value = (True, "")
                    with patch(f"{RBAC_MODULE}.increment_usage_counter", new_callable=AsyncMock) as mock_inc:
                        mock_inc.return_value = True
                        await client.post("/api/v2/internal/proxy/api/hosts", headers=headers, json={"remark": "test"})
                        mock_perm.assert_called_once_with(2, "hosts", "create")


async def test_post_with_bulk_maps_to_bulk_operations(client, app):
    headers = _admin_headers(account_id=1)
    with patch.object(api_client, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = {"response": {}}
        with patch(f"{RBAC_MODULE}.get_admin_account_by_id", new_callable=AsyncMock) as mock_admin:
            mock_admin.return_value = {"role_name": "admin", "role_id": 2}
            with patch("shared.rbac.has_permission", new_callable=AsyncMock) as mock_perm:
                mock_perm.return_value = True
                await client.post("/api/v2/internal/proxy/api/users/bulk/delete", headers=headers, json={"uuids": []})
                mock_perm.assert_called_once_with(2, "users", "bulk_operations")


# ── Missing auth test ────────────────────────────────────────────

async def test_missing_internal_secret_returns_401(client, app):
    resp = await client.get("/api/v2/internal/proxy/api/users")
    assert resp.status_code == 401

"""IP юзеров ноды: имена вместо числовых id панели и зона видимости админа."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

PANEL_RESULT = {"response": {"isCompleted": True, "isFailed": False, "result": {
    "success": True, "nodeUuid": "n-1",
    "users": [
        {"userId": 7, "ips": [{"ip": "1.2.3.4", "lastSeen": "2026-09-23T10:00:00Z"}]},
        {"userId": 8, "ips": [{"ip": "5.6.7.8", "lastSeen": "2026-09-23T11:00:00Z"}]},
        {"userId": 99, "ips": [{"ip": "9.9.9.9", "lastSeen": "2026-09-23T12:00:00Z"}]},
    ],
}}}


@pytest.fixture()
def db():
    conn = MagicMock(fetch=AsyncMock(return_value=[
        {"id": 7, "uuid": "aaa", "username": "alice"},
        {"id": 8, "uuid": "bbb", "username": "bob"},
    ]))

    @asynccontextmanager
    async def acquire():
        yield conn

    with patch("shared.database.db_service", MagicMock(is_connected=True, acquire=acquire)):
        yield conn


def _get(client):
    return client.get("/api/v2/users/node/n-1/fetch-users-ips/result/job-1")


@pytest.mark.asyncio
@patch("web.backend.api.v2.users.check_access", new_callable=AsyncMock, return_value=True)
@patch("web.backend.api.v2.users.get_visible_user_uuids", new_callable=AsyncMock, return_value=None)
async def test_users_get_names(_vis, _acc, db, client):
    from shared.api_client import api_client

    with patch.object(api_client, "get_fetch_users_ips_result", new_callable=AsyncMock, return_value=PANEL_RESULT):
        resp = await _get(client)
    assert resp.status_code == 200
    users = resp.json()["result"]["users"]
    assert [(u["userId"], u["username"], u["uuid"]) for u in users] == [
        (7, "alice", "aaa"), (8, "bob", "bbb"), (99, None, None),
    ]
    # время последнего появления IP не теряется
    assert users[0]["ips"][0]["lastSeen"] == "2026-09-23T10:00:00Z"


@pytest.mark.asyncio
@patch("web.backend.api.v2.users.check_access", new_callable=AsyncMock, return_value=True)
@patch("web.backend.api.v2.users.get_visible_user_uuids", new_callable=AsyncMock, return_value={"aaa"})
async def test_limited_admin_sees_only_own_users(_vis, _acc, db, client):
    """Раньше ограниченный админ получал адреса всех юзеров ноды."""
    from shared.api_client import api_client

    with patch.object(api_client, "get_fetch_users_ips_result", new_callable=AsyncMock, return_value=PANEL_RESULT):
        resp = await _get(client)
    assert [u["username"] for u in resp.json()["result"]["users"]] == ["alice"]


@pytest.mark.asyncio
@patch("web.backend.api.v2.users.check_access", new_callable=AsyncMock, return_value=False)
async def test_node_outside_scope_is_forbidden(_acc, client):
    assert (await _get(client)).status_code == 403
    assert (await client.post("/api/v2/users/node/n-1/fetch-users-ips")).status_code == 403

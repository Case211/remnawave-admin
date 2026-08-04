"""Tests for scripts API — /api/v2/fleet/scripts/*."""
import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock

from web.backend.api.deps import get_current_admin
from .conftest import make_admin


MOCK_SCRIPT_ROW = {
    "id": 1,
    "name": "check_disk",
    "display_name": "Check Disk Usage",
    "description": "Reports disk usage on the node",
    "category": "monitoring",
    "script_content": "#!/bin/bash\ndf -h",
    "timeout_seconds": 60,
    "requires_root": False,
    "is_builtin": False,
    "source_url": None,
    "imported_at": None,
    "created_at": datetime(2026, 2, 1, 12, 0, 0),
    "updated_at": None,
    "created_by": 1,
}

MOCK_SCRIPT_BUILTIN = {
    **MOCK_SCRIPT_ROW,
    "id": 2,
    "name": "system_info",
    "display_name": "System Info",
    "is_builtin": True,
}

MOCK_EXEC_ROW = {
    "id": 10,
    "node_uuid": "node-111",
    "status": "completed",
    "output": "Filesystem  Size  Used\n/dev/sda1  50G  20G",
    "exit_code": 0,
    "started_at": datetime(2026, 3, 6, 10, 0, 0),
    "finished_at": datetime(2026, 3, 6, 10, 0, 3),
    "duration_ms": 3000,
}


def _mock_db_service(fetch_return=None, fetchrow_return=None, fetchval_return=None, execute_return="DELETE 1"):
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=fetch_return or [])
    mock_conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    mock_conn.fetchval = AsyncMock(return_value=fetchval_return)
    mock_conn.execute = AsyncMock(return_value=execute_return)

    mock_svc = MagicMock()
    mock_svc.is_connected = True
    mock_svc.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_svc.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_svc, mock_conn


# ── Helper unit tests ────────────────────────────────────────────


class TestNormalizeGithubUrl:
    """Unit tests for _normalize_github_url."""

    def test_blob_url_converted(self):
        from web.backend.api.v2.scripts import _normalize_github_url
        url = "https://github.com/user/repo/blob/main/scripts/check.sh"
        result = _normalize_github_url(url)
        assert result == "https://raw.githubusercontent.com/user/repo/main/scripts/check.sh"

    def test_raw_url_unchanged(self):
        from web.backend.api.v2.scripts import _normalize_github_url
        url = "https://raw.githubusercontent.com/user/repo/main/script.sh"
        result = _normalize_github_url(url)
        assert result == url

    def test_non_github_url_unchanged(self):
        from web.backend.api.v2.scripts import _normalize_github_url
        url = "https://example.com/script.sh"
        result = _normalize_github_url(url)
        assert result == url


class TestParseRepoUrl:
    """Unit tests for _parse_repo_url."""

    def test_valid_repo_url(self):
        from web.backend.api.v2.scripts import _parse_repo_url
        owner, repo = _parse_repo_url("https://github.com/user/my-repo")
        assert owner == "user"
        assert repo == "my-repo"

    def test_repo_url_with_git_suffix(self):
        from web.backend.api.v2.scripts import _parse_repo_url
        owner, repo = _parse_repo_url("https://github.com/user/my-repo.git")
        assert owner == "user"
        assert repo == "my-repo"

    def test_invalid_url_raises(self):
        from web.backend.api.v2.scripts import _parse_repo_url
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _parse_repo_url("https://example.com/not-github")
        assert exc_info.value.status_code == 400


# ── Script CRUD tests ────────────────────────────────────────────


class TestListScripts:
    """GET /api/v2/fleet/scripts."""

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_list_scripts_success(self, mock_db_svc, client):
        list_row = {k: v for k, v in MOCK_SCRIPT_ROW.items()
                    if k in ("id", "name", "display_name", "description", "category",
                             "timeout_seconds", "requires_root", "is_builtin")}
        mock_svc, _ = _mock_db_service(fetch_return=[list_row])
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.get("/api/v2/fleet/scripts")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "check_disk"

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_list_scripts_with_category(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service(fetch_return=[])
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.get("/api/v2/fleet/scripts?category=monitoring")
        assert resp.status_code == 200


class TestGetScript:
    """GET /api/v2/fleet/scripts/{id}."""

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_get_script_success(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service(fetchrow_return=MOCK_SCRIPT_ROW)
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.get("/api/v2/fleet/scripts/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "check_disk"
        assert data["script_content"] == "#!/bin/bash\ndf -h"

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_get_script_not_found(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service(fetchrow_return=None)
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.get("/api/v2/fleet/scripts/999")
        assert resp.status_code == 404


class TestCreateScript:
    """POST /api/v2/fleet/scripts."""

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_create_script_success(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service(fetchrow_return=MOCK_SCRIPT_ROW)
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.post("/api/v2/fleet/scripts", json={
            "name": "check_disk",
            "display_name": "Check Disk Usage",
            "script_content": "#!/bin/bash\ndf -h",
            "category": "monitoring",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "check_disk"


class TestUpdateScript:
    """PATCH /api/v2/fleet/scripts/{id}."""

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_update_script_success(self, mock_db_svc, client):
        updated = {**MOCK_SCRIPT_ROW, "display_name": "Updated Name"}
        mock_svc, mock_conn = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire
        # First call: check exists, second: update
        mock_conn.fetchrow = AsyncMock(side_effect=[
            {"is_builtin": False},
            updated,
        ])

        resp = await client.patch("/api/v2/fleet/scripts/1", json={"display_name": "Updated Name"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_update_builtin_script_forbidden(self, mock_db_svc, client):
        mock_svc, mock_conn = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire
        mock_conn.fetchrow = AsyncMock(return_value={"is_builtin": True})

        resp = await client.patch("/api/v2/fleet/scripts/2", json={"display_name": "X"})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_update_script_not_found(self, mock_db_svc, client):
        mock_svc, mock_conn = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire
        mock_conn.fetchrow = AsyncMock(return_value=None)

        resp = await client.patch("/api/v2/fleet/scripts/999", json={"display_name": "X"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_update_script_no_fields(self, mock_db_svc, client):
        mock_svc, mock_conn = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire
        mock_conn.fetchrow = AsyncMock(return_value={"is_builtin": False})

        resp = await client.patch("/api/v2/fleet/scripts/1", json={})
        assert resp.status_code == 400


class TestDeleteScript:
    """DELETE /api/v2/fleet/scripts/{id}."""

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_delete_script_success(self, mock_db_svc, client):
        mock_svc, mock_conn = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire
        mock_conn.fetchrow = AsyncMock(return_value={"is_builtin": False})

        resp = await client.delete("/api/v2/fleet/scripts/1")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_delete_builtin_script_forbidden(self, mock_db_svc, client):
        mock_svc, mock_conn = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire
        mock_conn.fetchrow = AsyncMock(return_value={"is_builtin": True})

        resp = await client.delete("/api/v2/fleet/scripts/2")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_delete_script_not_found(self, mock_db_svc, client):
        mock_svc, mock_conn = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire
        mock_conn.fetchrow = AsyncMock(return_value=None)

        resp = await client.delete("/api/v2/fleet/scripts/999")
        assert resp.status_code == 404


# ── Execution tests ──────────────────────────────────────────────


class TestExecScript:
    """POST /api/v2/fleet/exec-script."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.scripts.sign_command_with_ts", return_value=({"type": "exec_script"}, "sig"))
    @patch("web.backend.api.v2.scripts.agent_manager")
    @patch("shared.database.db_service")
    async def test_exec_script_success(self, mock_db_svc, mock_agent_mgr, mock_sign, client):
        mock_svc, mock_conn = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        # Call 1: get script, Call 2: get agent_token, Call 3: insert command log
        mock_conn.fetchrow = AsyncMock(side_effect=[
            MOCK_SCRIPT_ROW,
            {"agent_token": "token-123"},
            {"id": 10},
        ])

        mock_agent_mgr.is_connected = MagicMock(return_value=True)
        mock_agent_mgr.send_command = AsyncMock(return_value=True)

        resp = await client.post("/api/v2/fleet/exec-script", json={
            "script_id": 1,
            "node_uuid": "node-111",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["exec_id"] == 10
        assert data["status"] == "running"

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.scripts.agent_manager")
    @patch("shared.database.db_service")
    async def test_exec_script_agent_not_connected(self, mock_db_svc, mock_agent_mgr, client):
        mock_svc, _ = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire
        mock_agent_mgr.is_connected = MagicMock(return_value=False)

        resp = await client.post("/api/v2/fleet/exec-script", json={
            "script_id": 1,
            "node_uuid": "node-111",
        })
        assert resp.status_code == 400


class TestExecScriptBulk:
    """POST /api/v2/fleet/exec-script-bulk."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.scripts.sign_command_with_ts", return_value=({"type": "exec_script"}, "sig"))
    @patch("web.backend.api.v2.scripts.agent_manager")
    @patch("shared.database.db_service")
    async def test_bulk_single_node_success(self, mock_db_svc, mock_agent_mgr, mock_sign, client):
        mock_svc, mock_conn = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire
        # fetch script once, then per node: agent_token, insert command log
        mock_conn.fetchrow = AsyncMock(side_effect=[
            MOCK_SCRIPT_ROW,
            {"agent_token": "token-123"},
            {"id": 20},
        ])
        mock_agent_mgr.is_connected = MagicMock(return_value=True)
        mock_agent_mgr.send_command = AsyncMock(return_value=True)

        resp = await client.post("/api/v2/fleet/exec-script-bulk", json={
            "script_id": 1,
            "node_uuids": ["node-111"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["exec_id"] == 20
        assert data["results"][0]["status"] == "running"
        assert data["results"][0].get("error") is None

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.scripts.agent_manager")
    @patch("shared.database.db_service")
    async def test_bulk_node_not_connected_reported(self, mock_db_svc, mock_agent_mgr, client):
        mock_svc, mock_conn = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire
        mock_conn.fetchrow = AsyncMock(side_effect=[MOCK_SCRIPT_ROW])  # only script fetch
        mock_agent_mgr.is_connected = MagicMock(return_value=False)

        resp = await client.post("/api/v2/fleet/exec-script-bulk", json={
            "script_id": 1,
            "node_uuids": ["node-off"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["status"] == "error"
        assert data["results"][0]["error"] == "AGENT_NOT_CONNECTED"

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_bulk_empty_nodes_rejected(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service()
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire
        resp = await client.post("/api/v2/fleet/exec-script-bulk", json={
            "script_id": 1,
            "node_uuids": [],
        })
        assert resp.status_code == 400


class TestExecStatus:
    """GET /api/v2/fleet/exec/{id}."""

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_exec_status_success(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service(fetchrow_return=MOCK_EXEC_ROW)
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.get("/api/v2/fleet/exec/10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["exit_code"] == 0

    @pytest.mark.asyncio
    @patch("shared.database.db_service")
    async def test_exec_status_not_found(self, mock_db_svc, client):
        mock_svc, _ = _mock_db_service(fetchrow_return=None)
        mock_db_svc.is_connected = mock_svc.is_connected
        mock_db_svc.acquire = mock_svc.acquire

        resp = await client.get("/api/v2/fleet/exec/999")
        assert resp.status_code == 404


# ── RBAC ─────────────────────────────────────────────────────────


class TestScriptsRBAC:
    """RBAC tests for scripts endpoints."""

    @pytest.mark.asyncio
    async def test_anon_unauthorized(self, anon_client):
        resp = await anon_client.get("/api/v2/fleet/scripts")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_no_scripts_access(self, app, viewer):
        """Viewer has fleet.view but NOT fleet.scripts."""
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v2/fleet/scripts")
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_exec_script(self, app, viewer):
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v2/fleet/exec-script", json={
                "script_id": 1, "node_uuid": "node-111",
            })
            assert resp.status_code == 403


class TestResolvePendingUpdateCommands:
    """Реконнект агента закрывает зависшие running-команды update_agent.

    Кейс из сообщества: обновление агента прошло штатно, но перекат убил
    агента до отправки command_result — команда зависала в running и позже
    показывалась как Error при фактически успешном обновлении.
    """

    @pytest.mark.asyncio
    async def test_marks_running_update_completed(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from web.backend.api.v2 import agent_ws

        conn = AsyncMock()
        conn.execute.return_value = "UPDATE 1"
        acquire_cm = MagicMock()
        acquire_cm.__aenter__ = AsyncMock(return_value=conn)
        acquire_cm.__aexit__ = AsyncMock(return_value=False)
        mock_svc = MagicMock()
        mock_svc.is_connected = True
        mock_svc.acquire.return_value = acquire_cm

        with patch("shared.database.db_service", mock_svc):
            await agent_ws._resolve_pending_update_commands("node-1")

        conn.execute.assert_awaited_once()
        sql = conn.execute.call_args.args[0]
        assert "status = 'completed'" in sql
        assert "status = 'running'" in sql
        assert "script=update_agent" in sql
        assert conn.execute.call_args.args[1] == "node-1"

    @pytest.mark.asyncio
    async def test_silent_when_db_down(self):
        from unittest.mock import MagicMock, patch
        from web.backend.api.v2 import agent_ws

        mock_svc = MagicMock()
        mock_svc.is_connected = False
        with patch("shared.database.db_service", mock_svc):
            await agent_ws._resolve_pending_update_commands("node-1")
        mock_svc.acquire.assert_not_called()

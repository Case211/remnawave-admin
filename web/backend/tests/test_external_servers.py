"""Свои серверы в мониторинге: строка nodes с is_external.

Агент, коллектор и алерты работают как для ноды; синк с панелью такие
строки не удаляет, страница нод их не показывает, Fleet помечает бейджем.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.db._base import _db_row_to_api_format
from .test_nodes_api import MOCK_NODES


EXTERNAL = {
    "uuid": "ext-111",
    "name": "panel-01",
    "address": "203.0.113.10",
    "port": None,
    "is_disabled": False,
    "is_connected": True,
    "is_external": True,
    "description": "Панель и бот",
    "cpu_usage": 12.0,
    "memory_usage": 40.0,
}


class TestRowFormat:
    def test_external_row_reads_connection_from_column(self):
        """raw_data своего сервера никто не обновляет — связь берём из столбца."""
        raw = {"uuid": "ext-111", "name": "panel-01", "isConnected": False, "isExternal": True}
        row = {"uuid": "ext-111", "is_external": True, "is_connected": True,
               "raw_data": json.dumps(raw), "cpu_usage": 12.0}
        result = _db_row_to_api_format(row)
        assert result["isExternal"] is True
        assert result["isConnected"] is True
        assert result["cpu_usage"] == 12.0

    def test_panel_row_untouched(self):
        raw = {"uuid": "n1", "name": "EU-1", "isConnected": False}
        row = {"uuid": "n1", "is_external": False, "is_connected": True, "raw_data": json.dumps(raw)}
        result = _db_row_to_api_format(row)
        assert "isExternal" not in result
        assert result["isConnected"] is False

    def test_fallback_without_raw_data_exposes_flag(self):
        row = {"uuid": "ext-1", "name": "db-01", "is_external": True, "is_connected": False}
        result = _db_row_to_api_format(row)
        assert result["isExternal"] is True and result["name"] == "db-01"


class TestNodesListHidesExternal:
    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes._get_nodes_list", new_callable=AsyncMock,
           return_value=MOCK_NODES + [EXTERNAL])
    @patch("web.backend.api.v2.nodes.fetch_nodes_usage_by_range", new_callable=AsyncMock, return_value=None)
    @patch("web.backend.api.v2.nodes.fetch_nodes_realtime_usage", new_callable=AsyncMock, return_value=None)
    async def test_external_not_in_nodes_page(self, _rt, _range, _get, client):
        resp = await client.get("/api/v2/nodes")
        assert resp.status_code == 200
        uuids = {n["uuid"] for n in resp.json()["items"]}
        assert "ext-111" not in uuids
        assert {"node-aaa", "node-bbb"} <= uuids


class TestFleetShowsExternal:
    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes._get_nodes_list", new_callable=AsyncMock,
           return_value=MOCK_NODES + [EXTERNAL])
    @patch("web.backend.api.v2.analytics.fetch_nodes_usage_by_range", new_callable=AsyncMock, return_value=None)
    @patch("web.backend.api.v2.analytics.fetch_nodes_realtime_usage", new_callable=AsyncMock, return_value=[])
    async def test_external_marked_in_fleet(self, _rt, _range, _get, client):
        db = MagicMock()
        db.is_connected = False
        with patch("shared.database.db_service", db):
            resp = await client.get("/api/v2/analytics/node-fleet")
        assert resp.status_code == 200
        items = {n["uuid"]: n for n in resp.json()["nodes"]}
        assert items["ext-111"]["is_external"] is True
        assert items["ext-111"]["description"] == "Панель и бот"
        assert items["node-aaa"]["is_external"] is False


def _db(create_ok=True, delete_ok=True):
    db = MagicMock()
    db.is_connected = True
    db.create_external_node = AsyncMock(return_value=create_ok)
    db.delete_external_node = AsyncMock(return_value=delete_ok)
    return db


class TestCreateExternalServer:
    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes.write_audit_log", new_callable=AsyncMock)
    @patch("shared.agent_tokens.set_node_agent_token", new_callable=AsyncMock, return_value="tok-123")
    async def test_creates_row_token_and_command(self, _tok, _audit, client):
        db = _db()
        with patch("shared.database.db_service", db):
            resp = await client.post("/api/v2/nodes/external", json={
                "name": "  panel-01 ", "address": "203.0.113.10", "description": "бот и панель",
            })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "panel-01" and data["token"] == "tok-123"
        assert f"--uuid {data['uuid']}" in data["install_command"]
        assert "--token tok-123" in data["install_command"]
        assert "--url http://test" in data["install_command"]
        args = db.create_external_node.call_args.args
        assert args[0] == data["uuid"] and args[1:] == ("panel-01", "203.0.113.10", "бот и панель")

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes.write_audit_log", new_callable=AsyncMock)
    @patch("shared.agent_tokens.set_node_agent_token", new_callable=AsyncMock, return_value=None)
    async def test_token_failure_rolls_back_row(self, _tok, _audit, client):
        db = _db()
        with patch("shared.database.db_service", db):
            resp = await client.post("/api/v2/nodes/external", json={"name": "x"})
        assert resp.status_code == 500
        db.delete_external_node.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_name_required(self, client):
        with patch("shared.database.db_service", _db()):
            resp = await client.post("/api/v2/nodes/external", json={"name": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_viewer_forbidden(self, viewer_client):
        resp = await viewer_client.post("/api/v2/nodes/external", json={"name": "x"})
        assert resp.status_code == 403


class TestDeleteExternalServer:
    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes.write_audit_log", new_callable=AsyncMock)
    @patch("web.backend.api.v2.nodes.check_access", new_callable=AsyncMock, return_value=True)
    async def test_deletes(self, _access, _audit, client):
        db = _db()
        with patch("shared.database.db_service", db):
            resp = await client.delete("/api/v2/nodes/external/ext-111")
        assert resp.status_code == 200 and resp.json()["success"] is True
        db.delete_external_node.assert_awaited_once_with("ext-111")

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes.check_access", new_callable=AsyncMock, return_value=True)
    async def test_panel_node_is_not_deletable_here(self, _access, client):
        """delete_external_node трогает только is_external — для ноды панели это 404."""
        with patch("shared.database.db_service", _db(delete_ok=False)):
            resp = await client.delete("/api/v2/nodes/external/node-aaa")
        assert resp.status_code == 404


class TestSyncKeepsExternal:
    @pytest.mark.asyncio
    async def test_reconciliation_skips_external_rows(self):
        from shared.sync import SyncService

        api = AsyncMock()
        api.get_nodes.return_value = {"response": [{"uuid": "N1", "name": "Estonia"}]}
        db = AsyncMock()
        db.is_connected = True
        db.get_all_nodes.return_value = [
            {"uuid": "N1", "name": "Estonia"},
            {"uuid": "N2", "name": "Gone"},
            {"uuid": "E1", "name": "panel-01", "isExternal": True},
        ]
        db.delete_node.return_value = True
        with patch("shared.sync.db_service", db), patch("shared.sync.api_client", api):
            synced = await SyncService().sync_nodes()
        assert synced == 1
        deleted = [c.args[0] for c in db.delete_node.await_args_list]
        assert deleted == ["N2"]

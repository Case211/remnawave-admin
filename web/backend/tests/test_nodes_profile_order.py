"""Правка профиля ноды и порядок нод в панели."""
from unittest.mock import AsyncMock, patch

import pytest

UUID = "6a4a7ce3-5574-4c2f-83ff-7cd979c82251"
PANEL_NODE = {"uuid": UUID, "name": "Finland", "address": "a", "port": 3000,
              "configProfile": {"activeConfigProfileUuid": "p-1",
                                "activeInbounds": [{"uuid": "i-1", "tag": "Finland W"}]}}


class TestProfileEdit:
    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes.write_audit_log", new_callable=AsyncMock)
    @patch("web.backend.api.v2.nodes.check_access", new_callable=AsyncMock, return_value=True)
    async def test_profile_and_inbounds_go_to_panel_together(self, _acc, _audit, client):
        from shared.api_client import api_client

        with patch.object(api_client, "update_node", new_callable=AsyncMock,
                          return_value={"response": PANEL_NODE}) as upd:
            resp = await client.patch(f"/api/v2/nodes/{UUID}",
                                      json={"config_profile_uuid": "p-1", "active_inbounds": ["i-1"]})
        assert resp.status_code == 200
        assert upd.await_args.kwargs == {"config_profile_uuid": "p-1", "active_inbounds": ["i-1"]}
        body = resp.json()
        assert body["config_profile_uuid"] == "p-1" and body["active_inbound_uuids"] == ["i-1"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", [
        {"config_profile_uuid": "p-1"},
        {"active_inbounds": ["i-1"]},
        {"config_profile_uuid": "p-1", "active_inbounds": []},
        {"port": 70000},
        {"node_consumption_multiplier": -1},
    ])
    async def test_bad_payload_is_rejected(self, payload, client):
        resp = await client.patch(f"/api/v2/nodes/{UUID}", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes.check_access", new_callable=AsyncMock, return_value=True)
    async def test_panel_message_reaches_the_admin(self, _acc, client):
        """Раньше любая ошибка панели превращалась в «Internal server error»."""
        from shared.api_client import api_client
        from shared.exceptions import ValidationError

        with patch.object(api_client, "update_node", new_callable=AsyncMock,
                          side_effect=ValidationError("Port is already in use")):
            resp = await client.patch(f"/api/v2/nodes/{UUID}", json={"port": 2222})
        assert resp.status_code == 400
        assert "Port is already in use" in resp.json()["detail"]


class TestReorder:
    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes.write_audit_log", new_callable=AsyncMock)
    @patch("web.backend.api.v2.nodes.get_scope", new_callable=AsyncMock, return_value=None)
    async def test_order_goes_to_panel(self, _scope, _audit, client):
        from shared.api_client import api_client

        with patch.object(api_client, "reorder_nodes", new_callable=AsyncMock,
                          return_value={"response": []}) as reorder:
            resp = await client.post("/api/v2/nodes/reorder", json={"uuids": ["b", "a", "c"]})
        assert resp.status_code == 200
        assert reorder.await_args.args[0] == [
            {"uuid": "b", "viewPosition": 0}, {"uuid": "a", "viewPosition": 1}, {"uuid": "c", "viewPosition": 2},
        ]

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes.get_scope", new_callable=AsyncMock, return_value={"a"})
    async def test_limited_admin_cannot_reorder_everyone(self, _scope, client):
        resp = await client.post("/api/v2/nodes/reorder", json={"uuids": ["a"]})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.nodes.get_scope", new_callable=AsyncMock, return_value=None)
    async def test_duplicates_rejected(self, _scope, client):
        resp = await client.post("/api/v2/nodes/reorder", json={"uuids": ["a", "a"]})
        assert resp.status_code == 422

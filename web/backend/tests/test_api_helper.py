"""Tests for web.backend.core.api_helper — API client and data normalization.

Covers: _normalize, _get_client, api_get, fetch_users_from_api,
fetch_nodes_from_api, fetch_hosts_from_api, fetch_bandwidth_stats,
fetch_nodes_usage_by_range, fetch_nodes_realtime_usage, close_client.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import web.backend.core.api_helper as mod
from web.backend.core.api_helper import (
    _normalize,
    _get_client,
    api_get,
    close_client,
    fetch_bandwidth_stats,
    fetch_hosts_from_api,
    fetch_nodes_from_api,
    fetch_nodes_realtime_usage,
    fetch_nodes_usage_by_range,
    fetch_users_from_api,
)


# ── _normalize tests ─────────────────────────────────────────


class TestNormalize:
    """Tests for _normalize() — camelCase→snake_case aliasing."""

    def test_adds_snake_case_aliases(self):
        data = {"shortUuid": "abc", "username": "alice"}
        result = _normalize(data)
        assert result["short_uuid"] == "abc"
        assert result["shortUuid"] == "abc"
        assert result["username"] == "alice"

    def test_does_not_overwrite_existing_snake_key(self):
        data = {"shortUuid": "camel", "short_uuid": "existing"}
        result = _normalize(data)
        assert result["short_uuid"] == "existing"

    def test_flattens_user_traffic(self):
        data = {
            "username": "alice",
            "userTraffic": {
                "usedTrafficBytes": 5000,
                "lifetimeUsedTrafficBytes": 50000,
                "onlineAt": "2025-06-01",
                "firstConnectedAt": "2025-01-15",
                "lastConnectedNodeUuid": "node-x",
            },
        }
        result = _normalize(data)
        assert result["usedTrafficBytes"] == 5000
        assert result["used_traffic_bytes"] == 5000
        assert result["lifetime_used_traffic_bytes"] == 50000
        assert result["first_connected_at"] == "2025-01-15"

    def test_traffic_total_fallback(self):
        data = {"trafficUsedBytes": 12345}
        result = _normalize(data)
        assert result["traffic_used_bytes"] == 12345
        assert result["traffic_total_bytes"] == 12345

    def test_preserves_original_keys(self):
        data = {"isConnected": True, "usersOnline": 5}
        result = _normalize(data)
        assert result["isConnected"] is True
        assert result["is_connected"] is True
        assert result["usersOnline"] == 5
        assert result["users_online"] == 5

    def test_empty_dict(self):
        assert _normalize({}) == {}

    def test_unknown_keys_unchanged(self):
        data = {"custom_field": "value"}
        result = _normalize(data)
        assert result["custom_field"] == "value"


# ── _get_client tests ────────────────────────────────────────


class TestGetClient:
    """Tests for _get_client() — singleton httpx client creation."""

    def setup_method(self):
        mod._client = None

    def teardown_method(self):
        mod._client = None

    @patch("web.backend.core.api_helper.get_web_settings")
    def test_creates_client_with_bearer_token(self, mock_settings):
        s = MagicMock()
        s.api_base_url = "https://panel.example.com"
        s.api_token = "my-token"
        mock_settings.return_value = s

        client = _get_client()
        assert client.headers["Authorization"] == "Bearer my-token"
        assert client.headers["Content-Type"] == "application/json"

    @patch("web.backend.core.api_helper.get_web_settings")
    def test_no_bearer_when_api_token_empty(self, mock_settings):
        s = MagicMock()
        s.api_base_url = "https://panel.example.com"
        s.api_token = ""
        mock_settings.return_value = s

        client = _get_client()
        assert "Authorization" not in client.headers

    @patch("web.backend.core.api_helper.get_web_settings")
    def test_adds_proxy_headers_for_http(self, mock_settings):
        s = MagicMock()
        s.api_base_url = "http://internal:3000"
        s.api_token = "tok"
        mock_settings.return_value = s

        client = _get_client()
        assert client.headers["X-Forwarded-Proto"] == "https"
        assert client.headers["X-Forwarded-For"] == "127.0.0.1"
        assert client.headers["X-Real-IP"] == "127.0.0.1"

    @patch("web.backend.core.api_helper.get_web_settings")
    def test_no_proxy_headers_for_https(self, mock_settings):
        s = MagicMock()
        s.api_base_url = "https://panel.example.com"
        s.api_token = "tok"
        mock_settings.return_value = s

        client = _get_client()
        assert "X-Forwarded-Proto" not in client.headers

    @patch("web.backend.core.api_helper.get_web_settings")
    def test_reuses_existing_client(self, mock_settings):
        s = MagicMock()
        s.api_base_url = "http://localhost:3000"
        s.api_token = ""
        mock_settings.return_value = s

        c1 = _get_client()
        c2 = _get_client()
        assert c1 is c2
        assert mock_settings.call_count == 1

    @patch("web.backend.core.api_helper.get_web_settings")
    def test_recreates_client_if_closed(self, mock_settings):
        s = MagicMock()
        s.api_base_url = "http://localhost:3000"
        s.api_token = ""
        mock_settings.return_value = s

        _get_client()
        closed = MagicMock()
        closed.is_closed = True
        mod._client = closed

        c2 = _get_client()
        assert c2 is not closed
        assert mock_settings.call_count == 2


# ── api_get tests ─────────────────────────────────────────────


class TestApiGet:
    """Tests for api_get() — async GET requests."""

    @patch("web.backend.core.api_helper._get_client")
    async def test_successful_get(self, mock_gc):
        expected = {"response": {"users": []}}
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = expected
        resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_gc.return_value = mock_client

        result = await api_get("/api/users")
        assert result == expected

    @patch("web.backend.core.api_helper._get_client")
    async def test_get_with_params(self, mock_gc):
        resp = MagicMock()
        resp.json.return_value = {"data": "ok"}
        resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_gc.return_value = mock_client

        await api_get("/api/users", params={"start": 0, "size": 10})
        mock_client.get.assert_awaited_once_with("/api/users", params={"start": 0, "size": 10})

    @patch("web.backend.core.api_helper._get_client")
    async def test_http_error_returns_none(self, mock_gc):
        resp = MagicMock()
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock()
        )

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_gc.return_value = mock_client

        assert await api_get("/api/nonexistent") is None

    @patch("web.backend.core.api_helper._get_client")
    async def test_network_error_returns_none(self, mock_gc):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_gc.return_value = mock_client

        assert await api_get("/api/users") is None

    @patch("web.backend.core.api_helper._get_client")
    async def test_timeout_returns_none(self, mock_gc):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ReadTimeout("timeout"))
        mock_gc.return_value = mock_client

        assert await api_get("/api/users") is None


# ── fetch_users_from_api tests ────────────────────────────────


class TestFetchUsersFromApi:
    """Tests for fetch_users_from_api() — paginated user fetching."""

    @patch("web.backend.core.api_helper.api_get")
    async def test_single_page(self, mock_api_get):
        mock_api_get.return_value = {
            "response": {
                "users": [
                    {"username": "alice", "shortUuid": "a1"},
                    {"username": "bob", "shortUuid": "b2"},
                ],
                "total": 2,
            }
        }

        result = await fetch_users_from_api(size=500)
        assert len(result) == 2
        assert result[0]["username"] == "alice"
        assert result[0]["short_uuid"] == "a1"

    @patch("web.backend.core.api_helper.api_get")
    async def test_multi_page_pagination(self, mock_api_get):
        page1 = {"response": {"users": [{"username": "a"}], "total": 3}}
        page2 = {"response": {"users": [{"username": "b"}], "total": 3}}
        page3 = {"response": {"users": [{"username": "c"}], "total": 3}}
        mock_api_get.side_effect = [page1, page2, page3]

        result = await fetch_users_from_api(size=1)
        assert len(result) == 3

    @patch("web.backend.core.api_helper.api_get")
    async def test_empty_response(self, mock_api_get):
        mock_api_get.return_value = {"response": {"users": [], "total": 0}}
        assert await fetch_users_from_api() == []

    @patch("web.backend.core.api_helper.api_get")
    async def test_api_error_returns_empty(self, mock_api_get):
        mock_api_get.return_value = None
        assert await fetch_users_from_api() == []

    @patch("web.backend.core.api_helper.api_get")
    async def test_no_response_wrapper(self, mock_api_get):
        mock_api_get.return_value = {"users": [{"username": "alice"}], "total": 1}
        result = await fetch_users_from_api()
        assert len(result) == 1

    @patch("web.backend.core.api_helper.api_get")
    async def test_second_page_failure(self, mock_api_get):
        page1 = {"response": {"users": [{"username": "a"}], "total": 5}}
        mock_api_get.side_effect = [page1, None]
        result = await fetch_users_from_api(size=1)
        assert len(result) == 1


# ── fetch_nodes_from_api tests ────────────────────────────────


class TestFetchNodesFromApi:
    """Tests for fetch_nodes_from_api() — various response shapes."""

    @patch("web.backend.core.api_helper.api_get")
    async def test_list_response(self, mock_api_get):
        mock_api_get.return_value = {
            "response": [
                {"uuid": "n1", "name": "Node1", "isConnected": True},
                {"uuid": "n2", "name": "Node2", "isConnected": False},
            ]
        }
        result = await fetch_nodes_from_api()
        assert len(result) == 2
        assert result[0]["is_connected"] is True

    @patch("web.backend.core.api_helper.api_get")
    async def test_dict_with_nodes_key(self, mock_api_get):
        mock_api_get.return_value = {
            "response": {"nodes": [{"uuid": "n1", "usersOnline": 5}]}
        }
        result = await fetch_nodes_from_api()
        assert len(result) == 1
        assert result[0]["users_online"] == 5

    @patch("web.backend.core.api_helper.api_get")
    async def test_single_node_dict(self, mock_api_get):
        mock_api_get.return_value = {"response": {"uuid": "n1", "xrayVersion": "1.8"}}
        result = await fetch_nodes_from_api()
        assert len(result) == 1
        assert result[0]["xray_version"] == "1.8"

    @patch("web.backend.core.api_helper.api_get")
    async def test_api_error(self, mock_api_get):
        mock_api_get.return_value = None
        assert await fetch_nodes_from_api() == []

    @patch("web.backend.core.api_helper.api_get")
    async def test_non_dict_items_filtered(self, mock_api_get):
        mock_api_get.return_value = {
            "response": [{"uuid": "n1"}, "bad", None, {"uuid": "n2"}]
        }
        result = await fetch_nodes_from_api()
        assert len(result) == 2

    @patch("web.backend.core.api_helper.api_get")
    async def test_non_list_non_dict_response(self, mock_api_get):
        mock_api_get.return_value = {"response": "unexpected"}
        assert await fetch_nodes_from_api() == []


# ── fetch_hosts_from_api tests ────────────────────────────────


class TestFetchHostsFromApi:

    @patch("web.backend.core.api_helper.api_get")
    async def test_list_response(self, mock_api_get):
        mock_api_get.return_value = {
            "response": [{"uuid": "h1", "viewPosition": 1, "securityLayer": "tls"}]
        }
        result = await fetch_hosts_from_api()
        assert len(result) == 1
        assert result[0]["view_position"] == 1

    @patch("web.backend.core.api_helper.api_get")
    async def test_dict_with_hosts_key(self, mock_api_get):
        mock_api_get.return_value = {
            "response": {"hosts": [{"uuid": "h1", "allowInsecure": True}]}
        }
        result = await fetch_hosts_from_api()
        assert result[0]["allow_insecure"] is True

    @patch("web.backend.core.api_helper.api_get")
    async def test_single_host_dict(self, mock_api_get):
        mock_api_get.return_value = {"response": {"uuid": "h1", "shuffleHost": True}}
        result = await fetch_hosts_from_api()
        assert len(result) == 1

    @patch("web.backend.core.api_helper.api_get")
    async def test_api_error(self, mock_api_get):
        mock_api_get.return_value = None
        assert await fetch_hosts_from_api() == []


# ── fetch_bandwidth_stats tests ───────────────────────────────


class TestFetchBandwidthStats:

    @patch("web.backend.core.api_helper.api_get")
    async def test_returns_response(self, mock_api_get):
        stats = {"bandwidthLastTwoDays": {"current": "1000"}}
        mock_api_get.return_value = {"response": stats}
        assert await fetch_bandwidth_stats() == stats

    @patch("web.backend.core.api_helper.api_get")
    async def test_api_error(self, mock_api_get):
        mock_api_get.return_value = None
        assert await fetch_bandwidth_stats() is None


# ── fetch_nodes_usage_by_range tests ──────────────────────────


class TestFetchNodesUsageByRange:

    @patch("web.backend.core.api_helper.api_get")
    async def test_returns_response(self, mock_api_get):
        usage = {"topNodes": [{"nodeUuid": "n1", "total": 5000}]}
        mock_api_get.return_value = {"response": usage}
        result = await fetch_nodes_usage_by_range("2025-01-01", "2025-01-31")
        assert result == usage

    @patch("web.backend.core.api_helper.api_get")
    async def test_passes_params(self, mock_api_get):
        mock_api_get.return_value = {"response": {}}
        await fetch_nodes_usage_by_range("2025-01-01", "2025-01-31", top_nodes_limit=50)
        mock_api_get.assert_awaited_once_with(
            "/api/bandwidth-stats/nodes",
            params={"start": "2025-01-01", "end": "2025-01-31", "topNodesLimit": 50},
        )

    @patch("web.backend.core.api_helper.api_get")
    async def test_api_error(self, mock_api_get):
        mock_api_get.return_value = None
        assert await fetch_nodes_usage_by_range("a", "b") is None


# ── fetch_nodes_realtime_usage tests ──────────────────────────


class TestFetchNodesRealtimeUsage:

    @patch("web.backend.core.api_helper.api_get")
    async def test_returns_list(self, mock_api_get):
        nodes = [{"nodeUuid": "n1", "totalBytes": 1000}]
        mock_api_get.return_value = {"response": nodes}
        assert await fetch_nodes_realtime_usage() == nodes

    @patch("web.backend.core.api_helper.api_get")
    async def test_api_error(self, mock_api_get):
        mock_api_get.return_value = None
        assert await fetch_nodes_realtime_usage() == []

    @patch("web.backend.core.api_helper.api_get")
    async def test_non_list_response(self, mock_api_get):
        mock_api_get.return_value = {"response": {"unexpected": "dict"}}
        assert await fetch_nodes_realtime_usage() == []


# ── close_client tests ────────────────────────────────────────


class TestCloseClient:

    def teardown_method(self):
        mod._client = None

    async def test_closes_open_client(self):
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        mod._client = mock_client

        await close_client()
        mock_client.aclose.assert_awaited_once()
        assert mod._client is None

    async def test_no_op_when_none(self):
        mod._client = None
        await close_client()
        assert mod._client is None

    async def test_no_op_when_already_closed(self):
        mock_client = AsyncMock()
        mock_client.is_closed = True
        mod._client = mock_client

        await close_client()
        mock_client.aclose.assert_not_awaited()

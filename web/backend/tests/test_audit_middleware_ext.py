"""Tests for web.backend.core.audit_middleware — route matching, field extraction,
token parsing, and middleware dispatch logic.

Covers: _match_route, _extract_token, _build_details, AuditMiddleware.dispatch.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core.audit_middleware import (
    _match_route,
    _extract_token,
    _build_details,
    AuditMiddleware,
    _SKIP_DUPLICATES,
)


# ── _match_route tests ────────────────────────────────────────


class TestMatchRoute:
    """Tests for URL to (resource, action, resource_id) matching."""

    # Users
    def test_create_user(self):
        assert _match_route("POST", "/api/v2/users") == ("users", "create", None)

    def test_update_user(self):
        result = _match_route("PATCH", "/api/v2/users/abc-123")
        assert result == ("users", "update", "abc-123")

    def test_delete_user(self):
        result = _match_route("DELETE", "/api/v2/users/abc-123")
        assert result == ("users", "delete", "abc-123")

    def test_enable_user(self):
        result = _match_route("POST", "/api/v2/users/abc-123/enable")
        assert result == ("users", "enable", "abc-123")

    def test_disable_user(self):
        result = _match_route("POST", "/api/v2/users/abc-123/disable")
        assert result == ("users", "disable", "abc-123")

    def test_reset_traffic(self):
        result = _match_route("POST", "/api/v2/users/abc-123/reset-traffic")
        assert result == ("users", "reset_traffic", "abc-123")

    def test_bulk_enable(self):
        result = _match_route("POST", "/api/v2/users/bulk/enable")
        assert result == ("users", "bulk_enable", "enable")

    def test_bulk_delete(self):
        result = _match_route("POST", "/api/v2/users/bulk/delete")
        assert result == ("users", "bulk_delete", "delete")

    # Nodes
    def test_create_node(self):
        assert _match_route("POST", "/api/v2/nodes") == ("nodes", "create", None)

    def test_restart_node(self):
        result = _match_route("POST", "/api/v2/nodes/n1/restart")
        assert result == ("nodes", "restart", "n1")

    def test_generate_agent_token(self):
        result = _match_route("POST", "/api/v2/nodes/n1/agent-token")
        assert result == ("nodes", "generate_token", "n1")

    def test_revoke_agent_token(self):
        result = _match_route("DELETE", "/api/v2/nodes/n1/agent-token")
        assert result == ("nodes", "revoke_token", "n1")

    # Hosts
    def test_create_host(self):
        assert _match_route("POST", "/api/v2/hosts") == ("hosts", "create", None)

    def test_update_host(self):
        result = _match_route("PATCH", "/api/v2/hosts/h1")
        assert result == ("hosts", "update", "h1")

    # Violations
    def test_resolve_violation(self):
        result = _match_route("POST", "/api/v2/violations/v1/resolve")
        assert result == ("violations", "resolve", "v1")

    # Settings
    def test_update_setting(self):
        result = _match_route("PUT", "/api/v2/settings/some-key")
        assert result == ("settings", "update", "some-key")

    def test_update_ip_whitelist(self):
        result = _match_route("PUT", "/api/v2/settings/ip-whitelist")
        assert result == ("settings", "update_ip_whitelist", None)

    def test_trigger_sync(self):
        result = _match_route("POST", "/api/v2/settings/sync")
        assert result == ("settings", "trigger_sync", None)

    # No match
    def test_no_match_get(self):
        assert _match_route("GET", "/api/v2/users") is None

    def test_no_match_unknown_path(self):
        assert _match_route("POST", "/api/v2/unknown") is None

    # Admin/auth routes (skipped by middleware)
    def test_admin_create_in_skip_list(self):
        result = _match_route("POST", "/api/v2/admins")
        assert result is not None
        assert (result[0], result[1]) in _SKIP_DUPLICATES

    def test_auth_login_in_skip_list(self):
        result = _match_route("POST", "/api/v2/auth/password")
        assert result is not None
        assert (result[0], result[1]) in _SKIP_DUPLICATES


# ── _extract_token tests ─────────────────────────────────────


class TestExtractToken:

    def test_extracts_bearer_token(self):
        request = MagicMock()
        request.headers = {"authorization": "Bearer my-jwt-token"}
        assert _extract_token(request) == "my-jwt-token"

    def test_case_insensitive_bearer(self):
        request = MagicMock()
        request.headers = {"authorization": "bearer lower-case-token"}
        assert _extract_token(request) == "lower-case-token"

    def test_no_auth_header(self):
        request = MagicMock()
        request.headers = {"other": "value"}
        assert _extract_token(request) is None

    def test_non_bearer_scheme(self):
        request = MagicMock()
        request.headers = {"authorization": "Basic abc123"}
        assert _extract_token(request) is None


# ── _build_details tests ─────────────────────────────────────


class TestBuildDetails:
    """Tests for extracting audit details from request bodies."""

    def test_extracts_user_fields(self):
        body = {"username": "alice", "data_limit": 1000, "extra_ignored": True}
        result = _build_details("users", "create", None, body)
        import json
        parsed = json.loads(result)
        assert parsed["username"] == "alice"
        assert parsed["data_limit"] == 1000
        assert "extra_ignored" not in parsed

    def test_settings_includes_key(self):
        body = {"value": "new-value"}
        result = _build_details("settings", "update", "my-setting", body)
        import json
        parsed = json.loads(result)
        assert parsed["setting"] == "my-setting"
        assert parsed["value"] == "new-value"

    def test_filters_sensitive_fields(self):
        body = {"name": "test", "password": "secret123", "token": "abc"}
        result = _build_details("unknown_resource", "action", None, body)
        import json
        parsed = json.loads(result)
        assert "password" not in parsed
        assert "token" not in parsed
        assert parsed["name"] == "test"

    def test_empty_body(self):
        assert _build_details("users", "create", None, None) is None
        assert _build_details("users", "create", None, {}) is None

    def test_name_like_identifier_captured(self):
        body = {"title": "My Rule", "some_other_field": True}
        result = _build_details("unknown_resource", "create", None, body)
        import json
        parsed = json.loads(result)
        assert parsed["title"] == "My Rule"

    def test_nodes_extracts_correct_fields(self):
        body = {"name": "Node-EU", "address": "1.2.3.4", "port": 443, "secret_config": "x"}
        result = _build_details("nodes", "create", None, body)
        import json
        parsed = json.loads(result)
        assert parsed["name"] == "Node-EU"
        assert parsed["address"] == "1.2.3.4"
        assert parsed["port"] == 443


# ── AuditMiddleware.dispatch tests ────────────────────────────


class TestAuditMiddleware:

    async def test_passes_through_get_requests(self):
        middleware = AuditMiddleware(app=MagicMock())
        request = MagicMock()
        request.method = "GET"

        expected = MagicMock()
        call_next = AsyncMock(return_value=expected)

        response = await middleware.dispatch(request, call_next)
        assert response is expected
        call_next.assert_awaited_once_with(request)

    async def test_passes_through_non_api_paths(self):
        middleware = AuditMiddleware(app=MagicMock())
        request = MagicMock()
        request.method = "POST"
        request.url = MagicMock()
        request.url.path = "/some/other/path"

        expected = MagicMock()
        call_next = AsyncMock(return_value=expected)

        response = await middleware.dispatch(request, call_next)
        assert response is expected

    async def test_passes_through_health_check(self):
        middleware = AuditMiddleware(app=MagicMock())
        request = MagicMock()
        request.method = "POST"
        request.url = MagicMock()
        request.url.path = "/api/v2/health"

        expected = MagicMock()
        call_next = AsyncMock(return_value=expected)

        response = await middleware.dispatch(request, call_next)
        assert response is expected

    async def test_skips_read_only_post_endpoints(self):
        middleware = AuditMiddleware(app=MagicMock())
        request = MagicMock()
        request.method = "POST"
        request.url = MagicMock()
        request.url.path = "/api/v2/users/lookup-ips"

        expected = MagicMock()
        call_next = AsyncMock(return_value=expected)

        response = await middleware.dispatch(request, call_next)
        assert response is expected

    @patch("web.backend.core.audit_middleware._write_audit_entry", new_callable=AsyncMock)
    async def test_logs_successful_mutation(self, mock_write):
        middleware = AuditMiddleware(app=MagicMock())
        request = MagicMock()
        request.method = "POST"
        request.url = MagicMock()
        request.url.path = "/api/v2/users"
        request.headers = {}
        request.body = AsyncMock(return_value=b'{"username": "alice"}')

        response = MagicMock()
        response.status_code = 201
        call_next = AsyncMock(return_value=response)

        result = await middleware.dispatch(request, call_next)
        assert result is response

    async def test_skips_already_logged_actions(self):
        middleware = AuditMiddleware(app=MagicMock())
        request = MagicMock()
        request.method = "POST"
        request.url = MagicMock()
        request.url.path = "/api/v2/admins"

        expected = MagicMock()
        expected.status_code = 200
        call_next = AsyncMock(return_value=expected)

        with patch("web.backend.core.audit_middleware._write_audit_entry") as mock_write:
            response = await middleware.dispatch(request, call_next)
            assert response is expected

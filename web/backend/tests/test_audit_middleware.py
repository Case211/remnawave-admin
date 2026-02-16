"""Tests for audit middleware — URL matching, detail extraction, and middleware dispatch."""
import json

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from web.backend.core.audit_middleware import (
    _match_route,
    _build_details,
    _extract_token,
    AuditMiddleware,
)


# ── _match_route tests ────────────────────────────────────────


class TestMatchRoute:
    """Tests for URL→resource/action mapping."""

    def test_post_users_create(self):
        result = _match_route("POST", "/api/v2/users")
        assert result == ("users", "create", None)

    def test_delete_user_by_uuid(self):
        result = _match_route("DELETE", "/api/v2/users/abc-123")
        assert result == ("users", "delete", "abc-123")

    def test_patch_user_update(self):
        result = _match_route("PATCH", "/api/v2/users/abc-123")
        assert result == ("users", "update", "abc-123")

    def test_bulk_enable(self):
        result = _match_route("POST", "/api/v2/users/bulk/enable")
        assert result == ("users", "bulk_enable", "enable")

    def test_bulk_disable(self):
        result = _match_route("POST", "/api/v2/users/bulk/disable")
        assert result == ("users", "bulk_disable", "disable")

    def test_bulk_delete(self):
        result = _match_route("POST", "/api/v2/users/bulk/delete")
        assert result == ("users", "bulk_delete", "delete")

    def test_node_restart(self):
        result = _match_route("POST", "/api/v2/nodes/uuid-1/restart")
        assert result == ("nodes", "restart", "uuid-1")

    def test_node_create(self):
        result = _match_route("POST", "/api/v2/nodes")
        assert result == ("nodes", "create", None)

    def test_host_enable(self):
        result = _match_route("POST", "/api/v2/hosts/uuid-1/enable")
        assert result == ("hosts", "enable", "uuid-1")

    def test_settings_update(self):
        result = _match_route("PUT", "/api/v2/settings/some-key")
        assert result == ("settings", "update", "some-key")

    def test_settings_ip_whitelist(self):
        result = _match_route("PUT", "/api/v2/settings/ip-whitelist")
        assert result == ("settings", "update_ip_whitelist", None)

    def test_violations_resolve(self):
        result = _match_route("POST", "/api/v2/violations/uuid-1/resolve")
        assert result == ("violations", "resolve", "uuid-1")

    def test_get_request_returns_none(self):
        assert _match_route("GET", "/api/v2/users") is None

    def test_unknown_path_returns_none(self):
        assert _match_route("POST", "/api/v2/unknown-endpoint") is None

    def test_non_api_path_returns_none(self):
        assert _match_route("POST", "/some/other/path") is None


# ── _build_details tests ──────────────────────────────────────


class TestBuildDetails:
    """Tests for audit detail extraction from request bodies."""

    def test_extracts_allowed_user_fields(self):
        body = {"username": "alice", "password": "secret", "status": "active", "note": "test"}
        result = json.loads(_build_details("users", "create", None, body))
        assert "username" in result
        assert "status" in result
        assert "note" in result
        assert "password" not in result

    def test_filters_sensitive_fields(self):
        body = {"name": "node1", "token": "abc", "secret": "xyz", "api_key": "key"}
        result = json.loads(_build_details("nodes", "create", None, body))
        assert "name" in result
        assert "token" not in result
        assert "secret" not in result
        assert "api_key" not in result

    def test_settings_includes_resource_id(self):
        body = {"value": "new-val"}
        result = json.loads(_build_details("settings", "update", "log_level", body))
        assert result["setting"] == "log_level"
        assert result["value"] == "new-val"

    def test_empty_body_returns_none(self):
        assert _build_details("users", "create", None, None) is None

    def test_empty_dict_returns_none(self):
        assert _build_details("users", "create", None, {}) is None

    def test_unknown_resource_captures_non_sensitive(self):
        body = {"foo": "bar", "password": "secret"}
        result = json.loads(_build_details("unknown_resource", "action", None, body))
        assert "foo" in result
        assert "password" not in result

    def test_name_like_fields_always_captured(self):
        """Fields like username, name, remark, title are always captured."""
        body = {"remark": "my-host"}
        result = json.loads(_build_details("hosts", "create", None, body))
        assert result["remark"] == "my-host"


# ── _extract_token tests ──────────────────────────────────────


class TestExtractToken:
    """Tests for JWT extraction from Authorization header."""

    def test_bearer_token(self):
        req = MagicMock()
        req.headers = {"authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.test"}
        assert _extract_token(req) == "eyJhbGciOiJIUzI1NiJ9.test"

    def test_bearer_case_insensitive(self):
        req = MagicMock()
        req.headers = {"authorization": "bearer my-token"}
        assert _extract_token(req) == "my-token"

    def test_no_authorization_header(self):
        req = MagicMock()
        req.headers = {}
        assert _extract_token(req) is None

    def test_wrong_scheme(self):
        req = MagicMock()
        req.headers = {"authorization": "Basic dXNlcjpwYXNz"}
        assert _extract_token(req) is None


# ── Middleware dispatch tests ─────────────────────────────────


class TestAuditMiddlewareDispatch:
    """Integration tests for the AuditMiddleware using FastAPI test client."""

    @pytest.mark.asyncio
    @patch("web.backend.core.audit_middleware._write_audit_entry", new_callable=AsyncMock)
    async def test_get_request_not_audited(self, mock_write, app, client):
        resp = await client.get("/api/v2/health")
        assert resp.status_code == 200
        mock_write.assert_not_called()

    @pytest.mark.asyncio
    @patch("web.backend.core.audit_middleware._write_audit_entry", new_callable=AsyncMock)
    async def test_skip_list_not_audited(self, mock_write, app, client):
        """Endpoints in the skip list should not be audited."""
        resp = await client.post("/api/v2/auth/refresh", json={"refresh_token": "tok"})
        # May return 4xx due to invalid token, but audit should still be skipped
        mock_write.assert_not_called()

    @pytest.mark.asyncio
    @patch("web.backend.core.audit_middleware._write_audit_entry", new_callable=AsyncMock)
    async def test_duplicate_action_skipped(self, mock_write, app, client):
        """Actions in _SKIP_DUPLICATES (admins.create, auth.login, etc.) should be skipped."""
        # POST /api/v2/auth/password is in _SKIP_DUPLICATES as (auth, login)
        resp = await client.post("/api/v2/auth/password", json={"username": "a", "password": "b"})
        mock_write.assert_not_called()

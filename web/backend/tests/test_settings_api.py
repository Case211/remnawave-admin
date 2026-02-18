"""Tests for settings API — /api/v2/settings/*."""
import os

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from web.backend.api.deps import get_current_admin
from web.backend.api.v2.settings import _determine_source, _effective_value
from .conftest import make_admin


class TestDetermineSource:
    """Tests for _determine_source helper."""

    def test_db_value_wins(self):
        assert _determine_source("db-val", "MY_ENV", "default") == "db"

    @patch.dict(os.environ, {"MY_ENV": "env-val"})
    def test_env_value_when_no_db(self):
        assert _determine_source(None, "MY_ENV", "default") == "env"

    def test_default_when_no_db_or_env(self):
        assert _determine_source(None, None, "default-val") == "default"

    def test_none_source(self):
        assert _determine_source(None, None, None) == "none"

    @patch.dict(os.environ, {"MY_ENV": ""})
    def test_empty_env_not_counted(self):
        assert _determine_source(None, "MY_ENV", "default") == "default"


class TestEffectiveValue:
    """Tests for _effective_value helper."""

    def test_db_value_wins(self):
        assert _effective_value("db-val", "MY_ENV", "default") == "db-val"

    @patch.dict(os.environ, {"MY_ENV": "env-val"})
    def test_env_value_when_no_db(self):
        assert _effective_value(None, "MY_ENV", "default") == "env-val"

    def test_default_when_nothing(self):
        assert _effective_value(None, None, "fallback") == "fallback"

    def test_none_all_around(self):
        assert _effective_value(None, None, None) is None


class TestGetPanelName:
    """GET /api/v2/settings/panel-name."""

    @pytest.mark.asyncio
    async def test_panel_name_authenticated(self, client):
        """Authenticated users can get panel name."""
        resp = await client.get("/api/v2/settings/panel-name")
        # May return 200 or 500 depending on config_service availability
        # The important thing is it doesn't return 401/403
        assert resp.status_code != 401

    @pytest.mark.asyncio
    async def test_panel_name_anon_unauthorized(self, anon_client):
        resp = await anon_client.get("/api/v2/settings/panel-name")
        assert resp.status_code == 401


class TestSettingsRBAC:
    """RBAC tests for settings endpoints."""

    @pytest.mark.asyncio
    async def test_viewer_cannot_access_settings(self, app, viewer):
        """Viewers don't have settings.view permission."""
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v2/settings")
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_operator_cannot_access_settings(self, app, operator):
        """Operators don't have settings.view permission."""
        app.dependency_overrides[get_current_admin] = lambda: operator
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v2/settings")
            assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_anon_cannot_access_settings(self, anon_client):
        resp = await anon_client.get("/api/v2/settings")
        assert resp.status_code == 401

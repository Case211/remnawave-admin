"""Tests for health check and root endpoints."""
import pytest
from unittest.mock import patch, AsyncMock


class TestHealthEndpoint:
    """GET /api/v2/health."""

    @pytest.mark.asyncio
    @patch(
        "web.backend.main.get_latest_version",
        new_callable=AsyncMock,
        return_value="2.6.0",
    )
    async def test_health_check(self, mock_version, anon_client):
        resp = await anon_client.get("/api/v2/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "remnawave-admin-web"
        assert "version" in data


class TestRootEndpoint:
    """GET /."""

    @pytest.mark.asyncio
    @patch(
        "web.backend.main.get_latest_version",
        new_callable=AsyncMock,
        return_value="2.6.0",
    )
    async def test_root(self, mock_version, anon_client):
        resp = await anon_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "remnawave-admin-web"

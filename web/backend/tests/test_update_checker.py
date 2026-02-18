"""Tests for GitHub update checker — version fetching and caching."""
import time

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

import web.backend.core.update_checker as uc


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset module-level cache between tests."""
    uc._cache = {}
    uc._cache_ts = 0
    yield
    uc._cache = {}
    uc._cache_ts = 0


class TestFetchLatestRelease:
    """Tests for _fetch_latest_release."""

    @pytest.mark.asyncio
    @patch("web.backend.core.update_checker.httpx.AsyncClient")
    async def test_success(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v1.2.3",
            "html_url": "https://github.com/Case211/remnawave-admin/releases/tag/v1.2.3",
            "body": "Changelog text",
            "published_at": "2026-02-15T10:00:00Z",
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await uc._fetch_latest_release()
        assert result["tag_name"] == "v1.2.3"

    @pytest.mark.asyncio
    @patch("web.backend.core.update_checker.httpx.AsyncClient")
    async def test_404_returns_none(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await uc._fetch_latest_release()
        assert result is None

    @pytest.mark.asyncio
    @patch("web.backend.core.update_checker.httpx.AsyncClient")
    async def test_network_error_returns_none(self, mock_client_cls):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await uc._fetch_latest_release()
        assert result is None


class TestCheckForUpdates:
    """Tests for check_for_updates."""

    @pytest.mark.asyncio
    @patch("web.backend.core.update_checker._fetch_latest_release", new_callable=AsyncMock)
    async def test_parses_version(self, mock_fetch):
        mock_fetch.return_value = {
            "tag_name": "v2.0.0",
            "html_url": "https://github.com/example/releases/tag/v2.0.0",
            "body": "New release",
            "published_at": "2026-02-15T10:00:00Z",
        }

        result = await uc.check_for_updates()
        assert result["current_version"] == "2.0.0"
        assert result["release_url"] == "https://github.com/example/releases/tag/v2.0.0"
        assert result["changelog"] == "New release"

    @pytest.mark.asyncio
    @patch("web.backend.core.update_checker._fetch_latest_release", new_callable=AsyncMock)
    async def test_fetch_failure_returns_fallback(self, mock_fetch):
        mock_fetch.return_value = None
        result = await uc.check_for_updates()
        assert result["current_version"] == "unknown"
        assert result["update_available"] is False

    @pytest.mark.asyncio
    @patch("web.backend.core.update_checker._fetch_latest_release", new_callable=AsyncMock)
    async def test_cache_within_ttl(self, mock_fetch):
        mock_fetch.return_value = {"tag_name": "v1.0.0", "html_url": "", "body": "", "published_at": None}

        await uc.check_for_updates()
        await uc.check_for_updates()
        # Only called once due to caching
        assert mock_fetch.call_count == 1

    @pytest.mark.asyncio
    @patch("web.backend.core.update_checker._fetch_latest_release", new_callable=AsyncMock)
    async def test_cache_expired(self, mock_fetch):
        mock_fetch.return_value = {"tag_name": "v1.0.0", "html_url": "", "body": "", "published_at": None}

        await uc.check_for_updates()

        # Expire cache
        uc._cache_ts = time.time() - 2000

        await uc.check_for_updates()
        assert mock_fetch.call_count == 2


class TestGetLatestVersion:
    """Tests for get_latest_version."""

    @pytest.mark.asyncio
    @patch("web.backend.core.update_checker.check_for_updates", new_callable=AsyncMock)
    async def test_returns_version_string(self, mock_check):
        mock_check.return_value = {"current_version": "3.1.0"}
        version = await uc.get_latest_version()
        assert version == "3.1.0"

    @pytest.mark.asyncio
    async def test_returns_cached_version(self):
        uc._cache = {"current_version": "2.5.0"}
        version = await uc.get_latest_version()
        assert version == "2.5.0"

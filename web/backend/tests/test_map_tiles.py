"""Тайлы карты в аналитике: с ключом CARTO — чистые, без ключа — старый адрес и флаг для подсказки."""
from unittest.mock import MagicMock, patch

import pytest

from web.backend.api.v2.advanced_analytics import _map_tile_urls


def test_without_key_keeps_legacy_urls():
    tiles = _map_tile_urls("")
    assert tiles["has_key"] is False
    assert tiles["dark"] == "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    assert tiles["light"] == "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"


def test_with_key_uses_rastertiles_endpoint_and_encodes_key():
    tiles = _map_tile_urls(" ab c/d ")
    assert tiles["has_key"] is True
    assert tiles["dark"] == "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png?key=ab%20c%2Fd"
    assert tiles["light"].startswith("https://basemaps.cartocdn.com/rastertiles/light_all/")


@pytest.mark.asyncio
async def test_endpoint_reads_key_from_settings(client):
    cfg = MagicMock()
    cfg.get.return_value = "secret-key"
    with patch("shared.config_service.config_service", cfg):
        resp = await client.get("/api/v2/analytics/advanced/map-tiles")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_key"] is True
    assert body["dark"].endswith("?key=secret-key")
    cfg.get.assert_called_with("map_tiles_api_key")

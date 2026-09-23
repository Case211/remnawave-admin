"""Раздел и подпись настройки подтягиваются из кода и у уже созданных строк."""
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared import config_service as cs


def _item(**overrides):
    fields = dict(key="panel_name", value="STi", value_type=cs.ConfigValueType.STRING,
                  category=cs.ConfigCategory.GENERAL, subcategory=None,
                  display_name="Название панели", description="старое", default_value="",
                  sort_order=6)
    fields.update(overrides)
    return cs.ConfigItem(**fields)


DEF = {"key": "panel_name", "category": "general", "subcategory": "panel",
       "display_name": "Название панели", "description": "новое", "default_value": "x", "sort_order": 6}


@pytest.fixture()
def conn():
    c = MagicMock(execute=AsyncMock())

    @asynccontextmanager
    async def acquire():
        yield c

    with patch.object(cs.db_service, "acquire", acquire):
        yield c


@pytest.mark.asyncio
async def test_old_row_gets_its_section(conn):
    """На проде 44 настройки жили без раздела и сваливались в «Основные»."""
    item = _item()
    await cs.DynamicConfigService()._sync_config_metadata(item, DEF)

    sql, key, category, subcategory, *_ = conn.execute.await_args.args
    assert "UPDATE bot_config" in sql and key == "panel_name"
    assert (category, subcategory) == ("general", "panel")
    assert item.subcategory == "panel" and item.description == "новое"
    # значение и значение по умолчанию — поведение, их синк не трогает
    assert item.value == "STi" and item.default_value == ""


@pytest.mark.asyncio
async def test_row_in_sync_is_not_touched(conn):
    item = _item(subcategory="panel", description="новое")
    await cs.DynamicConfigService()._sync_config_metadata(item, DEF)
    conn.execute.assert_not_awaited()


def test_every_setting_has_a_translated_section():
    """Без раздела настройка оседает в «Основных» и выпадает из оглавления
    категории; одиночной настройке в категории раздел не нужен."""
    import collections
    import json
    from pathlib import Path

    per_category = collections.Counter(d["category"] for d in cs.DEFAULT_CONFIG_DEFINITIONS)
    orphans = [d["key"] for d in cs.DEFAULT_CONFIG_DEFINITIONS
               if not d.get("subcategory") and per_category[d["category"]] > 1]
    assert orphans == []

    locales = Path(__file__).resolve().parents[2] / "frontend" / "src" / "locales"
    sections = {d["subcategory"] for d in cs.DEFAULT_CONFIG_DEFINITIONS if d.get("subcategory")}
    for lang in ("ru", "en"):
        names = json.loads((locales / lang / "translation.json").read_text(encoding="utf-8"))
        missing = sections - set(names["settings"]["subcategories"])
        assert not missing, (lang, missing)

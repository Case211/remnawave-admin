"""Отчёты: выдача подстраивается под область видимости, ASN-синхронизация
пишет статус. Планировщик — в src/tests/test_report_scheduler.py."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from web.backend.api.v2 import reports


def test_serialize_parses_json_and_scopes_top():
    row = {
        "id": 1,
        "top_violators": '[{"user_uuid": "AAA", "violations_count": 2, "max_score": 90},'
                         ' {"user_uuid": "bbb", "violations_count": 1, "max_score": 40}]',
        "by_country": '{"RU": 3}',
        "by_action": "not json",
        "by_asn_type": None,
        "period_start": datetime(2026, 9, 14, tzinfo=timezone.utc),
    }
    full = reports._serialize(row, None)
    assert [v["user_uuid"] for v in full["top_violators"]] == ["AAA", "bbb"]
    assert full["by_country"] == {"RU": 3} and full["by_action"] is None
    assert full["period_start"] == "2026-09-14T00:00:00+00:00"
    assert "scoped" not in full

    scoped = reports._serialize(row, {"aaa"})
    assert [v["user_uuid"] for v in scoped["top_violators"]] == ["AAA"]
    assert scoped["scoped"] is True


@pytest.mark.asyncio
async def test_asn_sync_records_status_for_any_caller():
    from shared.asn_parser import ASNParser

    db = MagicMock()
    db.update_sync_metadata = AsyncMock()
    parser = ASNParser.__new__(ASNParser)
    parser.db = db
    parser._sync_russian_asn_database = AsyncMock(
        return_value={"total": 5, "success": 2, "failed": 1, "skipped": 2})
    await parser.sync_russian_asn_database(limit=None)
    db.update_sync_metadata.assert_awaited_with(key="asn", status="success", records_synced=4)

    parser._sync_russian_asn_database = AsyncMock(side_effect=RuntimeError("RIPE down"))
    with pytest.raises(RuntimeError):
        await parser.sync_russian_asn_database(limit=None)
    db.update_sync_metadata.assert_awaited_with(key="asn", status="error", error_message="RIPE down")

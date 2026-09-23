"""Отчёты аналитики: корзины графиков, окно отчёта, статистика панели и
выгрузка IP в пределах области видимости админа."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from shared.db.network import _bucket_sql
from web.backend.api.v2 import advanced_analytics as aa
from web.backend.core.api_helper import parse_nodes_usage_series


def test_daily_bucket_cuts_days_in_display_zone():
    with patch("shared.timefmt.sql_zone", return_value="'Europe/Moscow'"):
        sql = _bucket_sql("ts", 1440)
    assert sql == "(date_trunc('day', ts AT TIME ZONE 'Europe/Moscow') AT TIME ZONE 'Europe/Moscow')"


def test_hour_and_minute_buckets():
    # Раньше 1440 минут давали почасовые точки: FLOOR(минуты / 1440) = 0
    assert _bucket_sql("ts", 60) == "date_trunc('hour', ts)"
    assert "5 * FLOOR(EXTRACT(MINUTE FROM ts) / 5)" in _bucket_sql("ts", 5)


def test_bounds_default_period_ends_now():
    since, until = aa._bounds("30d")
    assert timedelta(days=29, hours=23) < until - since <= timedelta(days=30)
    assert abs((datetime.now(timezone.utc) - until).total_seconds()) < 5


def test_bounds_custom_dates_include_the_last_day():
    with patch("shared.timefmt.display_tz", return_value=timezone.utc):
        since, until = aa._bounds("7d", "2026-01-10", "2026-01-12")
    assert since == datetime(2026, 1, 10, tzinfo=timezone.utc)
    assert until == datetime(2026, 1, 13, tzinfo=timezone.utc)


def test_panel_series_by_node_arrays():
    resp = {
        "categories": ["2026-09-01", "2026-09-02"],
        "series": [
            {"uuid": "a", "data": [10, 20]},
            {"uuid": "b", "data": [1, "x"]},
        ],
    }
    assert parse_nodes_usage_series(resp) == [
        ("2026-09-01", {"a": 10, "b": 1}),
        ("2026-09-02", {"a": 20}),
    ]


def test_panel_series_legacy_rows():
    resp = {"series": [{"date": "2026-09-01", "a": "5", "b": 7}]}
    assert parse_nodes_usage_series(resp) == [("2026-09-01", {"a": 5, "b": 7})]
    assert parse_nodes_usage_series(None) == []


@pytest.mark.asyncio
async def test_traffic_trend_respects_node_scope():
    resp = {"categories": ["2026-09-01"], "series": [
        {"uuid": "AAA", "data": [100]}, {"uuid": "bbb", "data": [5]},
    ]}
    with patch("web.backend.core.api_helper.fetch_nodes_usage_by_range", AsyncMock(return_value=resp)):
        now = datetime.now(timezone.utc)
        series = await aa._traffic_series(now - timedelta(days=1), now, ["aaa"])
    assert series == [{"date": "2026-09-01", "value": 100}]


@pytest.mark.asyncio
async def test_export_ips_limited_to_visible_nodes(client):
    export = AsyncMock(return_value={"items": [], "total": 0, "truncated": False})
    with patch.object(aa, "_node_scope", AsyncMock(return_value=["n1"])), \
            patch.object(aa, "_user_scope", AsyncMock(return_value=["u1"])), \
            patch.object(aa, "_export_ips", export), \
            patch("web.backend.core.audit.write_audit_log", AsyncMock()) as audit:
        resp = await client.get(
            "/api/v2/analytics/advanced/export-ips",
            params={"date_from": "2026-09-01", "date_to": "2026-09-07", "node_uuids": "n1,n2"},
        )
    assert resp.status_code == 200, resp.text
    args = export.await_args.args
    assert args[2] == ["n1"]      # чужую ноду из запроса выкинули
    assert args[5] == ["u1"]      # и юзеров ограничили видимыми
    assert audit.await_args.kwargs["action"] == "analytics.export_ips"


@pytest.mark.asyncio
async def test_export_ips_foreign_nodes_only_returns_nothing(client):
    export = AsyncMock()
    with patch.object(aa, "_node_scope", AsyncMock(return_value=["n1"])), \
            patch.object(aa, "_export_ips", export):
        resp = await client.get(
            "/api/v2/analytics/advanced/export-ips",
            params={"date_from": "2026-09-01", "date_to": "2026-09-07", "node_uuids": "n2"},
        )
    assert resp.json() == {"items": [], "total": 0, "truncated": False}
    export.assert_not_awaited()


@pytest.mark.asyncio
async def test_export_ips_rejects_bad_dates(client):
    resp = await client.get(
        "/api/v2/analytics/advanced/export-ips",
        params={"date_from": "2026-09-07", "date_to": "2026-09-01"},
    )
    assert resp.status_code == 400

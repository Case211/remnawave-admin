"""#306: какие подключения дали нарушение — улики в разборе, страна в ленте,
сводка адресов вокруг нарушения."""
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import web.backend.api.v2.collector as collector
from shared.db.connections import ConnectionsMixin
from web.backend.api.v2 import violations as violations_api

from .test_violation_detector import conn, make_detector, meta, run_check

USER = "11111111-2222-3333-4444-555555555555"


def _residential(ip, country, asn, city="Moscow", lat=55.7, lon=37.6, kind="residential"):
    return meta(ip, country_code=country, city=city, latitude=lat, longitude=lon,
                asn=asn, asn_org=f"ISP-{asn}", connection_type=kind)


class TestAnalyzerEvidence:
    @pytest.mark.asyncio
    async def test_geo_names_the_connections_from_each_country(self):
        geo_map = {
            "1.1.1.1": _residential("1.1.1.1", "RU", 1),
            "2.2.2.2": _residential("2.2.2.2", "KZ", 2, city="Almaty", lat=43.2, lon=76.9),
        }
        res = await run_check(make_detector(geo_map, recent_violations=0), [conn("1.1.1.1", 60), conn("2.2.2.2", 60)])
        evidence = res.breakdown["geo"].evidence
        assert {(e["ip"], e["country"], e["kind"]) for e in evidence} == {
            ("1.1.1.1", "RU", "simultaneous"), ("2.2.2.2", "KZ", "simultaneous"),
        }
        assert {e["node_uuid"] for e in evidence} == {"n"}

    @pytest.mark.asyncio
    async def test_temporal_lists_addresses_online_together(self):
        ips = ["1.1.1.1", "2.2.2.2", "3.3.3.3"]
        geo_map = {ip: _residential(ip, "RU", 10 + i) for i, ip in enumerate(ips)}
        res = await run_check(make_detector(geo_map), [conn(ip, 600, seen_sec_ago=30) for ip in ips])
        temporal = res.breakdown["temporal"]
        assert temporal.score > 0
        assert [e["ip"] for e in temporal.evidence] == ips

    @pytest.mark.asyncio
    async def test_clean_session_has_no_evidence(self):
        geo_map = {"1.1.1.1": _residential("1.1.1.1", "RU", 1)}
        res = await run_check(make_detector(geo_map), [conn("1.1.1.1", 60)])
        assert res.breakdown["temporal"].evidence == []
        assert res.breakdown["geo"].evidence == []

    @pytest.mark.asyncio
    async def test_asn_points_at_the_datacenter_address(self):
        geo_map = {
            "1.1.1.1": _residential("1.1.1.1", "RU", 1),
            "5.5.5.5": _residential("5.5.5.5", "DE", 24940, kind="datacenter"),
        }
        res = await run_check(make_detector(geo_map), [conn("1.1.1.1", 60), conn("5.5.5.5", 60)])
        assert [(e["ip"], e["connection_type"]) for e in res.breakdown["asn"].evidence] == [("5.5.5.5", "datacenter")]

    @pytest.mark.asyncio
    async def test_evidence_survives_into_raw_breakdown(self):
        geo_map = {
            "1.1.1.1": _residential("1.1.1.1", "RU", 1),
            "2.2.2.2": _residential("2.2.2.2", "KZ", 2, city="Almaty", lat=43.2, lon=76.9),
        }
        res = await run_check(make_detector(geo_map, recent_violations=0), [conn("1.1.1.1", 60), conn("2.2.2.2", 60)])
        stored = json.loads(collector._breakdown_json(res.breakdown))
        first = stored["breakdown"]["geo"]["evidence"][0]
        assert datetime.fromisoformat(first["connected_at"])
        assert first["ip"] in {"1.1.1.1", "2.2.2.2"}


def _acquire(conn_obj):
    @asynccontextmanager
    async def acquire():
        yield conn_obj
    return acquire


@pytest.mark.asyncio
async def test_evidence_gets_node_names():
    conn_obj = MagicMock(fetch=AsyncMock(return_value=[{"uuid": "node-1", "name": "Germany W"}]))
    db = SimpleNamespace(acquire=_acquire(conn_obj))
    raw = {"breakdown": {"geo": {"evidence": [{"ip": "1.1.1.1", "node_uuid": "node-1"}]},
                         "temporal": {"evidence": [{"ip": "2.2.2.2", "node_uuid": None}]}}}
    named = await violations_api._name_evidence_nodes(raw, db)
    assert named["breakdown"]["geo"]["evidence"][0]["node_name"] == "Germany W"
    assert "node_name" not in named["breakdown"]["temporal"]["evidence"][0]
    assert conn_obj.fetch.await_args.args[1] == ["node-1"]


DETECTED = datetime(2026, 9, 30, 11, 16, tzinfo=timezone.utc)


def _api_db():
    db = MagicMock()
    db.is_connected = True
    db.get_violation_by_id = AsyncMock(return_value={"id": 5, "user_uuid": USER, "detected_at": DETECTED})
    db.get_user_address_summary = AsyncMock(return_value=[{"ip": "1.1.1.1", "country_code": "KZ", "connections": 3}])
    return db


class TestAddressSummaryEndpoint:
    @pytest.mark.asyncio
    async def test_window_around_detection(self, app, client):
        from web.backend.api.deps import get_db
        db = _api_db()
        app.dependency_overrides[get_db] = lambda: db
        with patch("web.backend.core.rbac.get_visible_user_uuids", new_callable=AsyncMock, return_value=None):
            resp = await client.get("/api/v2/violations/5/addresses?window_minutes=30")
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"] == [{"ip": "1.1.1.1", "country_code": "KZ", "connections": 3}]
        user, start, end = db.get_user_address_summary.await_args.args
        assert (user, start, end) == (USER, DETECTED - timedelta(minutes=30), DETECTED + timedelta(minutes=30))

    @pytest.mark.asyncio
    async def test_hidden_user_is_not_found(self, app, client):
        from web.backend.api.deps import get_db
        db = _api_db()
        app.dependency_overrides[get_db] = lambda: db
        with patch("web.backend.core.rbac.get_visible_user_uuids", new_callable=AsyncMock, return_value={"other"}):
            resp = await client.get("/api/v2/violations/5/addresses")
        assert resp.status_code == 404
        db.get_user_address_summary.assert_not_awaited()


@pytest.mark.asyncio
async def test_timeline_shows_country_and_network(app, client):
    from web.backend.api.deps import get_db
    db = MagicMock()
    db.is_connected = True
    db.get_user_violations = AsyncMock(return_value=[])
    db.get_user_hwid_devices = AsyncMock(return_value=[])
    db.get_user_connection_history = AsyncMock(return_value=[{
        "connected_at": "2026-09-30T11:01:00+00:00", "ip_address": "2.2.2.2", "node_name": "Germany W",
        "country_code": "KZ", "connection_type": "mobile", "device_info": None,
    }])
    app.dependency_overrides[get_db] = lambda: db
    with patch("web.backend.core.rbac.get_visible_user_uuids", new_callable=AsyncMock, return_value=None):
        resp = await client.get(f"/api/v2/violations/user/{USER}/timeline")
    assert resp.status_code == 200, resp.text
    event = resp.json()["items"][0]
    assert (event["ip"], event["country_code"], event["connection_type"]) == ("2.2.2.2", "KZ", "mobile")


@pytest.mark.asyncio
async def test_address_summary_query():
    rows = [{"ip": "1.1.1.1", "first_seen": DETECTED, "last_seen": DETECTED + timedelta(minutes=5),
             "connections": 3, "nodes": ["Germany W"], "country_code": "KZ", "city": None,
             "connection_type": "mobile", "asn_org": "Beeline"}]
    conn_obj = MagicMock(fetch=AsyncMock(return_value=rows))
    db = SimpleNamespace(is_connected=True, acquire=_acquire(conn_obj))
    start, end = DETECTED - timedelta(hours=1), DETECTED + timedelta(hours=1)

    items = await ConnectionsMixin.get_user_address_summary(db, USER, start, end)

    sql, *args = conn_obj.fetch.await_args.args
    assert "COALESCE(uc.disconnected_at, NOW()) >= $2" in sql and "GROUP BY uc.ip_address" in sql
    assert args == [USER, start, end, 50]
    assert items[0]["first_seen"] == DETECTED.isoformat() and items[0]["nodes"] == ["Germany W"]

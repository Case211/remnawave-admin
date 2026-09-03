"""Карта активности коллектора: детектор считает одновременность по ней.

Строки в базе стартов не обновляют и переписываются только при изменениях,
поэтому «кто сейчас в сети с какого адреса» коллектор помнит сам.
"""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.api.v2 import collector
from web.backend.tests.test_collector_api import (
    AGENT_HEADERS, NODE_UUID, USER_UUID, make_batch, make_connection, make_db_mock, make_pipeline_config,
)


@pytest.fixture(autouse=True)
def _clean_activity():
    collector._activity.clear()
    collector._last_activity_sweep = datetime.min
    yield
    collector._activity.clear()


def _seen(ip, seen_sec_ago=0, user="u1", node="n1"):
    return {"user_uuid": user, "ip_address": ip, "node_uuid": node,
            "connected_at": datetime.utcnow() - timedelta(seconds=seen_sec_ago)}


class TestActivityMap:
    def test_first_sighting_is_kept_as_start_and_last_seen_advances(self):
        collector._note_activity([_seen("1.1.1.1", seen_sec_ago=600)])
        collector._note_activity([_seen("1.1.1.1", seen_sec_ago=5, node="n2")])
        first, last, node = collector._activity["u1"]["1.1.1.1"]
        assert (last - first).total_seconds() > 500
        assert node == "n2"

    def test_live_connections_respect_the_window(self):
        collector._note_activity([_seen("1.1.1.1", 10), _seen("2.2.2.2", 20), _seen("3.3.3.3", 600)])
        live = collector._live_connections(["u1", "nobody"])
        assert sorted(c.ip_address for c in live["u1"]) == ["1.1.1.1", "2.2.2.2"]
        assert live["nobody"] == []
        assert all(c.last_seen_at is not None for c in live["u1"])

    def test_sweep_forgets_stale_addresses_and_empty_users(self):
        collector._note_activity([_seen("1.1.1.1", 10), _seen("9.9.9.9", 3600, user="u2")])
        collector._sweep_activity(datetime.utcnow())
        assert "u2" not in collector._activity
        assert "1.1.1.1" in collector._activity["u1"]


class TestDetectorGetsLiveConnections:
    @pytest.mark.asyncio
    async def test_live_connections_are_passed_to_batch_check(self):
        collector._note_activity([_seen("1.1.1.1", 5, user=USER_UUID), _seen("2.2.2.2", 7, user=USER_UUID)])
        db = make_db_mock()
        db.batch_get_whitelist_status = AsyncMock(return_value={USER_UUID: (False, None)})
        db.batch_get_user_hwid_devices = AsyncMock(return_value={USER_UUID: []})
        detector = MagicMock()
        detector.check_users_batch = AsyncMock(return_value={})
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "violation_detector", detector), \
             patch.object(collector, "config_service", make_pipeline_config()):
            await collector._run_violation_detection({USER_UUID})
        live = detector.check_users_batch.await_args.kwargs["live_connections"]
        assert sorted(c.ip_address for c in live[USER_UUID]) == ["1.1.1.1", "2.2.2.2"]

    @pytest.mark.asyncio
    async def test_unchanged_rows_still_feed_the_detector(self, anon_client):
        """База не переписала ни одной строки, но пользователь был в батче — детектор обязан его увидеть."""
        db = make_db_mock()
        db.batch_upsert_connections = AsyncMock(return_value={"upserted": 0, "closed_stale": 0})
        enqueue = MagicMock()
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)), \
             patch.object(collector, "_enqueue_violation_users", enqueue):
            resp = await anon_client.post(
                "/api/v2/collector/batch",
                json=make_batch(connections=[make_connection()]), headers=AGENT_HEADERS,
            )
        assert resp.status_code == 200
        assert resp.json()["processed"] == 1
        enqueue.assert_called_once_with({USER_UUID})
        assert "1.2.3.4" in collector._activity[USER_UUID]

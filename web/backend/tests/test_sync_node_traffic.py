"""Синк трафика нод: формат ответа панели и итог по ноде.

Регрессия: 3.2.0 переименовала список юзеров ``users`` -> ``topUsers``,
синк продолжал читать старый ключ и получал пустоту. Исключений при
этом не было — в ``node_traffic_snapshots`` молча писались нули, и
график «Трафик 24ч» на дашборде схлопывался в пустоту (сводка сверху
и разрезы 7д/30д живы, они идут в Panel API напрямую).

Второе: ``topUsers`` режется параметром ``topUsersLimit``, поэтому
итог ноды берём из ``sparklineData`` — иначе на панели, где юзеров
больше лимита, снапшот занижен.
"""
from unittest.mock import AsyncMock, patch

import pytest

from shared.sync import NODE_USAGE_TOP_USERS, SyncService, _node_total_bytes


def _panel_320(day: str, total: int, users: list) -> dict:
    """Ответ /bandwidth-stats/nodes/{uuid}/users как его шлёт 3.2.0."""
    return {"response": {
        "categories": [day, "2026-08-06"],
        "sparklineData": [total, 0],
        "topUsers": users,
    }}


def _db_mock():
    db = AsyncMock()
    db.is_connected = True
    db.get_all_nodes.return_value = [{"uuid": "N1", "name": "Estonia", "isConnected": True}]
    db.get_user_node_traffic_snapshot.return_value = {}
    db.get_user_uuid_by_panel_id.side_effect = lambda pid: f"uuid-{pid}"
    return db


class TestNodeTotalBytes:
    def test_takes_value_for_requested_day(self):
        resp = {"categories": ["2026-08-04", "2026-08-05"], "sparklineData": [11, 22]}
        assert _node_total_bytes(resp, "2026-08-05", fallback=0) == 22

    def test_falls_back_when_panel_has_no_sparkline(self):
        """Панель постарше не шлёт categories — остаётся сумма по юзерам."""
        assert _node_total_bytes({"users": []}, "2026-08-05", fallback=777) == 777

    def test_falls_back_when_day_missing(self):
        resp = {"categories": ["2026-08-04"], "sparklineData": [11]}
        assert _node_total_bytes(resp, "2026-08-05", fallback=42) == 42

    def test_survives_broken_payload(self):
        assert _node_total_bytes({"categories": "x", "sparklineData": 5}, "d", fallback=1) == 1
        assert _node_total_bytes(None, "d", fallback=1) == 1


class TestSyncNodeTraffic:
    @pytest.mark.asyncio
    async def test_reads_top_users_from_320(self):
        """Главная регрессия: снапшот ноды не должен быть нулевым."""
        svc = SyncService()
        db = _db_mock()
        api = AsyncMock()
        api.get_node_users_usage.return_value = _panel_320(
            "2026-08-05", 900, [{"userId": 561, "total": 500}, {"userId": 247, "total": 400}],
        )
        with patch("shared.sync.db_service", db), \
             patch("shared.sync.api_client", api), \
             patch("shared.sync.datetime") as dt:
            dt.now.return_value.replace.return_value.strftime.return_value = "2026-08-05"
            await svc.sync_node_traffic()

        snapshots = db.insert_node_traffic_snapshots.await_args.args[0]
        assert snapshots == [("N1", 900)]

    @pytest.mark.asyncio
    async def test_asks_for_enough_users(self):
        """Панель отдаёт ровно топ-N, дефолтные 10 обрезали бы срез."""
        svc = SyncService()
        db = _db_mock()
        api = AsyncMock()
        api.get_node_users_usage.return_value = _panel_320("2026-08-05", 0, [])
        with patch("shared.sync.db_service", db), patch("shared.sync.api_client", api):
            await svc.sync_node_traffic()
        assert api.get_node_users_usage.await_args.kwargs["top_users_limit"] == NODE_USAGE_TOP_USERS

    @pytest.mark.asyncio
    async def test_node_total_ignores_missing_users(self):
        """Юзеров на ноде больше лимита — итог всё равно панельный."""
        svc = SyncService()
        db = _db_mock()
        api = AsyncMock()
        api.get_node_users_usage.return_value = _panel_320(
            "2026-08-05", 5000, [{"userId": 561, "total": 500}],
        )
        with patch("shared.sync.db_service", db), \
             patch("shared.sync.api_client", api), \
             patch("shared.sync.datetime") as dt:
            dt.now.return_value.replace.return_value.strftime.return_value = "2026-08-05"
            await svc.sync_node_traffic()
        assert db.insert_node_traffic_snapshots.await_args.args[0] == [("N1", 5000)]

    @pytest.mark.asyncio
    async def test_legacy_users_key_still_works(self):
        """Панель постарше: ключ users и uuid вместо числового id."""
        svc = SyncService()
        db = _db_mock()
        api = AsyncMock()
        api.get_node_users_usage.return_value = {"response": {
            "users": [{"userUuid": "U1", "trafficBytes": 300},
                      {"userUuid": "U2", "trafficBytes": 200}],
        }}
        with patch("shared.sync.db_service", db), patch("shared.sync.api_client", api):
            await svc.sync_node_traffic()
        assert db.insert_node_traffic_snapshots.await_args.args[0] == [("N1", 500)]

    @pytest.mark.asyncio
    async def test_panel_ids_resolve_to_local_uuids(self):
        """Дельты и апсерты живут на локальном uuid, а не панельном id."""
        svc = SyncService()
        db = _db_mock()
        api = AsyncMock()
        api.get_node_users_usage.return_value = _panel_320(
            "2026-08-05", 500, [{"userId": 561, "total": 500}],
        )
        with patch("shared.sync.db_service", db), patch("shared.sync.api_client", api):
            await svc.sync_node_traffic()
        upserts = db.batch_upsert_user_node_traffic.await_args.args[0]
        assert upserts == [("uuid-561", "N1", 500)]
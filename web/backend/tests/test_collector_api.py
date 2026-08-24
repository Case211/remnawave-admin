"""Tests for the collector API (web/backend/api/v2/collector.py).

Покрывает: аутентификацию агентов, rate limit per node, node_uuid mismatch,
приём батча (метрики/подключения/резолв идентификаторов), кулдаун-логику
batch-пайплайна нарушений, /health и /stats.
"""
import gzip
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import web.backend.api.v2.collector as collector

NODE_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
USER_UUID = "11111111-2222-3333-4444-555555555555"
AGENT_HEADERS = {"Authorization": "Bearer valid-agent-token"}


def make_batch(node_uuid: str = NODE_UUID, connections=None, torrent_events=None):
    return {
        "node_uuid": node_uuid,
        "timestamp": "2026-06-07T12:00:00Z",
        "connections": connections or [],
        "torrent_events": torrent_events or [],
    }


def make_connection(email: str = "alice@example.com"):
    return {
        "user_email": email,
        "ip_address": "1.2.3.4",
        "node_uuid": NODE_UUID,
        "connected_at": "2026-06-07T12:00:00Z",
        "bytes_sent": 100,
        "bytes_received": 200,
    }


def make_db_mock():
    """db_service mock с дефолтами для happy-path батча."""
    db = MagicMock()
    db.is_connected = True
    db.get_node_by_uuid = AsyncMock(return_value={"name": "test-node"})
    db.update_node_metrics = AsyncMock()
    db.update_node_agent_version = AsyncMock()
    db.insert_node_metrics_snapshot = AsyncMock()
    db.cleanup_old_metrics_snapshots = AsyncMock(return_value=0)
    db.cleanup_old_connections = AsyncMock(return_value=0)
    db.ensure_connection_partitions = AsyncMock()
    db.cleanup_old_torrent_events = AsyncMock(return_value=0)
    db.get_email_to_uuid_map = AsyncMock(return_value={"alice@example.com": USER_UUID})
    db.get_short_uuid_to_uuid_map = AsyncMock(return_value={})
    db.get_user_uuid_by_email = AsyncMock(return_value=None)
    db.get_user_by_short_uuid = AsyncMock(return_value=None)
    db.get_user_uuid_by_id_from_raw_data = AsyncMock(return_value=None)
    db.batch_upsert_connections = AsyncMock(return_value={"upserted": 1, "closed_stale": 0})
    db.batch_save_torrent_events = AsyncMock(return_value=0)

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    db.acquire = MagicMock(return_value=cm)
    return db


@pytest.fixture(autouse=True)
def reset_collector_state():
    """Глобальное состояние модуля не должно протекать между тестами."""
    collector._node_last_batch.clear()
    collector._pending_violation_users.clear()
    collector._violation_check_cooldown.clear()
    collector._node_name_cache.clear()
    # Гасим часовой таймер чистки нарушений, чтобы не дёргал db в тестах
    collector._last_violation_cleanup = datetime.utcnow()
    yield
    collector._node_last_batch.clear()
    collector._pending_violation_users.clear()
    collector._violation_check_cooldown.clear()
    collector._node_name_cache.clear()


# ── Аутентификация агента ─────────────────────────────────────


class TestAgentAuth:
    """POST /api/v2/collector/batch — auth."""

    @pytest.mark.asyncio
    async def test_missing_authorization_header(self, anon_client):
        resp = await anon_client.post("/api/v2/collector/batch", json=make_batch())
        assert resp.status_code == 422  # Header(...) обязателен

    @pytest.mark.asyncio
    async def test_non_bearer_header(self, anon_client):
        resp = await anon_client.post(
            "/api/v2/collector/batch", json=make_batch(),
            headers={"Authorization": "Basic abc123"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_token(self, anon_client):
        resp = await anon_client.post(
            "/api/v2/collector/batch", json=make_batch(),
            headers={"Authorization": "Bearer   "},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token(self, anon_client):
        db = make_db_mock()
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "get_node_by_token", AsyncMock(return_value=None)):
            resp = await anon_client.post(
                "/api/v2/collector/batch", json=make_batch(), headers=AGENT_HEADERS,
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_node_uuid_mismatch(self, anon_client):
        db = make_db_mock()
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)):
            resp = await anon_client.post(
                "/api/v2/collector/batch",
                json=make_batch(node_uuid="ffffffff-0000-0000-0000-000000000000"),
                headers=AGENT_HEADERS,
            )
        assert resp.status_code == 403
        assert "does not match" in resp.json()["detail"]


# ── Приём батча ───────────────────────────────────────────────


class TestReceiveBatch:
    """POST /api/v2/collector/batch — happy paths."""

    @pytest.mark.asyncio
    async def test_empty_batch_ok(self, anon_client):
        db = make_db_mock()
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)):
            resp = await anon_client.post(
                "/api/v2/collector/batch", json=make_batch(), headers=AGENT_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["processed"] == 0

    @pytest.mark.asyncio
    async def test_rate_limit_second_batch(self, anon_client):
        db = make_db_mock()
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)):
            first = await anon_client.post(
                "/api/v2/collector/batch", json=make_batch(), headers=AGENT_HEADERS,
            )
            second = await anon_client.post(
                "/api/v2/collector/batch", json=make_batch(), headers=AGENT_HEADERS,
            )
        assert first.status_code == 200
        assert second.status_code == 429

    @pytest.mark.asyncio
    async def test_connections_processed_and_enqueued(self, anon_client):
        db = make_db_mock()
        enqueue = MagicMock()
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)), \
             patch.object(collector, "_enqueue_violation_users", enqueue):
            resp = await anon_client.post(
                "/api/v2/collector/batch",
                json=make_batch(connections=[make_connection()]),
                headers=AGENT_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] == 1
        assert data["errors"] == 0
        db.batch_upsert_connections.assert_awaited_once()
        enqueue.assert_called_once_with({USER_UUID})

    @pytest.mark.asyncio
    async def test_unresolved_user_counts_as_error(self, anon_client):
        db = make_db_mock()
        db.get_email_to_uuid_map = AsyncMock(return_value={})
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)):
            resp = await anon_client.post(
                "/api/v2/collector/batch",
                json=make_batch(connections=[make_connection("ghost@example.com")]),
                headers=AGENT_HEADERS,
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["processed"] == 0
        assert data["errors"] == 1
        db.batch_upsert_connections.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_network_metrics_reach_db(self, anon_client):
        """Сетевые метрики агента 1.3.0+ доезжают и до ноды, и до истории."""
        db = make_db_mock()
        batch = make_batch()
        batch["system_metrics"] = {"cpu_percent": 5.0}
        batch["network_metrics"] = {"rx_bps": 1_250_000, "rx_pps": 90_000, "conntrack_count": 42}

        with patch.object(collector, "db_service", db), \
             patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)):
            resp = await anon_client.post(
                "/api/v2/collector/batch", json=batch, headers=AGENT_HEADERS,
            )

        assert resp.status_code == 200
        network = db.update_node_metrics.await_args.kwargs["network"]
        assert network["rx_bps"] == 1_250_000
        assert network["rx_pps"] == 90_000
        assert network["conntrack_count"] == 42
        assert db.insert_node_metrics_snapshot.await_args.kwargs["network"] == network

    @pytest.mark.asyncio
    async def test_agent_without_network_metrics_leaves_columns_alone(self, anon_client):
        """Агент до 1.3.0 сетевого не шлёт — колонки нельзя перетирать нулями."""
        db = make_db_mock()
        batch = make_batch()
        batch["system_metrics"] = {"cpu_percent": 5.0}

        with patch.object(collector, "db_service", db), \
             patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)):
            resp = await anon_client.post(
                "/api/v2/collector/batch", json=batch, headers=AGENT_HEADERS,
            )

        assert resp.status_code == 200
        assert db.update_node_metrics.await_args.kwargs["network"] is None
        assert db.insert_node_metrics_snapshot.await_args.kwargs["network"] is None

    @pytest.mark.asyncio
    async def test_oversized_batch_rejected(self, anon_client):
        batch = make_batch(connections=[make_connection() for _ in range(5001)])
        with patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)):
            resp = await anon_client.post(
                "/api/v2/collector/batch", json=batch, headers=AGENT_HEADERS,
            )
        assert resp.status_code == 422  # max_length=5000


# ── Кулдаун batch-пайплайна нарушений ─────────────────────────


def make_violation_score(total: float = 80.0):
    score = MagicMock()
    score.total = total
    score.confidence = 0.9
    score.reasons = ["test reason"]
    score.breakdown = {}
    score.recommended_action = MagicMock()
    score.recommended_action.value = "monitor"
    return score


def make_pipeline_config(overrides: dict = None):
    values = {
        "violations_enabled": True,
        "violations_min_score": 50.0,
        "violation_check_cooldown_minutes": 15,
        "user_blacklist_enabled": False,
        "hwid_blacklist_enabled": False,
    }
    values.update(overrides or {})
    cfg = MagicMock()
    cfg.get = MagicMock(side_effect=lambda key, default=None: values.get(key, default))
    return cfg


class TestViolationCooldown:
    """_run_violation_detection — фильтрация и обновление кулдауна."""

    @pytest.mark.asyncio
    async def test_user_on_cooldown_is_skipped(self):
        collector._violation_check_cooldown[USER_UUID] = datetime.utcnow()
        db = make_db_mock()
        detector = MagicMock()
        detector.check_users_batch = AsyncMock(return_value={})
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "violation_detector", detector), \
             patch.object(collector, "config_service", make_pipeline_config()):
            await collector._run_violation_detection({USER_UUID})
        detector.check_users_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_violation_sets_full_cooldown(self):
        db = make_db_mock()
        db.batch_get_whitelist_status = AsyncMock(return_value={USER_UUID: (False, None)})
        db.batch_get_user_hwid_devices = AsyncMock(return_value={USER_UUID: []})
        detector = MagicMock()
        detector.check_users_batch = AsyncMock(return_value={})  # нарушений нет
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "violation_detector", detector), \
             patch.object(collector, "config_service", make_pipeline_config()):
            await collector._run_violation_detection({USER_UUID})
        detector.check_users_batch.assert_awaited_once()
        cooldown_at = collector._violation_check_cooldown[USER_UUID]
        # Полный кулдаун: метка «сейчас» (не сдвинута в прошлое)
        assert (datetime.utcnow() - cooldown_at).total_seconds() < 5

    @pytest.mark.asyncio
    async def test_violation_sets_reduced_cooldown(self):
        db = make_db_mock()
        db.batch_get_whitelist_status = AsyncMock(return_value={USER_UUID: (False, None)})
        db.batch_get_user_hwid_devices = AsyncMock(return_value={USER_UUID: []})
        db.batch_get_users_info = AsyncMock(return_value={USER_UUID: {"username": "alice"}})
        detector = MagicMock()
        detector.check_users_batch = AsyncMock(
            return_value={USER_UUID: make_violation_score(80.0)}
        )
        handle = AsyncMock()
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "violation_detector", detector), \
             patch.object(collector, "config_service", make_pipeline_config()), \
             patch.object(collector, "_handle_violation", handle):
            await collector._run_violation_detection({USER_UUID})
        handle.assert_awaited_once()
        cooldown_at = collector._violation_check_cooldown[USER_UUID]
        # Нарушитель: кулдаун сокращён на 5 минут (метка сдвинута в прошлое)
        shift = (datetime.utcnow() - cooldown_at).total_seconds()
        assert 9 * 60 < shift < 11 * 60

    @pytest.mark.asyncio
    async def test_fully_whitelisted_user_not_checked(self):
        db = make_db_mock()
        db.batch_get_whitelist_status = AsyncMock(return_value={USER_UUID: (True, None)})
        detector = MagicMock()
        detector.check_users_batch = AsyncMock(return_value={})
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "violation_detector", detector), \
             patch.object(collector, "config_service", make_pipeline_config()):
            await collector._run_violation_detection({USER_UUID})
        detector.check_users_batch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_violations_disabled_short_circuits(self):
        db = make_db_mock()
        detector = MagicMock()
        detector.check_users_batch = AsyncMock(return_value={})
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "violation_detector", detector), \
             patch.object(collector, "config_service",
                          make_pipeline_config({"violations_enabled": False})):
            await collector._run_violation_detection({USER_UUID})
        detector.check_users_batch.assert_not_awaited()
        db.batch_get_whitelist_status.assert_not_called()


# ── Service endpoints ─────────────────────────────────────────


class TestCollectorHealth:
    """GET /api/v2/collector/health."""

    @pytest.mark.asyncio
    async def test_health_ok(self, anon_client):
        db = make_db_mock()
        with patch.object(collector, "db_service", db):
            resp = await anon_client.get("/api/v2/collector/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["database_connected"] is True

    @pytest.mark.asyncio
    async def test_health_degraded_without_db(self, anon_client):
        db = make_db_mock()
        db.is_connected = False
        with patch.object(collector, "db_service", db):
            resp = await anon_client.get("/api/v2/collector/health")
        assert resp.status_code == 503
        assert resp.json()["status"] == "degraded"


class TestCollectorStats:
    """GET /api/v2/collector/stats — только для админов (JWT)."""

    @pytest.mark.asyncio
    async def test_stats_requires_auth(self, anon_client):
        resp = await anon_client.get("/api/v2/collector/stats")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_stats_rejects_garbage_token(self, anon_client):
        resp = await anon_client.get(
            "/api/v2/collector/stats",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_stats_with_valid_jwt(self, anon_client):
        from web.backend.core.security import create_access_token
        token = create_access_token("100000", "testadmin")
        resp = await anon_client.get(
            "/api/v2/collector/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "queue" in data
        assert "processing" in data
        assert data["queue"]["health"] in ("idle", "ok", "busy", "overloaded")


class TestSharedHwidUserUuids:
    """_shared_hwid_user_uuids — разворачивание групп get_shared_hwids() для HWID-скана.

    Регрессия C3: скан-цикл читал r["user_uuid"] из группированного ответа
    ({hwid, users: [...]}) — ключа там нет, множество всегда выходило пустым
    и оффлайн-абузеры никогда не попадали в очередь детектора.
    """

    def test_extracts_uuids_from_groups(self):
        groups = [
            {"hwid": "HW1", "user_count": 2, "users": [
                {"uuid": "U1", "username": "a"},
                {"uuid": "U2", "username": "b"},
            ]},
            {"hwid": "HW2", "user_count": 2, "users": [
                {"uuid": "U2", "username": "b"},
                {"uuid": "U3", "username": "c"},
            ]},
        ]
        assert collector._shared_hwid_user_uuids(groups) == {"U1", "U2", "U3"}

    def test_empty_and_malformed_groups(self):
        assert collector._shared_hwid_user_uuids([]) == set()
        assert collector._shared_hwid_user_uuids(None) == set()
        assert collector._shared_hwid_user_uuids([{"hwid": "HW1"}]) == set()
        assert collector._shared_hwid_user_uuids([{"hwid": "HW1", "users": [{"username": "x"}]}]) == set()


class TestAgentVersion:
    """Версия агента из батча пишется в ноду (и не пишется, если не прислана)."""

    @pytest.mark.asyncio
    async def test_agent_version_saved(self, anon_client):
        db = make_db_mock()
        batch = make_batch()
        batch["agent_version"] = "1.1.0"
        with patch.object(collector, "db_service", db),              patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)):
            resp = await anon_client.post(
                "/api/v2/collector/batch", json=batch, headers=AGENT_HEADERS,
            )
        assert resp.status_code == 200
        db.update_node_agent_version.assert_awaited_once_with(NODE_UUID, "1.1.0")

    @pytest.mark.asyncio
    async def test_no_version_no_update(self, anon_client):
        db = make_db_mock()
        with patch.object(collector, "db_service", db),              patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)):
            resp = await anon_client.post(
                "/api/v2/collector/batch", json=make_batch(), headers=AGENT_HEADERS,
            )
        assert resp.status_code == 200
        db.update_node_agent_version.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_db_error_does_not_break_batch(self, anon_client):
        db = make_db_mock()
        db.update_node_agent_version = AsyncMock(side_effect=RuntimeError("db down"))
        batch = make_batch()
        batch["agent_version"] = "1.1.0"
        with patch.object(collector, "db_service", db),              patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)):
            resp = await anon_client.post(
                "/api/v2/collector/batch", json=batch, headers=AGENT_HEADERS,
            )
        assert resp.status_code == 200  # батч не падает из-за версии


class TestConsoleNoiseFilter:
    """Пульс коллектора глушится на консоли, но не в файлах (их читает UI)."""

    def _rec(self, name, msg):
        import logging
        return logging.LogRecord(name, logging.INFO, __file__, 1, msg, None, None)

    def test_batch_lines_muted_on_console(self):
        from shared.logger import ConsoleNoiseFilter
        f = ConsoleNoiseFilter()
        assert f.filter(self._rec("web.backend.api.v2.collector", "Batch received      node=X")) is False
        assert f.filter(self._rec("web.backend.api.v2.collector", "Batch upserted      node=X")) is False

    def test_other_collector_lines_pass(self):
        from shared.logger import ConsoleNoiseFilter
        f = ConsoleNoiseFilter()
        assert f.filter(self._rec("web.backend.api.v2.collector", "Node UUID mismatch")) is True

    def test_same_prefix_other_logger_passes(self):
        from shared.logger import ConsoleNoiseFilter
        f = ConsoleNoiseFilter()
        assert f.filter(self._rec("some.other.module", "Batch received whatever")) is True


class TestHandleViolationDisabledUser:
    """_handle_violation скипает юзеров со статусом DISABLED в панели.

    Кейс из сообщества: заблокированный (отключённый) юзер продолжал
    порождать нарушения по остаточным коннектам каждый детект-цикл —
    «нарушения по кругу» на всю сеть кросс-аккаунтов.
    """

    @pytest.mark.asyncio
    async def test_disabled_user_skipped(self):
        db = make_db_mock()
        db.save_violation = AsyncMock(return_value=(1, True))
        monitor = MagicMock()
        monitor.get_user_active_connections = AsyncMock(return_value=[])
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "connection_monitor", monitor):
            await collector._handle_violation(
                USER_UUID, make_violation_score(100.0),
                {"username": "alice", "status": "DISABLED"}, [], False,
            )
        monitor.get_user_active_connections.assert_not_awaited()
        db.save_violation.assert_not_awaited()


class TestHwidBlacklistScan:
    """Периодический скан блеклиста не должен рапортовать по кругу.

    Скан ходит раз в 30 минут по всем собранным HWID. Пока устройство висит на
    аккаунте, совпадение находится каждый раз — и админ получал «HWID Blacklist:
    users blocked» про уже отключённого юзера до бесконечности, да ещё голым
    UUID вместо имени и отдельным сообщением на каждого.
    """

    @staticmethod
    def _db(status, username="bob"):
        db = make_db_mock()
        db.batch_get_whitelist_status = AsyncMock(return_value={USER_UUID: (False, None)})
        db.batch_get_user_hwid_devices = AsyncMock(
            return_value={USER_UUID: [{"hwid": "BADHWID"}]}
        )
        db.batch_get_users_info = AsyncMock(
            return_value={USER_UUID: {"username": username, "status": status}}
        )
        db.check_hwids_against_blacklist = AsyncMock(
            return_value=[{"hwid": "BADHWID", "action": "block", "reason": "Абуз триала"}]
        )
        return db

    async def _run(self, db, handler):
        detector = MagicMock()
        detector.check_users_batch = AsyncMock(return_value={})
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "violation_detector", detector), \
             patch.object(collector, "config_service", make_pipeline_config()), \
             patch("web.backend.api.v2.violations._handle_blacklisted_hwid_users", handler):
            await collector._run_violation_detection({USER_UUID})

    @pytest.mark.asyncio
    async def test_disabled_user_not_reported_again(self):
        handler = AsyncMock()
        await self._run(self._db("DISABLED"), handler)
        handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_active_user_reported_with_username(self):
        handler = AsyncMock()
        await self._run(self._db("ACTIVE"), handler)
        handler.assert_awaited_once()
        hwid, action, reason, affected = handler.await_args.args
        assert hwid == "BADHWID"
        assert action == "block"
        assert affected == [{"user_uuid": USER_UUID, "username": "bob"}]


class TestHwidReuseNotification:
    """Сигнал в момент привязки устройства, уже засветившегося на другом аккаунте.

    Периодический скан заметит это в течение получаса, и всё это время свежий
    триал работает. Но шуметь на всякое совпадение нельзя: по журналу за
    полтора месяца пар «пробная → купленная» у одного человека набралось 20,
    а реальных нарушений — 4.
    """

    OTHER = "22222222-2222-2222-2222-222222222222"

    @staticmethod
    def _db(group, blacklisted=False):
        db = make_db_mock()
        db.get_shared_hwids_for_user = AsyncMock(return_value=[group] if group else [])
        db.check_hwids_against_blacklist = AsyncMock(
            return_value=[{"hwid": "HW1", "action": "block"}] if blacklisted else []
        )
        db.get_user_hwid_devices = AsyncMock(return_value=[
            {"hwid": "HW1", "platform": "android", "os_version": "15", "app_version": "Happ/3.25"},
        ])
        db.batch_get_users_info = AsyncMock(return_value={
            USER_UUID: {"username": "new-one", "status": "ACTIVE"},
        })
        return db

    async def _run(self, group, blacklisted=False):
        notify = AsyncMock()
        db = self._db(group, blacklisted)
        cfg = MagicMock()
        cfg.get = MagicMock(side_effect=lambda key, default=None: default)
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "config_service", cfg), \
             patch("web.backend.core.notification_service.create_notification", notify):
            await collector._notify_hwid_reuse({"user_uuid": USER_UUID, "hwid": "HW1"})
        return notify

    def _group(self, **over):
        group = {
            "hwid": "HW1", "self_telegram_id": 100, "self_email": None,
            "self_is_trial": True, "self_is_active": True,
            "other_users": [{
                "uuid": self.OTHER, "username": "old", "telegram_id": 100,
                "email": None, "is_trial": True, "is_active": False, "removed_at": None,
            }],
        }
        group.update(over)
        return group

    @pytest.mark.asyncio
    async def test_no_other_accounts_is_silent(self):
        assert (await self._run(None)).await_count == 0

    @pytest.mark.asyncio
    async def test_conversion_trial_to_paid_is_silent(self):
        """Тот же человек, старая подписка уже не пробная — это покупка."""
        group = self._group()
        group["other_users"][0]["is_trial"] = False
        assert (await self._run(group)).await_count == 0

    @pytest.mark.asyncio
    async def test_repeat_trial_same_person_is_critical(self):
        notify = await self._run(self._group())
        notify.assert_awaited_once()
        assert notify.await_args.kwargs["severity"] == "critical"
        assert notify.await_args.kwargs["event"] == "violation.hwid_reused"

    @pytest.mark.asyncio
    async def test_stranger_account_is_warning(self):
        group = self._group()
        group["other_users"][0]["telegram_id"] = 999
        notify = await self._run(group)
        notify.assert_awaited_once()
        assert notify.await_args.kwargs["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_unlinked_device_marked_in_body(self):
        group = self._group()
        group["other_users"][0]["telegram_id"] = 999
        group["other_users"][0]["removed_at"] = datetime.utcnow()
        notify = await self._run(group)
        assert "Устройство отвязано" in notify.await_args.kwargs["body"]

    @pytest.mark.asyncio
    async def test_blacklisted_hwid_is_left_to_blacklist_path(self):
        """Про устройство из чёрного списка скажет блеклист — и скажет больше."""
        assert (await self._run(self._group(), blacklisted=True)).await_count == 0

    @pytest.mark.asyncio
    async def test_card_carries_device_and_target(self):
        """Карточка без деталей устройства и принимающего аккаунта бесполезна."""
        body = (await self._run(self._group())).await_args.kwargs["body"]
        assert "Android 15" in body
        assert "new-one" in body
        assert "<b>" in body, "разметка нужна боту для rich-сообщения"


class TestPublicIpForAgent:
    """_public_ip_for_agent: за внутренним прокси agent_ip не должен
    становиться приватным 172.x (у всех нод был «IP» docker-nginx)."""

    def _req(self, headers=None):
        req = MagicMock()
        req.headers = headers or {}
        return req

    def test_public_peer_wins(self):
        assert collector._public_ip_for_agent(
            self._req({"x-forwarded-for": "1.2.3.4"}), "5.6.7.8") == "5.6.7.8"

    def test_private_peer_takes_rightmost_public_xff(self):
        req = self._req({"x-forwarded-for": "9.9.9.9, 77.88.55.66, 172.19.0.10"})
        assert collector._public_ip_for_agent(req, "172.19.0.10") == "77.88.55.66"

    def test_private_peer_falls_back_to_real_ip(self):
        req = self._req({"x-real-ip": "77.88.55.66"})
        assert collector._public_ip_for_agent(req, "172.19.0.10") == "77.88.55.66"

    def test_private_everything_returns_none(self):
        req = self._req({"x-forwarded-for": "10.0.0.5, 192.168.1.1"})
        assert collector._public_ip_for_agent(req, "172.19.0.10") is None

    @pytest.mark.asyncio
    async def test_remember_skips_empty(self):
        db = make_db_mock()
        with patch.object(collector, "db_service", db):
            await collector._remember_agent_ip("node-1", None)
        db.acquire.assert_not_called()


# ── Сжатые тела (агент 1.6.0+) ────────────────────────────────


class TestGzipBody:
    """POST /api/v2/collector/batch с Content-Encoding: gzip."""

    @staticmethod
    def _gzip_headers():
        return {**AGENT_HEADERS, "Content-Type": "application/json", "Content-Encoding": "gzip"}

    @pytest.mark.asyncio
    async def test_gzipped_batch_processed_like_plain(self, anon_client):
        """Сжатый батч доходит до обработчика в том же виде, что и обычный."""
        db = make_db_mock()
        body = gzip.compress(
            json.dumps(make_batch(connections=[make_connection()])).encode("utf-8")
        )
        with patch.object(collector, "db_service", db), \
             patch.object(collector, "get_node_by_token", AsyncMock(return_value=NODE_UUID)), \
             patch.object(collector, "_enqueue_violation_users", MagicMock()):
            resp = await anon_client.post(
                "/api/v2/collector/batch", content=body, headers=self._gzip_headers(),
            )
        assert resp.status_code == 200
        assert resp.json()["processed"] == 1
        db.batch_upsert_connections.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_malformed_gzip_rejected(self, anon_client):
        """Тело, объявленное сжатым, но не сжатое, — явный 400, а не 500."""
        resp = await anon_client.post(
            "/api/v2/collector/batch", content=b"not actually gzip",
            headers=self._gzip_headers(),
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "BAD_ENCODING"

    @pytest.mark.asyncio
    async def test_decompression_bomb_rejected(self, anon_client):
        """Маленькое сжатое тело с гигантской начинкой не должно разворачиваться."""
        body = gzip.compress(b"\0" * (32 * 1024 * 1024))
        assert len(body) < 1024 * 1024  # именно бомба: сжатое мало, распакованное огромно
        resp = await anon_client.post(
            "/api/v2/collector/batch", content=body, headers=self._gzip_headers(),
        )
        assert resp.status_code == 413
        assert resp.json()["code"] == "BODY_TOO_LARGE"

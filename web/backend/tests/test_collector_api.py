"""Tests for the collector API (web/backend/api/v2/collector.py).

Покрывает: аутентификацию агентов, rate limit per node, node_uuid mismatch,
приём батча (метрики/подключения/резолв идентификаторов), кулдаун-логику
batch-пайплайна нарушений, /health и /stats.
"""
from datetime import datetime, timedelta
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

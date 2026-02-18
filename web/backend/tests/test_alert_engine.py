"""Tests for web.backend.core.alert_engine — alert rules, metrics, escalation.

Covers: _SafeDict, OPERATORS, AlertEngine start/stop, _evaluate_rule,
_fire_alert, _collect_metrics.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core.alert_engine import (
    _SafeDict,
    OPERATORS,
    AlertEngine,
)


# ── _SafeDict ──────────────────────────────────────────────────


class TestSafeDict:

    def test_existing_key(self):
        d = _SafeDict({"name": "test"})
        assert d["name"] == "test"

    def test_missing_key_returns_placeholder(self):
        d = _SafeDict({})
        assert d["missing"] == "{missing}"

    def test_format_map_safe(self):
        tpl = "Hello {name}, value is {value}"
        result = tpl.format_map(_SafeDict({"name": "World"}))
        assert result == "Hello World, value is {value}"


# ── OPERATORS ──────────────────────────────────────────────────


class TestOperators:

    def test_gt(self):
        assert OPERATORS["gt"](10, 5) is True
        assert OPERATORS["gt"](5, 10) is False

    def test_gte(self):
        assert OPERATORS["gte"](10, 10) is True
        assert OPERATORS["gte"](9, 10) is False

    def test_lt(self):
        assert OPERATORS["lt"](5, 10) is True
        assert OPERATORS["lt"](10, 5) is False

    def test_lte(self):
        assert OPERATORS["lte"](10, 10) is True
        assert OPERATORS["lte"](11, 10) is False

    def test_eq(self):
        assert OPERATORS["eq"](5, 5) is True
        assert OPERATORS["eq"](5, 6) is False

    def test_neq(self):
        assert OPERATORS["neq"](5, 6) is True
        assert OPERATORS["neq"](5, 5) is False


# ── AlertEngine lifecycle ─────────────────────────────────────


class TestAlertEngineLifecycle:

    async def test_start_and_stop(self):
        engine = AlertEngine()
        await engine.start()
        assert engine._running is True
        assert engine._task is not None
        await engine.stop()
        assert engine._running is False
        assert engine._task is None

    async def test_double_start_is_noop(self):
        engine = AlertEngine()
        await engine.start()
        task1 = engine._task
        await engine.start()
        assert engine._task is task1
        await engine.stop()

    async def test_stop_without_start(self):
        engine = AlertEngine()
        await engine.stop()  # should not raise


# ── _evaluate_rule ────────────────────────────────────────────


class TestEvaluateRule:

    async def test_triggered(self):
        engine = AlertEngine()
        rule = {
            "id": 1, "name": "CPU Alert",
            "metric": "cpu_usage_percent",
            "operator": "gt",
            "threshold": 80,
            "cooldown_minutes": 30,
            "last_triggered_at": None,
        }
        metrics = {"cpu_usage_percent": 95}

        with patch.object(engine, "_fire_alert", new_callable=AsyncMock) as mock_fire:
            await engine._evaluate_rule(rule, metrics)

        mock_fire.assert_awaited_once()

    async def test_not_triggered_below_threshold(self):
        engine = AlertEngine()
        rule = {
            "id": 1, "name": "CPU Alert",
            "metric": "cpu_usage_percent",
            "operator": "gt",
            "threshold": 80,
        }
        metrics = {"cpu_usage_percent": 50}

        with patch.object(engine, "_fire_alert", new_callable=AsyncMock) as mock_fire:
            await engine._evaluate_rule(rule, metrics)

        mock_fire.assert_not_awaited()

    async def test_cooldown_prevents_firing(self):
        engine = AlertEngine()
        rule = {
            "id": 1, "name": "CPU Alert",
            "metric": "cpu_usage_percent",
            "operator": "gt",
            "threshold": 80,
            "cooldown_minutes": 30,
            "last_triggered_at": datetime.now(timezone.utc) - timedelta(minutes=5),
        }
        metrics = {"cpu_usage_percent": 95}

        with patch.object(engine, "_fire_alert", new_callable=AsyncMock) as mock_fire:
            await engine._evaluate_rule(rule, metrics)

        mock_fire.assert_not_awaited()

    async def test_cooldown_expired_allows_firing(self):
        engine = AlertEngine()
        rule = {
            "id": 1, "name": "Alert",
            "metric": "cpu_usage_percent",
            "operator": "gte",
            "threshold": 90,
            "cooldown_minutes": 30,
            "last_triggered_at": datetime.now(timezone.utc) - timedelta(minutes=31),
        }
        metrics = {"cpu_usage_percent": 95}

        with patch.object(engine, "_fire_alert", new_callable=AsyncMock) as mock_fire:
            await engine._evaluate_rule(rule, metrics)

        mock_fire.assert_awaited_once()

    async def test_missing_metric_skips(self):
        engine = AlertEngine()
        rule = {
            "id": 1, "name": "Alert",
            "metric": "nonexistent",
            "operator": "gt",
            "threshold": 0,
        }
        metrics = {"cpu_usage_percent": 95}

        with patch.object(engine, "_fire_alert", new_callable=AsyncMock) as mock_fire:
            await engine._evaluate_rule(rule, metrics)

        mock_fire.assert_not_awaited()

    async def test_missing_required_fields_skips(self):
        engine = AlertEngine()
        # No metric field
        rule = {"id": 1, "name": "Alert", "operator": "gt", "threshold": 0}
        with patch.object(engine, "_fire_alert", new_callable=AsyncMock) as mock_fire:
            await engine._evaluate_rule(rule, {})
        mock_fire.assert_not_awaited()

    async def test_unknown_operator_skips(self):
        engine = AlertEngine()
        rule = {
            "id": 1, "name": "Alert",
            "metric": "cpu_usage_percent",
            "operator": "INVALID",
            "threshold": 0,
        }
        metrics = {"cpu_usage_percent": 50}

        with patch.object(engine, "_fire_alert", new_callable=AsyncMock) as mock_fire:
            await engine._evaluate_rule(rule, metrics)

        mock_fire.assert_not_awaited()

    async def test_last_triggered_as_string(self):
        engine = AlertEngine()
        rule = {
            "id": 1, "name": "Alert",
            "metric": "cpu_usage_percent",
            "operator": "gt",
            "threshold": 80,
            "cooldown_minutes": 5,
            "last_triggered_at": datetime.now(timezone.utc) - timedelta(minutes=1),
        }
        metrics = {"cpu_usage_percent": 95}

        with patch.object(engine, "_fire_alert", new_callable=AsyncMock) as mock_fire:
            await engine._evaluate_rule(rule, metrics)

        mock_fire.assert_not_awaited()


# ── _fire_alert ───────────────────────────────────────────────


class TestFireAlert:

    async def test_creates_notification_and_logs(self):
        engine = AlertEngine()
        rule = {
            "id": 1, "name": "CPU High",
            "metric": "cpu_usage_percent",
            "operator": "gt",
            "threshold": 80,
            "severity": "critical",
            "channels": '["in_app","telegram"]',
            "title_template": None,
            "body_template": None,
            "group_key": None,
            "escalation_admin_id": None,
            "escalation_minutes": 0,
        }
        metrics = {"cpu_usage_percent": 95, "offline_nodes": []}

        conn = AsyncMock()
        conn.execute = AsyncMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        db = MagicMock()
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.create_notification",
                   new_callable=AsyncMock, return_value=1) as mock_notify:
            await engine._fire_alert(rule, 95.0, metrics)

        mock_notify.assert_awaited_once()
        assert conn.execute.await_count == 2  # log + update

    async def test_custom_templates(self):
        engine = AlertEngine()
        rule = {
            "id": 2, "name": "Disk Full",
            "metric": "disk_usage_percent",
            "operator": "gte",
            "threshold": 90,
            "severity": "warning",
            "channels": ["in_app"],
            "title_template": "DISK: {rule_name}",
            "body_template": "Disk at {value}%",
            "group_key": "disk_alert",
            "escalation_admin_id": None,
            "escalation_minutes": 0,
        }
        metrics = {"disk_usage_percent": 95, "offline_nodes": []}

        conn = AsyncMock()
        conn.execute = AsyncMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        db = MagicMock()
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.create_notification",
                   new_callable=AsyncMock) as mock_notify:
            await engine._fire_alert(rule, 95.0, metrics)

        call_kwargs = mock_notify.call_args.kwargs
        assert "DISK:" in call_kwargs["title"]
        assert "95.0" in call_kwargs["body"]

    async def test_escalation_scheduled(self):
        engine = AlertEngine()
        rule = {
            "id": 3, "name": "Alert",
            "metric": "cpu_usage_percent",
            "operator": "gt",
            "threshold": 80,
            "severity": "critical",
            "channels": ["in_app"],
            "title_template": None,
            "body_template": None,
            "group_key": None,
            "escalation_admin_id": 5,
            "escalation_minutes": 10,
        }
        metrics = {"offline_nodes": []}

        conn = AsyncMock()
        conn.execute = AsyncMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        db = MagicMock()
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.create_notification",
                   new_callable=AsyncMock), \
             patch("web.backend.core.alert_engine.asyncio.create_task") as mock_task:
            await engine._fire_alert(rule, 95.0, metrics)

        mock_task.assert_called_once()


# ── _collect_metrics ──────────────────────────────────────────


class TestCollectMetrics:

    async def test_collects_node_metrics(self):
        engine = AlertEngine()
        node_rows = [
            {
                "uuid": "n1", "name": "Node-EU", "is_connected": True,
                "is_disabled": False, "cpu_usage": 45.0, "memory_usage": 60.0,
                "disk_usage": 30.0, "traffic_used_bytes": 1000, "metrics_updated_at": None,
            }
        ]
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=node_rows)
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        db = MagicMock()
        db.is_connected = True
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.api_helper.fetch_nodes_from_api",
                   new_callable=AsyncMock, return_value=[]):
            metrics = await engine._collect_metrics()

        assert metrics["cpu_usage_percent"] == 45.0
        assert metrics["ram_usage_percent"] == 60.0
        assert metrics["disk_usage_percent"] == 30.0

    async def test_offline_node_tracking(self):
        engine = AlertEngine()
        last_update = datetime.now(timezone.utc) - timedelta(minutes=10)
        node_rows = [
            {
                "uuid": "n1", "name": "Node-Offline", "is_connected": False,
                "is_disabled": False, "cpu_usage": 0, "memory_usage": 0,
                "disk_usage": 0, "traffic_used_bytes": 0,
                "metrics_updated_at": last_update,
            }
        ]
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=node_rows)
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        db = MagicMock()
        db.is_connected = True
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.api_helper.fetch_nodes_from_api",
                   new_callable=AsyncMock, return_value=[]):
            metrics = await engine._collect_metrics()

        assert len(metrics["offline_nodes"]) == 1
        assert metrics["node_offline_minutes"] > 0

    async def test_handles_db_error(self):
        engine = AlertEngine()
        db = MagicMock()
        db.is_connected = True
        db.acquire.side_effect = Exception("DB fail")

        with patch("shared.database.db_service", db):
            metrics = await engine._collect_metrics()

        assert isinstance(metrics, dict)


# ── _check_rules ──────────────────────────────────────────────


class TestCheckRules:

    async def test_no_rules(self):
        engine = AlertEngine()
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        db = MagicMock()
        db.is_connected = True
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db):
            await engine._check_rules()  # should not raise

    async def test_evaluates_rules(self):
        engine = AlertEngine()
        rule = {"id": 1, "name": "Test", "metric": "cpu_usage_percent",
                "operator": "gt", "threshold": 80, "rule_type": "threshold"}
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[rule])
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        db = MagicMock()
        db.is_connected = True
        db.acquire.return_value = cm

        with patch("shared.database.db_service", db), \
             patch.object(engine, "_collect_metrics", new_callable=AsyncMock, return_value={}), \
             patch.object(engine, "_evaluate_rule", new_callable=AsyncMock) as mock_eval:
            await engine._check_rules()

        mock_eval.assert_awaited_once()

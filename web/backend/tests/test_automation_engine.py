"""Tests for web.backend.core.automation_engine — CRON parser, conditions, target inference."""
import time
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from web.backend.core.automation_engine import (
    _parse_cron_field,
    cron_matches_now,
    AutomationEngine,
)


class TestParseCronField:
    """CRON field parsing."""

    def test_wildcard(self):
        result = _parse_cron_field("*", 0, 59)
        assert result == set(range(0, 60))

    def test_single_value(self):
        result = _parse_cron_field("5", 0, 59)
        assert result == {5}

    def test_range(self):
        result = _parse_cron_field("1-5", 0, 59)
        assert result == {1, 2, 3, 4, 5}

    def test_step(self):
        result = _parse_cron_field("*/15", 0, 59)
        assert result == {0, 15, 30, 45}

    def test_step_from_base(self):
        result = _parse_cron_field("5/10", 0, 59)
        assert result == {5, 15, 25, 35, 45, 55}

    def test_list(self):
        result = _parse_cron_field("1,3,5,7", 0, 59)
        assert result == {1, 3, 5, 7}

    def test_combined(self):
        result = _parse_cron_field("1-3,10,*/20", 0, 59)
        assert 1 in result
        assert 2 in result
        assert 3 in result
        assert 10 in result
        assert 0 in result
        assert 20 in result
        assert 40 in result

    def test_hour_range(self):
        result = _parse_cron_field("9-17", 0, 23)
        assert result == set(range(9, 18))

    def test_day_of_week(self):
        result = _parse_cron_field("1-5", 0, 6)
        assert result == {1, 2, 3, 4, 5}


class TestCronMatchesNow:
    """CRON expression matching against current time."""

    def test_every_minute(self):
        assert cron_matches_now("* * * * *")

    def test_invalid_format(self):
        assert not cron_matches_now("* * *")  # only 3 parts

    def test_invalid_expression(self):
        assert not cron_matches_now("bad cron expression here now")

    @patch("web.backend.core.automation_engine.datetime")
    def test_specific_minute(self, mock_dt):
        mock_now = datetime(2026, 2, 11, 10, 30, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        # 30th minute, 10th hour
        assert cron_matches_now("30 10 * * *")
        assert not cron_matches_now("0 10 * * *")

    @patch("web.backend.core.automation_engine.datetime")
    def test_specific_hour(self, mock_dt):
        mock_now = datetime(2026, 2, 11, 14, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert cron_matches_now("0 14 * * *")
        assert not cron_matches_now("0 15 * * *")


class TestConditionEvaluation:
    """AutomationEngine._evaluate_conditions."""

    def setup_method(self):
        self.engine = AutomationEngine()

    def test_no_conditions_passes(self):
        rule = {"conditions": []}
        assert self.engine._evaluate_conditions(rule, {"key": "value"})

    def test_missing_conditions_key(self):
        assert self.engine._evaluate_conditions({}, {"key": "value"})

    def test_equal_condition(self):
        rule = {"conditions": [{"field": "status", "operator": "==", "value": "active"}]}
        assert self.engine._evaluate_conditions(rule, {"status": "active"})
        assert not self.engine._evaluate_conditions(rule, {"status": "disabled"})

    def test_not_equal_condition(self):
        rule = {"conditions": [{"field": "status", "operator": "!=", "value": "disabled"}]}
        assert self.engine._evaluate_conditions(rule, {"status": "active"})
        assert not self.engine._evaluate_conditions(rule, {"status": "disabled"})

    def test_greater_than(self):
        rule = {"conditions": [{"field": "score", "operator": ">", "value": 50}]}
        assert self.engine._evaluate_conditions(rule, {"score": 80})
        assert not self.engine._evaluate_conditions(rule, {"score": 30})

    def test_greater_equal(self):
        rule = {"conditions": [{"field": "score", "operator": ">=", "value": 50}]}
        assert self.engine._evaluate_conditions(rule, {"score": 50})
        assert not self.engine._evaluate_conditions(rule, {"score": 49})

    def test_less_than(self):
        rule = {"conditions": [{"field": "count", "operator": "<", "value": 10}]}
        assert self.engine._evaluate_conditions(rule, {"count": 5})
        assert not self.engine._evaluate_conditions(rule, {"count": 15})

    def test_less_equal(self):
        rule = {"conditions": [{"field": "count", "operator": "<=", "value": 10}]}
        assert self.engine._evaluate_conditions(rule, {"count": 10})
        assert not self.engine._evaluate_conditions(rule, {"count": 11})

    def test_contains(self):
        rule = {"conditions": [{"field": "name", "operator": "contains", "value": "test"}]}
        assert self.engine._evaluate_conditions(rule, {"name": "this is a test"})
        assert not self.engine._evaluate_conditions(rule, {"name": "no match"})

    def test_not_contains(self):
        rule = {"conditions": [{"field": "name", "operator": "not_contains", "value": "bad"}]}
        assert self.engine._evaluate_conditions(rule, {"name": "good thing"})
        assert not self.engine._evaluate_conditions(rule, {"name": "bad thing"})

    def test_missing_field_fails(self):
        rule = {"conditions": [{"field": "nonexistent", "operator": "==", "value": "x"}]}
        assert not self.engine._evaluate_conditions(rule, {"other": "x"})

    def test_multiple_conditions_all_must_pass(self):
        rule = {"conditions": [
            {"field": "score", "operator": ">=", "value": 50},
            {"field": "status", "operator": "==", "value": "active"},
        ]}
        assert self.engine._evaluate_conditions(
            rule, {"score": 60, "status": "active"}
        )
        assert not self.engine._evaluate_conditions(
            rule, {"score": 60, "status": "disabled"}
        )
        assert not self.engine._evaluate_conditions(
            rule, {"score": 30, "status": "active"}
        )

    def test_conditions_as_json_string(self):
        import json
        rule = {"conditions": json.dumps([
            {"field": "x", "operator": "==", "value": 1}
        ])}
        assert self.engine._evaluate_conditions(rule, {"x": 1})

    def test_unknown_operator(self):
        rule = {"conditions": [{"field": "x", "operator": "INVALID", "value": 1}]}
        assert not self.engine._evaluate_conditions(rule, {"x": 1})


class TestTargetInference:
    """AutomationEngine._infer_target_type."""

    def test_user_event(self):
        assert AutomationEngine._infer_target_type("user.traffic_exceeded") == "user"

    def test_node_event(self):
        assert AutomationEngine._infer_target_type("node.went_offline") == "node"

    def test_violation_event(self):
        assert AutomationEngine._infer_target_type("violation.detected") == "user"

    def test_unknown_event(self):
        assert AutomationEngine._infer_target_type("something.else") == "system"

    def test_system_event(self):
        assert AutomationEngine._infer_target_type("system.health") == "system"


class TestEngineStartStop:
    """Engine lifecycle."""

    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        engine = AutomationEngine()
        await engine.start()
        assert engine._running
        await engine.stop()
        assert not engine._running

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self):
        engine = AutomationEngine()
        await engine.start()
        task1 = engine._schedule_task
        await engine.start()  # should be no-op
        assert engine._schedule_task is task1
        await engine.stop()

    @pytest.mark.asyncio
    async def test_stop_without_start(self):
        engine = AutomationEngine()
        await engine.stop()  # should not raise
        assert not engine._running

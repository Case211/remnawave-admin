"""Extended tests for web.backend.core.automation_engine.

Covers: handle_event, _process_event_rule, _execute_action action handlers,
dry_run, _check_scheduled_rules interval logic.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core.automation_engine import AutomationEngine


# ── handle_event ──────────────────────────────────────────────


class TestHandleEvent:

    async def test_dispatches_to_matching_rules(self):
        engine = AutomationEngine()
        rule = {
            "id": 1, "name": "Block sharers",
            "trigger_config": json.dumps({"event": "violation.detected", "min_score": 80}),
            "conditions": "[]",
            "action_type": "block_user",
            "action_config": json.dumps({"reason": "sharing"}),
        }

        with patch("web.backend.core.automation.get_enabled_event_rules",
                    new_callable=AsyncMock, return_value=[rule]), \
             patch.object(engine, "_process_event_rule", new_callable=AsyncMock) as mock_process:
            await engine.handle_event("violation.detected", {"score": 90, "user_uuid": "u1"})

        mock_process.assert_awaited_once()

    async def test_no_matching_rules(self):
        engine = AutomationEngine()
        with patch("web.backend.core.automation.get_enabled_event_rules",
                    new_callable=AsyncMock, return_value=[]):
            await engine.handle_event("violation.detected", {})

    async def test_handles_rule_error(self):
        engine = AutomationEngine()
        rule = {"id": 1, "name": "Bad rule"}

        with patch("web.backend.core.automation.get_enabled_event_rules",
                    new_callable=AsyncMock, return_value=[rule]), \
             patch.object(engine, "_process_event_rule",
                          new_callable=AsyncMock, side_effect=Exception("err")):
            await engine.handle_event("violation.detected", {})  # should not raise


# ── _process_event_rule ──────────────────────────────────────


class TestProcessEventRule:

    async def test_skips_low_score(self):
        engine = AutomationEngine()
        rule = {
            "id": 1, "name": "R",
            "trigger_config": {"event": "violation.detected", "min_score": 80},
            "conditions": [],
            "action_type": "block_user",
            "action_config": {},
        }

        with patch("web.backend.core.automation.try_acquire_trigger",
                    new_callable=AsyncMock) as mock_acquire:
            await engine._process_event_rule(rule, "violation.detected", {"score": 50})

        mock_acquire.assert_not_awaited()

    async def test_skips_insufficient_offline_minutes(self):
        engine = AutomationEngine()
        rule = {
            "id": 1, "name": "R",
            "trigger_config": {"event": "node.went_offline", "offline_minutes": 15},
            "conditions": [],
            "action_type": "restart_node",
            "action_config": {},
        }

        with patch("web.backend.core.automation.try_acquire_trigger",
                    new_callable=AsyncMock) as mock_acquire:
            await engine._process_event_rule(
                rule, "node.went_offline", {"offline_minutes": 3},
            )

        mock_acquire.assert_not_awaited()

    async def test_skips_failed_conditions(self):
        engine = AutomationEngine()
        rule = {
            "id": 1, "name": "R",
            "trigger_config": {"event": "violation.detected"},
            "conditions": [{"field": "score", "operator": ">=", "value": 80}],
            "action_type": "block_user",
            "action_config": {},
        }

        with patch("web.backend.core.automation.try_acquire_trigger",
                    new_callable=AsyncMock) as mock_acquire:
            await engine._process_event_rule(
                rule, "violation.detected", {"score": 30},
            )

        mock_acquire.assert_not_awaited()

    async def test_skips_when_trigger_not_acquired(self):
        engine = AutomationEngine()
        rule = {
            "id": 1, "name": "R",
            "trigger_config": {"event": "violation.detected"},
            "conditions": [],
            "action_type": "block_user",
            "action_config": {},
        }

        with patch("web.backend.core.automation.try_acquire_trigger",
                    new_callable=AsyncMock, return_value=False), \
             patch.object(engine, "_execute_action", new_callable=AsyncMock) as mock_exec:
            await engine._process_event_rule(
                rule, "violation.detected", {"score": 90},
            )

        mock_exec.assert_not_awaited()

    async def test_executes_and_logs(self):
        engine = AutomationEngine()
        rule = {
            "id": 1, "name": "R",
            "trigger_config": {"event": "violation.detected"},
            "conditions": [],
            "action_type": "block_user",
            "action_config": {},
        }

        with patch("web.backend.core.automation.try_acquire_trigger",
                    new_callable=AsyncMock, return_value=True), \
             patch("web.backend.core.automation.write_automation_log",
                    new_callable=AsyncMock) as mock_log, \
             patch.object(engine, "_execute_action",
                          new_callable=AsyncMock, return_value=("success", {})):
            await engine._process_event_rule(
                rule, "violation.detected", {"user_uuid": "u1", "score": 90},
            )

        mock_log.assert_awaited_once()

    async def test_trigger_config_as_json_string(self):
        engine = AutomationEngine()
        rule = {
            "id": 1, "name": "R",
            "trigger_config": json.dumps({"event": "violation.detected", "min_score": 80}),
            "conditions": [],
            "action_type": "block_user",
            "action_config": {},
        }

        with patch("web.backend.core.automation.try_acquire_trigger",
                    new_callable=AsyncMock, return_value=True), \
             patch("web.backend.core.automation.write_automation_log",
                    new_callable=AsyncMock), \
             patch.object(engine, "_execute_action",
                          new_callable=AsyncMock, return_value=("success", {})):
            await engine._process_event_rule(
                rule, "violation.detected", {"score": 90, "user_uuid": "u1"},
            )


# ── _execute_action ──────────────────────────────────────────


class TestExecuteAction:

    async def test_unknown_action_type(self):
        engine = AutomationEngine()
        rule = {"action_type": "nonexistent", "action_config": {}}
        result, details = await engine._execute_action(rule, "user", "u1", {})
        assert result == "error"
        assert "Unknown action type" in details["error"]

    async def test_action_config_as_json_string(self):
        engine = AutomationEngine()
        rule = {
            "action_type": "notify",
            "action_config": json.dumps({"channel": "telegram", "message": "Test"}),
        }

        with patch.object(engine, "_action_notify",
                          new_callable=AsyncMock, return_value={"sent": True}):
            result, details = await engine._execute_action(rule, "user", "u1", {})

        assert result == "success"

    async def test_action_exception(self):
        engine = AutomationEngine()
        rule = {"id": 1, "action_type": "block_user", "action_config": {}}

        with patch.object(engine, "_action_block_user",
                          new_callable=AsyncMock, side_effect=Exception("API down")):
            result, details = await engine._execute_action(rule, "user", "u1", {})

        assert result == "error"
        assert "API down" in details["error"]


# ── Individual action handlers ────────────────────────────────


class TestActionNotify:

    async def test_telegram_notify(self):
        engine = AutomationEngine()
        config = {"channel": "telegram", "message": "User {username} blocked"}

        with patch("web.backend.core.notifier._send_telegram_message",
                    new_callable=AsyncMock, return_value=True) as mock_send, \
             patch("web.backend.core.notifier._esc", side_effect=lambda x: x):
            result = await engine._action_notify(
                config, "user", "u1", {"username": "alice"},
            )

        assert result["channel"] == "telegram"
        assert result["sent"] is True

    async def test_webhook_notify(self):
        engine = AutomationEngine()
        config = {
            "channel": "webhook",
            "webhook_url": "https://example.com/hook",
            "message": "Test",
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("web.backend.core.automation_engine.httpx.AsyncClient",
                    return_value=mock_client):
            result = await engine._action_notify(config, "system", None, {})

        assert result["channel"] == "webhook"
        assert result["status"] == 200

    async def test_webhook_no_url(self):
        engine = AutomationEngine()
        config = {"channel": "webhook", "message": "Test"}

        result = await engine._action_notify(config, "system", None, {})
        assert "error" in result

    async def test_unknown_channel(self):
        engine = AutomationEngine()
        config = {"channel": "sms", "message": "Test"}

        result = await engine._action_notify(config, "system", None, {})
        assert "error" in result


class TestActionDisableUser:

    async def test_disables_user(self):
        engine = AutomationEngine()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("web.backend.core.api_helper._get_client",
                    return_value=mock_client):
            result = await engine._action_disable_user({}, "user", "u1", {})

        assert result["action"] == "disable_user"
        assert result["user_uuid"] == "u1"

    async def test_no_target_raises(self):
        engine = AutomationEngine()
        with pytest.raises(ValueError, match="No target user"):
            await engine._action_disable_user({}, "user", None, {})


class TestActionBlockUser:

    async def test_blocks_user(self):
        engine = AutomationEngine()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("web.backend.core.api_helper._get_client",
                    return_value=mock_client):
            result = await engine._action_block_user(
                {"reason": "sharing"}, "user", "u1", {},
            )

        assert result["action"] == "block_user"
        assert result["reason"] == "sharing"


class TestActionResetTraffic:

    async def test_resets_traffic(self):
        engine = AutomationEngine()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("web.backend.core.api_helper._get_client",
                    return_value=mock_client):
            result = await engine._action_reset_traffic({}, "user", "u1", {})

        assert result["action"] == "reset_traffic"

    async def test_no_target_raises(self):
        engine = AutomationEngine()
        with pytest.raises(ValueError, match="No target user"):
            await engine._action_reset_traffic({}, "user", None, {})


class TestActionForceSync:

    async def test_syncs(self):
        engine = AutomationEngine()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("web.backend.core.api_helper._get_client",
                    return_value=mock_client):
            result = await engine._action_force_sync({}, "system", None, {})

        assert result["action"] == "force_sync"


# ── dry_run ──────────────────────────────────────────────────


class TestDryRun:

    async def test_rule_not_found(self):
        engine = AutomationEngine()
        with patch("web.backend.core.automation.get_automation_rule_by_id",
                    new_callable=AsyncMock, return_value=None):
            result = await engine.dry_run(999)

        assert result["would_trigger"] is False
        assert "не найдено" in result["details"]

    async def test_event_trigger(self):
        engine = AutomationEngine()
        rule = {
            "id": 1, "trigger_type": "event",
            "trigger_config": {"event": "violation.detected"},
            "action_type": "block_user",
        }
        with patch("web.backend.core.automation.get_automation_rule_by_id",
                    new_callable=AsyncMock, return_value=rule):
            result = await engine.dry_run(1)

        assert result["would_trigger"] is True
        assert "событию" in result["details"]

    async def test_schedule_trigger_with_cron(self):
        engine = AutomationEngine()
        rule = {
            "id": 2, "trigger_type": "schedule",
            "trigger_config": {"cron": "* * * * *"},
            "action_type": "notify",
        }
        with patch("web.backend.core.automation.get_automation_rule_by_id",
                    new_callable=AsyncMock, return_value=rule):
            result = await engine.dry_run(2)

        assert result["would_trigger"] is True
        assert "CRON" in result["details"]

    async def test_schedule_trigger_with_interval(self):
        engine = AutomationEngine()
        rule = {
            "id": 3, "trigger_type": "schedule",
            "trigger_config": {"interval_minutes": 5},
            "last_triggered_at": None,
            "action_type": "notify",
        }
        with patch("web.backend.core.automation.get_automation_rule_by_id",
                    new_callable=AsyncMock, return_value=rule):
            result = await engine.dry_run(3)

        assert result["would_trigger"] is True
        assert "Интервал" in result["details"]

    async def test_threshold_trigger_user_traffic(self):
        engine = AutomationEngine()
        rule = {
            "id": 4, "trigger_type": "threshold",
            "trigger_config": {"metric": "user_traffic_percent", "operator": ">=", "value": 90},
            "action_type": "notify",
        }
        users = [
            {"uuid": "u1", "username": "alice", "traffic_limit_bytes": 1000, "used_traffic_bytes": 950},
            {"uuid": "u2", "username": "bob", "traffic_limit_bytes": 1000, "used_traffic_bytes": 100},
        ]
        with patch("web.backend.core.automation.get_automation_rule_by_id",
                    new_callable=AsyncMock, return_value=rule), \
             patch("web.backend.core.api_helper.fetch_users_from_api",
                    new_callable=AsyncMock, return_value=users):
            result = await engine.dry_run(4)

        assert result["would_trigger"] is True
        assert len(result["matching_targets"]) == 1
        assert result["matching_targets"][0]["name"] == "alice"

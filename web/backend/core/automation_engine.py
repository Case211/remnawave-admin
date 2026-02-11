"""Automation Engine — scheduler, event handler, action executor.

Manages three trigger mechanisms:
- Event triggers: fired by hooks in API endpoints and WebSocket handler
- Schedule triggers: CRON and interval-based, checked every 60 seconds
- Threshold triggers: metric-based, checked every 5 minutes

All action execution is logged to the automation_log table.
"""
import asyncio
import json
import logging
import operator as op_module
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# Operator mapping for condition evaluation
_OPERATORS = {
    "==": op_module.eq,
    "!=": op_module.ne,
    ">": op_module.gt,
    ">=": op_module.ge,
    "<": op_module.lt,
    "<=": op_module.le,
    "contains": lambda a, b: str(b) in str(a),
    "not_contains": lambda a, b: str(b) not in str(a),
}


def _parse_cron_field(field: str, min_val: int, max_val: int) -> set:
    """Parse a single CRON field into a set of matching integers."""
    values = set()
    for part in field.split(","):
        part = part.strip()
        if part == "*":
            values.update(range(min_val, max_val + 1))
        elif "/" in part:
            base, step = part.split("/", 1)
            step = int(step)
            start = min_val if base == "*" else int(base)
            values.update(range(start, max_val + 1, step))
        elif "-" in part:
            lo, hi = part.split("-", 1)
            values.update(range(int(lo), int(hi) + 1))
        else:
            values.add(int(part))
    return values


def cron_matches_now(cron_expr: str) -> bool:
    """Check if a CRON expression matches the current minute.

    Supports: minute hour day-of-month month day-of-week
    With *, ranges (1-5), steps (*/5), and lists (1,3,5).
    """
    try:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            logger.warning("Invalid CRON expression (expected 5 parts): %s", cron_expr)
            return False

        now = datetime.now(timezone.utc)
        minute_set = _parse_cron_field(parts[0], 0, 59)
        hour_set = _parse_cron_field(parts[1], 0, 23)
        dom_set = _parse_cron_field(parts[2], 1, 31)
        month_set = _parse_cron_field(parts[3], 1, 12)
        dow_set = _parse_cron_field(parts[4], 0, 6)

        # Convert Python weekday (Mon=0..Sun=6) to CRON weekday (Sun=0..Sat=6)
        cron_dow = (now.weekday() + 1) % 7

        return (
            now.minute in minute_set
            and now.hour in hour_set
            and now.day in dom_set
            and now.month in month_set
            and cron_dow in dow_set
        )
    except Exception as e:
        logger.warning("CRON parse error for '%s': %s", cron_expr, e)
        return False


class AutomationEngine:
    """Singleton engine that manages event triggers, scheduled tasks, and threshold checks."""

    def __init__(self):
        self._running = False
        self._schedule_task: Optional[asyncio.Task] = None
        self._threshold_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the scheduler and threshold loops."""
        if self._running:
            return
        self._running = True
        self._schedule_task = asyncio.create_task(self._schedule_loop())
        self._threshold_task = asyncio.create_task(self._threshold_loop())
        logger.info("Automation engine started")

    async def stop(self):
        """Stop all background tasks."""
        self._running = False
        for task in (self._schedule_task, self._threshold_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._schedule_task = None
        self._threshold_task = None
        logger.info("Automation engine stopped")

    # ── Event triggers ───────────────────────────────────────

    async def handle_event(self, event_type: str, payload: dict) -> None:
        """Handle an event from API endpoints or WebSocket handler.

        Finds matching enabled rules and evaluates/executes them.
        """
        try:
            from web.backend.core.automation import get_enabled_event_rules
            rules = await get_enabled_event_rules(event_type)

            for rule in rules:
                try:
                    await self._process_event_rule(rule, event_type, payload)
                except Exception as e:
                    logger.error(
                        "Error processing event rule %d (%s): %s",
                        rule["id"], rule["name"], e,
                    )
        except Exception as e:
            logger.error("Error handling event %s: %s", event_type, e)

    async def _process_event_rule(self, rule: dict, event_type: str, payload: dict) -> None:
        """Process a single event-type rule."""
        from web.backend.core.automation import try_acquire_trigger, write_automation_log

        trigger_config = rule.get("trigger_config", {})
        if isinstance(trigger_config, str):
            trigger_config = json.loads(trigger_config)

        # Check min_score for violation events
        min_score = trigger_config.get("min_score")
        if min_score is not None:
            score = payload.get("score", 0)
            if score < min_score:
                return

        # Check offline_minutes for node events
        offline_minutes = trigger_config.get("offline_minutes")
        if offline_minutes is not None:
            actual_offline = payload.get("offline_minutes", 0)
            if actual_offline < offline_minutes:
                return

        # Evaluate conditions
        if not self._evaluate_conditions(rule, payload):
            return

        # Acquire trigger lock (prevent double-firing within 30s)
        if not await try_acquire_trigger(rule["id"], min_interval_seconds=30):
            return

        # Determine target
        target_type = self._infer_target_type(event_type)
        target_id = (
            payload.get("user_uuid")
            or payload.get("node_uuid")
            or payload.get("uuid")
            or str(payload.get("id", ""))
        )

        # Execute action
        result, details = await self._execute_action(rule, target_type, target_id, payload)

        # Log
        await write_automation_log(
            rule_id=rule["id"],
            target_type=target_type,
            target_id=target_id,
            action_taken=rule["action_type"],
            result=result,
            details=details,
        )

    # ── Schedule loop ────────────────────────────────────────

    async def _schedule_loop(self):
        """Check schedule-type rules every 60 seconds."""
        while self._running:
            try:
                await asyncio.sleep(60)
                if not self._running:
                    break
                await self._check_scheduled_rules()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Schedule loop error: %s", e)

    async def _check_scheduled_rules(self):
        """Evaluate all enabled schedule-type rules."""
        from web.backend.core.automation import (
            get_enabled_rules_by_trigger_type,
            try_acquire_trigger,
            write_automation_log,
        )

        rules = await get_enabled_rules_by_trigger_type("schedule")

        for rule in rules:
            try:
                trigger_config = rule.get("trigger_config", {})
                if isinstance(trigger_config, str):
                    trigger_config = json.loads(trigger_config)

                should_fire = False

                # CRON expression
                cron = trigger_config.get("cron")
                if cron:
                    should_fire = cron_matches_now(cron)

                # Interval minutes
                interval = trigger_config.get("interval_minutes")
                if interval and not should_fire:
                    last = rule.get("last_triggered_at")
                    if last is None:
                        should_fire = True
                    else:
                        if isinstance(last, str):
                            last = datetime.fromisoformat(last)
                        if last.tzinfo is None:
                            last = last.replace(tzinfo=timezone.utc)
                        elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 60
                        should_fire = elapsed >= interval

                if not should_fire:
                    continue

                # Acquire trigger lock
                min_interval = max(55, (interval or 1) * 60 - 10) if interval else 55
                if not await try_acquire_trigger(rule["id"], min_interval_seconds=min_interval):
                    continue

                # Execute action
                context = {"trigger": "schedule", "cron": cron, "interval_minutes": interval}
                result, details = await self._execute_action(rule, "system", None, context)

                await write_automation_log(
                    rule_id=rule["id"],
                    target_type="system",
                    target_id=None,
                    action_taken=rule["action_type"],
                    result=result,
                    details=details,
                )
            except Exception as e:
                logger.error("Error checking schedule rule %d: %s", rule.get("id"), e)

    # ── Threshold loop ───────────────────────────────────────

    async def _threshold_loop(self):
        """Check threshold-type rules every 5 minutes."""
        while self._running:
            try:
                await asyncio.sleep(300)
                if not self._running:
                    break
                await self._check_threshold_rules()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Threshold loop error: %s", e)

    async def _check_threshold_rules(self):
        """Evaluate all enabled threshold-type rules."""
        from web.backend.core.automation import (
            get_enabled_rules_by_trigger_type,
            try_acquire_trigger,
            write_automation_log,
        )
        from web.backend.core.api_helper import fetch_users_from_api, fetch_nodes_from_api

        rules = await get_enabled_rules_by_trigger_type("threshold")
        if not rules:
            return

        # Pre-fetch data for threshold evaluation
        users = None
        nodes = None

        for rule in rules:
            try:
                trigger_config = rule.get("trigger_config", {})
                if isinstance(trigger_config, str):
                    trigger_config = json.loads(trigger_config)

                metric = trigger_config.get("metric", "")
                operator_str = trigger_config.get("operator", ">=")
                threshold_value = trigger_config.get("value", 0)

                op_fn = _OPERATORS.get(operator_str)
                if not op_fn:
                    continue

                targets = []

                # Evaluate metric against data
                if metric == "users_online":
                    if nodes is None:
                        nodes = await fetch_nodes_from_api()
                    total_online = sum(n.get("users_online", 0) for n in nodes)
                    if op_fn(total_online, threshold_value):
                        targets.append(("system", None, {"users_online": total_online}))

                elif metric == "traffic_today":
                    if nodes is None:
                        nodes = await fetch_nodes_from_api()
                    total_traffic = sum(n.get("traffic_today_bytes", 0) for n in nodes)
                    total_gb = total_traffic / (1024 ** 3)
                    if op_fn(total_gb, threshold_value):
                        targets.append(("system", None, {"traffic_today_gb": round(total_gb, 2)}))

                elif metric == "node_uptime_percent":
                    if nodes is None:
                        nodes = await fetch_nodes_from_api()
                    for node in nodes:
                        is_connected = node.get("is_connected", False)
                        uptime = 100 if is_connected else 0
                        if op_fn(uptime, threshold_value):
                            targets.append((
                                "node",
                                node.get("uuid", str(node.get("id", ""))),
                                {"node_name": node.get("name", ""), "uptime": uptime},
                            ))

                elif metric == "user_traffic_percent":
                    if users is None:
                        users = await fetch_users_from_api()
                    for user in users:
                        limit = user.get("traffic_limit_bytes", 0)
                        if not limit:
                            continue
                        used = user.get("used_traffic_bytes", 0)
                        percent = (used / limit) * 100
                        if op_fn(percent, threshold_value):
                            targets.append((
                                "user",
                                user.get("uuid", user.get("short_uuid", "")),
                                {
                                    "username": user.get("username", ""),
                                    "percent": round(percent, 1),
                                },
                            ))

                if not targets:
                    continue

                # Acquire trigger lock (5-min minimum between threshold triggers)
                if not await try_acquire_trigger(rule["id"], min_interval_seconds=280):
                    continue

                for target_type, target_id, ctx in targets:
                    result, details = await self._execute_action(
                        rule, target_type, target_id, ctx,
                    )
                    await write_automation_log(
                        rule_id=rule["id"],
                        target_type=target_type,
                        target_id=target_id,
                        action_taken=rule["action_type"],
                        result=result,
                        details=details,
                    )

            except Exception as e:
                logger.error("Error checking threshold rule %d: %s", rule.get("id"), e)

    # ── Condition evaluation ─────────────────────────────────

    def _evaluate_conditions(self, rule: dict, context: dict) -> bool:
        """Evaluate the conditions array against context. All conditions must pass."""
        conditions = rule.get("conditions", [])
        if isinstance(conditions, str):
            conditions = json.loads(conditions)

        if not conditions:
            return True

        for cond in conditions:
            field = cond.get("field", "")
            cond_op = cond.get("operator", "==")
            cond_value = cond.get("value")

            actual_value = context.get(field)
            if actual_value is None:
                return False

            op_fn = _OPERATORS.get(cond_op)
            if not op_fn:
                logger.warning("Unknown condition operator: %s", cond_op)
                return False

            try:
                # Try numeric comparison first
                if isinstance(cond_value, (int, float)):
                    actual_value = float(actual_value)
                if not op_fn(actual_value, cond_value):
                    return False
            except (ValueError, TypeError):
                if not op_fn(str(actual_value), str(cond_value)):
                    return False

        return True

    # ── Action execution ─────────────────────────────────────

    async def _execute_action(
        self,
        rule: dict,
        target_type: Optional[str],
        target_id: Optional[str],
        context: dict,
    ) -> Tuple[str, dict]:
        """Execute the action defined in the rule. Returns (result, details)."""
        action_type = rule["action_type"]
        action_config = rule.get("action_config", {})
        if isinstance(action_config, str):
            action_config = json.loads(action_config)

        try:
            handler = {
                "disable_user": self._action_disable_user,
                "block_user": self._action_block_user,
                "notify": self._action_notify,
                "restart_node": self._action_restart_node,
                "cleanup_expired": self._action_cleanup_expired,
                "reset_traffic": self._action_reset_traffic,
                "force_sync": self._action_force_sync,
            }.get(action_type)

            if not handler:
                return "error", {"error": f"Unknown action type: {action_type}"}

            details = await handler(action_config, target_type, target_id, context)
            return "success", details

        except Exception as e:
            logger.error(
                "Action %s failed for rule %d: %s",
                action_type, rule.get("id", 0), e,
            )
            return "error", {"error": str(e)}

    async def _action_disable_user(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Disable a user via Remnawave API."""
        from web.backend.core.api_helper import _get_client
        client = _get_client()
        resp = await client.post(
            f"/api/users/{target_id}/actions/disable",
            json={},
        )
        resp.raise_for_status()
        return {"action": "disable_user", "user_uuid": target_id, "status": resp.status_code}

    async def _action_block_user(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Block a user (disable + mark reason) via Remnawave API."""
        from web.backend.core.api_helper import _get_client
        reason = config.get("reason", "Blocked by automation")
        client = _get_client()
        resp = await client.post(
            f"/api/users/{target_id}/actions/disable",
            json={"reason": reason},
        )
        resp.raise_for_status()
        return {"action": "block_user", "user_uuid": target_id, "reason": reason}

    async def _action_notify(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Send notification via Telegram or webhook."""
        channel = config.get("channel", "telegram")
        message_template = config.get("message", "Automation triggered")

        # Simple template substitution
        message = message_template
        for key, value in context.items():
            message = message.replace(f"{{{key}}}", str(value))

        if channel == "telegram":
            from web.backend.core.notifier import _send_telegram_message, _esc
            text = f"<b>Automation</b>\n\n{_esc(message)}"
            success = await _send_telegram_message(text)
            return {"action": "notify", "channel": "telegram", "sent": success}

        elif channel == "webhook":
            webhook_url = config.get("webhook_url")
            if not webhook_url:
                return {"action": "notify", "channel": "webhook", "error": "No webhook_url configured"}
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json={
                    "event": "automation",
                    "message": message,
                    "target_type": target_type,
                    "target_id": target_id,
                    "context": {k: str(v) for k, v in context.items()},
                })
                return {"action": "notify", "channel": "webhook", "status": resp.status_code}

        return {"action": "notify", "error": f"Unknown channel: {channel}"}

    async def _action_restart_node(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Restart a node via Remnawave API."""
        from web.backend.core.api_helper import _get_client
        client = _get_client()
        resp = await client.post(
            f"/api/nodes/{target_id}/actions/restart",
            json={},
        )
        resp.raise_for_status()
        return {"action": "restart_node", "node_uuid": target_id, "status": resp.status_code}

    async def _action_cleanup_expired(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Disable users whose subscription expired more than N days ago."""
        from web.backend.core.api_helper import fetch_users_from_api, _get_client

        older_than_days = config.get("older_than_days", 30)
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        users = await fetch_users_from_api()

        disabled_count = 0
        client = _get_client()

        for user in users:
            expire_at = user.get("expire_at")
            if not expire_at:
                continue
            try:
                if isinstance(expire_at, str):
                    expire_dt = datetime.fromisoformat(expire_at.replace("Z", "+00:00"))
                else:
                    expire_dt = expire_at
                if expire_dt.tzinfo is None:
                    expire_dt = expire_dt.replace(tzinfo=timezone.utc)

                if expire_dt < cutoff and not user.get("is_disabled", False):
                    uuid = user.get("uuid", user.get("short_uuid", ""))
                    if uuid:
                        try:
                            resp = await client.post(
                                f"/api/users/{uuid}/actions/disable",
                                json={},
                            )
                            if resp.status_code < 400:
                                disabled_count += 1
                        except Exception:
                            pass
            except Exception:
                continue

        return {
            "action": "cleanup_expired",
            "older_than_days": older_than_days,
            "disabled_count": disabled_count,
        }

    async def _action_reset_traffic(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Reset traffic counter for a user via Remnawave API."""
        from web.backend.core.api_helper import _get_client
        client = _get_client()
        resp = await client.post(
            f"/api/users/{target_id}/actions/reset-traffic",
            json={},
        )
        resp.raise_for_status()
        return {"action": "reset_traffic", "user_uuid": target_id, "status": resp.status_code}

    async def _action_force_sync(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Force sync nodes with Remnawave API."""
        from web.backend.core.api_helper import _get_client
        client = _get_client()
        resp = await client.post("/api/nodes/actions/sync", json={})
        resp.raise_for_status()
        return {"action": "force_sync", "status": resp.status_code}

    # ── Dry-run ──────────────────────────────────────────────

    async def dry_run(self, rule_id: int) -> dict:
        """Simulate execution of a rule without performing side effects."""
        from web.backend.core.automation import get_automation_rule_by_id
        from web.backend.core.api_helper import fetch_users_from_api, fetch_nodes_from_api

        rule = await get_automation_rule_by_id(rule_id)
        if not rule:
            return {
                "rule_id": rule_id,
                "would_trigger": False,
                "matching_targets": [],
                "estimated_actions": 0,
                "details": "Правило не найдено",
            }

        trigger_type = rule["trigger_type"]
        trigger_config = rule.get("trigger_config", {})
        if isinstance(trigger_config, str):
            trigger_config = json.loads(trigger_config)

        matching_targets: List[dict] = []
        would_trigger = False
        details_parts = []

        # Localized labels for action types
        _ACTION_LABELS = {
            "disable_user": "Отключить пользователя",
            "block_user": "Заблокировать пользователя",
            "notify": "Отправить уведомление",
            "restart_node": "Перезапустить ноду",
            "cleanup_expired": "Очистить истёкших",
            "reset_traffic": "Сбросить трафик",
            "force_sync": "Синхронизация нод",
        }
        _EVENT_LABELS = {
            "violation.detected": "Обнаружено нарушение",
            "node.went_offline": "Нода ушла офлайн",
            "user.traffic_exceeded": "Трафик превышен",
        }
        _METRIC_LABELS = {
            "users_online": "Пользователей онлайн",
            "traffic_today": "Трафик за сегодня (ГБ)",
            "node_uptime_percent": "Аптайм ноды (%)",
            "user_traffic_percent": "Использование трафика (%)",
        }
        _OPERATOR_LABELS = {
            "==": "=", "!=": "≠", ">": ">", ">=": "≥",
            "<": "<", "<=": "≤", "contains": "содержит", "not_contains": "не содержит",
        }

        if trigger_type == "event":
            event = trigger_config.get("event", "")
            event_label = _EVENT_LABELS.get(event, event)
            details_parts.append(f"Триггер по событию: {event_label}")
            details_parts.append("Сработает при следующем совпадающем событии.")
            would_trigger = True

        elif trigger_type == "schedule":
            cron = trigger_config.get("cron")
            interval = trigger_config.get("interval_minutes")
            if cron:
                would_trigger = cron_matches_now(cron)
                details_parts.append(f"CRON: {cron} — {'совпадает с текущим временем' if would_trigger else 'не совпадает с текущим временем'}")
            elif interval:
                last = rule.get("last_triggered_at")
                if last is None:
                    would_trigger = True
                else:
                    if isinstance(last, str):
                        last = datetime.fromisoformat(last)
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 60
                    would_trigger = elapsed >= interval
                details_parts.append(f"Интервал: каждые {interval} мин.")

        elif trigger_type == "threshold":
            metric = trigger_config.get("metric", "")
            operator_str = trigger_config.get("operator", ">=")
            threshold_value = trigger_config.get("value", 0)
            op_fn = _OPERATORS.get(operator_str)

            if metric == "user_traffic_percent" and op_fn:
                users = await fetch_users_from_api()
                for user in users:
                    limit = user.get("traffic_limit_bytes", 0)
                    if not limit:
                        continue
                    used = user.get("used_traffic_bytes", 0)
                    percent = (used / limit) * 100
                    if op_fn(percent, threshold_value):
                        matching_targets.append({
                            "type": "user",
                            "id": user.get("uuid", ""),
                            "name": user.get("username", ""),
                            "value": round(percent, 1),
                        })

            elif metric in ("users_online", "traffic_today", "node_uptime_percent") and op_fn:
                nodes = await fetch_nodes_from_api()
                if metric == "users_online":
                    total = sum(n.get("users_online", 0) for n in nodes)
                    if op_fn(total, threshold_value):
                        matching_targets.append({"type": "system", "value": total})
                elif metric == "traffic_today":
                    total_gb = sum(n.get("traffic_today_bytes", 0) for n in nodes) / (1024 ** 3)
                    if op_fn(total_gb, threshold_value):
                        matching_targets.append({"type": "system", "value": round(total_gb, 2)})
                elif metric == "node_uptime_percent":
                    for node in nodes:
                        uptime = 100 if node.get("is_connected") else 0
                        if op_fn(uptime, threshold_value):
                            matching_targets.append({
                                "type": "node",
                                "id": node.get("uuid", ""),
                                "name": node.get("name", ""),
                                "value": uptime,
                            })

            would_trigger = len(matching_targets) > 0
            metric_label = _METRIC_LABELS.get(metric, metric)
            op_label = _OPERATOR_LABELS.get(operator_str, operator_str)
            details_parts.append(f"Порог: {metric_label} {op_label} {threshold_value}")

        action_label = _ACTION_LABELS.get(rule['action_type'], rule['action_type'])
        details_parts.append(f"Действие: {action_label}")
        if matching_targets:
            details_parts.append(f"Подходящих целей: {len(matching_targets)}")

        return {
            "rule_id": rule_id,
            "would_trigger": would_trigger,
            "matching_targets": matching_targets[:50],
            "estimated_actions": len(matching_targets) if matching_targets else (1 if would_trigger else 0),
            "details": "; ".join(details_parts),
        }

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _infer_target_type(event_type: str) -> str:
        """Infer target type from event type string."""
        if event_type.startswith("user."):
            return "user"
        if event_type.startswith("node."):
            return "node"
        if event_type.startswith("violation."):
            return "user"
        return "system"


# Module-level singleton
engine = AutomationEngine()

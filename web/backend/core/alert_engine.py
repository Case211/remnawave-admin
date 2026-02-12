"""Alert rules engine — monitors metrics and fires alerts.

Runs a background loop that checks threshold-based alert rules
every 60 seconds against current system metrics.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

OPERATORS = {
    "gt": lambda v, t: v > t,
    "gte": lambda v, t: v >= t,
    "lt": lambda v, t: v < t,
    "lte": lambda v, t: v <= t,
    "eq": lambda v, t: v == t,
    "neq": lambda v, t: v != t,
}


class AlertEngine:
    """Background engine for monitoring alert rules."""

    CHECK_INTERVAL = 60  # seconds

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the alert monitoring loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Alert engine started (interval=%ds)", self.CHECK_INTERVAL)

    async def stop(self):
        """Stop the alert monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Alert engine stopped")

    async def _run_loop(self):
        """Main loop — checks rules periodically."""
        while self._running:
            try:
                await asyncio.sleep(self.CHECK_INTERVAL)
                await self._check_rules()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Alert engine error: %s", e)
                await asyncio.sleep(10)

    async def _check_rules(self):
        """Load enabled threshold rules and evaluate them."""
        try:
            from src.services.database import db_service
            if not db_service.is_connected:
                return

            async with db_service.acquire() as conn:
                rules = await conn.fetch(
                    "SELECT * FROM alert_rules WHERE is_enabled = true AND rule_type = 'threshold'"
                )

            if not rules:
                return

            # Collect metrics once
            metrics = await self._collect_metrics()

            for rule in rules:
                try:
                    await self._evaluate_rule(dict(rule), metrics)
                except Exception as e:
                    logger.error("Error evaluating rule %s: %s", rule["id"], e)

        except Exception as e:
            logger.error("Rule check failed: %s", e)

    async def _collect_metrics(self) -> Dict[str, Any]:
        """Collect current system metrics for rule evaluation.

        Uses DB columns for hardware metrics (cpu, memory, disk) and the
        Remnawave API for live data (users_online, traffic_today).
        """
        metrics: Dict[str, Any] = {}

        try:
            from src.services.database import db_service

            async with db_service.acquire() as conn:
                # Node metrics from DB (only columns that actually exist)
                nodes = await conn.fetch(
                    "SELECT uuid, name, is_connected, is_disabled, "
                    "cpu_usage, memory_usage, disk_usage, "
                    "traffic_used_bytes, metrics_updated_at "
                    "FROM nodes WHERE is_disabled = false"
                )

                max_cpu = 0.0
                max_ram = 0.0
                max_disk = 0.0
                offline_nodes: List[Dict[str, Any]] = []

                for node in nodes:
                    cpu = node.get("cpu_usage") or 0
                    ram = node.get("memory_usage") or 0
                    disk = node.get("disk_usage") or 0

                    max_cpu = max(max_cpu, cpu)
                    max_ram = max(max_ram, ram)
                    max_disk = max(max_disk, disk)

                    if not node.get("is_connected", True):
                        last_update = node.get("metrics_updated_at")
                        offline_min = 0
                        if last_update:
                            if last_update.tzinfo is None:
                                last_update = last_update.replace(tzinfo=timezone.utc)
                            delta = datetime.now(timezone.utc) - last_update
                            offline_min = delta.total_seconds() / 60
                        offline_nodes.append({
                            "uuid": str(node["uuid"]),
                            "name": node["name"],
                            "offline_minutes": offline_min,
                        })

                    # Per-node metrics
                    node_name = node["name"] or str(node["uuid"])
                    metrics[f"node_{node_name}_cpu"] = cpu
                    metrics[f"node_{node_name}_ram"] = ram
                    metrics[f"node_{node_name}_disk"] = disk

                metrics["cpu_usage_percent"] = max_cpu
                metrics["ram_usage_percent"] = max_ram
                metrics["disk_usage_percent"] = max_disk
                metrics["offline_nodes"] = offline_nodes

                # Node offline minutes (max)
                if offline_nodes:
                    metrics["node_offline_minutes"] = max(n["offline_minutes"] for n in offline_nodes)
                else:
                    metrics["node_offline_minutes"] = 0

            # Fetch live data from Remnawave API for users_online & traffic
            try:
                from web.backend.core.api_helper import fetch_nodes_from_api
                api_nodes = await fetch_nodes_from_api()
                total_users_online = 0
                total_traffic_today = 0
                for n in api_nodes:
                    total_users_online += int(n.get("users_online") or n.get("usersOnline") or 0)
                    total_traffic_today += int(n.get("traffic_today_bytes") or n.get("trafficTodayBytes") or 0)
                metrics["users_online"] = total_users_online
                metrics["traffic_today_gb"] = total_traffic_today / (1024 ** 3) if total_traffic_today else 0
            except Exception as e:
                logger.warning("Could not fetch API metrics: %s", e)
                metrics.setdefault("users_online", 0)
                metrics.setdefault("traffic_today_gb", 0)

        except Exception as e:
            logger.error("Metric collection error: %s", e)

        return metrics

    async def _evaluate_rule(self, rule: Dict[str, Any], metrics: Dict[str, Any]):
        """Evaluate a single alert rule against metrics."""
        metric_name = rule.get("metric")
        operator = rule.get("operator")
        threshold = rule.get("threshold")

        if not metric_name or not operator or threshold is None:
            return

        current_value = metrics.get(metric_name)
        if current_value is None:
            return

        op_fn = OPERATORS.get(operator)
        if not op_fn:
            return

        triggered = op_fn(float(current_value), float(threshold))

        if not triggered:
            return

        # Check cooldown
        last_triggered = rule.get("last_triggered_at")
        cooldown = rule.get("cooldown_minutes", 30)
        if last_triggered:
            if hasattr(last_triggered, 'replace'):
                last_triggered = last_triggered.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_triggered).total_seconds() / 60
            if elapsed < cooldown:
                return

        # Fire alert
        await self._fire_alert(rule, float(current_value), metrics)

    async def _fire_alert(self, rule: Dict[str, Any], current_value: float, metrics: Dict[str, Any]):
        """Create notification and log for a triggered alert."""
        from web.backend.core.notification_service import create_notification

        rule_id = rule["id"]
        rule_name = rule["name"]
        severity = rule.get("severity", "warning")
        threshold = rule.get("threshold", 0)
        metric = rule.get("metric", "")
        channels = rule.get("channels", ["in_app"])
        if isinstance(channels, str):
            channels = json.loads(channels)

        # Map metric → Telegram topic so the alert goes to the right thread
        METRIC_TOPIC_MAP = {
            "cpu_usage_percent": "nodes",
            "ram_usage_percent": "nodes",
            "disk_usage_percent": "nodes",
            "node_offline_minutes": "nodes",
            "traffic_today_gb": "nodes",
            "users_online": "service",
        }
        topic_type = METRIC_TOPIC_MAP.get(metric, "service")

        title = f"Alert: {rule_name}"
        body = (
            f"{metric}: {current_value:.1f} "
            f"({rule.get('operator', '>')} {threshold:.1f})"
        )

        # Build details with offline node info if applicable
        details = body
        if metric == "node_offline_minutes" and metrics.get("offline_nodes"):
            offline = metrics["offline_nodes"]
            node_names = ", ".join(n["name"] for n in offline[:5])
            details += f" | Nodes: {node_names}"

        try:
            from src.services.database import db_service

            # Log the alert
            async with db_service.acquire() as conn:
                await conn.execute(
                    "INSERT INTO alert_rule_log (rule_id, rule_name, metric_value, threshold_value, "
                    "severity, channels_notified, details) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7)",
                    rule_id, rule_name, current_value, threshold,
                    severity, json.dumps(channels), details,
                )

                # Update rule state
                await conn.execute(
                    "UPDATE alert_rules SET last_triggered_at = NOW(), last_value = $1, "
                    "trigger_count = trigger_count + 1, updated_at = NOW() WHERE id = $2",
                    current_value, rule_id,
                )

            # Create notification (broadcast to all admins)
            await create_notification(
                title=title,
                body=details,
                type="alert",
                severity=severity,
                link="/notifications",
                source="alert_engine",
                source_id=str(rule_id),
                group_key=rule.get("group_key") or f"alert_{rule_id}",
                channels=channels,
                topic_type=topic_type,
            )

            # Escalation check
            escalation_admin_id = rule.get("escalation_admin_id")
            escalation_minutes = rule.get("escalation_minutes", 0)
            if escalation_admin_id and escalation_minutes > 0:
                asyncio.create_task(
                    self._schedule_escalation(rule_id, escalation_admin_id, escalation_minutes, title, details, severity)
                )

            logger.info("Alert fired: %s (value=%.1f, threshold=%.1f)", rule_name, current_value, threshold)

        except Exception as e:
            logger.error("Failed to fire alert %s: %s", rule_name, e)

    async def _schedule_escalation(
        self,
        rule_id: int,
        admin_id: int,
        delay_minutes: int,
        title: str,
        body: str,
        severity: str,
    ):
        """Wait N minutes, then check if alert is acknowledged. If not, escalate."""
        await asyncio.sleep(delay_minutes * 60)

        try:
            from src.services.database import db_service
            async with db_service.acquire() as conn:
                # Check if any recent log entry for this rule is still unacknowledged
                unacked = await conn.fetchval(
                    "SELECT COUNT(*) FROM alert_rule_log "
                    "WHERE rule_id = $1 AND acknowledged = false "
                    "AND created_at > NOW() - INTERVAL '1 hour'",
                    rule_id,
                )
                if unacked and unacked > 0:
                    from web.backend.core.notification_service import create_notification
                    await create_notification(
                        title=f"ESCALATION: {title}",
                        body=f"Alert not acknowledged for {delay_minutes} min. Original: {body}",
                        type="escalation",
                        severity="critical",
                        admin_id=admin_id,
                        link="/notifications",
                        source="alert_engine",
                        source_id=str(rule_id),
                        group_key=f"escalation_{rule_id}",
                    )
                    logger.info("Escalated alert rule %d to admin %d", rule_id, admin_id)
        except Exception as e:
            logger.error("Escalation error for rule %d: %s", rule_id, e)


# Global engine instance
alert_engine = AlertEngine()

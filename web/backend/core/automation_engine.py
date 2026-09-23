"""Automation Engine — scheduler, event handler, action executor.

Manages three trigger mechanisms:
- Event triggers: fired by hooks in API endpoints and WebSocket handler
- Schedule triggers: CRON and interval-based, checked every 60 seconds
- Threshold triggers: metric-based, checked every 5 minutes

All action execution is logged to the automation_log table.
"""
import asyncio
import html
import json
import logging
import operator as op_module
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx

from shared import timefmt

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
    """Parse a single CRON field: *, N, a-b, lists and steps (*/n, a/n, a-b/n)."""
    values = set()
    for part in field.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            part, step_raw = part.split("/", 1)
            step = int(step_raw)
            if step < 1:
                raise ValueError("step must be positive")
        if part == "*":
            lo, hi = min_val, max_val
        elif "-" in part:
            lo_raw, hi_raw = part.split("-", 1)
            lo, hi = int(lo_raw), int(hi_raw)
        else:
            lo = int(part)
            hi = max_val if step > 1 else lo
        values.update(range(lo, hi + 1, step))
    return values


def cron_matches(cron_expr: str, moment: datetime) -> bool:
    """Совпадает ли CRON с минутой ``moment`` (время на часах панели).

    Поля: minute hour day-of-month month day-of-week; день недели 0 и 7 —
    воскресенье.
    """
    try:
        parts = cron_expr.strip().split()
        if len(parts) != 5:
            logger.warning("Invalid CRON expression (expected 5 parts): %s", cron_expr)
            return False
        dow_set = {d % 7 for d in _parse_cron_field(parts[4], 0, 7)}
        cron_dow = (moment.weekday() + 1) % 7  # Python Mon=0 → CRON Sun=0
        return (
            moment.minute in _parse_cron_field(parts[0], 0, 59)
            and moment.hour in _parse_cron_field(parts[1], 0, 23)
            and moment.day in _parse_cron_field(parts[2], 1, 31)
            and moment.month in _parse_cron_field(parts[3], 1, 12)
            and cron_dow in dow_set
        )
    except Exception as e:
        logger.warning("CRON parse error for '%s': %s", cron_expr, e)
        return False


def cron_matches_now(cron_expr: str) -> bool:
    """CRON совпадает с текущей минутой по часам панели."""
    return cron_matches(cron_expr, timefmt.now())


def cron_due(cron_expr: str, since: datetime, now: datetime) -> bool:
    """Была ли совпадающая минута в (since, now].

    Цикл «раз в минуту» уползает: проверка точной минуты иногда её
    перескакивала, и правило не срабатывало. Смотрим все минуты с прошлой
    проверки, но не дальше 10 минут назад — после простоя не догоняем.
    """
    start = max(since, now - timedelta(minutes=10)).replace(second=0, microsecond=0)
    moment = now.replace(second=0, microsecond=0)
    while moment > start:
        if cron_matches(cron_expr, moment):
            return True
        moment -= timedelta(minutes=1)
    return False


# Имена полей, которые раньше предлагал конструктор, — к тем, что в данных
_CONDITION_ALIASES = {"online_count": "users_online"}

# Сколько держать журнал и замки срабатываний
_HISTORY_KEEP_DAYS = 90


class AutomationEngine:
    """Singleton engine that manages event triggers, scheduled tasks, and threshold checks."""

    def __init__(self):
        self._running = False
        self._schedule_task: Optional[asyncio.Task] = None
        self._threshold_task: Optional[asyncio.Task] = None
        self._event_detect_task: Optional[asyncio.Task] = None
        # State tracking for event detection
        self._node_offline_since: Dict[str, datetime] = {}
        self._user_traffic_exceeded: set = set()
        # Первый проход после старта только запоминает, кто уже за лимитом:
        # иначе рестарт заново рассылает событие по всем превысившим
        self._traffic_seeded = False
        # Dedup for threshold rules: (rule_id, target_id) -> (value, timestamp)
        self._threshold_notified: Dict[tuple, Tuple[float, datetime]] = {}
        # Прошлая проверка расписаний — чтобы не перескакивать минуты
        self._last_schedule_check: Optional[datetime] = None
        # День последней чистки журнала
        self._last_history_cleanup: Optional[str] = None

    async def start(self):
        """Start the scheduler, threshold, and event detection loops."""
        if self._running:
            return
        self._running = True
        self._schedule_task = asyncio.create_task(self._schedule_loop())
        self._threshold_task = asyncio.create_task(self._threshold_loop())
        self._event_detect_task = asyncio.create_task(self._event_detection_loop())
        logger.debug("Automation engine started")

    async def stop(self):
        """Stop all background tasks."""
        self._running = False
        for task in (self._schedule_task, self._threshold_task, self._event_detect_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._schedule_task = None
        self._threshold_task = None
        self._event_detect_task = None
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
        from web.backend.core.automation import try_acquire_target, write_automation_log

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

        target_type = self._infer_target_type(event_type)
        target_id = (
            payload.get("user_uuid")
            or payload.get("node_uuid")
            or payload.get("uuid")
            or str(payload.get("id", ""))
        )

        # Замок на пару «правило + цель»: разные юзеры и ноды друг друга не
        # глушат. Офлайн ноды — один раз на каждое падение: ключ включает
        # момент, с которого нода лежит.
        if event_type == "node.went_offline" and payload.get("offline_since"):
            lock_key, lock_seconds = f"{target_id}@{payload['offline_since']}", 30 * 86400
        else:
            lock_key, lock_seconds = target_id or "-", 30
        if not await try_acquire_target(rule["id"], lock_key, lock_seconds):
            return

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

        from web.backend.core.webhook_security import fire_event
        fire_event("automation.triggered", {
            "rule_id": rule["id"],
            "rule_name": rule.get("name"),
            "event": event_type,
            "action": rule["action_type"],
            "target_type": target_type,
            "target_id": target_id,
            "result": result,
            "details": details,
        })

    # ── Schedule loop ────────────────────────────────────────

    async def _schedule_loop(self):
        """Check schedule-type rules every 60 seconds."""
        while self._running:
            try:
                await asyncio.sleep(60)
                if not self._running:
                    break
                await self._check_scheduled_rules()
                await self._cleanup_history_daily()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Schedule loop error: %s", e)

    async def _cleanup_history_daily(self) -> None:
        """Раз в сутки — журнал и замки старше _HISTORY_KEEP_DAYS прочь."""
        today = timefmt.now().strftime("%Y-%m-%d")
        if self._last_history_cleanup == today:
            return
        from web.backend.core.automation import cleanup_automation_history
        try:
            removed = await cleanup_automation_history(_HISTORY_KEEP_DAYS)
            if removed:
                logger.info("Automation log: removed %d entries older than %d days", removed, _HISTORY_KEEP_DAYS)
            self._last_history_cleanup = today
        except Exception as e:
            logger.warning("Automation history cleanup failed: %s", e)

    async def _check_scheduled_rules(self):
        """Evaluate all enabled schedule-type rules."""
        from web.backend.core.automation import (
            get_enabled_rules_by_trigger_type,
            try_acquire_target,
            write_automation_log,
        )

        now_local = timefmt.now()
        since = self._last_schedule_check or (now_local - timedelta(minutes=1))
        self._last_schedule_check = now_local

        rules = await get_enabled_rules_by_trigger_type("schedule")

        for rule in rules:
            try:
                trigger_config = rule.get("trigger_config", {})
                if isinstance(trigger_config, str):
                    trigger_config = json.loads(trigger_config)

                should_fire = False

                # CRON — по часам панели, с прошлой проверки
                cron = trigger_config.get("cron")
                if cron:
                    should_fire = cron_due(cron, since, now_local)

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

                min_interval = max(55, (interval or 1) * 60 - 10) if interval else 55
                if not await try_acquire_target(rule["id"], "schedule", min_interval):
                    logger.debug("Schedule rule %d skipped (trigger lock)", rule["id"])
                    continue

                logger.info("Schedule rule %d (%s) fired", rule["id"], rule.get("name", "?"))
                context: Dict[str, Any] = {
                    "trigger": "schedule", "cron": cron, "interval_minutes": interval,
                    "timestamp": timefmt.fmt(datetime.now(timezone.utc), "%Y-%m-%d %H:%M"),
                }
                if rule["action_type"] == "notify" or rule.get("conditions"):
                    await self._fill_schedule_context(context)

                if not self._evaluate_conditions(rule, context):
                    await write_automation_log(
                        rule_id=rule["id"], target_type="system", target_id=None,
                        action_taken=rule["action_type"], result="skipped",
                        details={"reason": "conditions_not_met"},
                    )
                    continue

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

    async def _fill_schedule_context(self, context: Dict[str, Any]) -> None:
        """Сводка для сообщений по расписанию. Сутки — по часам панели."""
        from shared.database import db_service
        now = datetime.now(timezone.utc)
        today_start = timefmt.now().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)

        try:
            from web.backend.core.api_helper import fetch_nodes_from_api
            nodes = await fetch_nodes_from_api()
            context["nodes_total"] = len(nodes)
            context["nodes_online"] = sum(1 for n in nodes if n.get("is_connected"))
            # Онлайн сейчас — со счётчиков нод, а не «хоть раз был онлайн»
            context["users_online"] = sum(int(n.get("users_online") or 0) for n in nodes)
        except Exception:
            pass
        try:
            if db_service.is_connected:
                async with db_service.acquire() as conn:
                    context["users_total"] = await conn.fetchval("SELECT COUNT(*) FROM users")
        except Exception:
            pass

        try:
            if db_service.is_connected:
                today_map = await db_service.get_nodes_traffic_for_period(today_start, now)
                context["traffic_today"] = f"{sum(today_map.values()) / (1024 ** 3):.2f} GB"
        except Exception:
            context.setdefault("traffic_today", "0.00 GB")

        context["report_date"] = yesterday_start.strftime("%Y-%m-%d")
        try:
            if db_service.is_connected:
                yday_map = await db_service.get_nodes_traffic_for_period(yesterday_start, today_start)
                context["traffic_yesterday"] = f"{sum(yday_map.values()) / (1024 ** 3):.2f} GB"
                top_nodes = await db_service.get_top_nodes_traffic_for_period(
                    yesterday_start, today_start, limit=3,
                )
                if top_nodes:
                    medals = ["🥇", "🥈", "🥉"]
                    context["top_nodes_yesterday"] = "\n".join(
                        f"{medals[i]} {html.escape(str(name))} — <b>{bytes_ / (1024 ** 3):.2f} GB</b>"
                        for i, (name, bytes_) in enumerate(top_nodes)
                    )
                else:
                    context["top_nodes_yesterday"] = "  <i>(нет данных)</i>"
                context["users_new_yesterday"] = await db_service.count_users_created_for_period(
                    yesterday_start, today_start,
                )
                context["users_expired_yesterday"] = await db_service.count_users_expired_for_period(
                    yesterday_start, today_start,
                )
        except Exception:
            context.setdefault("traffic_yesterday", "0.00 GB")
            context.setdefault("top_nodes_yesterday", "  (нет данных)")
            context.setdefault("users_new_yesterday", 0)
            context.setdefault("users_expired_yesterday", 0)

        try:
            if db_service.is_connected:
                context["violations_today"] = await db_service.count_violations_for_period(
                    start_date=today_start, end_date=now,
                )
                context["violations_yesterday"] = await db_service.count_violations_for_period(
                    start_date=yesterday_start, end_date=today_start,
                )
        except Exception:
            context.setdefault("violations_today", 0)
            context.setdefault("violations_yesterday", 0)

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
            try_acquire_target,
            write_automation_log,
        )

        rules = await get_enabled_rules_by_trigger_type("threshold")
        if not rules:
            return

        # Выборки нод и юзеров — общие на проход по всем правилам
        cache: dict = {}

        for rule in rules:
            try:
                trigger_config = rule.get("trigger_config", {})
                if isinstance(trigger_config, str):
                    trigger_config = json.loads(trigger_config)

                targets = await self._threshold_targets(trigger_config, cache)

                # Условия правила — к каждой цели отдельно
                targets = [tt for tt in targets if self._evaluate_conditions(rule, tt[2])]

                if not targets:
                    # No targets exceeded threshold — clear stale entries (>1h) for this rule
                    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
                    self._threshold_notified = {
                        k: v for k, v in self._threshold_notified.items()
                        if k[0] != rule["id"] or v[1] > cutoff
                    }
                    continue

                # Filter out already-notified targets (same rule + target + similar value)
                now = datetime.now(timezone.utc)
                new_targets = []
                for t in targets:
                    target_type, target_id, ctx = t
                    key = (rule["id"], target_id)
                    prev = self._threshold_notified.get(key)
                    cur_value = ctx.get("percent") or ctx.get("traffic_gb") or 0
                    if prev is None:
                        new_targets.append(t)
                        self._threshold_notified[key] = (cur_value, now)
                    else:
                        prev_value, prev_time = prev
                        age_minutes = (now - prev_time).total_seconds() / 60
                        value_changed = abs(cur_value - prev_value) > 5
                        # Re-notify only if value changed significantly AND at least 30 min passed
                        if value_changed and age_minutes >= 30:
                            new_targets.append(t)
                            self._threshold_notified[key] = (cur_value, now)

                # Clear notified state for targets that dropped below threshold
                # but keep entries for 1 hour grace period to prevent spam on flapping
                current_target_ids = {t[1] for t in targets}
                self._threshold_notified = {
                    k: v for k, v in self._threshold_notified.items()
                    if k[0] != rule["id"]
                    or k[1] in current_target_ids
                    or (now - v[1]).total_seconds() < 3600
                }

                if not new_targets:
                    continue

                # Acquire trigger lock (5-min minimum between threshold triggers)
                if not await try_acquire_target(rule["id"], "threshold", 280):
                    logger.info("Threshold rule %d skipped (trigger lock cooldown)", rule["id"])
                    continue

                logger.info("Threshold rule %d (%s) fired: %d targets", rule["id"], rule.get("name", "?"), len(new_targets))
                for target_type, target_id, ctx in new_targets:
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

    async def _threshold_targets(self, trigger_config: dict, cache: dict) -> list:
        """Цели порогового правила: (тип, id, контекст). ``cache`` — общие для
        прохода выборки нод и юзеров. Им же пользуется тестовый прогон,
        чтобы прогон и настоящий запуск считали одинаково."""
        from web.backend.core.api_helper import fetch_nodes_from_api, enrich_nodes_traffic_today
        from web.backend.core.automation import users_over_traffic

        metric = trigger_config.get("metric", "")
        threshold_value = trigger_config.get("value", 0)
        op_fn = _OPERATORS.get(trigger_config.get("operator", ">="))
        if not op_fn:
            return []
        targets: list = []

        # Evaluate metric against data
        if metric == "users_online":
            if cache.get("nodes") is None:
                cache["nodes"] = await fetch_nodes_from_api()
            total_online = sum(n.get("users_online", 0) for n in cache["nodes"])
            if op_fn(total_online, threshold_value):
                targets.append(("system", None, {"users_online": total_online}))

        elif metric == "traffic_today":
            if not cache.get("nodes_enriched"):
                cache["nodes"] = cache.get("nodes") or await fetch_nodes_from_api()
                await enrich_nodes_traffic_today(cache["nodes"])
                cache["nodes_enriched"] = True
            total_traffic = sum(n.get("traffic_today_bytes", 0) for n in cache["nodes"])
            total_gb = total_traffic / (1024 ** 3)
            if op_fn(total_gb, threshold_value):
                targets.append(("system", None, {"traffic_today_gb": round(total_gb, 2)}))

        elif metric == "user_traffic_percent":
            # Из своей базы: полный список юзеров из панели каждые 5 минут
            # на десятках тысяч юзеров — лишняя нагрузка
            if cache.get("users") is None:
                cache["users"] = await users_over_traffic(0)
            for user in cache["users"]:
                limit = user.get("traffic_limit_bytes") or 0
                if not limit:
                    continue
                used = user.get("used_traffic_bytes") or 0
                percent = (used / limit) * 100
                if op_fn(percent, threshold_value):
                    targets.append((
                        "user",
                        user.get("uuid", ""),
                        {
                            "username": user.get("username", ""),
                            "percent": round(percent, 1),
                            "threshold": threshold_value,
                            "over_percent": round(percent - threshold_value, 1),
                        },
                    ))

        elif metric == "user_node_traffic_gb":
            from shared.database import db_service
            node_uuid = trigger_config.get("node_uuid")
            if node_uuid:
                rows = await db_service.get_node_users_traffic(node_uuid)
            else:
                rows = await db_service.get_all_user_node_traffic_above(
                    int(threshold_value * (1024 ** 3))
                )
            for row in rows:
                traffic_gb = row["traffic_bytes"] / (1024 ** 3)
                if op_fn(traffic_gb, threshold_value):
                    # Check whitelist
                    uid = str(row["user_uuid"])
                    try:
                        wl, excl = await db_service.is_user_violation_whitelisted(uid)
                        if wl and (excl is None or "traffic_rate" in excl):
                            continue
                    except Exception:
                        pass
                    targets.append((
                        "user",
                        uid,
                        {
                            "username": row.get("username", ""),
                            "node_name": row.get("node_name", ""),
                            "traffic_gb": round(traffic_gb, 2),
                            "threshold": threshold_value,
                            "over_gb": round(traffic_gb - threshold_value, 2),
                        },
                    ))

        elif metric == "user_node_traffic_today_gb":
            from shared.database import db_service
            node_uuid = trigger_config.get("node_uuid")
            rows = await db_service.get_user_node_traffic_today(
                node_uuid=node_uuid,
                threshold_bytes=int(threshold_value * (1024 ** 3)),
            )
            for row in rows:
                traffic_gb = row["traffic_bytes"] / (1024 ** 3)
                if op_fn(traffic_gb, threshold_value):
                    uid = str(row["user_uuid"])
                    try:
                        wl, excl = await db_service.is_user_violation_whitelisted(uid)
                        if wl and (excl is None or "traffic_rate" in excl):
                            continue
                    except Exception:
                        pass
                    targets.append((
                        "user",
                        uid,
                        {
                            "username": row.get("username", ""),
                            "node_name": row.get("node_name", ""),
                            "traffic_gb": round(traffic_gb, 2),
                            "threshold": threshold_value,
                            "over_gb": round(traffic_gb - threshold_value, 2),
                        },
                    ))
        return targets

    # ── Event detection loop ────────────────────────────────

    async def _event_detection_loop(self):
        """Poll Remnawave API to detect state changes and dispatch events.

        Runs every 120 seconds. Detects:
        - Node going offline (state transition from connected to disconnected)
        - User traffic exceeding limit (newly exceeded)
        """
        while self._running:
            try:
                await asyncio.sleep(120)
                if not self._running:
                    break
                await self._detect_events()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Event detection loop error: %s", e)

    @staticmethod
    def _offline_since(node: dict) -> datetime:
        """С какого момента нода лежит: смена статуса в панели, иначе — сейчас
        (после рестарта движка не отсчитываем падение заново с нуля)."""
        raw = node.get("last_status_change") or node.get("lastStatusChange")
        now = datetime.now(timezone.utc)
        if raw:
            try:
                since = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if since.tzinfo is None:
                    since = since.replace(tzinfo=timezone.utc)
                if since <= now:
                    return since
            except ValueError:
                pass
        return now

    async def _detect_events(self):
        """Single pass of event detection."""
        from web.backend.core.api_helper import fetch_nodes_from_api
        from web.backend.core.automation import get_enabled_event_rules, users_over_traffic

        # ── Detect node offline transitions ───────────────
        try:
            nodes = await fetch_nodes_from_api()
            current_nodes: set = set()

            for node in nodes:
                uuid = node.get("uuid", "")
                if not uuid:
                    continue
                current_nodes.add(uuid)
                # Выключенная вручную нода не «упала» — не шлём по ней событий
                if node.get("is_disabled"):
                    self._node_offline_since.pop(uuid, None)
                    continue

                if node.get("is_connected", True):
                    was_offline_since = self._node_offline_since.pop(uuid, None)
                    if was_offline_since is not None:
                        # Переход offline → online: шлём вебхук подписчикам
                        from web.backend.core.webhook_security import fire_event
                        downtime = datetime.now(timezone.utc) - was_offline_since
                        fire_event("node.online", {
                            "uuid": uuid,
                            "name": node.get("name", ""),
                            "downtime_minutes": round(downtime.total_seconds() / 60, 1),
                        })
                    continue

                if uuid not in self._node_offline_since:
                    self._node_offline_since[uuid] = self._offline_since(node)
                    from web.backend.core.webhook_security import fire_event
                    fire_event("node.offline", {"uuid": uuid, "name": node.get("name", "")})

                since = self._node_offline_since[uuid]
                offline_minutes = (datetime.now(timezone.utc) - since).total_seconds() / 60
                # Событие уходит каждый проход, пока нода лежит; правило при
                # этом срабатывает один раз на падение — замок по offline_since
                await self.handle_event("node.went_offline", {
                    "node_uuid": uuid,
                    "uuid": uuid,
                    "node_name": node.get("name", ""),
                    "is_connected": False,
                    "offline_minutes": round(offline_minutes, 1),
                    "offline_since": since.isoformat(),
                })

            for u in [u for u in self._node_offline_since if u not in current_nodes]:
                del self._node_offline_since[u]
        except Exception as e:
            logger.warning("Node event detection error: %s", e)

        # ── Detect user traffic exceeded ──────────────────
        try:
            if await get_enabled_event_rules("user.traffic_exceeded"):
                current_exceeded: set = set()
                for user in await users_over_traffic(100):
                    uuid = user["uuid"]
                    current_exceeded.add(uuid)
                    if uuid in self._user_traffic_exceeded or not self._traffic_seeded:
                        continue
                    limit = user["traffic_limit_bytes"]
                    used = user["used_traffic_bytes"]
                    await self.handle_event("user.traffic_exceeded", {
                        "user_uuid": uuid,
                        "uuid": uuid,
                        "username": user.get("username") or "",
                        "traffic_limit_bytes": limit,
                        "used_traffic_bytes": used,
                        "percent": round(used / limit * 100, 1),
                        "traffic_gb": round(used / (1024 ** 3), 2),
                    })
                self._user_traffic_exceeded = current_exceeded
                self._traffic_seeded = True
        except Exception as e:
            logger.warning("User traffic event detection error: %s", e)

    # ── Condition evaluation ─────────────────────────────────

    def _evaluate_conditions(self, rule: dict, context: dict) -> bool:
        """Evaluate the conditions array against context. All conditions must pass."""
        conditions = rule.get("conditions", [])
        if isinstance(conditions, str):
            conditions = json.loads(conditions)

        if not conditions:
            return True

        for cond in conditions:
            field = _CONDITION_ALIASES.get(cond.get("field", ""), cond.get("field", ""))
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

        # Enrich context with rule metadata for downstream handlers (e.g. topic routing)
        context.setdefault("rule_id", rule.get("id"))
        context.setdefault("rule_name", rule.get("name", ""))
        context.setdefault("category", rule.get("category", "system"))
        context.setdefault("timestamp", timefmt.fmt(datetime.now(timezone.utc), "%Y-%m-%d %H:%M:%S"))

        try:
            handler = {
                "disable_user": self._action_disable_user,
                "block_user": self._action_block_user,
                "notify": self._action_notify,
                "restart_node": self._action_restart_node,
                "enable_node": self._action_enable_node,
                "disable_node": self._action_disable_node,
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
        target_id = target_id or config.get("user_uuid")
        if not target_id:
            raise ValueError("No target user specified (target_id and action_config.user_uuid are empty)")
        from shared.data_access import resolve_panel_user_id
        panel_user_id = await resolve_panel_user_id(target_id)
        from web.backend.core.api_helper import _get_client
        client = _get_client()
        resp = await client.post(
            f"/api/users/{panel_user_id}/actions/disable",
            json={},
        )
        resp.raise_for_status()
        from web.backend.core.webhook_security import fire_event
        fire_event("user.blocked", {
            "uuid": target_id,
            "username": context.get("username"),
            "reason": "automation",
            "details": "disable_user action",
            "blocked_by": "automation",
        })
        return {"action": "disable_user", "user_uuid": target_id, "status": resp.status_code}

    async def _action_block_user(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Block a user (disable + mark reason) via Remnawave API."""
        target_id = target_id or config.get("user_uuid")
        if not target_id:
            raise ValueError("No target user specified (target_id and action_config.user_uuid are empty)")
        from shared.data_access import resolve_panel_user_id
        panel_user_id = await resolve_panel_user_id(target_id)
        from web.backend.core.api_helper import _get_client
        reason = config.get("reason", "Blocked by automation")
        client = _get_client()
        resp = await client.post(
            f"/api/users/{panel_user_id}/actions/disable",
            json={"reason": reason},
        )
        resp.raise_for_status()
        from web.backend.core.webhook_security import fire_event
        fire_event("user.blocked", {
            "uuid": target_id,
            "username": context.get("username"),
            "reason": "automation",
            "details": reason,
            "blocked_by": "automation",
        })
        return {"action": "block_user", "user_uuid": target_id, "reason": reason}

    async def _action_notify(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Send notification via Telegram or webhook."""
        channel = config.get("channel", "telegram")
        message_template = config.get("message", "Automation triggered")

        # Template substitution — unknown tags become empty string
        # Add short aliases so UI placeholders {user},{node} work alongside
        # the canonical keys {username},{node_name}.
        _ALIASES = {
            "user": "username",
            "node": "node_name",
        }
        # Значения идут в Telegram-HTML: «<» в имени юзера ломал разметку, и
        # сообщение не уходило. Экранируем всё, кроме заведомо готового HTML.
        raw_html = {"top_nodes_yesterday"}
        enriched = {
            k: (v if k in raw_html or channel != "telegram" else html.escape(str(v), quote=False))
            for k, v in context.items()
        }
        for short, full in _ALIASES.items():
            if short not in enriched and full in enriched:
                enriched[short] = enriched[full]
        # <code>-wrapped versions for Telegram HTML
        if "username" in enriched:
            enriched.setdefault("user_code", f"<code>{enriched['username']}</code>")
        if "node_name" in enriched:
            enriched.setdefault("node_code", f"<code>{enriched['node_name']}</code>")
        if "traffic_gb" in enriched:
            enriched.setdefault("traffic", f"{enriched['traffic_gb']} ГБ")
        if "over_gb" in enriched:
            enriched.setdefault("over", f"{enriched['over_gb']} ГБ")

        class _SafeDict(dict):
            def __missing__(self, key: str) -> str:
                return ""

        try:
            message = message_template.format_map(_SafeDict({k: str(v) for k, v in enriched.items()}))
        except Exception:
            # Fallback to naive replacement if format_map fails (e.g. malformed braces)
            message = message_template
            for key, value in enriched.items():
                message = message.replace(f"{{{key}}}", str(value))

        if channel == "telegram":
            from web.backend.core.notification_service import create_notification
            # Route to the correct Telegram topic:
            # 1. Explicit topic_type in action_config (user override)
            # 2. Rule category (users/nodes/violations/system)
            # "system" category maps to "service" topic.
            topic_type = config.get("topic_type")
            if not topic_type:
                category = context.get("category", target_type or "service")
                topic_type = category if category != "system" else "service"

            await create_notification(
                title="Automation",
                body=message,
                type="automation",
                severity="info",
                source="automation",
                source_id=str(context.get("rule_id", "")),
                group_key=f"automation:{context.get('rule_id', '')}:{target_id}",
                channels=["telegram", "in_app"],
                topic_type=topic_type,
                telegram_body=message,
                link="/automations",
            )
            return {"action": "notify", "channel": "telegram", "sent": True}

        elif channel == "webhook":
            webhook_url = config.get("webhook_url")
            if not webhook_url:
                return {"action": "notify", "channel": "webhook", "error": "No webhook_url configured"}
            # Та же проверка, что у вебхуков: во внутреннюю сеть не ходим
            from web.backend.core.webhook_security import check_url_safety
            ok, reason = await asyncio.to_thread(check_url_safety, webhook_url)
            if not ok:
                raise ValueError(f"Webhook URL rejected: {reason}")
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
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
        """Restart a node via Remnawave API.

        If target_id is None (e.g. schedule trigger), restarts all connected
        nodes or a specific node from action_config['node_uuid'].
        """
        from web.backend.core.api_helper import _get_client, fetch_nodes_from_api

        # Check action_config for a specific node
        specific_node = config.get("node_uuid")
        if specific_node:
            target_id = specific_node

        if target_id:
            client = _get_client()
            resp = await client.post(
                f"/api/nodes/{target_id}/actions/restart",
                json={"forceRestart": True},
            )
            resp.raise_for_status()
            return {"action": "restart_node", "node_uuid": target_id, "status": resp.status_code}

        # No specific target — restart all connected nodes
        nodes = await fetch_nodes_from_api()
        client = _get_client()
        restarted = []
        errors = []
        for node in nodes:
            uuid = node.get("uuid", "")
            if not uuid or not node.get("is_connected", False):
                continue
            try:
                resp = await client.post(f"/api/nodes/{uuid}/actions/restart", json={"forceRestart": True})
                if resp.status_code < 400:
                    restarted.append(uuid)
                else:
                    errors.append(uuid)
            except Exception as e:
                logger.warning("Failed to restart node %s: %s", uuid, e)
                errors.append(uuid)

        return {
            "action": "restart_node",
            "restarted_count": len(restarted),
            "restarted_nodes": restarted,
            "errors": errors,
        }

    async def _action_enable_node(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Enable a node via Remnawave API."""
        from web.backend.core.api_helper import _get_client, fetch_nodes_from_api

        specific_node = config.get("node_uuid")
        if specific_node:
            target_id = specific_node

        if target_id:
            client = _get_client()
            resp = await client.post(f"/api/nodes/{target_id}/actions/enable", json={})
            resp.raise_for_status()
            return {"action": "enable_node", "node_uuid": target_id, "status": resp.status_code}

        # No specific target — enable all disabled nodes
        nodes = await fetch_nodes_from_api()
        client = _get_client()
        enabled = []
        errors = []
        for node in nodes:
            uuid = node.get("uuid", "")
            if not uuid or not node.get("is_disabled", False):
                continue
            try:
                resp = await client.post(f"/api/nodes/{uuid}/actions/enable", json={})
                if resp.status_code < 400:
                    enabled.append(uuid)
                else:
                    errors.append(uuid)
            except Exception as e:
                logger.warning("Failed to enable node %s: %s", uuid, e)
                errors.append(uuid)

        return {
            "action": "enable_node",
            "enabled_count": len(enabled),
            "enabled_nodes": enabled,
            "errors": errors,
        }

    async def _action_disable_node(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Disable a node via Remnawave API."""
        from web.backend.core.api_helper import _get_client, fetch_nodes_from_api

        specific_node = config.get("node_uuid")
        if specific_node:
            target_id = specific_node

        if target_id:
            client = _get_client()
            resp = await client.post(f"/api/nodes/{target_id}/actions/disable", json={})
            resp.raise_for_status()
            return {"action": "disable_node", "node_uuid": target_id, "status": resp.status_code}

        # No specific target — disable all connected nodes
        nodes = await fetch_nodes_from_api()
        client = _get_client()
        disabled = []
        errors = []
        for node in nodes:
            uuid = node.get("uuid", "")
            if not uuid or not node.get("is_connected", False):
                continue
            try:
                resp = await client.post(f"/api/nodes/{uuid}/actions/disable", json={})
                if resp.status_code < 400:
                    disabled.append(uuid)
                else:
                    errors.append(uuid)
            except Exception as e:
                logger.warning("Failed to disable node %s: %s", uuid, e)
                errors.append(uuid)

        return {
            "action": "disable_node",
            "disabled_count": len(disabled),
            "disabled_nodes": disabled,
            "errors": errors,
        }

    async def _action_cleanup_expired(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Отключить юзеров, чья подписка истекла больше N дней назад.

        Кандидаты — из своей базы; в панель — её идентификатор (в 3.x числовой
        id: с uuid каждый запрос падал, и очистка никого не отключала).
        """
        from shared.data_access import resolve_panel_user_id
        from web.backend.core.api_helper import _get_client
        from web.backend.core.automation import expired_users_to_disable

        older_than_days = int(config.get("older_than_days", 30) or 30)
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        client = _get_client()

        disabled, failed = 0, 0
        for uuid in await expired_users_to_disable(cutoff):
            try:
                panel_id = await resolve_panel_user_id(uuid)
                resp = await client.post(f"/api/users/{panel_id}/actions/disable", json={})
                if resp.status_code < 400:
                    disabled += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                logger.warning("cleanup_expired: failed to disable %s: %s", uuid, e)

        return {
            "action": "cleanup_expired",
            "older_than_days": older_than_days,
            "disabled_count": disabled,
            "failed_count": failed,
        }

    async def _action_reset_traffic(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Reset traffic counter for a user via Remnawave API."""
        target_id = target_id or config.get("user_uuid")
        if not target_id:
            raise ValueError("No target user specified (target_id and action_config.user_uuid are empty)")
        from shared.data_access import resolve_panel_user_id
        panel_user_id = await resolve_panel_user_id(target_id)
        from web.backend.core.api_helper import _get_client
        client = _get_client()
        resp = await client.post(
            f"/api/users/{panel_user_id}/actions/reset-traffic",
            json={},
        )
        resp.raise_for_status()
        return {"action": "reset_traffic", "user_uuid": target_id, "status": resp.status_code}

    async def _action_force_sync(
        self, config: dict, target_type: str, target_id: str, context: dict,
    ) -> dict:
        """Подтянуть ноды из панели в свою базу — то же, что «Синхронизация»
        в настройках. POST /api/nodes/actions/sync в панели 3.x не существует."""
        from shared.sync import sync_service
        synced = await sync_service.sync_nodes()
        return {"action": "force_sync", "nodes_synced": synced}

    # ── Dry-run ──────────────────────────────────────────────

    async def dry_run(self, rule_id: int) -> dict:
        """Прогнать правило без действий: сработает ли и на ком.

        Отдаёт данные (summary), текст собирает фронт на языке админа.
        Для порогов — тот же подсчёт целей, условия и белый список, что у
        настоящего запуска.
        """
        from web.backend.core.automation import get_automation_rule_by_id

        rule = await get_automation_rule_by_id(rule_id)
        if not rule:
            return {"rule_id": rule_id, "would_trigger": False, "matching_targets": [],
                    "estimated_actions": 0, "details": "", "summary": {"error": "not_found"}}

        trigger_type = rule["trigger_type"]
        trigger_config = rule.get("trigger_config", {})
        if isinstance(trigger_config, str):
            trigger_config = json.loads(trigger_config)

        summary: Dict[str, Any] = {"trigger_type": trigger_type, "action_type": rule["action_type"]}
        matching_targets: List[dict] = []
        would_trigger = False

        if trigger_type == "event":
            summary["event"] = trigger_config.get("event", "")
            would_trigger = True
        elif trigger_type == "schedule":
            cron = trigger_config.get("cron")
            interval = trigger_config.get("interval_minutes")
            if cron:
                summary["cron"] = cron
                would_trigger = cron_matches_now(cron)
                summary["cron_matches_now"] = would_trigger
            elif interval:
                summary["interval_minutes"] = interval
                last = rule.get("last_triggered_at")
                if last is None:
                    would_trigger = True
                else:
                    if isinstance(last, str):
                        last = datetime.fromisoformat(last)
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    would_trigger = (datetime.now(timezone.utc) - last).total_seconds() / 60 >= interval
        elif trigger_type == "threshold":
            summary.update({
                "metric": trigger_config.get("metric", ""),
                "operator": trigger_config.get("operator", ">="),
                "value": trigger_config.get("value", 0),
            })
            targets = await self._threshold_targets(trigger_config, {})
            targets = [tt for tt in targets if self._evaluate_conditions(rule, tt[2])]
            for target_type, target_id, ctx in targets:
                matching_targets.append({
                    "type": target_type,
                    "id": target_id or "",
                    "name": ctx.get("username") or ctx.get("node_name") or "",
                    "value": next((ctx[k] for k in ("percent", "traffic_gb", "users_online", "traffic_today_gb") if k in ctx), None),
                })
            would_trigger = bool(matching_targets)

        summary["targets"] = len(matching_targets)
        return {
            "rule_id": rule_id,
            "would_trigger": would_trigger,
            "matching_targets": matching_targets[:50],
            "estimated_actions": len(matching_targets) if matching_targets else (1 if would_trigger else 0),
            "details": "",
            "summary": summary,
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
        if event_type.startswith("torrent."):
            return "user"
        return "system"


# Module-level singleton
engine = AutomationEngine()

"""Traffic Rate Monitor — отслеживание аномально высокого потребления трафика.

Фоновая задача: периодически проверяет дельту raw_used_traffic_bytes per user
за настраиваемое окно. Если за N минут юзер потребил > X GB — уведомление в Telegram.
"""
import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Deque, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# (timestamp, raw_used_traffic_bytes) per user
_UserSnapshot = Tuple[float, int]

# Max snapshots per user (at 5-min intervals, 24 = 2 hours of history)
_MAX_SNAPSHOTS = 24


class TrafficRateMonitor:
    """Background monitor for traffic consumption rate per user."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        # user_uuid -> deque of (timestamp, raw_bytes)
        self._snapshots: Dict[str, Deque[_UserSnapshot]] = defaultdict(lambda: deque(maxlen=_MAX_SNAPSHOTS))
        # user_uuid -> last notification timestamp (cooldown)
        self._notified: Dict[str, float] = {}

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Traffic rate monitor started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Traffic rate monitor stopped")

    def _get_config(self):
        """Read config from config_service."""
        from shared.config_service import config_service
        return {
            "enabled": config_service.get("traffic_rate_enabled", False),
            "threshold_gb": float(config_service.get("traffic_rate_threshold_gb", 10.0) or 10.0),
            "window_minutes": int(config_service.get("traffic_rate_window_minutes", 60) or 60),
            "check_interval_minutes": int(config_service.get("traffic_rate_check_interval_minutes", 5) or 5),
            "cooldown_minutes": int(config_service.get("traffic_rate_cooldown_minutes", 60) or 60),
        }

    async def _run_loop(self):
        while self._running:
            try:
                cfg = self._get_config()
                interval = max(cfg["check_interval_minutes"], 1) * 60
                await asyncio.sleep(interval)

                if not self._running:
                    break
                if not cfg["enabled"]:
                    continue

                await self._check_traffic_rates(cfg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Traffic rate monitor error: %s", e)
                await asyncio.sleep(30)

    async def _check_traffic_rates(self, cfg: dict):
        """Take snapshot and check for rate violations."""
        from shared.database import db_service
        if not db_service.is_connected:
            return

        now = datetime.now(timezone.utc).timestamp()
        threshold_bytes = int(cfg["threshold_gb"] * 1024 ** 3)
        window_seconds = cfg["window_minutes"] * 60
        cooldown_seconds = cfg["cooldown_minutes"] * 60

        # Fetch current raw traffic for all users
        try:
            async with db_service.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT uuid::text, username, raw_used_traffic_bytes, traffic_limit_bytes "
                    "FROM users WHERE raw_used_traffic_bytes > 0"
                )
        except Exception as e:
            logger.warning("Failed to fetch user traffic: %s", e)
            return

        violators = []

        for row in rows:
            user_uuid = row["uuid"]
            current_bytes = int(row["raw_used_traffic_bytes"])
            username = row["username"] or user_uuid[:8]

            # Record snapshot
            self._snapshots[user_uuid].append((now, current_bytes))

            # Need at least 2 snapshots to calculate delta
            buf = self._snapshots[user_uuid]
            if len(buf) < 2:
                continue

            # Find oldest snapshot within the window
            cutoff = now - window_seconds
            oldest_in_window = None
            for ts, val in buf:
                if ts >= cutoff:
                    oldest_in_window = (ts, val)
                    break

            if oldest_in_window is None:
                continue

            old_ts, old_bytes = oldest_in_window
            elapsed = now - old_ts
            if elapsed < 60:  # need at least 1 minute of data
                continue

            delta_bytes = current_bytes - old_bytes
            if delta_bytes <= 0:
                continue

            if delta_bytes >= threshold_bytes:
                # Check cooldown
                last_notified = self._notified.get(user_uuid, 0)
                if now - last_notified < cooldown_seconds:
                    continue

                delta_gb = delta_bytes / (1024 ** 3)
                elapsed_min = elapsed / 60
                rate_gbh = delta_gb / (elapsed_min / 60) if elapsed_min > 0 else delta_gb

                violators.append({
                    "user_uuid": user_uuid,
                    "username": username,
                    "delta_gb": round(delta_gb, 2),
                    "elapsed_minutes": round(elapsed_min, 0),
                    "rate_gb_per_hour": round(rate_gbh, 2),
                    "traffic_limit_bytes": row["traffic_limit_bytes"],
                })
                self._notified[user_uuid] = now

        if not violators:
            return

        logger.info("Traffic rate violations: %d users exceeded %.1f GB/%d min",
                     len(violators), cfg["threshold_gb"], cfg["window_minutes"])

        # Send notifications
        for v in violators:
            await self._send_notification(v, cfg)

        # Cleanup old cooldown entries
        stale = [uid for uid, ts in self._notified.items() if now - ts > cooldown_seconds * 2]
        for uid in stale:
            del self._notified[uid]

    async def _send_notification(self, violator: dict, cfg: dict):
        """Send traffic rate violation notification."""
        try:
            from web.backend.core.notification_service import create_notification

            username = violator["username"]
            delta_gb = violator["delta_gb"]
            elapsed = int(violator["elapsed_minutes"])
            rate = violator["rate_gb_per_hour"]
            threshold = cfg["threshold_gb"]

            title = f"⚡ Высокое потребление трафика"
            body = (
                f"Пользователь <b>{_esc(username)}</b> потребил "
                f"<b>{delta_gb} GB</b> за {elapsed} мин "
                f"(~{rate} GB/ч)\n"
                f"Порог: {threshold} GB / {cfg['window_minutes']} мин"
            )

            user_uuid = violator["user_uuid"]
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "👤 Подробнее", "callback_data": f"vact:info:{user_uuid}"},
                        {"text": "🔒 Заблокировать", "callback_data": f"vact:block:{user_uuid}"},
                    ],
                    [
                        {"text": "⛔ Откл + разорвать", "callback_data": f"vact:kill:{user_uuid}"},
                        {"text": "🔄 Сбросить трафик", "callback_data": f"vact:reset:{user_uuid}"},
                    ],
                    [
                        {"text": "✅ Пропустить", "callback_data": f"vact:dismiss:{user_uuid}"},
                    ],
                ]
            }

            await create_notification(
                title=title,
                body=body,
                type="traffic_rate",
                severity="warning",
                source="traffic_rate_monitor",
                source_id=user_uuid,
                group_key=f"traffic_rate:{user_uuid}",
                channels=["telegram", "in_app"],
                topic_type="violations",
                telegram_body=body,
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error("Failed to send traffic rate notification for %s: %s",
                         violator["username"], e)


def _esc(text: str) -> str:
    """Escape HTML for Telegram."""
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


traffic_rate_monitor = TrafficRateMonitor()

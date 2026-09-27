"""Сторож синка с панелью: говорит админу, когда данные перестали обновляться.

27.09.2026 периодический синк в коллекторе встал посреди сетевого сбоя у
хостера и 12 часов молчал. Трафик, HWID и аналитика в админке застыли, а
монитор расхода сравнивал свежие цифры панели с полусуточными из базы и
присылал ложные «70 ГБ за 55 минут». Заметили случайно.

Сторож живёт в API-процессе, а не в коллекторе рядом с синком: так он видит
и зависший проход, и умерший цикл, и лежащий коллектор целиком. Смотрит на
время последнего УСПЕШНОГО синка пользователей: неудачный проход тоже ставит
отметку времени, и по ней одной «панель недоступна» не отличить от «всё идёт».
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from shared.logger import logger

CHECK_INTERVAL_SECONDS = 60
# Одного-двух пропущенных проходов мало, чтобы будить админа
_MIN_STALL = timedelta(minutes=15)


class SyncWatchdog:
    """Помнит последний успешный синк и то, предупредили ли уже админа."""

    def __init__(self, now: Optional[datetime] = None) -> None:
        # Отсчёт не раньше старта сторожа: после перезапуска коллектору нужно
        # время на первый проход, и полусуточная отметка в базе — не повод
        # поднимать тревогу в первую же минуту
        self._started_at = now or datetime.now(timezone.utc)
        self._last_ok: Optional[datetime] = None
        self._alerted = False

    async def check(self, now: Optional[datetime] = None) -> None:
        from shared.database import db_service
        from shared.sync import SyncService

        now = now or datetime.now(timezone.utc)
        meta = await db_service.get_sync_metadata("users")
        if not meta:
            return  # синк здесь не шёл ни разу — он не настроен, а не встал

        last = meta.get("last_sync_at")
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if meta.get("sync_status") == "success" and last is not None:
            self._last_ok = max(self._last_ok, last) if self._last_ok else last

        since = max(self._last_ok, self._started_at) if self._last_ok else self._started_at
        stalled = now - since
        limit = max(timedelta(seconds=3 * SyncService._get_sync_interval()), _MIN_STALL)

        if stalled > limit and not self._alerted:
            self._alerted = True
            minutes = int(stalled.total_seconds() // 60)
            logger.error("sync_watchdog: синк с панелью не проходит %d мин", minutes)
            await _notify(
                "⏸ Синк с панелью стоит",
                f"Последний успешный синк пользователей — {minutes} мин назад. "
                "Трафик, HWID и аналитика в админке не обновляются.\n"
                "Проверь связь с панелью и лог коллектора (web-collector).",
                severity="warning",
            )
        elif stalled <= limit and self._alerted:
            self._alerted = False
            logger.info("sync_watchdog: синк с панелью возобновился")
            await _notify(
                "▶️ Синк с панелью возобновился",
                "Данные в админке снова обновляются.",
                severity="info",
            )


async def _notify(title: str, body: str, *, severity: str) -> None:
    try:
        from web.backend.core.notification_service import create_notification
        await create_notification(
            title=title,
            body=body,
            type="alert",
            severity=severity,
            channels=["in_app", "telegram"],
            topic_type="errors",
            source="sync",
            group_key="sync_stalled",
        )
    except Exception as exc:  # noqa: BLE001 — уведомление не должно ронять сторожа
        logger.warning("sync_watchdog: уведомление не ушло: %s", exc)


async def loop() -> None:
    """Фоновый цикл сторожа."""
    watchdog = SyncWatchdog()
    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        try:
            await watchdog.check()
        except Exception as e:  # noqa: BLE001 — сбой базы не должен ронять сторожа
            logger.warning("sync_watchdog: проверка не удалась: %s", e)

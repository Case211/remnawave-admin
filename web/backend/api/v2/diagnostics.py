"""Снимок памяти: что занято под кэши и сколько живёт фоновых задач.

Ставится по следам разбора, где память админки на установке с десятками тысяч
онлайна росла до потолка за час-три после рестарта. Причину тогда пришлось
искать по коду вслепую: с работающей установки снять было нечего. Здесь ровно
то, чего не хватало — размеры всех словарей-кэшей, число фоновых задач и RSS
процесса, одним запросом и одной кнопкой в Telegram.

Снимок ничего не чинит и ничего не меняет: только читает счётчики.
"""
import asyncio
import gc
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from web.backend.core.errors import api_error, E
from web.backend.api.deps import AdminUser, require_permission
from shared.logger import logger

router = APIRouter()

# Куда слать снимок, если адресат не передан явно. Telegram не умеет доставлять
# в личку по @username — нужен числовой chat_id, и получатель должен хотя бы раз
# написать боту сам.
_CHAT_SETTING_KEY = "diagnostics_telegram_chat_id"


class MemorySnapshotSend(BaseModel):
    """Куда отправить снимок. Пусто — берём чат из настроек уведомлений."""
    chat_id: Optional[str] = None


def _rss_bytes() -> Optional[int]:
    """Резидентная память процесса. /proc есть только на Linux — на нём и живём."""
    try:
        with open(f"/proc/{os.getpid()}/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    return None


def _sizeof_deep(obj: Any, limit: int = 2000) -> int:
    """Грубая оценка веса контейнера: сам словарь плюс первые `limit` значений.

    Полный обход большого кэша сам по себе стоит дорого, поэтому берём выборку
    и масштабируем — для «что именно раздулось» точности хватает.
    """
    try:
        base = sys.getsizeof(obj)
        if not isinstance(obj, dict) or not obj:
            return base
        keys = list(obj.keys())[:limit]
        sample = sum(sys.getsizeof(k) + sys.getsizeof(obj[k]) for k in keys)
        if len(keys) < len(obj):
            sample = int(sample * (len(obj) / len(keys)))
        return base + sample
    except Exception:
        return 0


def _collect_caches() -> List[Dict[str, Any]]:
    """Размеры известных кэшей. Каждый — потенциальное место утечки."""
    entries: List[Dict[str, Any]] = []

    def add(name: str, container: Any, note: str = "") -> None:
        try:
            entries.append({
                "name": name,
                "items": len(container),
                "bytes": _sizeof_deep(container),
                "note": note,
            })
        except Exception:
            pass

    try:
        from shared.database import db_service
        add("db.whitelist_cache", getattr(db_service, "_whitelist_cache", {}), "белый список по пользователям")
        add("db.raw_data_id_cache", getattr(db_service, "_raw_data_id_cache", {}))
    except Exception:
        pass

    try:
        from web.backend.api.v2 import collector as collector_api
        add("collector.pending_violation_users", collector_api._pending_violation_users,
            "очередь на проверку нарушений")
        add("collector.background_tasks", collector_api._background_tasks, "фоновые задачи коллектора")
        add("collector.node_name_cache", collector_api._node_name_cache)
        add("collector.node_last_batch", collector_api._node_last_batch)
    except Exception:
        pass

    try:
        from web.backend.core import violation_notifier
        add("notifier.violation_notification_cache",
            violation_notifier._violation_notification_cache)
    except Exception:
        pass

    try:
        from web.backend.core import admin_accounts
        add("auth.admin_account_cache", admin_accounts._admin_account_cache)
    except Exception:
        pass

    return sorted(entries, key=lambda e: e["bytes"], reverse=True)


def _collect_detector_caches() -> List[Dict[str, Any]]:
    """Кэши анализаторов живут внутри детектора — достаём, если он поднят."""
    entries: List[Dict[str, Any]] = []
    try:
        from web.backend.api.v2 import collector as collector_api
        detector = getattr(collector_api, "_detector", None) or getattr(collector_api, "detector", None)
        if detector is None:
            return entries
        srh = getattr(detector, "_srh_cache", None)
        if srh is not None:
            entries.append({"name": "detector.srh_cache", "items": len(srh),
                            "bytes": _sizeof_deep(srh), "note": ""})
        profile = getattr(detector, "profile_analyzer", None)
        baseline = getattr(profile, "_baseline_cache", None) if profile else None
        if baseline is not None:
            entries.append({"name": "detector.baseline_cache", "items": len(baseline),
                            "bytes": _sizeof_deep(baseline), "note": "профили поведения"})
        bg = getattr(detector, "_baseline_bg_task", None)
        entries.append({"name": "detector.baseline_bg_task", "items": 0 if bg is None or bg.done() else 1,
                        "bytes": 0, "note": "фоновая достройка профилей"})
    except Exception:
        pass
    return entries


def _snapshot() -> Dict[str, Any]:
    tasks = [t for t in asyncio.all_tasks() if not t.done()] if _loop_running() else []
    caches = _collect_caches() + _collect_detector_caches()
    return {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "rss_bytes": _rss_bytes(),
        "asyncio_tasks": len(tasks),
        "gc_objects": len(gc.get_objects()) if os.getenv("DIAG_COUNT_GC_OBJECTS") == "1" else None,
        "gc_counts": list(gc.get_count()),
        "caches": sorted(caches, key=lambda e: e["bytes"], reverse=True),
    }


def _loop_running() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _human(size: Optional[int]) -> str:
    if size is None:
        return "—"
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            return f"{value:.0f} {unit}" if unit == "Б" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ГБ"


def _as_text(snap: Dict[str, Any]) -> str:
    """Снимок в вид, пригодный для сообщения в Telegram."""
    lines = [
        f"Память процесса: {_human(snap['rss_bytes'])}",
        f"Задач asyncio: {snap['asyncio_tasks']}",
        f"Поколения GC: {', '.join(str(c) for c in snap['gc_counts'])}",
        "",
        "Кэши (по весу):",
    ]
    for entry in snap["caches"][:15]:
        note = f" — {entry['note']}" if entry["note"] else ""
        lines.append(f"• {entry['name']}: {entry['items']} шт, {_human(entry['bytes'])}{note}")
    if not snap["caches"]:
        lines.append("• ничего не найдено (сервис только поднялся?)")
    return "\n".join(lines)


@router.get("/memory")
async def memory_snapshot(
    admin: AdminUser = Depends(require_permission("settings", "view")),
):
    """Снимок памяти: кэши, фоновые задачи, RSS."""
    return _snapshot()


@router.post("/memory/send")
async def send_memory_snapshot(
    body: MemorySnapshotSend,
    admin: AdminUser = Depends(require_permission("settings", "edit")),
):
    """Отправить снимок в Telegram — тем же каналом, что и обычные уведомления."""
    from web.backend.core.notification_service import send_telegram

    chat_id = (body.chat_id or "").strip()
    if not chat_id:
        # Сохранённый адресат: чтобы кнопка работала без ввода каждый раз
        try:
            from shared.config_service import config_service
            chat_id = str(config_service.get(_CHAT_SETTING_KEY, "") or "")
        except Exception:
            chat_id = ""
    if not chat_id:
        raise api_error(400, E.INVALID_INPUT, "Telegram chat is not configured")

    snap = _snapshot()
    ok = await send_telegram(
        chat_id,
        "Снимок памяти админки",
        _as_text(snap),
    )
    if not ok:
        raise api_error(502, "TELEGRAM_SEND_FAILED", "Telegram send failed")

    logger.info("Memory snapshot sent to Telegram by admin %s", admin.username)
    return {"sent": True, "chat_id": chat_id, "snapshot": snap}

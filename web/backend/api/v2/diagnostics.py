"""Снимок состояния для разбора инцидентов: процесс, хост, онлайн, база, кэши.

Ставится по следам разбора, где память админки на установке с десятками тысяч
онлайна росла до потолка за час-три после рестарта. Причину пришлось искать по
коду вслепую: с работающей установки снять было нечего.

Первая версия снимала только web-backend — и на раздельной установке получала
пустой процесс: детект, очередь нарушений и все тяжёлые кэши живут в
коллекторе. Теперь снимок собирается в том процессе, где его запросили, а
режим api дополнительно опрашивает коллектор и склеивает оба. Сверху — то,
без чего диагноз не поставить: железо и нагрузка хоста, онлайн и число нод,
размер базы, что в ней пишется и вычищается, долгие запросы и ожидания.

Одиночный снимок почти бесполезен — инцидент виден в динамике. Всё в файле
устроено так, чтобы два замера можно было сравнить: накопительные счётчики
CPU и записи, размеры кэшей, глубина очереди.

Снимок ничего не чинит и ничего не меняет: только читает счётчики.
"""
import asyncio
import gc
import hashlib
import hmac
import os
import random
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core.config import get_web_settings
from shared.logger import logger

router = APIRouter()

# Внутренний адрес коллектора в раздельном режиме: имя контейнера из compose и
# его WEB_PORT. Переопределяется, если контейнер назван иначе.
_COLLECTOR_URL = os.environ.get("COLLECTOR_INTERNAL_URL", "http://remnawave-web-collector:8081")


def _plain(value: Any) -> Any:
    """Привести ответ базы к тому, что умеет JSON.

    asyncpg отдаёт bigint-агрегаты и extract(epoch) как Decimal, а метки
    времени — как datetime; JSONResponse ни того, ни другого не сериализует.
    На живой установке серия собиралась целиком и падала уже на отдаче
    файла — локально без базы это не всплывало.
    """
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


# ── процесс ──────────────────────────────────────────────────────────────────

def _proc_status() -> Dict[str, Optional[int]]:
    """RSS, пик RSS и потоки из /proc — есть только на Linux, на нём и живём."""
    out: Dict[str, Optional[int]] = {"rss_bytes": None, "rss_peak_bytes": None, "threads": None}
    try:
        with open(f"/proc/{os.getpid()}/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    out["rss_bytes"] = int(line.split()[1]) * 1024
                elif line.startswith("VmHWM:"):
                    out["rss_peak_bytes"] = int(line.split()[1]) * 1024
                elif line.startswith("Threads:"):
                    out["threads"] = int(line.split()[1])
    except Exception:
        pass
    return out


def _cpu_seconds() -> Dict[str, float]:
    """Накопленное CPU-время процесса: разница двух снимков и есть нагрузка.

    os.times() вместо resource: последний есть только на Unix, а тесты гоняются
    и на Windows.
    """
    t = os.times()
    return {"user": round(t.user, 2), "system": round(t.system, 2)}


def _uptime_seconds() -> Optional[float]:
    try:
        with open("/proc/self/stat", encoding="utf-8") as f:
            start_ticks = int(f.read().split(")")[-1].split()[19])
        with open("/proc/uptime", encoding="utf-8") as f:
            sys_uptime = float(f.read().split()[0])
        ticks = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
        return round(sys_uptime - start_ticks / ticks, 1)
    except Exception:
        return None


# ── хост ─────────────────────────────────────────────────────────────────────

def _host() -> Dict[str, Any]:
    """Железо и нагрузка машины. В контейнере /proc показывает хост, не cgroup."""
    out: Dict[str, Any] = {"cpu_count": os.cpu_count()}
    try:
        out["load_avg"] = [round(x, 2) for x in os.getloadavg()]
    except Exception:
        out["load_avg"] = None
    try:
        mem: Dict[str, int] = {}
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                key, _, rest = line.partition(":")
                if key in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree", "Cached"):
                    mem[key] = int(rest.split()[0]) * 1024
        out["mem_total_bytes"] = mem.get("MemTotal")
        out["mem_available_bytes"] = mem.get("MemAvailable")
        out["page_cache_bytes"] = mem.get("Cached")
        if mem.get("SwapTotal") is not None and mem.get("SwapFree") is not None:
            out["swap_used_bytes"] = mem["SwapTotal"] - mem["SwapFree"]
    except Exception:
        pass
    # Лимит памяти контейнера — если задан, именно в него упирается OOM, а не в хост
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read().strip()
            if raw and raw != "max" and int(raw) < (1 << 60):
                out["cgroup_mem_limit_bytes"] = int(raw)
            break
        except Exception:
            continue
    try:
        st = os.statvfs("/app/logs" if os.path.isdir("/app/logs") else "/")
        out["disk_free_bytes"] = st.f_bavail * st.f_frsize
        out["disk_total_bytes"] = st.f_blocks * st.f_frsize
    except Exception:
        pass
    return out


# ── база ─────────────────────────────────────────────────────────────────────

async def _database() -> Dict[str, Any]:
    """Что происходит в Postgres: размер, запись, вакуум, соединения, долгие запросы."""
    out: Dict[str, Any] = {}
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"error": "нет соединения с базой"}
        async with db_service.acquire() as conn:
            out["size_bytes"] = await conn.fetchval("SELECT pg_database_size(current_database())")

            # Онлайн и масштаб: активные соединения, пользователи, ноды
            out["active_connections"] = await conn.fetchval(
                "SELECT count(*) FROM user_connections WHERE disconnected_at IS NULL"
            )
            out["connections_last_hour"] = await conn.fetchval(
                "SELECT count(*) FROM user_connections WHERE connected_at > now() - interval '1 hour'"
            )
            out["users_total"] = await conn.fetchval("SELECT count(*) FROM users")
            out["nodes_total"] = await conn.fetchval("SELECT count(*) FROM nodes")
            out["nodes_connected"] = await conn.fetchval(
                "SELECT count(*) FROM nodes WHERE is_connected = true"
            )

            # Кто пишет: топ таблиц по апдейтам/вставкам за аптайм базы
            rows = await conn.fetch(
                """SELECT s.relname, n_live_tup, n_dead_tup, n_tup_ins, n_tup_upd, n_tup_hot_upd,
                          n_tup_del, pg_total_relation_size(relid) AS total_bytes,
                          last_autovacuum, c.reloptions
                     FROM pg_stat_user_tables s JOIN pg_class c ON c.oid = s.relid
                    ORDER BY n_tup_upd + n_tup_ins DESC LIMIT 12"""
            )
            out["top_tables"] = [
                {
                    "table": r["relname"], "live": r["n_live_tup"], "dead": r["n_dead_tup"],
                    "ins": r["n_tup_ins"], "upd": r["n_tup_upd"], "hot_upd": r["n_tup_hot_upd"],
                    "del": r["n_tup_del"], "bytes": r["total_bytes"],
                    "last_autovacuum": r["last_autovacuum"].isoformat() if r["last_autovacuum"] else None,
                    "options": list(r["reloptions"] or []),
                }
                for r in rows
            ]

            # Индексы: размер и сколько раз их брал планировщик — лишние
            # снимаются по цифрам, а не по догадкам
            rows = await conn.fetch(
                """SELECT relname, indexrelname, idx_scan,
                          pg_relation_size(indexrelid) AS bytes
                     FROM pg_stat_user_indexes
                    ORDER BY pg_relation_size(indexrelid) DESC LIMIT 15"""
            )
            out["top_indexes"] = [
                {"table": r["relname"], "index": r["indexrelname"], "scans": r["idx_scan"], "bytes": r["bytes"]}
                for r in rows
            ]

            # Буферы: buffers_backend, догоняющий buffers_checkpoint, — признак
            # нехватки shared_buffers
            bg = await conn.fetchrow(
                "SELECT buffers_checkpoint, buffers_clean, buffers_backend, "
                "checkpoints_timed, checkpoints_req FROM pg_stat_bgwriter"
            )
            out["bgwriter"] = dict(bg) if bg else None

            # WAL за аптайм — главный показатель объёма записи
            try:
                wal = await conn.fetchrow("SELECT wal_records, wal_fpi, wal_bytes FROM pg_stat_wal")
                out["wal"] = dict(wal) if wal else None
            except Exception:
                out["wal"] = None

            # Соединения к базе: сколько всего, сколько ждут, самый долгий запрос
            act = await conn.fetchrow(
                """SELECT count(*) AS total,
                          count(*) FILTER (WHERE state = 'active') AS active,
                          count(*) FILTER (WHERE wait_event_type = 'Lock') AS waiting_lock,
                          count(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_tx,
                          coalesce(max(extract(epoch FROM now() - query_start))
                                   FILTER (WHERE state = 'active' AND pid <> pg_backend_pid()), 0)
                              AS longest_active_seconds
                     FROM pg_stat_activity WHERE datname = current_database()"""
            )
            out["activity"] = {k: (round(float(v), 1) if k == "longest_active_seconds" else v)
                               for k, v in dict(act).items()} if act else None

            # Долгие запросы прямо сейчас — что именно висит
            slow = await conn.fetch(
                """SELECT round(extract(epoch FROM now() - query_start))::int AS seconds,
                          state, wait_event_type, left(regexp_replace(query, '\\s+', ' ', 'g'), 160) AS query
                     FROM pg_stat_activity
                    WHERE datname = current_database() AND state <> 'idle'
                      AND pid <> pg_backend_pid()
                      AND now() - query_start > interval '2 seconds'
                    ORDER BY query_start LIMIT 8"""
            )
            out["slow_queries"] = [dict(r) for r in slow]

            settings = await conn.fetch(
                "SELECT name, setting, unit FROM pg_settings WHERE name IN "
                "('shared_buffers','effective_cache_size','work_mem','max_connections','autovacuum')"
            )
            out["settings"] = {r["name"]: (f"{r['setting']}{r['unit'] or ''}") for r in settings}
            out["uptime_seconds"] = await conn.fetchval(
                "SELECT round(extract(epoch FROM now() - pg_postmaster_start_time()))::bigint"
            )
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return _plain(out)


# ── кэши и очереди ───────────────────────────────────────────────────────────

def _sizeof_deep(obj: Any, limit: int = 2000) -> int:
    """Грубая оценка веса контейнера: сам контейнер плюс первые `limit` элементов.

    Полный обход большого кэша сам по себе стоит дорого, поэтому берём выборку
    и масштабируем — для «что именно раздулось» точности хватает.
    """
    try:
        base = sys.getsizeof(obj)
        if isinstance(obj, dict):
            if not obj:
                return base
            keys = list(obj.keys())[:limit]
            sample = sum(sys.getsizeof(k) + sys.getsizeof(obj[k]) for k in keys)
            if len(keys) < len(obj):
                sample = int(sample * (len(obj) / len(keys)))
            return base + sample
        if isinstance(obj, (set, list, tuple)):
            if not obj:
                return base
            items = list(obj)[:limit]
            sample = sum(sys.getsizeof(i) for i in items)
            if len(items) < len(obj):
                sample = int(sample * (len(obj) / len(items)))
            return base + sample
        return base
    except Exception:
        return 0


def _entry(name: str, container: Any, note: str = "") -> Optional[Dict[str, Any]]:
    try:
        return {"name": name, "items": len(container), "bytes": _sizeof_deep(container), "note": note}
    except Exception:
        return None


def _collect_caches() -> List[Dict[str, Any]]:
    """Все известные держатели памяти этого процесса. Каждый — кандидат в утечку."""
    entries: List[Optional[Dict[str, Any]]] = []

    try:
        from shared.database import db_service
        entries.append(_entry("db.whitelist_cache", getattr(db_service, "_whitelist_cache", {}),
                              "белый список по пользователям"))
        entries.append(_entry("db.raw_data_id_cache", getattr(db_service, "_raw_data_id_cache", {}),
                              "id панели → uuid"))
    except Exception:
        pass

    # Коллектор и детектор — импорт модуля в режиме api безвреден: роутер не
    # подключён, а состояние в нём просто пустое.
    try:
        from web.backend.api.v2 import collector as c
        entries.append(_entry("collector.pending_violation_users", c._pending_violation_users,
                              "очередь на проверку нарушений"))
        entries.append(_entry("collector.violation_check_cooldown", c._violation_check_cooldown,
                              "кулдаун повторных проверок"))
        entries.append(_entry("collector.background_tasks",
                              {t for t in c._background_tasks if not t.done()}, "живые фоновые задачи"))
        entries.append(_entry("collector.node_name_cache", c._node_name_cache))
        entries.append(_entry("collector.node_last_batch", c._node_last_batch))

        det = getattr(c, "violation_detector", None)
        if det is not None:
            entries.append(_entry("detector.srh_cache", getattr(det, "_srh_cache", {}),
                                  "история запросов подписки по пользователям"))
            prof = getattr(det, "profile_analyzer", None)
            if prof is not None:
                entries.append(_entry("detector.baseline_cache", getattr(prof, "_baseline_cache", {}),
                                      "профили поведения"))
            bg = getattr(det, "_baseline_bg_task", None)
            entries.append({"name": "detector.baseline_bg_task",
                            "items": 0 if bg is None or bg.done() else 1, "bytes": 0,
                            "note": "фоновая достройка профилей"})
            for attr in ("geo_analyzer", "asn_analyzer", "device_analyzer", "hwid_analyzer",
                         "user_agent_analyzer", "temporal_analyzer"):
                an = getattr(det, attr, None)
                if an is None:
                    continue
                for field, val in vars(an).items():
                    if isinstance(val, (dict, set, list)) and len(val) > 0:
                        entries.append(_entry(f"detector.{attr}.{field}", val))
    except Exception:
        pass

    try:
        from web.backend.core import violation_notifier
        entries.append(_entry("notifier.violation_notification_cache",
                              violation_notifier._violation_notification_cache))
    except Exception:
        pass

    try:
        from web.backend.core import admin_accounts
        entries.append(_entry("auth.admin_account_cache", admin_accounts._admin_account_cache))
    except Exception:
        pass

    return sorted((e for e in entries if e), key=lambda e: e["bytes"], reverse=True)


def _collector_stats() -> Optional[Dict[str, Any]]:
    """Счётчики конвейера коллектора — есть только там, где он поднят."""
    try:
        from web.backend.api.v2 import collector as c
        st = dict(c._stats)
        st["pending_users"] = len(c._pending_violation_users)
        return st
    except Exception:
        return None


def _tasks_by_name(limit: int = 15) -> List[Dict[str, Any]]:
    """Живые задачи asyncio, сгруппированные по корутине: кто размножился."""
    counts: Dict[str, int] = {}
    try:
        for t in asyncio.all_tasks():
            if t.done():
                continue
            coro = t.get_coro()
            name = getattr(coro, "__qualname__", None) or getattr(coro, "__name__", None) or repr(coro)[:60]
            counts[name] = counts.get(name, 0) + 1
    except Exception:
        pass
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [{"coroutine": n, "count": c} for n, c in top]


def _process_snapshot() -> Dict[str, Any]:
    proc = _proc_status()
    tasks = _tasks_by_name(10_000)
    return {
        "app_mode": os.environ.get("APP_MODE", "full").lower(),
        "pid": os.getpid(),
        "uptime_seconds": _uptime_seconds(),
        "rss_bytes": proc["rss_bytes"],
        "rss_peak_bytes": proc["rss_peak_bytes"],
        "threads": proc["threads"],
        "cpu_seconds": _cpu_seconds(),
        "asyncio_tasks": sum(t["count"] for t in tasks),
        "tasks_by_coroutine": tasks[:15],
        "gc_counts": list(gc.get_count()),
        "collector_stats": _collector_stats(),
        "caches": _collect_caches(),
    }


# ── сборка ───────────────────────────────────────────────────────────────────

def _internal_secret() -> str:
    """Ключ, которым api забирает снимок у коллектора.

    INTERNAL_API_SECRET, если задан. Без него — производный от WEB_SECRET_KEY:
    тот обязателен для backend, а коллектор крутится на том же образе с тем же
    .env, так что ключ совпадает у обоих и настраивать ничего не нужно. Раньше
    без INTERNAL_API_SECRET серия оставалась без коллектора, а на раздельных
    установках он как раз обычно не задан. Совсем без проверки нельзя: порт
    коллектора смотрит наружу, а снимок обходит все кэши детектора.
    """
    explicit = os.environ.get("INTERNAL_API_SECRET", "")
    if explicit:
        return explicit
    key = get_web_settings().secret_key.encode("utf-8")
    return hmac.new(key, b"remnawave-admin:collector-diagnostics", hashlib.sha256).hexdigest()


async def _fetch_collector_snapshot() -> Dict[str, Any]:
    """В режиме api тяжёлое живёт в коллекторе — забираем его снимок по внутреннему URL."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{_COLLECTOR_URL}/api/v2/collector/diagnostics/memory",
                headers={"X-Internal-Api-Secret": _internal_secret()},
            )
        if resp.status_code != 200:
            return {"error": f"коллектор ответил {resp.status_code}"}
        return resp.json()
    except Exception as e:
        return {"error": f"коллектор недоступен: {e}"}


async def _full_snapshot() -> Dict[str, Any]:
    mine = _process_snapshot()
    result: Dict[str, Any] = {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "host": _host(),
        "database": await _database(),
        "processes": [mine],
    }
    if mine["app_mode"] == "api":
        other = await _fetch_collector_snapshot()
        if "error" in other:
            result["collector_error"] = other["error"]
        else:
            result["processes"].append(other)
    return result


# ── вывод ────────────────────────────────────────────────────────────────────

def _human(size: Optional[int]) -> str:
    if size is None:
        return "—"
    value = float(size)
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if value < 1024 or unit == "ГБ":
            return f"{value:.0f} {unit}" if unit == "Б" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} ГБ"


def _as_text(full: Dict[str, Any]) -> str:
    lines = [f"Снимок: {full['taken_at']}", ""]

    h = full.get("host") or {}
    lines.append("=== Хост")
    lines.append(f"Ядер: {h.get('cpu_count')}, load average: {h.get('load_avg')}")
    lines.append(f"Память: всего {_human(h.get('mem_total_bytes'))}, доступно {_human(h.get('mem_available_bytes'))}, "
                 f"page cache {_human(h.get('page_cache_bytes'))}, swap занят {_human(h.get('swap_used_bytes'))}")
    if h.get("cgroup_mem_limit_bytes"):
        lines.append(f"Лимит памяти контейнера: {_human(h['cgroup_mem_limit_bytes'])}")
    lines.append(f"Диск: свободно {_human(h.get('disk_free_bytes'))} из {_human(h.get('disk_total_bytes'))}")
    lines.append("")

    d = full.get("database") or {}
    lines.append("=== База")
    if d.get("error"):
        lines.append(f"⚠ {d['error']}")
    else:
        up = d.get("uptime_seconds") or 0
        lines.append(f"Размер {_human(d.get('size_bytes'))}, аптайм {up // 3600} ч, настройки: {d.get('settings')}")
        lines.append(f"Онлайн (активных соединений): {d.get('active_connections')}, за час: {d.get('connections_last_hour')}; "
                     f"пользователей {d.get('users_total')}, нод {d.get('nodes_connected')}/{d.get('nodes_total')}")
        a = d.get("activity") or {}
        lines.append(f"Соединений к БД: {a.get('total')}, активных {a.get('active')}, ждут блокировку {a.get('waiting_lock')}, "
                     f"idle in tx {a.get('idle_in_tx')}, самый долгий запрос {a.get('longest_active_seconds')} с")
        bg = d.get("bgwriter") or {}
        lines.append(f"Буферы: checkpoint {bg.get('buffers_checkpoint')}, backend {bg.get('buffers_backend')} "
                     f"(backend ≈ checkpoint → мало shared_buffers); чекпоинтов по таймеру {bg.get('checkpoints_timed')}, "
                     f"по требованию {bg.get('checkpoints_req')}")
        w = d.get("wal") or {}
        if w:
            lines.append(f"WAL за аптайм: {_human(w.get('wal_bytes'))}, записей {w.get('wal_records')}")
        if d.get("slow_queries"):
            lines.append("Долгие запросы сейчас:")
            for q in d["slow_queries"]:
                lines.append(f"   {q['seconds']} с [{q['state']}{'/' + q['wait_event_type'] if q.get('wait_event_type') else ''}] {q['query']}")
        lines.append("Таблицы по записи (live/dead, ins/upd/hot/del):")
        for t in d.get("top_tables", [])[:8]:
            hot = f"{100 * t['hot_upd'] / t['upd']:.0f}%" if t["upd"] else "—"
            opts = f" [{', '.join(t['options'])}]" if t.get("options") else ""
            lines.append(f"   {t['table']}: {_human(t['bytes'])}, {t['live']}/{t['dead']}, "
                         f"{t['ins']}/{t['upd']}/{hot}/{t['del']}{opts}")
        if d.get("top_indexes"):
            lines.append("Индексы по размеру (сканов за аптайм):")
            for i in d["top_indexes"][:10]:
                lines.append(f"   {i['index']} на {i['table']}: {_human(i['bytes'])}, {i['scans']}")
    lines.append("")

    if full.get("collector_error"):
        lines += [f"⚠ Коллектор: {full['collector_error']}", ""]

    for p in full["processes"]:
        cpu = p.get("cpu_seconds") or {}
        up = p.get("uptime_seconds")
        head = f"=== Процесс: {p.get('app_mode')} (pid {p.get('pid')}"
        head += f", аптайм {up:.0f} с)" if up else ")"
        lines.append(head)
        lines.append(f"Память: {_human(p.get('rss_bytes'))}, пик {_human(p.get('rss_peak_bytes'))}, потоков {p.get('threads')}")
        lines.append(f"CPU накоплено: user {cpu.get('user')} с, system {cpu.get('system')} с")
        lines.append(f"Задач asyncio: {p.get('asyncio_tasks')}")
        for t in p.get("tasks_by_coroutine", [])[:6]:
            lines.append(f"   {t['count']:>4} × {t['coroutine']}")
        cs = p.get("collector_stats")
        if cs:
            lines.append(f"Коллектор: очередь {cs.get('pending_users')}, пик очереди {cs.get('peak_queue_size')}, "
                         f"последний проход {cs.get('last_drain_duration_ms')} мс, "
                         f"батчей {cs.get('total_batches_received')}, нарушений {cs.get('total_violations_found')}, "
                         f"задач сброшено {cs.get('total_tasks_dropped')}")
        lines.append("Кэши (по весу):")
        shown_empty = 0
        for c in p.get("caches", []):
            if c["items"] == 0:
                shown_empty += 1
                if shown_empty > 3:
                    continue
            note = f" — {c['note']}" if c.get("note") else ""
            lines.append(f"   {c['name']}: {c['items']} шт, {_human(c['bytes'])}{note}")
        lines.append("")
    return "\n".join(lines)


# ── серия снимков ────────────────────────────────────────────────────────────
#
# Один снимок инцидент не показывает: утечка и всплеск видны только в динамике.
# Серия снимает несколько минут со случайным шагом 1–15 с — случайным, чтобы
# не попадать в такт периодическим задачам и не пропускать их пики. Состояние
# живёт в памяти процесса: серия одна на процесс, рестарт её сбрасывает.

_SERIES_MIN_INTERVAL = 1
_SERIES_MAX_INTERVAL = 15
_SERIES_DEFAULT_MINUTES = 3
_SERIES_MAX_MINUTES = 15

_series: Dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "duration_seconds": 0,
    "snapshots": [],
    "error": None,
    "task": None,
}


class SeriesStart(BaseModel):
    minutes: int = _SERIES_DEFAULT_MINUTES


async def _run_series(duration_seconds: int) -> None:
    """Снимать до истечения времени; каждый снимок — полный, с базой и коллектором."""
    started = datetime.now(timezone.utc)
    _series.update({
        "running": True, "started_at": started.isoformat(), "finished_at": None,
        "duration_seconds": duration_seconds, "snapshots": [], "error": None,
    })
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_seconds
        while True:
            _series["snapshots"].append(await _full_snapshot())
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(remaining, random.uniform(_SERIES_MIN_INTERVAL, _SERIES_MAX_INTERVAL)))
    except asyncio.CancelledError:
        _series["error"] = "остановлено"
        raise
    except Exception as e:  # один сбойный снимок не должен уронить серию целиком
        _series["error"] = f"{type(e).__name__}: {e}"
        logger.warning("Diagnostics series failed: %s", e)
    finally:
        _series["running"] = False
        _series["finished_at"] = datetime.now(timezone.utc).isoformat()
        _series["task"] = None


def _series_public() -> Dict[str, Any]:
    """Состояние серии без объекта задачи и без тяжёлых снимков — для опроса с фронта."""
    snaps = _series["snapshots"]
    elapsed = 0.0
    if _series["started_at"]:
        start = datetime.fromisoformat(_series["started_at"])
        end = datetime.fromisoformat(_series["finished_at"]) if _series["finished_at"] else datetime.now(timezone.utc)
        elapsed = (end - start).total_seconds()
    return {
        "running": _series["running"],
        "started_at": _series["started_at"],
        "finished_at": _series["finished_at"],
        "duration_seconds": _series["duration_seconds"],
        "elapsed_seconds": round(elapsed),
        "snapshots_taken": len(snaps),
        "error": _series["error"],
        "has_result": bool(snaps) and not _series["running"],
    }


def _series_result() -> Dict[str, Any]:
    """Готовый результат серии: все снимки плюс сводка «что выросло»."""
    snaps = _series["snapshots"]
    summary: Dict[str, Any] = {}
    if len(snaps) >= 2:
        first, last = snaps[0], snaps[-1]
        growth: Dict[str, Any] = {}
        for p_last in last["processes"]:
            mode = p_last.get("app_mode")
            p_first = next((p for p in first["processes"] if p.get("app_mode") == mode), None)
            if not p_first:
                continue
            caches_first = {c["name"]: c for c in p_first.get("caches", [])}
            cache_growth = []
            for c in p_last.get("caches", []):
                before = caches_first.get(c["name"])
                if before is None:
                    continue
                d_items = c["items"] - before["items"]
                d_bytes = c["bytes"] - before["bytes"]
                if d_items or d_bytes:
                    cache_growth.append({"name": c["name"], "items_delta": d_items, "bytes_delta": d_bytes})
            cache_growth.sort(key=lambda g: g["bytes_delta"], reverse=True)
            cpu_f, cpu_l = p_first.get("cpu_seconds") or {}, p_last.get("cpu_seconds") or {}
            growth[mode] = {
                "rss_delta_bytes": (p_last.get("rss_bytes") or 0) - (p_first.get("rss_bytes") or 0),
                "cpu_user_delta": round((cpu_l.get("user") or 0) - (cpu_f.get("user") or 0), 2),
                "cpu_system_delta": round((cpu_l.get("system") or 0) - (cpu_f.get("system") or 0), 2),
                "asyncio_tasks_delta": (p_last.get("asyncio_tasks") or 0) - (p_first.get("asyncio_tasks") or 0),
                "caches_grown": cache_growth[:10],
            }
        db_f, db_l = first.get("database") or {}, last.get("database") or {}
        wal_f, wal_l = db_f.get("wal") or {}, db_l.get("wal") or {}
        summary = {
            "span_seconds": round((datetime.fromisoformat(last["taken_at"])
                                   - datetime.fromisoformat(first["taken_at"])).total_seconds()),
            "processes": growth,
            "database": {
                "wal_bytes_delta": ((wal_l.get("wal_bytes") or 0) - (wal_f.get("wal_bytes") or 0))
                if wal_f and wal_l else None,
                "active_connections_min": min(((s.get("database") or {}).get("active_connections") or 0) for s in snaps),
                "active_connections_max": max(((s.get("database") or {}).get("active_connections") or 0) for s in snaps),
                "longest_query_seconds_max": max(
                    (((s.get("database") or {}).get("activity") or {}).get("longest_active_seconds") or 0) for s in snaps
                ),
            },
            "host": {
                "load_avg_max": max(((s.get("host") or {}).get("load_avg") or [0])[0] for s in snaps),
                "mem_available_min_bytes": min(((s.get("host") or {}).get("mem_available_bytes") or 0) for s in snaps),
            },
        }
    return {**_series_public(), "summary": summary, "snapshots": snaps}


def _series_as_text(result: Dict[str, Any]) -> str:
    lines = [
        f"Серия снимков: {result.get('started_at')} → {result.get('finished_at')}",
        f"Снимков: {result.get('snapshots_taken')}, длительность {result.get('elapsed_seconds')} с",
    ]
    if result.get("error"):
        lines.append(f"⚠ {result['error']}")
    sm = result.get("summary") or {}
    if sm:
        lines += ["", "=== Что изменилось за серию"]
        for mode, g in (sm.get("processes") or {}).items():
            lines.append(f"[{mode}] RSS {_human(g['rss_delta_bytes'])}, CPU user +{g['cpu_user_delta']} с / "
                         f"system +{g['cpu_system_delta']} с, задач asyncio {g['asyncio_tasks_delta']:+d}")
            for c in g.get("caches_grown", [])[:5]:
                lines.append(f"     {c['name']}: {c['items_delta']:+d} шт, {_human(c['bytes_delta'])}")
        db = sm.get("database") or {}
        lines.append(f"База: WAL {_human(db.get('wal_bytes_delta'))}, онлайн {db.get('active_connections_min')}–"
                     f"{db.get('active_connections_max')}, самый долгий запрос {db.get('longest_query_seconds_max')} с")
        h = sm.get("host") or {}
        lines.append(f"Хост: load max {h.get('load_avg_max')}, памяти доступно min {_human(h.get('mem_available_min_bytes'))}")
    snaps = result.get("snapshots") or []
    if snaps:
        lines += ["", "=== Первый снимок", _as_text(snaps[0])]
        if len(snaps) > 1:
            lines += ["=== Последний снимок", _as_text(snaps[-1])]
    return "\n".join(lines)


# ── роуты ────────────────────────────────────────────────────────────────────

@router.get("/memory")
async def memory_snapshot(
    admin: AdminUser = Depends(require_permission("settings", "view")),
):
    """Снимок: хост, база, свой процесс и коллектор в раздельном режиме."""
    return _plain(await _full_snapshot())


@router.get("/memory/download")
async def download_memory_snapshot(
    fmt: str = "json",
    admin: AdminUser = Depends(require_permission("settings", "view")),
):
    """Тот же снимок файлом: json для сравнения двух замеров, txt — чтобы прочитать."""
    full = await _full_snapshot()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    logger.info("Diagnostics snapshot downloaded by admin %s", admin.username)
    if fmt == "txt":
        return PlainTextResponse(
            _as_text(full),
            headers={"Content-Disposition": f'attachment; filename="diagnostics-{stamp}.txt"'},
        )
    return JSONResponse(
        _plain(full),
        headers={"Content-Disposition": f'attachment; filename="diagnostics-{stamp}.json"'},
    )


@router.post("/series/start")
async def start_series(
    body: SeriesStart,
    admin: AdminUser = Depends(require_permission("settings", "view")),
):
    """Запустить серию снимков. Пока идёт — повторный запуск отклоняется."""
    if _series["running"]:
        return JSONResponse(status_code=409, content={"detail": "series already running", **_series_public()})
    minutes = max(1, min(int(body.minutes or _SERIES_DEFAULT_MINUTES), _SERIES_MAX_MINUTES))
    _series["task"] = asyncio.create_task(_run_series(minutes * 60))
    logger.info("Diagnostics series started by admin %s for %d min", admin.username, minutes)
    return _series_public()


@router.get("/series/status")
async def series_status(
    admin: AdminUser = Depends(require_permission("settings", "view")),
):
    return _series_public()


@router.post("/series/stop")
async def stop_series(
    admin: AdminUser = Depends(require_permission("settings", "view")),
):
    """Остановить досрочно — уже снятое сохраняется и доступно к скачиванию."""
    task = _series.get("task")
    if task and not task.done():
        task.cancel()
    return _series_public()


@router.get("/series/download")
async def download_series(
    fmt: str = "json",
    admin: AdminUser = Depends(require_permission("settings", "view")),
):
    """Результат серии файлом: json со всеми снимками и сводкой, txt — сводка и крайние снимки."""
    if not _series["snapshots"]:
        return JSONResponse(status_code=404, content={"detail": "no series result"})
    result = _series_result()
    stamp = (_series["started_at"] or datetime.now(timezone.utc).isoformat())[:19].replace(":", "").replace("-", "")
    logger.info("Diagnostics series downloaded by admin %s", admin.username)
    if fmt == "txt":
        return PlainTextResponse(
            _series_as_text(result),
            headers={"Content-Disposition": f'attachment; filename="diagnostics-series-{stamp}.txt"'},
        )
    return JSONResponse(
        _plain(result),
        headers={"Content-Disposition": f'attachment; filename="diagnostics-series-{stamp}.json"'},
    )


# ── внутренний роут коллектора ───────────────────────────────────────────────

internal_router = APIRouter()


@internal_router.get("/diagnostics/memory")
async def collector_memory_snapshot(request: Request):
    """Снимок процесса коллектора — для сборки из режима api.

    Роуты коллектора не проходят через middleware авторизации, поэтому
    внутренний секрет проверяется вручную, как и при пересылке в бот.
    """
    received = request.headers.get("X-Internal-Api-Secret", "")
    if not hmac.compare_digest(received.encode("utf-8"), _internal_secret().encode("utf-8")):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return _plain(_process_snapshot())

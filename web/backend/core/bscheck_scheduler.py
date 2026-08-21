"""BS-Check авто-тесты (jobs) по расписанию.

Проходит по сохранённым тестам (bscheck_jobs): для каждого enabled и «пора»
(now - last_run_at >= interval_minutes) запускает проверку по kind+config, пишет
результат в журнал с job_id, обновляет last_run_at.

Платно → бюджет-гард по каждому job (budget_daily, сумма cost за сегодня по
job_id). Троттлинг 1 req/s. scan/vless асинхронны — submit + поллинг статуса.
Алерт на просадку (passed↓ vs прошлой проверки ноды).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_TICK_SECONDS = 120
_STARTUP_DELAY = 180
_POLL_ROUNDS = 60      # async-результат ждём до ~6 мин
_POLL_EVERY = 6


def _due(last_iso, interval_min: int, now: datetime) -> bool:
    if interval_min <= 0:
        return False
    if not last_iso:
        return True
    try:
        last = datetime.fromisoformat(last_iso)
    except (ValueError, TypeError):
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last) >= timedelta(minutes=interval_min)


def _dpi(cfg) -> str:
    """Фильтр по белому списку из конфига теста; неизвестное значение → «только с БС».

    Режим off появился в контракте 1.1 — до него в сохранённых тестах его быть
    не могло, поэтому старые конфиги просто продолжают работать как раньше.
    """
    return cfg.get("dpi") if cfg.get("dpi") in ("on", "off", "any") else "on"


def _probes(cfg) -> dict:
    return cfg.get("probes") or {"icmp": True, "tcp": True, "sni": False}


async def _poll_async(getter, sid):
    for _ in range(_POLL_ROUNDS):
        await asyncio.sleep(_POLL_EVERY)
        st = await getter(sid)
        if st.get("result_ready") or st.get("state") in ("done", "failed", "error", "cancelled"):
            return st
    return None


async def _alert(node, ip, passed, total, prev):
    try:
        from web.backend.core.notification_service import notify_bscheck_drop
        await notify_bscheck_drop(node, ip, passed, total, prev)
    except Exception as e:  # noqa: BLE001
        logger.warning("BS-Check alert delivery failed: %s", e)


async def _run_node(bs, db, job, cfg, budget, spent) -> None:
    operators = cfg.get("operators") or []
    node_filter = set(cfg.get("nodes") or [])
    alert = job.get("alert")
    rows = await db.get_all_nodes()
    for n in rows:
        uuid = n.get("uuid")
        if node_filter and uuid not in node_filter:
            continue
        ip = n.get("agent_ip") or n.get("address")
        if not ip:
            continue
        if budget > 0 and spent >= budget:
            break
        target = f"{ip}:443"
        prev = await db.get_last_bscheck(uuid)
        try:
            result = await bs.probe({"target": target, "operators": operators, "probes": _probes(cfg), "dpi": _dpi(cfg)})
        except bs.BscheckError as e:
            logger.warning("bscheck job %s: проба %s: %s", job["id"], ip, e)
            await asyncio.sleep(1)
            continue
        summary = bs.summarize(result, target)
        spent += int(summary.get("cost_credits") or 0)
        await db.save_bscheck(uuid, summary["passed"], summary["total"], summary.get("cost_credits"),
                              {"summary": summary, "raw": result}, created_by="scheduler", target=ip, job_id=job["id"])
        if alert and isinstance(prev, dict) and isinstance(prev.get("result"), dict):
            pp = (prev["result"].get("summary") or {}).get("passed")
            if isinstance(pp, int) and summary["passed"] < pp:
                await _alert(n.get("name") or ip, ip, summary["passed"], summary["total"], pp)
        await asyncio.sleep(1)  # троттлинг bsbord


async def _run_probe(bs, db, job, cfg) -> None:
    targets = [str(t).strip() for t in (cfg.get("targets") or []) if str(t).strip()][:10]
    if not targets:
        return
    result = await bs.probe({"targets": targets, "operators": cfg.get("operators") or [],
                             "probes": _probes(cfg), "dpi": _dpi(cfg)})
    rows = bs.summarize_all(result)
    passed = sum(x["passed"] for x in rows)
    total = sum(x["total"] for x in rows)
    label = targets[0] + (f" +{len(targets) - 1}" if len(targets) > 1 else "")
    await db.save_bscheck_run("probe", label, passed, total, result.get("cost_credits"),
                              {"targets": rows}, created_by="scheduler", job_id=job["id"])


async def _run_scan(bs, db, job, cfg) -> None:
    cidr = str(cfg.get("cidr") or "").strip()
    if not cidr:
        return
    sub = await bs.scans_submit({"cidr": cidr, "operators": cfg.get("operators") or [],
                                 "probes": _probes(cfg), "dpi": _dpi(cfg)})
    sid = sub.get("scan_id")
    st = await _poll_async(bs.scans_status, sid) if sid is not None else None
    if not st:
        logger.warning("bscheck job %s: скан %s не завершился вовремя", job["id"], cidr)
        return
    r = st.get("result") or st
    by_target = r.get("by_target") or st.get("by_target") or {}
    alive = total = 0
    if isinstance(by_target, dict):
        for _, v in by_target.items():
            if isinstance(v, dict) and isinstance(v.get("by_operator"), dict):
                total += 1
                if any(isinstance(l, dict) and l.get("ok") for l in v["by_operator"].values()):
                    alive += 1
    cost = st.get("cost_credits") or (r.get("cost_credits") if isinstance(r, dict) else None)
    await db.save_bscheck_run("scan", cidr, alive, total, cost, st, created_by="scheduler", job_id=job["id"])


async def _run_vless(bs, db, job, cfg) -> None:
    raw = str(cfg.get("raw_input") or "")
    if not raw.strip():
        return
    modems = cfg.get("operators") or cfg.get("selected_modems") or []
    # "new" — легаси-имя prerelease-ядра: тесты, заведённые до контракта 1.1,
    # хранят именно его. "" = Авто, сервис подберёт ядро по самому конфигу.
    core = {"new": "prerelease", "auto": ""}.get(cfg.get("core"), cfg.get("core"))
    if core not in ("", "stable", "prerelease"):
        core = ""
    sub = await bs.vless_submit({"raw_input": raw, "selected_modems": modems, "dpi": _dpi(cfg), "core": core})
    tid = sub.get("test_id")
    st = await _poll_async(bs.vless_status, tid) if tid is not None else None
    data = st or sub
    servers = data.get("result") if isinstance(data.get("result"), list) else []
    passed = sum(1 for s in servers if isinstance(s, dict) and (s.get("ok") or s.get("tunnel_up")))
    first = servers[0].get("server_name") if servers and isinstance(servers[0], dict) else None
    await db.save_bscheck_run("vless", first or f"{len(servers)} серв.", passed, len(servers),
                              sub.get("cost_credits"), data, created_by="scheduler", job_id=job["id"])


async def _run_reputation(bs, db, job, cfg) -> None:
    from web.backend.core import reputation as rep
    node_filter = set(cfg.get("nodes") or [])
    targets = []
    for n in await db.get_all_nodes():
        if node_filter and n.get("uuid") not in node_filter:
            continue
        ip = n.get("agent_ip") or n.get("address")
        if ip:
            targets.append(ip)
    targets += [str(t).strip() for t in (cfg.get("targets") or []) if str(t).strip()]
    targets = list(dict.fromkeys(targets))
    if not targets:
        return
    providers = set(cfg.get("providers") or []) or None
    batch = int(cfg.get("batch") or 0)
    if batch > 0 and len(targets) > batch:
        last = await db.get_bscheck_last_by_target(job["id"], "reputation")
        targets.sort(key=lambda x: last.get(x) or "")   # никогда/давно проверенные — первыми (ротация)
        targets = targets[:batch]
    for target in targets:
        try:
            results = await rep.lookup_all(target, only=providers)
        except Exception as e:  # noqa: BLE001
            logger.warning("bscheck job %s: репутация %s: %s", job["id"], target, e)
            await asyncio.sleep(2.5)
            continue
        clean = [r for r in results if not r.get("error")]
        blocked = any(r.get("blocked") for r in clean)
        maxscore = max([0] + [int(r.get("score") or 0) for r in clean])
        passed = sum(1 for r in clean if not r.get("blocked") and int(r.get("score") or 0) < 50)
        await db.save_bscheck_run("reputation", target, passed, len(clean), None,
                                  {"results": results, "blocked": blocked, "score": maxscore},
                                  created_by="scheduler", job_id=job["id"])
        if job.get("alert") and blocked:
            try:
                from web.backend.core.notification_service import notify_rkn_blocked
                rkn = next((r.get("rkn_domain") for r in clean if r.get("blocked")), None)
                await notify_rkn_blocked(target, rkn)
            except Exception as e:  # noqa: BLE001
                logger.warning("BS-Check RKN alert delivery failed: %s", e)
        await asyncio.sleep(2.5)   # троттлинг cheburcheck (~30/мин на IP)


_RUNNERS = {"probe": _run_probe, "scan": _run_scan, "vless": _run_vless, "reputation": _run_reputation}


async def run_bscheck_jobs_tick() -> None:
    from shared.database import db_service
    from web.backend.core import bscheck as bs
    if not bs.is_configured():
        return
    now = datetime.now(timezone.utc)
    for job in await db_service.list_bscheck_jobs():
        if not job.get("enabled"):
            continue
        if not _due(job.get("last_run_at"), int(job.get("interval_minutes") or 0), now):
            continue

        budget = int(job.get("budget_daily") or 0)
        spent = await db_service.get_bscheck_spent_today_job(job["id"])
        if budget > 0 and spent >= budget:
            logger.info("bscheck job %s: дневной бюджет исчерпан (%d/%d)", job["id"], spent, budget)
            await db_service.touch_bscheck_job_run(job["id"])
            continue

        cfg = job.get("config") if isinstance(job.get("config"), dict) else {}
        try:
            if job.get("kind") == "node":
                await _run_node(bs, db_service, job, cfg, budget, spent)
            elif job.get("kind") in _RUNNERS:
                await _RUNNERS[job["kind"]](bs, db_service, job, cfg)
        except bs.BscheckError as e:
            logger.warning("bscheck job %s (%s): %s", job["id"], job.get("kind"), e)
        except Exception as e:  # noqa: BLE001
            logger.warning("bscheck job %s failed: %s", job["id"], e)
        await db_service.touch_bscheck_job_run(job["id"])


async def bscheck_scheduler_loop() -> None:
    await asyncio.sleep(_STARTUP_DELAY)
    while True:
        try:
            await run_bscheck_jobs_tick()
        except Exception as exc:  # noqa: BLE001
            logger.warning("bscheck scheduler tick failed: %s", exc)
        await asyncio.sleep(_TICK_SECONDS)

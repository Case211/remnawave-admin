"""BS-Check API — проверка нод через операторов РФ (bschekbot/bsbord).

Показывает, проходит ли IP ноды через операторский DPI/белые списки. Проба
платная (кредиты bsbord) — перед запуском есть /probe/preview с ценой. Токен
хранится зашифрованным; RBAC-ресурс `bscheck` (view — читать/превью, check —
запускать пробу и управлять токеном).
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core import bscheck as bs
from web.backend.core.audit import write_audit_log
from shared.database import db_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _upstream(e: bs.BscheckError) -> HTTPException:
    return HTTPException(status_code=502, detail=str(e))


# Фильтр единиц по белому списку (контракт 1.1): on — только с БС, off — только
# без БС, any — обе группы. Раньше режима off не было вовсе.
DPI_MODES = ("on", "off", "any")
# Ядро xray для VLESS-теста: "" — Авто (сервис определит по конфигу), иначе форс.
# При форсе перепроверки вторым ядром не будет.
CORE_MODES = ("", "stable", "prerelease")
CORE_ALIASES = {"new": "prerelease", "auto": ""}


# ── Схемы ────────────────────────────────────────────────────────


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ProbeIn(BaseModel):
    target: Optional[str] = None              # одна цель (проверка ноды)
    targets: Optional[List[str]] = None       # 1..10 целей (мульти-проверка)
    operators: List[str] = Field(default_factory=list)   # op_key[]; пусто = все
    probes: Dict[str, bool] = Field(default_factory=lambda: {"icmp": True, "tcp": True, "sni": False})
    sni_hosts: List[str] = Field(default_factory=list)
    dpi: str = "on"

    @field_validator("dpi")
    @classmethod
    def _dpi(cls, v: str) -> str:
        if v not in DPI_MODES:
            raise ValueError("dpi must be on|off|any")
        return v

    @model_validator(mode="after")
    def _has_target(self):
        if not (self.target and self.target.strip()) and not (self.targets and any(t.strip() for t in self.targets)):
            raise ValueError("target or targets required")
        if self.targets and len(self.targets) > 10:
            raise ValueError("too many targets (max 10)")
        return self


class ScanIn(BaseModel):
    cidr: str = Field(min_length=9, max_length=32)   # bsbord поддерживает РОВНО /24
    operators: List[str] = Field(default_factory=list)
    probes: Dict[str, bool] = Field(default_factory=lambda: {"icmp": True, "tcp": True, "sni": False})
    sni_hosts: List[str] = Field(default_factory=list)
    dpi: str = "on"

    @field_validator("dpi")
    @classmethod
    def _dpi(cls, v: str) -> str:
        if v not in DPI_MODES:
            raise ValueError("dpi must be on|off|any")
        return v

    @field_validator("cidr")
    @classmethod
    def _cidr(cls, v: str) -> str:
        import ipaddress
        v = v.strip()
        if not v.endswith("/24"):
            raise ValueError("bsbord поддерживает только /24")
        try:
            net = ipaddress.ip_network(v, strict=False)  # нормализует host-биты → x.x.x.0/24
        except ValueError:
            raise ValueError("некорректный CIDR")
        if net.version != 4 or net.prefixlen != 24:
            raise ValueError("только IPv4 /24")
        return str(net)


class HistoryIn(BaseModel):
    kind: str                                   # probe | scan | vless
    target: Optional[str] = Field(default=None, max_length=300)
    passed: int = 0
    total: int = 0
    cost_credits: Optional[int] = None
    result: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in ("probe", "scan", "vless"):
            raise ValueError("kind must be probe|scan|vless")
        return v


class VlessIn(BaseModel):
    raw_input: str = Field(min_length=1, max_length=1_000_000)
    selected_modems: List[str] = Field(default_factory=list)
    dpi: str = "on"
    core: str = ""     # "" = Авто (ядро определит сервис)

    @field_validator("dpi")
    @classmethod
    def _dpi(cls, v: str) -> str:
        if v not in DPI_MODES:
            raise ValueError("dpi must be on|off|any")
        return v

    @field_validator("core")
    @classmethod
    def _core(cls, v: str) -> str:
        v = CORE_ALIASES.get(v, v)
        if v not in CORE_MODES:
            raise ValueError("core must be empty|stable|prerelease")
        return v


class JobIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str                                     # node | probe | scan | vless
    enabled: bool = True
    interval_minutes: int = Field(default=360, ge=5, le=100_000)
    config: Dict[str, Any] = Field(default_factory=dict)
    budget_daily: int = Field(default=0, ge=0, le=1_000_000)
    alert: bool = True

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in ("node", "probe", "scan", "vless", "reputation"):
            raise ValueError("kind must be node|probe|scan|vless|reputation")
        return v


def _first_target(p: ProbeIn) -> str:
    if p.target and p.target.strip():
        return p.target.strip()
    return (p.targets[0].strip() if p.targets and p.targets[0].strip() else "")


def _body(p: ProbeIn) -> Dict:
    b = {"operators": p.operators, "probes": p.probes, "sni_hosts": p.sni_hosts, "dpi": p.dpi}
    if p.targets:
        b["targets"] = [t.strip() for t in p.targets if t.strip()][:10]
    elif p.target:
        b["target"] = p.target.strip()
    return b


def _scan_body(p: ScanIn) -> Dict:
    return {"cidr": p.cidr.strip(), "operators": p.operators,
            "probes": p.probes, "sni_hosts": p.sni_hosts, "dpi": p.dpi}


def _vless_body(p: VlessIn) -> Dict:
    return {"raw_input": p.raw_input, "selected_modems": p.selected_modems,
            "dpi": p.dpi, "core": p.core}


# ── Токен / статус ───────────────────────────────────────────────


@router.get("/status")
async def status(admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    """Токен настроен? Баланс и тариф. Ошибка апстрима отдаётся, а не глотается.

    Раньше отказ bsbord (истёк тариф, отозван ключ, обслуживание) уходил только
    в лог, а страница молча рисовала прочерк вместо баланса: снаружи выглядело
    так, будто кнопка «Обновить» ничего не делает.
    """
    if not bs.is_configured():
        return {"configured": False, "account": None, "error": None}
    try:
        return {"configured": True, "account": await bs.get_account(), "error": None}
    except bs.BscheckError as e:
        logger.info("bscheck account: %s", e)
        return {"configured": True, "account": None, "error": str(e)}


@router.put("/token")
async def set_token(data: TokenIn,
                    admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    if not await bs.verify_token(data.token.strip()):
        raise HTTPException(status_code=400, detail="Токен недействителен или тариф ниже Bronze")
    await bs.save_token(data.token)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.token.set", resource="bscheck", resource_id="token")
    return {"configured": True}


@router.delete("/token")
async def clear_token(admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    await bs.clear_token()
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.token.clear", resource="bscheck", resource_id="token")
    return {"configured": False}


# ── Операторы / превью / проверка ────────────────────────────────


def _unit_item(u: Dict[str, Any]) -> Dict[str, Any]:
    """Единица проверки в форме, понятной и новому UI, и старым записям.

    Контракт 1.1 переименовал поля (operator/region/probeable вместо
    id/region_label/alive) и добавил dpi. Отдаём и то, и другое: журнал
    проверок рисуется теми же компонентами, а в нём лежат ответы старого
    формата, которые никто не переписывал.
    """
    operator = u.get("operator") or u.get("id") or ""
    region = u.get("region") or u.get("region_label")
    probeable = u.get("probeable")
    if probeable is None:
        probeable = u.get("alive", True)
    return {
        "op_key": u.get("op_key") or "",
        "operator": operator,
        "name": u.get("name") or str(operator).upper(),
        "region": region,
        "region_code": u.get("region_code"),
        "dpi": u.get("dpi"),
        "channel_state": u.get("channel_state") or "UNKNOWN",
        "probeable": bool(probeable),
        # старые имена — чтобы не переписывать разбор исторических ответов
        "id": operator,
        "region_label": region,
        "alive": bool(probeable),
    }


@router.get("/operators")
async def operators(admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    try:
        units = await bs.get_operators()
    except bs.BscheckError as e:
        raise _upstream(e)
    return {"items": [_unit_item(u) for u in units]}


@router.post("/probe/preview")
async def preview(data: ProbeIn, admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    try:
        return await bs.probe_preview(_body(data))
    except bs.BscheckError as e:
        raise _upstream(e)


@router.post("/nodes/{node_uuid}/check")
async def check_node(node_uuid: str, data: ProbeIn,
                     admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    try:
        result = await bs.probe(_body(data))
    except bs.BscheckError as e:
        raise _upstream(e)
    summary = bs.summarize(result, _first_target(data))
    saved = await db_service.save_bscheck(
        node_uuid, summary["passed"], summary["total"], summary.get("cost_credits"),
        {"summary": summary, "raw": result}, created_by=admin.username,
        target=_first_target(data))
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.node.check", resource="bscheck", resource_id=node_uuid)
    return {"summary": summary, "checked_at": saved.get("checked_at") if saved else None}


@router.get("/nodes/{node_uuid}")
async def node_history(node_uuid: str,
                       admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    return {
        "last": await db_service.get_last_bscheck(node_uuid),
        "history": await db_service.list_bscheck(node_uuid, 20),
    }


@router.get("/summary")
async def summary_map(admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    return {"items": await db_service.get_bscheck_summary_map()}


# ── Ноды с реальным IP / мульти-проверка / скан /24 / VLESS ──────


@router.get("/nodes")
async def nodes(admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    """Ноды с РЕАЛЬНЫМ публичным IP (agent_ip; фолбэк address) — для проверки БС.

    За NetBird address = туннельный 100.x, поэтому для операторской пробы нужен
    agent_ip (реальный источник трафика, миграция 0076).
    """
    rows = await db_service.get_all_nodes()
    out = []
    for n in rows:
        out.append({
            "uuid": n.get("uuid"), "name": n.get("name"),
            "ip": n.get("agent_ip") or n.get("address"),
            "address": n.get("address"), "agent_ip": n.get("agent_ip"),
        })
    return {"items": out}


@router.post("/probe")
async def probe_multi(data: ProbeIn,
                      admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    """Проба одной или нескольких (до 10) целей — общий инструмент, не по ноде."""
    try:
        result = await bs.probe(_body(data))
    except bs.BscheckError as e:
        raise _upstream(e)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.probe", resource="bscheck", resource_id=_first_target(data))
    return {"targets": bs.summarize_all(result), "cost_credits": result.get("cost_credits")}


@router.post("/scans/preview")
async def scans_preview(data: ScanIn,
                        admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    try:
        return await bs.scans_preview(_scan_body(data))
    except bs.BscheckError as e:
        raise _upstream(e)


@router.post("/scans")
async def scans_submit(data: ScanIn,
                       admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    try:
        res = await bs.scans_submit(_scan_body(data))
    except bs.BscheckError as e:
        raise _upstream(e)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.scan", resource="bscheck", resource_id=data.cidr)
    return res


@router.get("/scans/{scan_id}")
async def scans_status(scan_id: str,
                       admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    try:
        return await bs.scans_status(scan_id)
    except bs.BscheckError as e:
        raise _upstream(e)


@router.post("/scans/{scan_id}/cancel")
async def scans_cancel(scan_id: str,
                       admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    """Остановить скан: несделанная часть гасится, платим за проверенные адреса."""
    try:
        res = await bs.scans_cancel(scan_id)
    except bs.BscheckError as e:
        raise _upstream(e)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.scan_cancel", resource="bscheck", resource_id=scan_id)
    return res


@router.post("/vless")
async def vless_submit(data: VlessIn,
                       admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    try:
        res = await bs.vless_submit(_vless_body(data))
    except bs.BscheckError as e:
        raise _upstream(e)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.vless", resource="bscheck", resource_id="config")
    return res


@router.get("/vless/{test_id}")
async def vless_status(test_id: str,
                       admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    try:
        return await bs.vless_status(test_id)
    except bs.BscheckError as e:
        raise _upstream(e)


@router.post("/vless/{test_id}/cancel")
async def vless_cancel(test_id: str,
                       admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    """Остановить VLESS-тест. Уже полученные вердикты остаются платными."""
    try:
        res = await bs.vless_cancel(test_id)
    except bs.BscheckError as e:
        raise _upstream(e)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.vless_cancel", resource="bscheck", resource_id=test_id)
    return res


# ── Журнал проверок (ноды + ad-hoc) ──────────────────────────────


@router.post("/history")
async def save_history(data: HistoryIn,
                       admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    """Записать ad-hoc проверку (probe/scan/vless) в общий журнал. Ноды пишутся сами."""
    saved = await db_service.save_bscheck_run(
        data.kind, data.target, data.passed, data.total,
        data.cost_credits, data.result, created_by=admin.username)
    return saved or {}


@router.get("/history")
async def list_history(kind: Optional[str] = None, limit: int = 50, job_id: Optional[int] = None,
                       admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    limit = max(1, min(limit, 200))
    k = kind if kind in ("node", "probe", "scan", "vless", "reputation") else None
    return {"items": await db_service.list_bscheck_runs(limit, k, job_id)}


# ── Авто-тесты (jobs) ────────────────────────────────────────────


@router.get("/jobs")
async def list_jobs(admin: AdminUser = Depends(require_permission("bscheck", "view"))):
    return {"items": await db_service.list_bscheck_jobs()}


@router.post("/jobs")
async def create_job(data: JobIn,
                     admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    job = await db_service.create_bscheck_job(
        data.name.strip(), data.kind, data.interval_minutes, data.config,
        data.budget_daily, data.alert, enabled=data.enabled, created_by=admin.username)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.job.create", resource="bscheck",
                          resource_id=str(job.get("id") if job else ""))
    return job or {}


@router.put("/jobs/{job_id}")
async def update_job(job_id: int, data: JobIn,
                     admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    job = await db_service.update_bscheck_job(
        job_id, name=data.name.strip(), kind=data.kind, enabled=data.enabled,
        interval_minutes=data.interval_minutes, config=data.config,
        budget_daily=data.budget_daily, alert=data.alert)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.job.update", resource="bscheck", resource_id=str(job_id))
    return job


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: int,
                     admin: AdminUser = Depends(require_permission("bscheck", "check"))):
    ok = await db_service.delete_bscheck_job(job_id)
    await write_audit_log(admin_id=admin.account_id, admin_username=admin.username,
                          action="bscheck.job.delete", resource="bscheck", resource_id=str(job_id))
    return {"ok": ok}

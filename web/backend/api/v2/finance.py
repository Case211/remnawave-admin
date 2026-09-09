"""Finance API — собственный учёт финансов инфраструктуры (P&L).

Заменяет прокси к панельному infra-billing: категории, провайдеры, записи
расходов/доходов с валютами и циклами, платежи с фиксацией курса, курсы
валют, сводка P&L и импорт данных из панели.
"""
import json
import logging
from datetime import date
from typing import Dict, List, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from web.backend.api.deps import AdminUser, require_permission
from shared.database import db_service
from shared.config_service import config_service
from shared.db.finance import BILLING_CYCLES, ITEM_KINDS

logger = logging.getLogger(__name__)
router = APIRouter()


def _base_currency() -> str:
    return str(config_service.get("finance_base_currency", "RUB") or "RUB").upper()


async def _base_rate() -> float:
    """Курс базовой валюты к RUB (RUB -> 1.0)."""
    base = _base_currency()
    if base == "RUB":
        return 1.0
    for r in await db_service.get_finance_rates():
        if r["currency"] == base and r["rate_rub"]:
            return float(r["rate_rub"])
    return 1.0


# ── Pydantic модели ──────────────────────────────────────────────


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str = "expense"
    color: Optional[str] = None
    icon: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in ITEM_KINDS:
            raise ValueError("kind must be expense|income")
        return v


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    color: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: Optional[str] = None
    favicon_url: Optional[str] = None
    notes: Optional[str] = None


class ProviderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    url: Optional[str] = None
    favicon_url: Optional[str] = None
    notes: Optional[str] = None
    archived: Optional[bool] = None


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = "expense"
    category_id: Optional[int] = None
    provider_id: Optional[int] = None
    node_uuid: Optional[str] = None
    currency: str = Field(default="RUB", min_length=3, max_length=8)
    amount: float = Field(default=0, ge=0)
    billing_cycle: str = "monthly"
    cycle_days: Optional[int] = Field(default=None, ge=1, le=3650)
    next_due_at: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in ITEM_KINDS:
            raise ValueError("kind must be expense|income")
        return v

    @field_validator("billing_cycle")
    @classmethod
    def _cycle(cls, v):
        if v not in BILLING_CYCLES:
            raise ValueError(f"billing_cycle must be one of {BILLING_CYCLES}")
        return v


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    kind: Optional[str] = None
    category_id: Optional[int] = None
    provider_id: Optional[int] = None
    node_uuid: Optional[str] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    amount: Optional[float] = Field(default=None, ge=0)
    billing_cycle: Optional[str] = None
    cycle_days: Optional[int] = Field(default=None, ge=1, le=3650)
    next_due_at: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v is not None and v not in ITEM_KINDS:
            raise ValueError("kind must be expense|income")
        return v

    @field_validator("billing_cycle")
    @classmethod
    def _cycle(cls, v):
        if v is not None and v not in BILLING_CYCLES:
            raise ValueError(f"billing_cycle must be one of {BILLING_CYCLES}")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v is not None and v not in ("active", "archived"):
            raise ValueError("status must be active|archived")
        return v


class MarkPaid(BaseModel):
    amount: Optional[float] = Field(default=None, ge=0)
    paid_at: Optional[str] = None
    comment: Optional[str] = None


class PaymentCreate(BaseModel):
    item_id: Optional[int] = None
    item_name: Optional[str] = Field(default=None, max_length=200)
    kind: str = "expense"
    paid_at: str
    amount: float = Field(gt=0)
    currency: str = Field(default="RUB", min_length=3, max_length=8)
    comment: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in ITEM_KINDS:
            raise ValueError("kind must be expense|income")
        return v


class PaymentUpdate(BaseModel):
    """Правка операции: все поля опциональны, comment=null очищает комментарий."""
    item_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    kind: Optional[str] = None
    paid_at: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    comment: Optional[str] = None

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v is not None and v not in ITEM_KINDS:
            raise ValueError("kind must be expense|income")
        return v

    @field_validator("paid_at")
    @classmethod
    def _paid_at(cls, v):
        if v is not None:
            date.fromisoformat(v)  # ValueError -> 422
        return v


class RateUpdate(BaseModel):
    rate_rub: float = Field(gt=0)
    is_manual: bool = True


class AccountCreate(BaseModel):
    provider_id: int
    adapter: str = Field(min_length=1, max_length=50)
    base_url: Optional[str] = Field(default=None, max_length=500)
    credentials: Dict[str, str]
    auto_sync: bool = True
    low_balance_threshold: Optional[float] = Field(default=None, ge=0)


class AccountUpdate(BaseModel):
    base_url: Optional[str] = Field(default=None, max_length=500)
    credentials: Optional[Dict[str, str]] = None  # None = не трогать сохранённые
    auto_sync: Optional[bool] = None
    low_balance_threshold: Optional[float] = Field(default=None, ge=0)


class AccountTest(BaseModel):
    """Тест подключения: либо account_id (сохранённые креды), либо полный набор."""
    account_id: Optional[int] = None
    adapter: Optional[str] = None
    base_url: Optional[str] = Field(default=None, max_length=500)
    credentials: Optional[Dict[str, str]] = None


# ── Summary / Upcoming ───────────────────────────────────────────


@router.get("/summary")
async def finance_summary(
    months: int = Query(6, ge=1, le=36),
    admin: AdminUser = Depends(require_permission("finance", "view")),
):
    summary = await db_service.finance_summary(months=months)
    base = _base_currency()
    base_rate = await _base_rate()

    def conv(v_rub: float) -> float:
        return round(v_rub / base_rate, 2)

    tm = summary.get("this_month") or {}
    return {
        "base_currency": base,
        "monthly": [
            {**m, "expense": conv(m["expense_rub"]), "income": conv(m["income_rub"]),
             "net": conv(m["net_rub"])}
            for m in summary["monthly"]
        ],
        "by_category": [
            {**c, "monthly": conv(c["monthly_rub"])} for c in summary["by_category"]
        ],
        "by_currency": summary["by_currency"],
        "recurring": {
            "expense": conv(summary["recurring"].get("expense_rub", 0)),
            "income": conv(summary["recurring"].get("income_rub", 0)),
            "net": conv(summary["recurring"].get("net_rub", 0)),
        },
        "this_month": {
            "month": tm.get("month"),
            "expense": conv(tm.get("expense_rub", 0)),
            "income": conv(tm.get("income_rub", 0)),
            "net": conv(tm.get("net_rub", 0)),
            "expense_actual": conv(tm.get("expense_actual_rub", 0)),
            "income_actual": conv(tm.get("income_actual_rub", 0)),
            "expense_upcoming": conv(tm.get("expense_upcoming_rub", 0)),
            "income_upcoming": conv(tm.get("income_upcoming_rub", 0)),
        },
    }


@router.get("/node-costs")
async def node_costs(
    days: int = Query(30, ge=1, le=31),
    admin: AdminUser = Depends(require_permission("finance", "view")),
):
    """Себестоимость нод: расход/мес, трафик и юзеры за окно, ₽/GB и ₽/юзер."""
    data = await db_service.finance_node_costs(days=days)
    base = _base_currency()
    base_rate = await _base_rate()

    def conv(v_rub):
        return round((v_rub or 0) / base_rate, 2)

    return {
        "base_currency": base,
        "days": data["days"],
        "unassigned_monthly": conv(data["unassigned_monthly_rub"]),
        "items": [
            {
                "node_uuid": it["node_uuid"],
                "node_name": it["node_name"],
                "monthly_cost": conv(it["monthly_cost_rub"]),
                "traffic_gb": it["traffic_gb"],
                "cost_per_gb": conv(it["cost_per_gb_rub"]) if it["cost_per_gb_rub"] is not None else None,
                "users": it["users"],
                "cost_per_user": conv(it["cost_per_user_rub"]) if it["cost_per_user_rub"] is not None else None,
            }
            for it in data["items"]
        ],
    }


@router.get("/upcoming")
async def finance_upcoming(
    days: int = Query(30, ge=1, le=365),
    admin: AdminUser = Depends(require_permission("finance", "view")),
):
    items = await db_service.upcoming_finance_payments(days=days)
    return {"items": items, "total": len(items)}


# ── Categories ───────────────────────────────────────────────────


@router.get("/categories")
async def list_categories(admin: AdminUser = Depends(require_permission("finance", "view"))):
    return {"items": await db_service.list_finance_categories()}


@router.post("/categories")
async def create_category(
    data: CategoryCreate,
    admin: AdminUser = Depends(require_permission("finance", "create")),
):
    created = await db_service.create_finance_category(data.name, data.kind, data.color, data.icon)
    if not created:
        raise HTTPException(status_code=409, detail="Category already exists")
    return created


@router.patch("/categories/{category_id}")
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    try:
        ok = await db_service.update_finance_category(
            category_id, **data.model_dump(exclude_unset=True, exclude_none=True),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Category already exists")
    if not ok:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"status": "ok"}


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    admin: AdminUser = Depends(require_permission("finance", "delete")),
):
    ok = await db_service.delete_finance_category(category_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Category not found or is system")
    return {"status": "ok"}


# ── Providers ────────────────────────────────────────────────────


@router.get("/providers")
async def list_providers(admin: AdminUser = Depends(require_permission("finance", "view"))):
    return {"items": await db_service.list_finance_providers()}


@router.post("/providers")
async def create_provider(
    data: ProviderCreate,
    admin: AdminUser = Depends(require_permission("finance", "create")),
):
    created = await db_service.create_finance_provider(
        data.name, data.url, data.favicon_url, data.notes,
    )
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create provider")
    return created


@router.patch("/providers/{provider_id}")
async def update_provider(
    provider_id: int,
    data: ProviderUpdate,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    ok = await db_service.update_finance_provider(
        provider_id, **data.model_dump(exclude_unset=True, exclude_none=True),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Provider not found")
    # архив хостера утаскивает в архив и его активные записи —
    # иначе они продолжают сидеть в обязательных расходах месяца
    archived_items = 0
    if data.archived is True:
        archived_items = await db_service.archive_finance_provider_items(provider_id)
    return {"status": "ok", "archived_items": archived_items}


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: int,
    admin: AdminUser = Depends(require_permission("finance", "delete")),
):
    ok = await db_service.delete_finance_provider(provider_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"status": "ok"}


# ── Items ────────────────────────────────────────────────────────


@router.get("/items")
async def list_items(
    kind: Optional[str] = Query(None),
    status: Optional[str] = Query("active"),
    category_id: Optional[int] = Query(None),
    currency: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("finance", "view")),
):
    items = await db_service.list_finance_items(
        kind=kind, status=status or None, category_id=category_id,
        currency=currency, search=search,
    )
    return {"items": items, "total": len(items)}


@router.post("/items")
async def create_item(
    data: ItemCreate,
    admin: AdminUser = Depends(require_permission("finance", "create")),
):
    item = await db_service.create_finance_item(**data.model_dump())
    if not item:
        raise HTTPException(status_code=500, detail="Failed to create item")
    # Разовые записи не висят в списке регулярных: сразу проводим платёж
    # (попадает в P&L/платежи) и архивируем — иначе список превращается в
    # портянку из одноразовых расходов/доходов.
    if item.get("billing_cycle") == "once":
        if (item.get("amount") or 0) > 0:
            await db_service.mark_finance_item_paid(item["id"], paid_at=item.get("next_due_at"))
        else:
            await db_service.update_finance_item(item["id"], status="archived")
        item = await db_service.get_finance_item(item["id"])
    return item


@router.patch("/items/{item_id}")
async def update_item(
    item_id: int,
    data: ItemUpdate,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    item = await db_service.update_finance_item(item_id, **data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    admin: AdminUser = Depends(require_permission("finance", "delete")),
):
    ok = await db_service.delete_finance_item(item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"status": "ok"}


@router.post("/items/{item_id}/paid")
async def mark_paid(
    item_id: int,
    data: MarkPaid,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    item = await db_service.mark_finance_item_paid(
        item_id, amount=data.amount, paid_at=data.paid_at, comment=data.comment,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@router.post("/items/{item_id}/skip")
async def skip_cycle(
    item_id: int,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    item = await db_service.skip_finance_item_cycle(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


# ── Payments ─────────────────────────────────────────────────────


@router.get("/payments")
async def list_payments(
    item_id: Optional[int] = Query(None),
    since: Optional[str] = Query(None),
    until: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("finance", "view")),
):
    items = await db_service.list_finance_payments(
        item_id=item_id, since=since, until=until, limit=limit, offset=offset,
    )
    return {"items": items, "total": len(items)}


@router.post("/payments")
async def create_payment(
    data: PaymentCreate,
    admin: AdminUser = Depends(require_permission("finance", "create")),
):
    """Произвольный платёж/доход без привязки к записи (или с привязкой без сдвига цикла)."""
    from shared.db_schema import FINANCE_PAYMENTS_TABLE, FINANCE_RATES_TABLE
    from datetime import date as _date

    item_name = data.item_name
    if data.item_id and not item_name:
        item = await db_service.get_finance_item(data.item_id)
        item_name = (item or {}).get("name")
    if not item_name:
        item_name = "Без названия"

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            f"""INSERT INTO {FINANCE_PAYMENTS_TABLE}
                (item_id, item_name, kind, paid_at, amount, currency, rate_rub, comment, source)
                VALUES ($1, $2, $3, $4::date, $5, $6,
                        (SELECT rate_rub FROM {FINANCE_RATES_TABLE} WHERE currency = $6),
                        $7, 'manual')
                RETURNING id""",
            data.item_id, item_name, data.kind, _date.fromisoformat(data.paid_at),
            round(data.amount, 2), data.currency.upper(), data.comment,
        )
    return {"id": row["id"], "status": "ok"}


@router.patch("/payments/{payment_id}")
async def update_payment(
    payment_id: int,
    data: PaymentUpdate,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    """Правка операции на месте — вместо «удалить и завести заново»."""
    fields = data.model_dump(exclude_unset=True)
    # null допустим только для comment (очистка); для остальных null = не менять
    fields = {k: v for k, v in fields.items() if v is not None or k == "comment"}
    updated = await db_service.update_finance_payment(payment_id, **fields)
    if not updated:
        raise HTTPException(status_code=404, detail="Payment not found")
    return updated


@router.delete("/payments/{payment_id}")
async def delete_payment(
    payment_id: int,
    admin: AdminUser = Depends(require_permission("finance", "delete")),
):
    ok = await db_service.delete_finance_payment(payment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"status": "ok"}


# ── Rates ────────────────────────────────────────────────────────


@router.get("/rates")
async def list_rates(admin: AdminUser = Depends(require_permission("finance", "view"))):
    return {"items": await db_service.get_finance_rates(), "base_currency": _base_currency()}


@router.put("/rates/{currency}")
async def set_rate(
    currency: str,
    data: RateUpdate,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    await db_service.upsert_finance_rate(currency, data.rate_rub, is_manual=data.is_manual)
    return {"status": "ok"}


@router.post("/rates/{currency}/auto")
async def reset_rate_to_auto(
    currency: str,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    """Снять ручной флаг и сразу подтянуть курс из внешнего источника.

    Если источник недоступен, флаг всё равно снят (updated=0 в ответе) —
    суточный цикл автообновления подхватит валюту при следующем проходе.
    """
    from web.backend.core.finance.rates import update_rates
    code = currency.upper()
    if not await db_service.set_finance_rate_manual(code, False):
        raise HTTPException(status_code=404, detail="Rate not found")
    updated = await update_rates([code])
    return {"updated": updated, "items": await db_service.get_finance_rates()}


@router.post("/rates/refresh")
async def refresh_rates(admin: AdminUser = Depends(require_permission("finance", "edit"))):
    from web.backend.core.finance.rates import update_rates
    updated = await update_rates()
    return {"updated": updated, "items": await db_service.get_finance_rates()}


# ── Provider API accounts (автосинк хостеров) ────────────────────


@router.get("/adapters")
async def list_hoster_adapters(admin: AdminUser = Depends(require_permission("finance", "view"))):
    """Реестр адаптеров с описанием полей — для динамической формы подключения."""
    from web.backend.core.finance.adapters import list_adapters
    return {"items": list_adapters()}


@router.get("/accounts")
async def list_accounts(admin: AdminUser = Depends(require_permission("finance", "view"))):
    items = await db_service.list_finance_accounts()
    await _attach_nodes_to_services(items)
    return {"items": items}


async def _attach_nodes_to_services(accounts: list) -> None:
    """Автосопоставление услуг хостера с нодами панели.

    Приоритет — совпадение IP услуги (adapters собирают их в Service.ips)
    с адресом ноды ИЛИ с agent_ip (реальный публичный IP по коллектор-батчам —
    работает и когда нода подключена через оверлей типа NetBird и address
    туннельный); фолбэк — точное совпадение имени. Ничего не храним:
    матчинг на чтении, всегда актуален.
    """
    try:
        nodes = await db_service.get_all_nodes()
    except Exception:
        return
    if not nodes:
        return
    by_ip: dict = {}
    by_name: dict = {}
    for n in nodes:
        uuid, name = n.get("uuid"), n.get("name")
        if not uuid:
            continue
        for addr_key in ("address", "agent_ip"):
            addr = str(n.get(addr_key) or "").strip()
            if addr:
                by_ip.setdefault(addr, (uuid, name))
        if name:
            by_name[str(name).strip().lower()] = (uuid, name)
    for acc in accounts:
        for svc in acc.get("services") or []:
            if not isinstance(svc, dict):
                continue
            hit = next((by_ip[ip] for ip in (svc.get("ips") or []) if ip in by_ip), None)
            if not hit:
                hit = by_name.get(str(svc.get("name") or "").strip().lower())
            if hit:
                svc["node_uuid"], svc["node_name"] = hit


@router.post("/accounts")
async def create_account(
    data: AccountCreate,
    admin: AdminUser = Depends(require_permission("finance", "create")),
):
    """Подключить API хостера к провайдеру (повтор по тому же провайдеру — перезапись)."""
    from web.backend.core.finance.adapters import AdapterError, get_adapter
    from web.backend.core.crypto import encrypt_field

    try:
        adapter = get_adapter(data.adapter)
        adapter.validate_credentials(data.credentials)
    except AdapterError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if adapter.needs_base_url and not (data.base_url or "").strip():
        raise HTTPException(status_code=400, detail="Не указан адрес биллинга (base_url)")

    account = await db_service.create_finance_account(
        provider_id=data.provider_id,
        adapter=data.adapter,
        credentials=encrypt_field(json.dumps(data.credentials, ensure_ascii=False)),
        base_url=(data.base_url or "").strip().rstrip("/") or None,
        auto_sync=data.auto_sync,
        low_balance_threshold=data.low_balance_threshold,
    )
    if not account:
        raise HTTPException(status_code=500, detail="Failed to create account")
    return account


@router.patch("/accounts/{account_id}")
async def update_account(
    account_id: int,
    data: AccountUpdate,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    from web.backend.core.crypto import encrypt_field

    fields = data.model_dump(exclude_unset=True)
    if fields.get("credentials") is not None:
        fields["credentials"] = encrypt_field(json.dumps(fields["credentials"], ensure_ascii=False))
    elif "credentials" in fields:
        fields.pop("credentials")
    if "base_url" in fields and fields["base_url"]:
        fields["base_url"] = fields["base_url"].strip().rstrip("/")
    account = await db_service.update_finance_account(account_id, **fields)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: int,
    admin: AdminUser = Depends(require_permission("finance", "delete")),
):
    ok = await db_service.delete_finance_account(account_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Account not found")
    return {"status": "ok"}


@router.post("/accounts/test")
async def test_account(
    data: AccountTest,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    """Проверка подключения до/после сохранения. Возвращает баланс и число услуг."""
    from web.backend.core.finance.adapters import AdapterError, get_adapter
    from web.backend.core.crypto import decrypt_field

    adapter_slug, base_url, credentials = data.adapter, data.base_url, data.credentials
    account = None
    if data.account_id and not credentials:
        account = await db_service.get_finance_account(data.account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        adapter_slug = adapter_slug or account["adapter"]
        base_url = base_url or account.get("base_url")
        encrypted = await db_service.get_finance_account_credentials(data.account_id)
        credentials = json.loads(decrypt_field(encrypted or ""))
    if not adapter_slug or credentials is None:
        raise HTTPException(status_code=400, detail="adapter и credentials обязательны (или account_id)")

    try:
        adapter = get_adapter(adapter_slug)
        adapter.validate_credentials(credentials)
        import structlog
        structlog.contextvars.bind_contextvars(
            hoster=(account.get("name") if account else None) or adapter_slug)
        try:
            result = await adapter.test((base_url or "").strip().rstrip("/") or None, credentials)
        finally:
            structlog.contextvars.unbind_contextvars("hoster")
    except AdapterError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        logger.warning("Finance account test failed: %s", e)
        return {"status": "error", "error": str(e)}
    return {
        "status": "ok",
        "balance": result.balance,
        "currency": result.currency,
        "services": [s.to_dict() for s in result.services],
    }


@router.post("/accounts/{account_id}/sync")
async def sync_account_now(
    account_id: int,
    admin: AdminUser = Depends(require_permission("finance", "edit")),
):
    """Синк аккаунта сейчас: баланс, снапшот, услуги, даты списаний."""
    from web.backend.core.finance.sync import sync_account
    result = await sync_account(account_id)
    if result.get("error") == "Account not found":
        raise HTTPException(status_code=404, detail="Account not found")
    return result


@router.get("/snapshots")
async def balance_snapshots(
    days: int = Query(90, ge=1, le=730),
    account_id: Optional[int] = Query(None),
    admin: AdminUser = Depends(require_permission("finance", "view")),
):
    """Дневные снапшоты балансов для тренда."""
    return {"items": await db_service.list_finance_balance_snapshots(days=days, account_id=account_id)}


# ── Import from panel ────────────────────────────────────────────


@router.post("/import-panel")
async def import_panel(
    currency: str = Query("USD", min_length=3, max_length=8),
    admin: AdminUser = Depends(require_permission("finance", "create")),
):
    """Одноразовый импорт провайдеров/биллинг-нод/истории из панельного infra-billing.

    Панельные суммы безвалютные — импортируются в выбранной валюте (default USD).
    Повторный импорт перетегирует ранее импортированные платежи.
    """
    from web.backend.core.finance.importer import import_from_panel
    return await import_from_panel(currency=currency)


# ── Bedolaga income ──────────────────────────────────────────────


@router.get("/bedolaga-income")
async def bedolaga_income(admin: AdminUser = Depends(require_permission("finance", "view"))):
    """Живой доход из Bedolaga Bot API (пополнения / выручка с подписок / профит)."""
    from web.backend.core.finance.bedolaga_income import fetch_income_overview
    return await fetch_income_overview()

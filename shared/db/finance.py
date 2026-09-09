"""
Finance mixin — собственный учёт финансов инфраструктуры (P&L).

Категории, провайдеры, записи расходов/доходов с валютой и циклом оплаты,
история платежей с фиксацией курса, курсы валют к RUB. Все суммы в агрегатах
возвращаются в RUB — конвертацию в базовую валюту делает API-слой.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from shared.logger import logger
from shared.db_schema import (
    FINANCE_CATEGORIES_TABLE, FINANCE_PROVIDERS_TABLE, FINANCE_ITEMS_TABLE,
    FINANCE_PAYMENTS_TABLE, FINANCE_RATES_TABLE, NODES_TABLE,
    NODE_TRAFFIC_SNAPSHOTS_TABLE, USER_CONNECTIONS_TABLE,
)

BILLING_CYCLES = ("monthly", "yearly", "once", "days")
ITEM_KINDS = ("expense", "income")


def _num(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    return float(v)


def _d(v: Any) -> Optional[str]:
    """date/datetime -> ISO-строка (или None)."""
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return str(v)


def _payment_row(r: Any) -> Dict[str, Any]:
    """Строка finance_payments -> dict для API: числа float, даты ISO, сумма в RUB."""
    d = dict(r)
    d["amount"] = _num(d.get("amount"))
    d["rate_rub"] = _num(d["rate_rub"]) if d.get("rate_rub") is not None else None
    d["amount_rub"] = round(d["amount"] * (d["rate_rub"] or 1.0), 2)
    d["paid_at"] = _d(d.get("paid_at"))
    d["created_at"] = _d(d.get("created_at"))
    return d


def _advance_due(next_due: date, cycle: str, cycle_days: Optional[int], today: date) -> Optional[date]:
    """Сдвинуть дату следующего платежа на один или несколько циклов вперёд.

    Крутит до первой даты в будущем: если платёж просрочен на несколько
    циклов, одна оплата возвращает расписание в актуальное состояние.
    """
    if cycle == "once":
        return None

    def _plus_month(d: date, months: int) -> date:
        y = d.year + (d.month - 1 + months) // 12
        m = (d.month - 1 + months) % 12 + 1
        # 31-е -> последний день короткого месяца
        for day in (d.day, 30, 29, 28):
            try:
                return date(y, m, day)
            except ValueError:
                continue
        return date(y, m, 28)

    cur = next_due
    for _ in range(1000):  # защита от вечного цикла на битых данных
        if cycle == "monthly":
            cur = _plus_month(cur, 1)
        elif cycle == "yearly":
            cur = _plus_month(cur, 12)
        else:  # days
            cur = cur + timedelta(days=max(1, int(cycle_days or 30)))
        if cur > today:
            return cur
    return cur


def monthly_equivalent(amount: float, cycle: str, cycle_days: Optional[int]) -> float:
    """Нормализованная стоимость записи в месяц (once = 0 — не регулярная)."""
    if cycle == "monthly":
        return amount
    if cycle == "yearly":
        return amount / 12.0
    if cycle == "days":
        return amount * 30.0 / max(1, int(cycle_days or 30))
    return 0.0


class FinanceMixin:
    # ==================== Categories ====================

    async def list_finance_categories(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM {FINANCE_CATEGORIES_TABLE} ORDER BY kind, sort_order, name"
            )
        return [dict(r) | {"created_at": _d(r["created_at"])} for r in rows]

    async def create_finance_category(self, name: str, kind: str, color: Optional[str] = None,
                                      icon: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                f"""INSERT INTO {FINANCE_CATEGORIES_TABLE} (name, kind, color, icon)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (name, kind) DO NOTHING
                    RETURNING *""",
                name, kind, color, icon,
            )
        return dict(row) | {"created_at": _d(row["created_at"])} if row else None

    async def update_finance_category(self, category_id: int, **fields) -> bool:
        if not self.is_connected:
            return False
        allowed = {k: v for k, v in fields.items() if k in ("name", "color", "icon", "sort_order")}
        if not allowed:
            return False
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(allowed))
        async with self.acquire() as conn:
            result = await conn.execute(
                f"UPDATE {FINANCE_CATEGORIES_TABLE} SET {sets} WHERE id = $1",
                category_id, *allowed.values(),
            )
        return "UPDATE 1" in result

    async def delete_finance_category(self, category_id: int) -> bool:
        """Удалить категорию (системные защищены)."""
        if not self.is_connected:
            return False
        async with self.acquire() as conn:
            result = await conn.execute(
                f"DELETE FROM {FINANCE_CATEGORIES_TABLE} WHERE id = $1 AND NOT is_system",
                category_id,
            )
        return "DELETE 1" in result

    # ==================== Providers ====================

    async def list_finance_providers(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT p.*, COUNT(i.id) AS items_count
                    FROM {FINANCE_PROVIDERS_TABLE} p
                    LEFT JOIN {FINANCE_ITEMS_TABLE} i ON i.provider_id = p.id AND i.status = 'active'
                    GROUP BY p.id ORDER BY p.name"""
            )
        return [dict(r) | {"created_at": _d(r["created_at"])} for r in rows]

    async def create_finance_provider(self, name: str, url: Optional[str] = None,
                                      favicon_url: Optional[str] = None,
                                      notes: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                f"""INSERT INTO {FINANCE_PROVIDERS_TABLE} (name, url, favicon_url, notes)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (name) DO UPDATE SET url = COALESCE(EXCLUDED.url, {FINANCE_PROVIDERS_TABLE}.url)
                    RETURNING *""",
                name, url, favicon_url, notes,
            )
        return dict(row) | {"created_at": _d(row["created_at"])} if row else None

    async def update_finance_provider(self, provider_id: int, **fields) -> bool:
        if not self.is_connected:
            return False
        allowed = {k: v for k, v in fields.items() if k in ("name", "url", "favicon_url", "notes", "archived")}
        if not allowed:
            return False
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(allowed))
        async with self.acquire() as conn:
            result = await conn.execute(
                f"UPDATE {FINANCE_PROVIDERS_TABLE} SET {sets} WHERE id = $1",
                provider_id, *allowed.values(),
            )
        return "UPDATE 1" in result

    async def archive_finance_provider_items(self, provider_id: int) -> int:
        """Архивировать все активные записи провайдера (каскад при архиве хостера)."""
        if not self.is_connected:
            return 0
        async with self.acquire() as conn:
            result = await conn.execute(
                f"""UPDATE {FINANCE_ITEMS_TABLE}
                    SET status = 'archived', next_due_at = NULL, updated_at = NOW()
                    WHERE provider_id = $1 AND status = 'active'""",
                provider_id,
            )
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    async def delete_finance_provider(self, provider_id: int) -> bool:
        if not self.is_connected:
            return False
        async with self.acquire() as conn:
            result = await conn.execute(
                f"DELETE FROM {FINANCE_PROVIDERS_TABLE} WHERE id = $1", provider_id,
            )
        return "DELETE 1" in result

    # ==================== Items ====================

    _ITEM_SELECT = f"""
        SELECT i.*,
               c.name AS category_name, c.color AS category_color, c.icon AS category_icon,
               p.name AS provider_name, p.url AS provider_url,
               n.name AS node_name
        FROM {FINANCE_ITEMS_TABLE} i
        LEFT JOIN {FINANCE_CATEGORIES_TABLE} c ON c.id = i.category_id
        LEFT JOIN {FINANCE_PROVIDERS_TABLE} p ON p.id = i.provider_id
        LEFT JOIN {NODES_TABLE} n ON n.uuid = i.node_uuid
    """

    @staticmethod
    def _item_row(r) -> Dict[str, Any]:
        d = dict(r)
        d["amount"] = _num(d.get("amount"))
        d["node_uuid"] = str(d["node_uuid"]) if d.get("node_uuid") else None
        for k in ("next_due_at", "last_reminded_at", "created_at", "updated_at"):
            d[k] = _d(d.get(k))
        d["monthly_equivalent"] = monthly_equivalent(
            d["amount"], d.get("billing_cycle") or "monthly", d.get("cycle_days"),
        )
        return d

    async def list_finance_items(
        self, kind: Optional[str] = None, status: Optional[str] = "active",
        category_id: Optional[int] = None, currency: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        where, params = [], []
        if kind:
            params.append(kind); where.append(f"i.kind = ${len(params)}")
        if status:
            params.append(status); where.append(f"i.status = ${len(params)}")
        if category_id:
            params.append(category_id); where.append(f"i.category_id = ${len(params)}")
        if currency:
            params.append(currency); where.append(f"i.currency = ${len(params)}")
        if search:
            params.append(f"%{search.lower()}%")
            where.append(f"(LOWER(i.name) LIKE ${len(params)} OR LOWER(COALESCE(i.notes, '')) LIKE ${len(params)})")
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"{self._ITEM_SELECT} {where_sql} ORDER BY i.next_due_at NULLS LAST, i.name"
            , *params)
        return [self._item_row(r) for r in rows]

    async def get_finance_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(f"{self._ITEM_SELECT} WHERE i.id = $1", item_id)
        return self._item_row(row) if row else None

    async def create_finance_item(
        self, name: str, kind: str = "expense", category_id: Optional[int] = None,
        provider_id: Optional[int] = None, node_uuid: Optional[str] = None,
        currency: str = "RUB", amount: float = 0.0, billing_cycle: str = "monthly",
        cycle_days: Optional[int] = None, next_due_at: Optional[str] = None,
        url: Optional[str] = None, notes: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                f"""INSERT INTO {FINANCE_ITEMS_TABLE}
                    (name, kind, category_id, provider_id, node_uuid, currency, amount,
                     billing_cycle, cycle_days, next_due_at, url, notes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    RETURNING id""",
                name, kind, category_id, provider_id, node_uuid,
                currency.upper(), round(float(amount), 2), billing_cycle, cycle_days,
                date.fromisoformat(next_due_at) if next_due_at else None, url, notes,
            )
        return await self.get_finance_item(row["id"]) if row else None

    async def update_finance_item(self, item_id: int, **fields) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        allowed_keys = (
            "name", "kind", "category_id", "provider_id", "node_uuid", "currency",
            "amount", "billing_cycle", "cycle_days", "next_due_at", "url", "notes", "status",
            "last_reminded_at",
        )
        allowed: Dict[str, Any] = {k: v for k, v in fields.items() if k in allowed_keys}
        if not allowed:
            return await self.get_finance_item(item_id)
        if "currency" in allowed and allowed["currency"]:
            allowed["currency"] = str(allowed["currency"]).upper()
        if "amount" in allowed and allowed["amount"] is not None:
            allowed["amount"] = round(float(allowed["amount"]), 2)
        if "next_due_at" in allowed and isinstance(allowed["next_due_at"], str):
            allowed["next_due_at"] = date.fromisoformat(allowed["next_due_at"])
        sets = ", ".join(f"{k} = ${i + 2}" for i, k in enumerate(allowed))
        async with self.acquire() as conn:
            await conn.execute(
                f"UPDATE {FINANCE_ITEMS_TABLE} SET {sets}, updated_at = NOW() WHERE id = $1",
                item_id, *allowed.values(),
            )
        return await self.get_finance_item(item_id)

    async def delete_finance_item(self, item_id: int) -> bool:
        if not self.is_connected:
            return False
        async with self.acquire() as conn:
            result = await conn.execute(
                f"DELETE FROM {FINANCE_ITEMS_TABLE} WHERE id = $1", item_id,
            )
        return "DELETE 1" in result

    # ==================== Payments ====================

    async def list_finance_payments(
        self, item_id: Optional[int] = None, since: Optional[str] = None,
        until: Optional[str] = None, limit: int = 100, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        where, params = [], []
        if item_id:
            params.append(item_id); where.append(f"item_id = ${len(params)}")
        if since:
            params.append(date.fromisoformat(since)); where.append(f"paid_at >= ${len(params)}")
        if until:
            params.append(date.fromisoformat(until)); where.append(f"paid_at <= ${len(params)}")
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        params += [limit, offset]
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT * FROM {FINANCE_PAYMENTS_TABLE} {where_sql}
                    ORDER BY paid_at DESC, id DESC LIMIT ${len(params) - 1} OFFSET ${len(params)}""",
                *params,
            )
        return [_payment_row(r) for r in rows]

    async def get_finance_payment(self, payment_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT * FROM {FINANCE_PAYMENTS_TABLE} WHERE id = $1", payment_id,
            )
        return _payment_row(row) if row else None

    async def update_finance_payment(self, payment_id: int, **fields) -> Optional[Dict[str, Any]]:
        """Править операцию на месте (сумма, дата, валюта, тип, название, комментарий).

        Курс к RUB зафиксирован на момент оплаты и при правке суммы/даты не
        трогается; при смене валюты перефиксируется по текущей таблице курсов.
        None — операции нет.
        """
        if not self.is_connected:
            return None
        allowed = {
            k: v for k, v in fields.items()
            if k in ("item_name", "kind", "paid_at", "amount", "currency", "comment")
        }
        if not allowed:
            return await self.get_finance_payment(payment_id)
        if isinstance(allowed.get("paid_at"), str):
            allowed["paid_at"] = date.fromisoformat(allowed["paid_at"])
        if "amount" in allowed:
            allowed["amount"] = round(float(allowed["amount"]), 2)
        if "currency" in allowed:
            allowed["currency"] = str(allowed["currency"]).upper()
        sets = [f"{k} = ${i + 2}" for i, k in enumerate(allowed)]
        if "currency" in allowed:
            cur_idx = list(allowed).index("currency") + 2
            sets.append(
                f"rate_rub = (SELECT rate_rub FROM {FINANCE_RATES_TABLE} WHERE currency = ${cur_idx})"
            )
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                f"UPDATE {FINANCE_PAYMENTS_TABLE} SET {', '.join(sets)} WHERE id = $1 RETURNING *",
                payment_id, *allowed.values(),
            )
        return _payment_row(row) if row else None

    async def delete_finance_payment(self, payment_id: int) -> bool:
        if not self.is_connected:
            return False
        async with self.acquire() as conn:
            result = await conn.execute(
                f"DELETE FROM {FINANCE_PAYMENTS_TABLE} WHERE id = $1", payment_id,
            )
        return "DELETE 1" in result

    async def mark_finance_item_paid(
        self, item_id: int, amount: Optional[float] = None,
        paid_at: Optional[str] = None, comment: Optional[str] = None,
        source: str = "manual",
    ) -> Optional[Dict[str, Any]]:
        """Записать оплату и сдвинуть next_due_at на следующий цикл.

        Курс валюты фиксируется в платеже на момент оплаты — исторические
        отчёты не «переоцениваются» при изменении курса. once-записи после
        оплаты архивируются.
        """
        if not self.is_connected:
            return None
        item = await self.get_finance_item(item_id)
        if not item:
            return None

        pay_amount = round(float(amount if amount is not None else item["amount"]), 2)
        pay_date = date.fromisoformat(paid_at) if paid_at else date.today()

        async with self.acquire() as conn:
            async with conn.transaction():
                rate = await conn.fetchval(
                    f"SELECT rate_rub FROM {FINANCE_RATES_TABLE} WHERE currency = $1",
                    item["currency"],
                )
                await conn.execute(
                    f"""INSERT INTO {FINANCE_PAYMENTS_TABLE}
                        (item_id, item_name, kind, paid_at, amount, currency, rate_rub, comment, source)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                    item_id, item["name"], item["kind"], pay_date, pay_amount,
                    item["currency"], rate, comment, source,
                )

                cycle = item.get("billing_cycle") or "monthly"
                if cycle == "once":
                    await conn.execute(
                        f"""UPDATE {FINANCE_ITEMS_TABLE}
                            SET status = 'archived', next_due_at = NULL, updated_at = NOW()
                            WHERE id = $1""",
                        item_id,
                    )
                else:
                    prev_due = (
                        date.fromisoformat(item["next_due_at"])
                        if item.get("next_due_at") else pay_date
                    )
                    new_due = _advance_due(prev_due, cycle, item.get("cycle_days"), date.today())
                    await conn.execute(
                        f"UPDATE {FINANCE_ITEMS_TABLE} SET next_due_at = $2, updated_at = NOW() WHERE id = $1",
                        item_id, new_due,
                    )
        return await self.get_finance_item(item_id)

    async def skip_finance_item_cycle(self, item_id: int) -> Optional[Dict[str, Any]]:
        """Сдвинуть next_due_at на цикл вперёд БЕЗ записи платежа."""
        if not self.is_connected:
            return None
        item = await self.get_finance_item(item_id)
        if not item:
            return None
        cycle = item.get("billing_cycle") or "monthly"
        today = date.today()
        if cycle == "once":
            await self.update_finance_item(item_id, status="archived", next_due_at=None)
        else:
            prev_due = date.fromisoformat(item["next_due_at"]) if item.get("next_due_at") else today
            new_due = _advance_due(prev_due, cycle, item.get("cycle_days"), today)
            await self.update_finance_item(item_id, next_due_at=new_due)
        return await self.get_finance_item(item_id)

    # ==================== Upcoming / Summary ====================

    async def upcoming_finance_payments(self, days: int = 30) -> List[Dict[str, Any]]:
        """Активные записи со списанием в ближайшие N дней (+ просроченные)."""
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""{self._ITEM_SELECT}
                    WHERE i.status = 'active' AND i.next_due_at IS NOT NULL
                      AND i.next_due_at <= CURRENT_DATE + $1::int
                    ORDER BY i.next_due_at""",
                days,
            )
        today = date.today()
        out = []
        for r in rows:
            d = self._item_row(r)
            due = date.fromisoformat(d["next_due_at"])
            d["days_left"] = (due - today).days
            d["is_overdue"] = due < today
            out.append(d)
        return out

    async def finance_summary(self, months: int = 6) -> Dict[str, Any]:
        """Сводка в RUB: месячный P&L по платежам + структура регулярных записей.

        Конвертация платежей — по зафиксированному rate_rub (fallback на
        текущий курс для старых записей без курса).
        """
        if not self.is_connected:
            return {"monthly": [], "by_category": [], "by_currency": [], "recurring": {}}

        async with self.acquire() as conn:
            monthly_rows = await conn.fetch(
                f"""SELECT date_trunc('month', p.paid_at)::date AS month, p.kind,
                           SUM(p.amount * COALESCE(p.rate_rub, r.rate_rub, 1)) AS total_rub
                    FROM {FINANCE_PAYMENTS_TABLE} p
                    LEFT JOIN {FINANCE_RATES_TABLE} r ON r.currency = p.currency
                    WHERE p.paid_at >= (date_trunc('month', CURRENT_DATE) - ($1::int - 1) * INTERVAL '1 month')
                    GROUP BY 1, 2 ORDER BY 1""",
                months,
            )
            item_rows = await conn.fetch(
                f"""SELECT i.id, i.kind, i.amount, i.billing_cycle, i.cycle_days, i.currency,
                           COALESCE(c.name, '—') AS category_name,
                           COALESCE(c.color, '#64748b') AS category_color
                    FROM {FINANCE_ITEMS_TABLE} i
                    LEFT JOIN {FINANCE_CATEGORIES_TABLE} c ON c.id = i.category_id
                    WHERE i.status = 'active'"""
            )
            rates = {r["currency"]: _num(r["rate_rub"]) for r in await conn.fetch(
                f"SELECT currency, rate_rub FROM {FINANCE_RATES_TABLE}"
            )}
            # записи, по которым в этом месяце УЖЕ был платёж, — их обязательная
            # часть в KPI заменяется фактом (без двойного счёта)
            paid_this_month = {
                r["item_id"] for r in await conn.fetch(
                    f"""SELECT DISTINCT item_id FROM {FINANCE_PAYMENTS_TABLE}
                        WHERE item_id IS NOT NULL
                          AND paid_at >= date_trunc('month', CURRENT_DATE)"""
                )
            }

        monthly: Dict[str, Dict[str, float]] = {}
        for r in monthly_rows:
            key = r["month"].strftime("%Y-%m")
            bucket = monthly.setdefault(key, {"expense": 0.0, "income": 0.0})
            bucket[r["kind"]] = round(_num(r["total_rub"]), 2)
        monthly_list = [
            {"month": k, "expense_rub": v["expense"], "income_rub": v["income"],
             "net_rub": round(v["income"] - v["expense"], 2)}
            for k, v in sorted(monthly.items())
        ]

        by_category: Dict[str, Dict[str, Any]] = {}
        by_currency: Dict[str, Dict[str, float]] = {}
        recurring = {"expense_rub": 0.0, "income_rub": 0.0}
        for r in item_rows:
            me = monthly_equivalent(_num(r["amount"]), r["billing_cycle"], r["cycle_days"])
            me_rub = me * rates.get(r["currency"], 1.0)
            recurring[f"{r['kind']}_rub"] = round(recurring[f"{r['kind']}_rub"] + me_rub, 2)
            cur = by_currency.setdefault(r["currency"], {"expense": 0.0, "income": 0.0})
            cur[r["kind"]] = round(cur[r["kind"]] + me, 2)
            if r["kind"] == "expense":
                cat = by_category.setdefault(r["category_name"], {
                    "category": r["category_name"], "color": r["category_color"], "monthly_rub": 0.0,
                })
                cat["monthly_rub"] = round(cat["monthly_rub"] + me_rub, 2)

        recurring["net_rub"] = round(recurring["income_rub"] - recurring["expense_rub"], 2)

        # KPI текущего месяца: факт + обязательные. Обязательная часть — месячный
        # эквивалент активных регулярных записей, ещё не оплаченных в этом месяце
        # (оплаченные уже сидят в факте). Так расходы не обнуляются, пока все
        # продления хостеров впереди, и нет двойного счёта после оплаты.
        cur_key = date.today().strftime("%Y-%m")
        actual = monthly.get(cur_key, {"expense": 0.0, "income": 0.0})
        upcoming = {"expense": 0.0, "income": 0.0}
        for r in item_rows:
            if r["id"] in paid_this_month:
                continue
            me = monthly_equivalent(_num(r["amount"]), r["billing_cycle"], r["cycle_days"])
            upcoming[r["kind"]] += me * rates.get(r["currency"], 1.0)
        this_month = {
            "month": cur_key,
            "expense_actual_rub": actual["expense"],
            "income_actual_rub": actual["income"],
            "expense_upcoming_rub": round(upcoming["expense"], 2),
            "income_upcoming_rub": round(upcoming["income"], 2),
            "expense_rub": round(actual["expense"] + upcoming["expense"], 2),
            "income_rub": round(actual["income"] + upcoming["income"], 2),
        }
        this_month["net_rub"] = round(this_month["income_rub"] - this_month["expense_rub"], 2)

        return {
            "monthly": monthly_list,
            "this_month": this_month,
            "by_category": sorted(by_category.values(), key=lambda c: -c["monthly_rub"]),
            "by_currency": [
                {"currency": k, "expense_monthly": v["expense"], "income_monthly": v["income"]}
                for k, v in sorted(by_currency.items())
            ],
            "recurring": recurring,
        }

    # ==================== Node costs (себестоимость) ====================

    async def finance_node_costs(self, days: int = 30) -> Dict[str, Any]:
        """Себестоимость нод: расход/мес + трафик и юзеры за окно days.

        - расход — месячный эквивалент активных expense-записей с node_uuid;
        - трафик — сумма положительных дневных дельт lifetime-счётчика ноды
          (устойчиво к ресетам при перезагрузках; снапшоты хранятся 31 день);
        - юзеры — DISTINCT user_uuid по коннектам окна.
        Всё в RUB; конвертацию в базовую валюту делает API-слой.
        """
        if not self.is_connected:
            return {"items": [], "unassigned_monthly_rub": 0.0, "days": days}

        async with self.acquire() as conn:
            item_rows = await conn.fetch(
                f"""SELECT i.node_uuid::text AS node_uuid, i.amount,
                           i.billing_cycle, i.cycle_days, i.currency
                    FROM {FINANCE_ITEMS_TABLE} i
                    WHERE i.status = 'active' AND i.kind = 'expense'"""
            )
            rates = {r["currency"]: _num(r["rate_rub"]) for r in await conn.fetch(
                f"SELECT currency, rate_rub FROM {FINANCE_RATES_TABLE}"
            )}
            traffic_rows = await conn.fetch(
                f"""SELECT node_uuid::text AS node_uuid,
                           SUM(GREATEST(delta, 0)) AS bytes
                    FROM (
                        SELECT node_uuid,
                               per_day - LAG(per_day) OVER (
                                   PARTITION BY node_uuid ORDER BY day) AS delta
                        FROM (
                            SELECT node_uuid,
                                   DATE(created_at AT TIME ZONE 'UTC') AS day,
                                   MAX(traffic_bytes) AS per_day
                            FROM {NODE_TRAFFIC_SNAPSHOTS_TABLE}
                            WHERE created_at >= NOW() - INTERVAL '1 day' * $1
                            GROUP BY node_uuid, DATE(created_at AT TIME ZONE 'UTC')
                        ) d
                    ) t
                    GROUP BY node_uuid""",
                days,
            )
            user_rows = await conn.fetch(
                f"""SELECT node_uuid::text AS node_uuid,
                           COUNT(DISTINCT user_uuid) AS users
                    FROM {USER_CONNECTIONS_TABLE}
                    WHERE node_uuid IS NOT NULL
                      AND connected_at >= NOW() - INTERVAL '1 day' * $1
                    GROUP BY node_uuid""",
                days,
            )
            name_rows = await conn.fetch(
                f"SELECT uuid::text AS node_uuid, name FROM {NODES_TABLE}"
            )

        return self._build_node_costs(
            [dict(r) for r in item_rows], rates,
            {r["node_uuid"]: int(r["bytes"] or 0) for r in traffic_rows},
            {r["node_uuid"]: int(r["users"] or 0) for r in user_rows},
            {r["node_uuid"]: r["name"] for r in name_rows},
            days,
        )

    @staticmethod
    def _build_node_costs(
        item_rows: List[Dict[str, Any]], rates: Dict[str, float],
        traffic: Dict[str, int], users: Dict[str, int],
        names: Dict[str, Optional[str]], days: int,
    ) -> Dict[str, Any]:
        """Чистая сборка метрик себестоимости из выборок (тестируемо без БД)."""
        per_node: Dict[str, Dict[str, Any]] = {}
        unassigned = 0.0
        for r in item_rows:
            me_rub = monthly_equivalent(
                _num(r["amount"]), r["billing_cycle"], r["cycle_days"]
            ) * rates.get(r["currency"], 1.0)
            node_uuid = r.get("node_uuid")
            if node_uuid:
                node = per_node.setdefault(node_uuid, {"monthly_cost_rub": 0.0})
                node["monthly_cost_rub"] += me_rub
            else:
                unassigned += me_rub

        # ноды с трафиком/юзерами, но без расходов — тоже показываем (cost=0)
        for node_uuid in set(traffic) | set(users):
            per_node.setdefault(node_uuid, {"monthly_cost_rub": 0.0})

        gib = float(1024 ** 3)
        items = []
        for node_uuid, node in per_node.items():
            cost = round(node["monthly_cost_rub"], 2)
            gb = round(traffic.get(node_uuid, 0) / gib, 2)
            n_users = users.get(node_uuid, 0)
            items.append({
                "node_uuid": node_uuid,
                "node_name": names.get(node_uuid) or node_uuid[:8],
                "monthly_cost_rub": cost,
                "traffic_gb": gb,
                "cost_per_gb_rub": round(cost / gb, 2) if gb > 0 and cost > 0 else None,
                "users": n_users,
                "cost_per_user_rub": round(cost / n_users, 2) if n_users > 0 and cost > 0 else None,
            })
        items.sort(key=lambda x: -x["monthly_cost_rub"])
        return {
            "items": items,
            "unassigned_monthly_rub": round(unassigned, 2),
            "days": days,
        }

    # ==================== Rates ====================

    async def get_finance_rates(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(f"SELECT * FROM {FINANCE_RATES_TABLE} ORDER BY currency")
        return [
            dict(r) | {"rate_rub": _num(r["rate_rub"]), "updated_at": _d(r["updated_at"])}
            for r in rows
        ]

    async def upsert_finance_rate(self, currency: str, rate_rub: float, is_manual: bool = False) -> None:
        if not self.is_connected:
            return
        async with self.acquire() as conn:
            await conn.execute(
                f"""INSERT INTO {FINANCE_RATES_TABLE} (currency, rate_rub, is_manual, updated_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (currency) DO UPDATE
                    SET rate_rub = EXCLUDED.rate_rub, is_manual = EXCLUDED.is_manual, updated_at = NOW()""",
                currency.upper(), rate_rub, is_manual,
            )

    async def set_finance_rate_manual(self, currency: str, is_manual: bool) -> bool:
        """Переключить ручной флаг курса. False — такой валюты в таблице нет."""
        if not self.is_connected:
            return False
        async with self.acquire() as conn:
            result = await conn.execute(
                f"UPDATE {FINANCE_RATES_TABLE} SET is_manual = $2 WHERE currency = $1",
                currency.upper(), is_manual,
            )
        return "UPDATE 1" in result

    async def finance_currencies_in_use(self) -> List[str]:
        """Валюты активных записей — какие курсы обновлять автоматически."""
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT DISTINCT currency FROM {FINANCE_ITEMS_TABLE} WHERE status = 'active'"
            )
        return [r["currency"] for r in rows]

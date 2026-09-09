"""Тесты финансового модуля: циклы оплат, API /api/v2/finance, курсы, напоминания, импорт."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.db.finance import _advance_due, monthly_equivalent


# ── Unit: логика циклов ──────────────────────────────────────────


class TestAdvanceDue:
    def test_monthly_simple(self):
        assert _advance_due(date(2026, 7, 10), "monthly", None, date(2026, 7, 5)) == date(2026, 8, 10)

    def test_monthly_end_of_month(self):
        # 31 января -> 28 февраля (короткий месяц)
        assert _advance_due(date(2026, 1, 31), "monthly", None, date(2026, 2, 1)) == date(2026, 2, 28)

    def test_monthly_overdue_rolls_to_future(self):
        # просрочка на полгода: одна оплата возвращает расписание в будущее
        assert _advance_due(date(2026, 1, 1), "monthly", None, date(2026, 7, 17)) == date(2026, 8, 1)

    def test_yearly(self):
        assert _advance_due(date(2026, 3, 1), "yearly", None, date(2026, 3, 2)) == date(2027, 3, 1)

    def test_days_cycle(self):
        assert _advance_due(date(2026, 7, 1), "days", 10, date(2026, 7, 17)) == date(2026, 7, 21)

    def test_once_returns_none(self):
        assert _advance_due(date(2026, 7, 1), "once", None, date(2026, 7, 1)) is None


class TestMonthlyEquivalent:
    def test_all_cycles(self):
        assert monthly_equivalent(100, "monthly", None) == 100
        assert monthly_equivalent(1200, "yearly", None) == 100
        assert monthly_equivalent(10, "days", 10) == 30
        assert monthly_equivalent(500, "once", None) == 0


# ── API ──────────────────────────────────────────────────────────


SUMMARY_RUB = {
    "monthly": [{"month": "2026-07", "expense_rub": 5000.0, "income_rub": 12000.0, "net_rub": 7000.0}],
    "by_category": [{"category": "Ноды", "color": "#06b6d4", "monthly_rub": 4000.0}],
    "by_currency": [{"currency": "EUR", "expense_monthly": 40.0, "income_monthly": 0.0}],
    "recurring": {"expense_rub": 5000.0, "income_rub": 12000.0, "net_rub": 7000.0},
}


class TestFinanceApi:
    @pytest.mark.asyncio
    async def test_summary_requires_auth(self, anon_client):
        resp = await anon_client.get("/api/v2/finance/summary")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_summary_denied_without_permission(self, viewer_client):
        resp = await viewer_client.get("/api/v2/finance/summary")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_summary_converts_to_base_currency(self, client):
        db = AsyncMock()
        db.finance_summary = AsyncMock(return_value=SUMMARY_RUB)
        db.get_finance_rates = AsyncMock(return_value=[
            {"currency": "USD", "rate_rub": 100.0, "is_manual": False},
        ])
        with patch("web.backend.api.v2.finance.db_service", db), \
             patch("web.backend.api.v2.finance.config_service") as cfg:
            cfg.get.side_effect = lambda k, d=None: "USD" if k == "finance_base_currency" else d
            resp = await client.get("/api/v2/finance/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["base_currency"] == "USD"
        # 5000 RUB / 100 = 50 USD
        assert data["recurring"]["expense"] == 50.0
        assert data["monthly"][0]["net"] == 70.0

    @pytest.mark.asyncio
    async def test_create_item_validates_cycle(self, client):
        resp = await client.post("/api/v2/finance/items", json={
            "name": "X", "billing_cycle": "weekly",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_item_validates_kind(self, client):
        resp = await client.post("/api/v2/finance/items", json={
            "name": "X", "kind": "profit",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_once_item_records_payment_and_archives(self, client):
        created = {"id": 7, "billing_cycle": "once", "amount": 500.0, "next_due_at": "2026-07-18"}
        archived = {"id": 7, "billing_cycle": "once", "status": "archived", "amount": 500.0}
        db = AsyncMock()
        db.create_finance_item = AsyncMock(return_value=created)
        db.mark_finance_item_paid = AsyncMock()
        db.get_finance_item = AsyncMock(return_value=archived)
        with patch("web.backend.api.v2.finance.db_service", db):
            resp = await client.post("/api/v2/finance/items", json={
                "name": "Халтурка", "kind": "income", "billing_cycle": "once",
                "amount": 500, "next_due_at": "2026-07-18",
            })
        assert resp.status_code == 200
        # разовая запись сразу проведена платежом (на дату next_due_at) и архивирована
        db.mark_finance_item_paid.assert_awaited_once()
        assert db.mark_finance_item_paid.await_args.kwargs.get("paid_at") == "2026-07-18"
        assert resp.json()["status"] == "archived"

    @pytest.mark.asyncio
    async def test_mark_paid_404_on_missing(self, client):
        db = AsyncMock()
        db.mark_finance_item_paid = AsyncMock(return_value=None)
        with patch("web.backend.api.v2.finance.db_service", db):
            resp = await client.post("/api/v2/finance/items/99/paid", json={})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_mark_paid_ok(self, client):
        item = {"id": 5, "name": "Node", "next_due_at": "2026-08-17"}
        db = AsyncMock()
        db.mark_finance_item_paid = AsyncMock(return_value=item)
        with patch("web.backend.api.v2.finance.db_service", db):
            resp = await client.post(
                "/api/v2/finance/items/5/paid", json={"comment": "июль"},
            )
        assert resp.status_code == 200
        assert resp.json()["next_due_at"] == "2026-08-17"
        kwargs = db.mark_finance_item_paid.await_args.kwargs
        assert kwargs["comment"] == "июль"

    @pytest.mark.asyncio
    async def test_delete_requires_delete_permission(self, operator_client):
        resp = await operator_client.delete("/api/v2/finance/items/1")
        assert resp.status_code == 403


# ── Курсы валют ──────────────────────────────────────────────────


class TestRatesUpdate:
    @pytest.mark.asyncio
    async def test_update_skips_manual_and_uses_cbr(self):
        from web.backend.core.finance import rates as rates_mod

        db = AsyncMock()
        db.is_connected = True
        db.finance_currencies_in_use = AsyncMock(return_value=["USD", "EUR", "TRY"])
        db.get_finance_rates = AsyncMock(return_value=[
            {"currency": "TRY", "rate_rub": 3.0, "is_manual": True},
        ])
        db.upsert_finance_rate = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch.object(rates_mod, "fetch_cbr_rates", AsyncMock(return_value={"USD": 92.5, "EUR": 100.1})), \
             patch.object(rates_mod, "fetch_crypto_rates", AsyncMock(return_value={"USDT": 92.4})):
            updated = await rates_mod.update_rates()
        assert updated == 3  # USD + EUR + USDT (из коробки)
        currencies = {c.args[0] for c in db.upsert_finance_rate.await_args_list}
        assert currencies == {"USD", "EUR", "USDT"}  # TRY ручной — не трогаем, RUB не нужен

    @pytest.mark.asyncio
    async def test_fallback_to_erapi(self):
        """Фиат, которого нет у ЦБ, добирается через er-api."""
        from web.backend.core.finance import rates as rates_mod

        db = AsyncMock()
        db.is_connected = True
        db.finance_currencies_in_use = AsyncMock(return_value=["KZT"])
        db.get_finance_rates = AsyncMock(return_value=[])
        db.upsert_finance_rate = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch.object(rates_mod, "fetch_cbr_rates", AsyncMock(return_value={"USD": 92.5})), \
             patch.object(rates_mod, "fetch_erapi_rates", AsyncMock(return_value={"KZT": 0.18})), \
             patch.object(rates_mod, "fetch_crypto_rates", AsyncMock(return_value={})):
            updated = await rates_mod.update_rates()
        assert any(c.args[0] == "KZT" for c in db.upsert_finance_rate.await_args_list)

    @pytest.mark.asyncio
    async def test_crypto_via_coingecko(self):
        """Крипта идёт через CoinGecko, а не через фиатные источники."""
        from web.backend.core.finance import rates as rates_mod

        db = AsyncMock()
        db.is_connected = True
        db.finance_currencies_in_use = AsyncMock(return_value=["BTC", "TON"])
        db.get_finance_rates = AsyncMock(return_value=[])
        db.upsert_finance_rate = AsyncMock()
        crypto_mock = AsyncMock(return_value={"BTC": 9500000.0, "TON": 550.0, "USDT": 92.0})
        with patch("shared.database.db_service", db), \
             patch.object(rates_mod, "fetch_cbr_rates", AsyncMock(return_value={"USD": 92.5, "EUR": 100.0})), \
             patch.object(rates_mod, "fetch_crypto_rates", crypto_mock):
            updated = await rates_mod.update_rates()
        # крипто-фетчу передали только крипту (BTC/TON/USDT), без USD/EUR
        asked = set(crypto_mock.await_args.args[0])
        assert asked == {"BTC", "TON", "USDT"}
        currencies = {c.args[0] for c in db.upsert_finance_rate.await_args_list}
        assert {"BTC", "TON", "USDT", "USD", "EUR"} <= currencies

    def test_fetch_crypto_rates_parsing(self):
        """Парсинг ответа CoinGecko (simple/price)."""
        import asyncio as aio
        import httpx as hx
        from web.backend.core.finance import rates as rates_mod

        def handler(request: hx.Request) -> hx.Response:
            assert "tether" in request.url.params["ids"]
            return hx.Response(200, json={
                "tether": {"rub": 92.35},
                "the-open-network": {"rub": 548.1},
                "bitcoin": {},  # нет rub -> пропускаем
            })

        transport = hx.MockTransport(handler)
        real_client = hx.AsyncClient

        class _Client(real_client):
            def __init__(self, *a, **kw):
                kw["transport"] = transport
                super().__init__(*a, **kw)

        with patch("httpx.AsyncClient", _Client):
            out = aio.run(rates_mod.fetch_crypto_rates(["USDT", "TON", "BTC"]))
        assert out == {"USDT": 92.35, "TON": 548.1}


class TestRatesAutoReset:
    """POST /rates/{currency}/auto — возврат ручного курса на автообновление."""

    @pytest.mark.asyncio
    async def test_resets_flag_and_refetches(self, client):
        db = AsyncMock()
        db.set_finance_rate_manual = AsyncMock(return_value=True)
        db.get_finance_rates = AsyncMock(return_value=[
            {"currency": "EUR", "rate_rub": 100.1, "is_manual": False},
        ])
        update = AsyncMock(return_value=1)
        with patch("web.backend.api.v2.finance.db_service", db),              patch("web.backend.core.finance.rates.update_rates", update):
            resp = await client.post("/api/v2/finance/rates/eur/auto")
        assert resp.status_code == 200
        db.set_finance_rate_manual.assert_awaited_once_with("EUR", False)  # код нормализуется
        update.assert_awaited_once_with(["EUR"])  # тянем только эту валюту
        data = resp.json()
        assert data["updated"] == 1
        assert data["items"][0]["is_manual"] is False

    @pytest.mark.asyncio
    async def test_source_unavailable_still_clears_flag(self, client):
        """Источник курсов недоступен: флаг снят, updated=0 — суточный цикл догонит."""
        db = AsyncMock()
        db.set_finance_rate_manual = AsyncMock(return_value=True)
        db.get_finance_rates = AsyncMock(return_value=[])
        with patch("web.backend.api.v2.finance.db_service", db),              patch("web.backend.core.finance.rates.update_rates", AsyncMock(return_value=0)):
            resp = await client.post("/api/v2/finance/rates/EUR/auto")
        assert resp.status_code == 200
        assert resp.json()["updated"] == 0

    @pytest.mark.asyncio
    async def test_unknown_currency_404(self, client):
        db = AsyncMock()
        db.set_finance_rate_manual = AsyncMock(return_value=False)
        update = AsyncMock(return_value=0)
        with patch("web.backend.api.v2.finance.db_service", db),              patch("web.backend.core.finance.rates.update_rates", update):
            resp = await client.post("/api/v2/finance/rates/XXX/auto")
        assert resp.status_code == 404
        update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_denied_without_permission(self, viewer_client):
        resp = await viewer_client.post("/api/v2/finance/rates/EUR/auto")
        assert resp.status_code == 403


class TestPaymentsEdit:
    """PATCH /payments/{id} — правка операции на месте."""

    @pytest.mark.asyncio
    async def test_update_forwards_fields(self, client):
        db = AsyncMock()
        db.update_finance_payment = AsyncMock(return_value={
            "id": 7, "item_name": "Hetzner", "kind": "expense", "paid_at": "2026-08-01",
            "amount": 12.5, "currency": "EUR", "rate_rub": 100.0, "amount_rub": 1250.0,
            "comment": None, "source": "manual",
        })
        with patch("web.backend.api.v2.finance.db_service", db):
            resp = await client.patch("/api/v2/finance/payments/7", json={
                "amount": 12.5, "paid_at": "2026-08-01", "comment": None,
            })
        assert resp.status_code == 200
        assert resp.json()["amount_rub"] == 1250.0
        # comment=null доходит до БД (очистка), незаданные поля — нет
        db.update_finance_payment.assert_awaited_once_with(7, amount=12.5, paid_at="2026-08-01", comment=None)

    @pytest.mark.asyncio
    async def test_update_not_found(self, client):
        db = AsyncMock()
        db.update_finance_payment = AsyncMock(return_value=None)
        with patch("web.backend.api.v2.finance.db_service", db):
            resp = await client.patch("/api/v2/finance/payments/404", json={"amount": 1})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_validates(self, client):
        db = AsyncMock()
        with patch("web.backend.api.v2.finance.db_service", db):
            bad_kind = await client.patch("/api/v2/finance/payments/1", json={"kind": "refund"})
            bad_date = await client.patch("/api/v2/finance/payments/1", json={"paid_at": "01.08.2026"})
            bad_amount = await client.patch("/api/v2/finance/payments/1", json={"amount": 0})
        assert (bad_kind.status_code, bad_date.status_code, bad_amount.status_code) == (422, 422, 422)
        db.update_finance_payment.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_denied_without_permission(self, viewer_client):
        resp = await viewer_client.patch("/api/v2/finance/payments/1", json={"amount": 1})
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_db_update_refixes_rate_on_currency_change(self, mock_db_acquire):
        """Смена валюты перефиксирует rate_rub из таблицы курсов; прочие правки курс не трогают."""
        from shared.db.finance import FinanceMixin

        mock_conn, cm = mock_db_acquire
        mock_conn.fetchrow = AsyncMock(return_value={
            "id": 1, "item_id": None, "item_name": "X", "kind": "expense", "paid_at": date(2026, 8, 1),
            "amount": 10, "currency": "USD", "rate_rub": 90, "comment": None, "source": "manual",
            "created_at": None,
        })

        class _DB(FinanceMixin):
            is_connected = True

            def acquire(self):
                return cm

        row = await _DB().update_finance_payment(1, currency="usd", amount=10)
        sql = mock_conn.fetchrow.await_args.args[0]
        assert "rate_rub = (SELECT rate_rub FROM" in sql
        assert mock_conn.fetchrow.await_args.args[2] == "USD"  # валюта нормализована
        assert row["amount_rub"] == 900.0
        assert row["paid_at"] == "2026-08-01"

        mock_conn.fetchrow.reset_mock()
        await _DB().update_finance_payment(1, amount=11, paid_at="2026-08-02")
        sql = mock_conn.fetchrow.await_args.args[0]
        assert "rate_rub" not in sql
        assert mock_conn.fetchrow.await_args.args[3] == date(2026, 8, 2)  # ISO-строка -> date


class TestCategoriesApi:
    @pytest.mark.asyncio
    async def test_rename_conflict_409(self, client):
        import asyncpg

        db = AsyncMock()
        db.update_finance_category = AsyncMock(side_effect=asyncpg.UniqueViolationError("dup"))
        with patch("web.backend.api.v2.finance.db_service", db):
            resp = await client.patch("/api/v2/finance/categories/3", json={"name": "Ноды"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_rename_ok(self, client):
        db = AsyncMock()
        db.update_finance_category = AsyncMock(return_value=True)
        with patch("web.backend.api.v2.finance.db_service", db):
            resp = await client.patch("/api/v2/finance/categories/3", json={"name": "Домены"})
        assert resp.status_code == 200
        db.update_finance_category.assert_awaited_once_with(3, name="Домены")


# ── Напоминания ──────────────────────────────────────────────────


def _upcoming_item(item_id=1, days_left=3, overdue=False, reminded=None):
    return {
        "id": item_id, "name": "Node-1", "amount": 5.0, "currency": "EUR",
        "next_due_at": "2026-07-20", "days_left": days_left, "is_overdue": overdue,
        "provider_name": "Aeza", "category_name": "Ноды", "url": None,
        "last_reminded_at": reminded,
    }


class TestReminders:
    @pytest.mark.asyncio
    async def test_sends_on_threshold(self):
        from web.backend.core.finance import reminders as rem

        db = AsyncMock()
        db.is_connected = True
        db.upcoming_finance_payments = AsyncMock(return_value=[_upcoming_item(days_left=3)])
        db.update_finance_item = AsyncMock()
        notify = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.create_notification", notify):
            sent = await rem.check_and_send_reminders()
        assert sent == 1
        notify.assert_awaited_once()
        assert "Node-1" in notify.await_args.kwargs["title"]
        db.update_finance_item.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_off_threshold_and_already_reminded(self):
        from web.backend.core.finance import reminders as rem

        today = date.today().isoformat()
        db = AsyncMock()
        db.is_connected = True
        db.upcoming_finance_payments = AsyncMock(return_value=[
            _upcoming_item(item_id=1, days_left=5),                 # не порог (7,3,1)
            _upcoming_item(item_id=2, days_left=3, reminded=today), # уже напоминали
        ])
        notify = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.create_notification", notify):
            sent = await rem.check_and_send_reminders()
        assert sent == 0
        notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_telegram_card_and_url_button(self):
        """HTML-карточка в telegram_body (blockquote, экранирование) + кнопка кабинета."""
        from web.backend.core.finance import reminders as rem

        db = AsyncMock()
        db.is_connected = True
        item = _upcoming_item(days_left=1)
        item["url"] = "https://my.hoster.com"
        item["provider_name"] = "A&B <Host>"
        db.upcoming_finance_payments = AsyncMock(return_value=[item])
        db.update_finance_item = AsyncMock()
        notify = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.create_notification", notify):
            sent = await rem.check_and_send_reminders()
        assert sent == 1
        kw = notify.await_args.kwargs
        tg = kw["telegram_body"]
        assert tg.startswith("<blockquote>") and tg.endswith("</blockquote>")
        assert "<b>5.00 EUR</b>" in tg
        assert "завтра" in tg and "(20.07.2026)" in tg
        assert "A&amp;B &lt;Host&gt;" in tg  # HTML экранируется
        rows = kw["reply_markup"]["inline_keyboard"]
        assert rows[0][0]["callback_data"] == "fin:paid:1"
        assert rows[1][0]["url"] == "https://my.hoster.com"

    @pytest.mark.asyncio
    async def test_overdue_always_reminds_daily(self):
        from web.backend.core.finance import reminders as rem

        db = AsyncMock()
        db.is_connected = True
        db.upcoming_finance_payments = AsyncMock(return_value=[
            _upcoming_item(days_left=-2, overdue=True),
        ])
        db.update_finance_item = AsyncMock()
        notify = AsyncMock()
        with patch("shared.database.db_service", db), \
             patch("web.backend.core.notification_service.create_notification", notify):
            sent = await rem.check_and_send_reminders()
        assert sent == 1
        assert notify.await_args.kwargs["severity"] == "critical"


# ── Импорт из панельного биллинга ────────────────────────────────


class TestPanelImport:
    @pytest.mark.asyncio
    async def test_imports_providers_nodes_history(self, mock_db_acquire):
        from web.backend.core.finance import importer

        mock_conn, cm = mock_db_acquire
        mock_conn.fetchval = AsyncMock(return_value=None)  # платежей-дублей нет

        db = AsyncMock()
        db.is_connected = True
        db.acquire = lambda: cm
        db.create_finance_provider = AsyncMock(side_effect=[{"id": 11}, {"id": 12}])
        db.list_finance_categories = AsyncMock(return_value=[
            {"id": 1, "kind": "expense", "name": "Ноды"},
        ])
        db.list_finance_items = AsyncMock(return_value=[])
        db.create_finance_item = AsyncMock(return_value={"id": 21})
        db.get_node_by_uuid = AsyncMock(return_value={"name": "de-1"})
        db.get_finance_rates = AsyncMock(return_value=[{"currency": "USD", "rate_rub": 90.0}])

        api = AsyncMock()
        api.get_infra_providers = AsyncMock(return_value={"response": {"providers": [
            {"uuid": "p1", "name": "Hetzner", "loginUrl": "https://h", "faviconLink": None},
            {"uuid": "p2", "name": "Aeza", "loginUrl": None, "faviconLink": None},
        ]}})
        api.get_infra_billing_nodes = AsyncMock(return_value={"response": {"billingNodes": [
            {"uuid": "bn1", "nodeUuid": "3f339d94-0000-0000-0000-000000000001",
             "providerUuid": "p1", "nextBillingAt": "2026-08-01T00:00:00Z"},
        ]}})
        api.get_infra_billing_history = AsyncMock(return_value={"response": {"records": [
            {"uuid": "r1", "provider": {"name": "Hetzner"}, "amount": 50.0, "billedAt": "2026-06-01T00:00:00Z"},
        ]}})

        with patch("shared.database.db_service", db), \
             patch("shared.api_client.api_client", api):
            result = await importer.import_from_panel()

        assert result["providers"] == 2
        assert result["items"] == 1
        assert result["payments"] == 1
        assert result["errors"] == []
        item_kwargs = db.create_finance_item.await_args.kwargs
        assert item_kwargs["name"] == "de-1"
        assert item_kwargs["next_due_at"] == "2026-08-01"
        # безвалютные панельные суммы импортируются в валюте по умолчанию (USD)
        assert item_kwargs["currency"] == "USD"
        # paid_at в INSERT платежа — datetime.date (asyncpg отвергает str для date-параметра)
        from datetime import date as _date
        insert_call = next(c for c in mock_conn.execute.await_args_list if "INSERT INTO" in c.args[0])
        assert isinstance(insert_call.args[2], _date)

    @pytest.mark.asyncio
    async def test_bedolaga_income_overview_normalizes(self):
        from web.backend.core.finance import bedolaga_income as bi

        full = {"transactions": {
            "totals": {"income_rubles": 1000.0, "subscription_income_rubles": 800.0, "profit_rubles": 750.0},
            "today": {"income_rubles": 50.0, "transactions_count": 3},
            "by_payment_method": {"card": {"amount": 100000}},
        }}
        client_bd = AsyncMock()
        client_bd.get_full_stats = AsyncMock(return_value=full)
        with patch("shared.bedolaga_client.bedolaga_client", client_bd), \
             patch("web.backend.api.v2.bedolaga.ensure_configured", lambda: None):
            ov = await bi.fetch_income_overview()
        assert ov["total"]["subscription_income"] == 800.0
        assert ov["total"]["deposit_income"] == 1000.0
        assert ov["total"]["profit"] == 750.0
        assert ov["by_payment_method"]["card"] == 1000.0  # копейки → рубли

    def test_pm_amount_shapes(self):
        from web.backend.core.finance.bedolaga_income import _pm_amount

        assert _pm_amount({"amount_rubles": 250.5}) == 250.5   # уже рубли
        assert _pm_amount({"amount_kopeks": 100000}) == 1000.0  # копейки
        assert _pm_amount({"amount": 100000}) == 1000.0         # эвристика: копейки
        assert _pm_amount(50000) == 500.0                       # голое число
        assert _pm_amount({}) == 0.0
        assert _pm_amount(None) == 0.0

    @pytest.mark.asyncio
    async def test_record_daily_deposits_groups_by_day_and_upserts(self, mock_db_acquire):
        from web.backend.core.finance import bedolaga_income as bi

        mock_conn, cm = mock_db_acquire
        mock_conn.execute = AsyncMock(return_value="UPDATE 0")  # записей ещё нет -> INSERT
        db = AsyncMock()
        db.is_connected = True
        db.acquire = lambda: cm

        client_bd = AsyncMock()
        client_bd.list_transactions = AsyncMock(side_effect=[
            {"items": [
                {"amount_kopeks": -25000, "created_at": "2026-07-10T08:00:00"},
                {"amount_kopeks": -15000, "created_at": "2026-07-10T20:00:00"},
                {"amount_kopeks": -40000, "created_at": "2026-07-11T09:00:00"},
            ]},
            {"items": []},
        ])
        with patch("shared.database.db_service", db), \
             patch("shared.bedolaga_client.bedolaga_client", client_bd), \
             patch("web.backend.api.v2.bedolaga.ensure_configured", lambda: None):
            result = await bi.record_daily_deposits()

        assert result["days"] == 2  # 10-е (250+150=400) и 11-е (400)
        inserts = [c for c in mock_conn.execute.await_args_list if "INSERT INTO" in c.args[0]]
        assert len(inserts) == 2
        amounts = sorted(c.args[3] for c in inserts)
        assert amounts == [400.0, 400.0]
        # paid_at обязан быть datetime.date (asyncpg отвергает str для date-параметра)
        assert all(isinstance(c.args[2], date) for c in inserts)

    @pytest.mark.asyncio
    async def test_skips_existing_node_items_and_duplicate_payments(self, mock_db_acquire):
        from web.backend.core.finance import importer

        mock_conn, cm = mock_db_acquire
        mock_conn.fetchval = AsyncMock(return_value=1)  # платёж уже есть

        db = AsyncMock()
        db.is_connected = True
        db.acquire = lambda: cm
        db.create_finance_provider = AsyncMock(return_value={"id": 11})
        db.list_finance_categories = AsyncMock(return_value=[])
        db.list_finance_items = AsyncMock(return_value=[
            {"node_uuid": "3f339d94-0000-0000-0000-000000000001", "name": "de-1"},
        ])
        db.create_finance_item = AsyncMock()
        db.get_finance_rates = AsyncMock(return_value=[{"currency": "USD", "rate_rub": 90.0}])

        api = AsyncMock()
        api.get_infra_providers = AsyncMock(return_value={"response": {"providers": []}})
        api.get_infra_billing_nodes = AsyncMock(return_value={"response": {"billingNodes": [
            {"uuid": "bn1", "nodeUuid": "3f339d94-0000-0000-0000-000000000001",
             "name": "de-1", "providerUuid": "p1"},
        ]}})
        api.get_infra_billing_history = AsyncMock(return_value={"response": {"records": [
            {"uuid": "r1", "provider": {"name": "Hetzner"}, "amount": 50.0, "billedAt": "2026-06-01T00:00:00Z"},
        ]}})

        with patch("shared.database.db_service", db), \
             patch("shared.api_client.api_client", api):
            result = await importer.import_from_panel()

        assert result["items"] == 0
        assert result["payments"] == 0
        assert result["skipped"] == 2
        db.create_finance_item.assert_not_awaited()

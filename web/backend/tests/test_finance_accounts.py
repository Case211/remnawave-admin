"""Тесты фазы 2 финмодуля: адаптеры хостеров, автосинк, API /finance/accounts."""
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest


# ── Реестр адаптеров ─────────────────────────────────────────────


class TestAdapterRegistry:
    def test_billmanager_and_hostkey_registered(self):
        from web.backend.core.finance.adapters import list_adapters, get_adapter

        slugs = {a["slug"] for a in list_adapters()}
        assert {"billmanager", "hostkey"} <= slugs
        assert get_adapter("billmanager").slug == "billmanager"

    def test_unknown_adapter_raises(self):
        from web.backend.core.finance.adapters import get_adapter, AdapterError

        with pytest.raises(AdapterError):
            get_adapter("nope")

    def test_meta_exposes_fields(self):
        from web.backend.core.finance.adapters import get_adapter

        meta = get_adapter("billmanager").to_meta()
        assert meta["needs_base_url"] is True
        names = {f["name"] for f in meta["fields"]}
        assert {"username", "password"} <= names

    def test_validate_credentials(self):
        from web.backend.core.finance.adapters import get_adapter, AdapterError

        adapter = get_adapter("billmanager")
        with pytest.raises(AdapterError):
            adapter.validate_credentials({"username": "", "password": ""})
        adapter.validate_credentials({"username": "u", "password": "p"})  # не кидает


# ── BILLmanager адаптер (мок httpx) ──────────────────────────────


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patched_client(handler):
    """Фабрика httpx.AsyncClient с MockTransport (без рекурсии на патче класса)."""
    def factory(**kw):
        kw.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw)
    return factory


class TestBillmanagerAdapter:
    @pytest.mark.asyncio
    async def test_endpoint_normalization(self):
        from web.backend.core.finance.adapters.billmanager import BillmanagerAdapter

        a = BillmanagerAdapter()
        assert a._endpoint("https://my.waicore.com") == "https://my.waicore.com/billmgr"
        assert a._endpoint("https://my.h2.nexus/billmgr?func=logon") == "https://my.h2.nexus/billmgr"
        assert a._endpoint("https://bill.1cent.host/billmgr/") == "https://bill.1cent.host/billmgr"
        # serv.host: нестандартный путь /billmgr-api — не доклеиваем /billmgr
        assert a._endpoint("https://my.serv.host/billmgr-api") == "https://my.serv.host/billmgr-api"
        # billmgr в ИМЕНИ ХОСТА — это не путь, /billmgr всё равно нужен
        assert a._endpoint("https://billmgr.example.com") == "https://billmgr.example.com/billmgr"

    @pytest.mark.asyncio
    async def test_fetch_falls_back_to_typed_when_unified_missing(self):
        """Реальный кейс h2.nexus: func=item/service нет («модуль не загружен»),
        услуги берутся из func=vds. Баланс должен подтянуться в любом случае."""
        from web.backend.core.finance.adapters.billmanager import BillmanagerAdapter

        def _not_found(func):
            return httpx.Response(200, json={"doc": {"error": {
                "$type": "missed",
                "msg": {"$": f"Не удалось найти функцию '{func}'. Возможно, управляющий модуль не загружен."},
            }}})

        def handler(request: httpx.Request) -> httpx.Response:
            func = request.url.params.get("func")
            if func == "subaccount":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"balance": {"$": "1234.50"}, "currency": {"$": "usd"}},
                ]}})
            if func == "vds":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"id": {"$": "801"}, "domain": {"$": "vds-de-1"}, "item_cost": {"$": "890.00"},
                     "expiredate": {"$": "2026-08-01"}, "status": {"$": "3"}},
                ]}})
            if func in ("service", "item", "dedic", "vhost", "domain", "soft", "certificate"):
                return _not_found(func)
            return httpx.Response(200, json={"doc": {}})

        adapter = BillmanagerAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            result = await adapter.fetch("https://my.h2.nexus/billmgr", {"username": "u", "password": "p"})

        assert result.balance == 1234.5
        assert result.currency == "USD"
        assert len(result.services) == 1
        vds = result.services[0]
        assert vds.name == "vds-de-1"
        assert vds.price == 890.0
        assert vds.next_due_at == "2026-08-01"
        assert vds.status == "active"

    @pytest.mark.asyncio
    async def test_fetch_uses_unified_service_list_when_available(self):
        from web.backend.core.finance.adapters.billmanager import BillmanagerAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            func = request.url.params.get("func")
            if func == "subaccount":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"balance": {"$": "50.00"}, "currency": {"$": "eur"}},
                ]}})
            if func == "service":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"id": {"$": "1"}, "name": {"$": "srv-1"}, "cost": {"$": "10"},
                     "expiredate": {"$": "2026-09-01"}, "status": {"$": "2"}},
                    {"id": {"$": "2"}, "name": {"$": "dom.ru"}, "expiredate": {"$": "2027-01-01"},
                     "status": {"$": "3"}},
                ]}})
            return httpx.Response(200, json={"doc": {}})

        adapter = BillmanagerAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            result = await adapter.fetch("https://my.waicore.com", {"username": "u", "password": "p"})

        assert result.balance == 50.0
        assert len(result.services) == 2
        # цена отсутствует у домена -> None, а не 0
        assert result.services[1].price is None

    @pytest.mark.asyncio
    async def test_fetch_discovers_submodule_funcs_via_menu(self):
        """Реальный кейс Waicore: vds отвечает, но пуст — реальные VPS живут в
        подмодуле vds.vps, имя которого берём из секции mainmenuservice меню."""
        from web.backend.core.finance.adapters.billmanager import BillmanagerAdapter

        called = []

        def handler(request: httpx.Request) -> httpx.Response:
            func = request.url.params.get("func")
            called.append(func)
            if func == "subaccount":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"balance": {"$": "0.00"}, "currency": {"$": "rub"}},
                ]}})
            if func == "item":
                return httpx.Response(200, json={"doc": {"error": {
                    "$type": "missed", "msg": {"$": "Не удалось найти функцию 'item'."},
                }}})
            if func == "menu":
                return httpx.Response(200, json={"doc": {"menu": [
                    {"$name": "mainmenuservice", "node": [
                        {"$name": "vds", "node": [
                            {"$name": "vds.vps"}, {"$name": "vds.vds_isp"},
                        ]},
                        {"$name": "dedic"},
                    ]},
                    {"$name": "finance", "node": [{"$name": "payment"}]},
                ]}})
            if func == "vds.vps":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"id": {"$": "42"}, "name": {"$": "waicore-de-1"}, "cost": {"$": "450.00"},
                     "expiredate": {"$": "2026-08-20"}, "status": {"$": "2"}},
                ]}})
            # vds/dedic/... отвечают без ошибки, но без elem (как на Waicore)
            return httpx.Response(200, json={"doc": {"p_cnt": {"$": "0"}}})

        adapter = BillmanagerAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            result = await adapter.fetch("https://my.waicore.com", {"username": "u", "password": "p"})

        assert "menu" in called and "vds.vps" in called
        assert len(result.services) == 1
        svc = result.services[0]
        assert svc.name == "waicore-de-1"
        assert svc.price == 450.0
        assert svc.next_due_at == "2026-08-20"
        assert svc.external_id == "42"
        # funcs из меню, недоступные как списки (payment не пробуем — вне секции услуг)
        assert "payment" not in called

    @pytest.mark.asyncio
    async def test_fetch_menu_discovery_augments_nonempty_typed(self):
        """Кейс Waicore: vhost отдаёт бесплатный хостинг (typed непустой),
        а реальные VPS живут в vds.vps — меню должно опрашиваться ВСЕГДА,
        иначе VPS теряются."""
        from web.backend.core.finance.adapters.billmanager import BillmanagerAdapter

        called = []

        def handler(request: httpx.Request) -> httpx.Response:
            func = request.url.params.get("func")
            called.append(func)
            if func == "subaccount":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"balance": {"$": "0.02"}, "currency": {"$": "rub"}},
                ]}})
            if func == "vhost":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"id": {"$": "182426"}, "name": {"$": "Бесплатный #182426"},
                     "cost": {"$": "0.00"}, "expiredate": {"$": "2026-11-14"},
                     "status": {"$": "2"}},
                ]}})
            if func == "menu":
                return httpx.Response(200, json={"doc": {"menu": [
                    {"$name": "mainmenuservice", "node": [
                        {"$name": "vds", "node": [{"$name": "vds.vps"}]},
                        {"$name": "vhost"},
                    ]},
                ]}})
            if func == "vds.vps":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"id": {"$": "42"}, "name": {"$": "waicore-de-1"},
                     "cost": {"$": "450.00"}, "expiredate": {"$": "2026-08-20"},
                     "status": {"$": "2"}},
                ]}})
            if func in ("service", "item"):
                return httpx.Response(200, json={"doc": {"error": {
                    "$type": "missed", "msg": {"$": f"Не удалось найти функцию '{func}'."},
                }}})
            return httpx.Response(200, json={"doc": {"p_cnt": {"$": "0"}}})

        adapter = BillmanagerAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            result = await adapter.fetch("https://my.waicore.net", {"username": "u", "password": "p"})

        assert "menu" in called and "vds.vps" in called
        names = {s.name for s in result.services}
        assert names == {"Бесплатный #182426", "waicore-de-1"}

    @pytest.mark.asyncio
    async def test_fetch_balance_survives_all_services_missing(self):
        """Если ни одной функции услуг нет — баланс всё равно возвращается, services=[]"""
        from web.backend.core.finance.adapters.billmanager import BillmanagerAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            func = request.url.params.get("func")
            if func == "subaccount":
                return httpx.Response(200, json={"doc": {"elem": [
                    {"balance": {"$": "7.00"}, "currency": {"$": "usd"}},
                ]}})
            return httpx.Response(200, json={"doc": {"error": {
                "$type": "missed", "msg": {"$": f"Не удалось найти функцию '{func}'."},
            }}})

        adapter = BillmanagerAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            result = await adapter.fetch("https://my.h2.nexus", {"username": "u", "password": "p"})

        assert result.balance == 7.0
        assert result.services == []

    @pytest.mark.asyncio
    async def test_auth_error_raises_adaptererror(self):
        from web.backend.core.finance.adapters.billmanager import BillmanagerAdapter
        from web.backend.core.finance.adapters import AdapterError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"doc": {"error": {
                "$type": "auth", "$object": "badpassword",
                "msg": {"$": "Неверное имя пользователя или пароль"},
            }}})

        adapter = BillmanagerAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            with pytest.raises(AdapterError, match="[Аа]вториз"):
                await adapter.fetch("https://my.waicore.com", {"username": "u", "password": "bad"})


# ── Hostkey адаптер ──────────────────────────────────────────────


class TestHostkeyAdapter:
    def test_base_ignores_provider_site_url(self):
        from web.backend.core.finance.adapters.hostkey import HostkeyAdapter, _DEFAULT_BASE

        a = HostkeyAdapter()
        # адрес сайта провайдера -> дефолтный invapi-эндпоинт
        assert a._base("https://hostkey.ru") == _DEFAULT_BASE
        assert a._base("") == _DEFAULT_BASE
        assert a._base(None) == _DEFAULT_BASE
        # явный invapi сохраняется
        assert a._base("https://invapi.hostkey.com") == "https://invapi.hostkey.com"

    def test_unwrap_envelope_semantics(self):
        from web.backend.core.finance.adapters.hostkey import _unwrap_envelope

        # dict/list в result -> payload
        assert _unwrap_envelope({"result": {"token": "T"}}) == ({"token": "T"}, None)
        assert _unwrap_envelope({"result": [1, 2]}) == ([1, 2], None)
        # отрицательный код / error -> ошибка
        p, e = _unwrap_envelope({"result": -2, "error": "malformed"})
        assert p is None and "malformed" in e
        # статус "OK" -> успех, payload в остальных ключах
        p, e = _unwrap_envelope({"result": "OK", "credits": {"credit": []}})
        assert e is None and p == {"credits": {"credit": []}}
        # нет конверта -> данные как есть
        assert _unwrap_envelope({"amount": 5}) == ({"amount": 5}, None)

    def test_extract_token_rejects_html(self):
        from web.backend.core.finance.adapters.hostkey import HostkeyAdapter

        assert HostkeyAdapter._extract_token(httpx.Response(200, text="<html><body>site</body></html>")) is None
        assert HostkeyAdapter._extract_token(httpx.Response(200, json={"token": "TKN"})) == "TKN"
        assert HostkeyAdapter._extract_token(httpx.Response(200, text="OPAQUE-TOKEN-123")) == "OPAQUE-TOKEN-123"

    @pytest.mark.asyncio
    async def test_fetch_full_flow_via_invapi(self):
        from urllib.parse import parse_qs
        from web.backend.core.finance.adapters.hostkey import HostkeyAdapter

        hosts_seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            hosts_seen.append(request.url.host)
            path = request.url.path
            body = parse_qs(request.content.decode())
            if path.endswith("/auth.php"):
                # invapi: action=login + key -> токен ВНУТРИ result
                action = (body.get("action") or [""])[0]
                if action == "login" and body.get("key"):
                    return httpx.Response(200, json={"result": {
                        "token": "TKN", "role": "Customer billing", "servers": [55054],
                    }})
                return httpx.Response(200, json={"result": -2, "error": "auth: malformed request #1"})
            if path.endswith("/whmcs.php"):
                action = (body.get("action") or [""])[0]
                if action == "getcredits":
                    # реальная структура: result="OK", ледж. в message.credits.credit,
                    # amount со знаком (сумма = текущий кредит), валюты в записях нет
                    return httpx.Response(200, json={"result": "OK", "message": {
                        "result": "success", "totalresults": 3, "clientid": 77412,
                        "credits": {"credit": [
                            {"id": 1, "amount": "560.00"},
                            {"id": 2, "amount": "-560.00"},
                            {"id": 3, "amount": "42.11"},
                        ]},
                    }})
            if path.endswith("/eq.php"):
                action = (body.get("action") or [""])[0]
                if action == "list":
                    return httpx.Response(200, json={"result": "OK", "message": {"servers": [
                        {"id": 55054, "name": "srv-de-1", "status": "active",
                         "cost": "5.00", "expiredate": "2026-08-10"},
                    ]}})
            return httpx.Response(404)

        adapter = HostkeyAdapter()
        # передаём адрес сайта провайдера — адаптер обязан уйти на invapi
        with patch("httpx.AsyncClient", _patched_client(handler)):
            result = await adapter.fetch("https://hostkey.ru", {"api_key": "KEY"})

        assert all(h.startswith("invapi.") for h in hosts_seen)
        # 560 - 560 + 42.11 = 42.11 (текущий кредит), валюта по домену .ru -> RUB
        assert result.balance == 42.11
        assert result.currency == "RUB"
        assert len(result.services) == 1
        assert result.services[0].name == "srv-de-1"
        assert result.services[0].next_due_at == "2026-08-10"
        assert result.services[0].price == 5.0

    @pytest.mark.asyncio
    async def test_fetch_services_enriches_bare_ids(self):
        """Реальный Hostkey: list -> голые id, детали по show (server_data) +
        get_billing_data (плоский, billing_reccuring/billing_cycle/next_due_date/IP)."""
        from urllib.parse import parse_qs
        from web.backend.core.finance.adapters.hostkey import HostkeyAdapter

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            body = parse_qs(request.content.decode())
            action = (body.get("action") or [""])[0]
            if path.endswith("/auth.php"):
                return httpx.Response(200, json={"result": {"token": "TKN"}})
            if path.endswith("/whmcs.php"):
                if action == "getcredits":
                    return httpx.Response(200, json={"result": "OK", "message": {
                        "credits": {"credit": [{"id": 1, "amount": "100.00"}]}}})
                if action == "get_billing_data":
                    assert (body.get("id") or [""])[0] == "55054"
                    # реальный ответ: плоский, без конверта result
                    return httpx.Response(200, json={
                        "IP": "pl-vmv2-nano", "client_id": 77412, "order_id": 173904,
                        "billing_setupfee": "830.00", "billing_status": "Active",
                        "reg_date": "2026-05-25", "billing_cycle": "Monthly",
                        "next_due_date": "2026-08-25", "billing_reccuring": "830.00",
                        "billing_name": "Услуги по предоставлению вычислительных мощностей (Instant server PL)"})
            if path.endswith("/eq.php"):
                if action == "list":
                    # голые id на верхнем уровне (как на реальном инстансе)
                    return httpx.Response(200, json={
                        "result": "OK", "module": "eq", "servers": [55054]})
                if action == "show":
                    assert (body.get("id") or [""])[0] == "55054"
                    # реальный ответ: запись под server_data, чистого имени нет
                    return httpx.Response(200, json={"result": "OK", "server_data": {
                        "id": 55054, "ref_tableName": "VPS", "account_id": 175709,
                        "limit_traffic": 3, "limit_bands": 1000}})
            return httpx.Response(404)

        adapter = HostkeyAdapter()
        with patch("httpx.AsyncClient", _patched_client(handler)):
            result = await adapter.fetch(None, {"api_key": "KEY"})

        assert len(result.services) == 1
        svc = result.services[0]
        assert svc.name == "pl-vmv2-nano"          # из поля IP
        assert svc.external_id == "55054"
        assert svc.price == 830.0                  # billing_reccuring
        assert svc.period == "monthly"             # Monthly -> нормализация
        assert svc.next_due_at == "2026-08-25"     # next_due_date
        assert svc.status == "active"              # billing_status
        assert svc.specs == "Instant server PL"    # из скобок billing_name
        assert svc.currency is None                # валюты нет -> фолбэк на баланс в UI


# ── Сопоставление услуг с нодами ─────────────────────────────────


class TestNodeMatching:
    def test_extract_ips(self):
        from web.backend.core.finance.adapters.base import extract_ips

        rec = {
            "ip": "89.19.223.46",
            "nested": {"iplist": ["10.0.5.7", "89.19.223.46"]},  # дедуп
            "deny": ["0.0.0.0", "127.0.0.1", "255.255.255.0"],
            "text": "srv 103.214.69.124:443",
        }
        ips = extract_ips(rec)
        assert ips.count("89.19.223.46") == 1
        assert "103.214.69.124" in ips
        assert "10.0.5.7" in ips
        assert not any(ip.startswith(("0.", "127.", "255.")) for ip in ips)

    @pytest.mark.asyncio
    async def test_attach_nodes_to_services(self):
        from web.backend.api.v2 import finance as fin_api

        accounts = [{
            "id": 1,
            "services": [
                {"name": "pl-vmv2-nano", "ips": ["82.38.65.201"]},  # матч по address
                {"name": "Germany W", "ips": None},                  # матч по имени
                {"name": "other", "ips": ["9.9.9.9"]},               # без матча
                {"name": "waicore-fi", "ips": ["65.109.1.2"]},       # матч по agent_ip (NetBird)
            ],
        }]
        nodes = [
            {"uuid": "u1", "name": "RWPanel", "address": "82.38.65.201"},
            {"uuid": "u2", "name": "Germany W", "address": "de.example.com"},
            # за NetBird: address — туннельный, публичный IP пришёл с коллектора
            {"uuid": "u3", "name": "Finland", "address": "100.101.2.3", "agent_ip": "65.109.1.2"},
        ]
        db = AsyncMock()
        db.get_all_nodes = AsyncMock(return_value=nodes)
        with patch.object(fin_api, "db_service", db):
            await fin_api._attach_nodes_to_services(accounts)
        svcs = accounts[0]["services"]
        assert svcs[0]["node_uuid"] == "u1" and svcs[0]["node_name"] == "RWPanel"
        assert svcs[1]["node_uuid"] == "u2"
        assert "node_uuid" not in svcs[2]
        assert svcs[3]["node_uuid"] == "u3" and svcs[3]["node_name"] == "Finland"


# ── Себестоимость нод ────────────────────────────────────────────


class TestNodeCosts:
    def test_build_node_costs(self):
        from shared.db.finance import FinanceMixin

        item_rows = [
            # нода A: 450 RUB/мес + 12 USD/мес (курс 80) = 450 + 960 = 1410
            {"node_uuid": "a", "amount": 450, "billing_cycle": "monthly", "cycle_days": None, "currency": "RUB"},
            {"node_uuid": "a", "amount": 12, "billing_cycle": "monthly", "cycle_days": None, "currency": "USD"},
            # нода B: 3600 RUB/год = 300/мес
            {"node_uuid": "b", "amount": 3600, "billing_cycle": "yearly", "cycle_days": None, "currency": "RUB"},
            # без ноды: 500/мес -> unassigned
            {"node_uuid": None, "amount": 500, "billing_cycle": "monthly", "cycle_days": None, "currency": "RUB"},
        ]
        gib = 1024 ** 3
        result = FinanceMixin._build_node_costs(
            item_rows, {"RUB": 1.0, "USD": 80.0},
            traffic={"a": 100 * gib, "c": 50 * gib},   # у c трафик есть, расходов нет
            users={"a": 47, "b": 10},
            names={"a": "Germany W", "b": "Finland", "c": "RU Route"},
            days=30,
        )
        assert result["unassigned_monthly_rub"] == 500.0
        by_uuid = {i["node_uuid"]: i for i in result["items"]}
        a, b, c = by_uuid["a"], by_uuid["b"], by_uuid["c"]
        assert a["monthly_cost_rub"] == 1410.0
        assert a["traffic_gb"] == 100.0
        assert a["cost_per_gb_rub"] == round(1410 / 100, 2)
        assert a["cost_per_user_rub"] == 30.0
        assert b["monthly_cost_rub"] == 300.0
        assert b["cost_per_gb_rub"] is None      # трафика нет
        assert b["cost_per_user_rub"] == 30.0
        assert c["monthly_cost_rub"] == 0.0      # нода без расходов, но с трафиком
        assert c["cost_per_gb_rub"] is None
        # сортировка по расходу: a, b, c
        assert [i["node_uuid"] for i in result["items"]] == ["a", "b", "c"]

    def test_deleted_node_shows_only_while_expense_is_assigned(self):
        """Регрессия: удалённые в панели ноды висели в таблице обрезанным UUID.

        Снапшоты трафика и коннекты переживают ноду до 31 дня; без расходов
        такой призрак только мешает. С назначенным расходом нода остаётся —
        деньги по ней всё ещё учитываются.
        """
        from shared.db.finance import FinanceMixin

        gib = 1024 ** 3
        result = FinanceMixin._build_node_costs(
            [{"node_uuid": "85839bc0-dead", "amount": 300, "billing_cycle": "monthly",
              "cycle_days": None, "currency": "RUB"}],
            {"RUB": 1.0},
            traffic={"3a5a830b-gone": 514 * gib, "85839bc0-dead": 115 * gib, "live": 10 * gib},
            users={"a8174d6e-gone": 5, "live": 40},
            names={"live": "Germany W"},
            days=30,
        )
        by_uuid = {i["node_uuid"]: i for i in result["items"]}
        assert set(by_uuid) == {"live", "85839bc0-dead"}
        assert by_uuid["live"]["node_name"] == "Germany W"
        assert by_uuid["85839bc0-dead"]["monthly_cost_rub"] == 300.0


# ── Автосинк ─────────────────────────────────────────────────────


def _fake_sync_result(balance=1000.0, currency="USD", services=None):
    from web.backend.core.finance.adapters.base import SyncResult, Service
    return SyncResult(balance=balance, currency=currency, services=services or [
        Service(name="vds-de-1", price=890.0, next_due_at="2026-08-01"),
    ])


class TestSync:
    @pytest.mark.asyncio
    async def test_sync_account_records_snapshot_and_due_dates(self):
        from web.backend.core.finance import sync as sync_mod

        account = {
            "id": 3, "provider_id": 7, "provider_name": "Waicore", "provider_url": None,
            "adapter": "billmanager", "base_url": "https://my.waicore.com",
            "low_balance_threshold": None, "last_alerted_at": None,
        }
        db = AsyncMock()
        db.is_connected = True
        db.get_finance_account = AsyncMock(return_value=account)
        db.get_finance_account_credentials = AsyncMock(return_value="ENC")
        db.set_finance_account_sync_result = AsyncMock()
        db.record_finance_balance_snapshot = AsyncMock()
        db.update_finance_item = AsyncMock()
        db.list_finance_items = AsyncMock(return_value=[
            {"id": 55, "name": "vds-de-1", "provider_id": 7, "next_due_at": "2026-07-01"},
        ])

        fake_adapter = AsyncMock()
        fake_adapter.fetch = AsyncMock(return_value=_fake_sync_result())

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.crypto.decrypt_field", return_value='{"username":"u","password":"p"}'), \
             patch("web.backend.core.finance.sync.get_adapter", return_value=fake_adapter), \
             patch("shared.config_service.config_service") as cfg:
            cfg.get.side_effect = lambda k, d=None: d
            result = await sync_mod.sync_account(3)

        assert result["status"] == "ok"
        assert result["balance"] == 1000.0
        db.record_finance_balance_snapshot.assert_awaited_once()
        # дата списания подтянулась к данным хостера
        db.update_finance_item.assert_awaited_once()
        assert db.update_finance_item.await_args.kwargs["next_due_at"] == "2026-08-01"
        ok_kwargs = db.set_finance_account_sync_result.await_args.kwargs
        assert ok_kwargs["ok"] is True

    @pytest.mark.asyncio
    async def test_sync_account_low_balance_alerts_once(self):
        from web.backend.core.finance import sync as sync_mod

        account = {
            "id": 3, "provider_id": 7, "provider_name": "Waicore", "provider_url": "https://w",
            "adapter": "billmanager", "base_url": "https://w",
            "low_balance_threshold": 500.0, "last_alerted_at": None,
        }
        db = AsyncMock()
        db.is_connected = True
        db.get_finance_account = AsyncMock(return_value=account)
        db.get_finance_account_credentials = AsyncMock(return_value="ENC")
        db.set_finance_account_sync_result = AsyncMock()
        db.record_finance_balance_snapshot = AsyncMock()
        db.update_finance_account = AsyncMock()
        db.list_finance_items = AsyncMock(return_value=[])

        fake_adapter = AsyncMock()
        fake_adapter.fetch = AsyncMock(return_value=_fake_sync_result(balance=100.0, services=[]))
        notify = AsyncMock()

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.crypto.decrypt_field", return_value='{"username":"u","password":"p"}'), \
             patch("web.backend.core.finance.sync.get_adapter", return_value=fake_adapter), \
             patch("web.backend.core.notification_service.create_notification", notify), \
             patch("shared.config_service.config_service") as cfg:
            cfg.get.side_effect = lambda k, d=None: d
            result = await sync_mod.sync_account(3)

        assert result["low_balance_alert"] is True
        notify.assert_awaited_once()
        assert notify.await_args.kwargs["event"] == "finance.low_balance"

    @pytest.mark.asyncio
    async def test_sync_account_adapter_error_marks_error(self):
        from web.backend.core.finance import sync as sync_mod
        from web.backend.core.finance.adapters import AdapterError

        account = {
            "id": 3, "provider_id": 7, "provider_name": "Waicore", "provider_url": None,
            "adapter": "billmanager", "base_url": "https://w",
            "low_balance_threshold": None, "last_alerted_at": None,
        }
        db = AsyncMock()
        db.is_connected = True
        db.get_finance_account = AsyncMock(return_value=account)
        db.get_finance_account_credentials = AsyncMock(return_value="ENC")
        db.set_finance_account_sync_result = AsyncMock()

        fake_adapter = AsyncMock()
        fake_adapter.fetch = AsyncMock(side_effect=AdapterError("Ошибка авторизации"))

        with patch("shared.database.db_service", db), \
             patch("web.backend.core.crypto.decrypt_field", return_value='{"username":"u","password":"p"}'), \
             patch("web.backend.core.finance.sync.get_adapter", return_value=fake_adapter):
            result = await sync_mod.sync_account(3)

        assert result["status"] == "error"
        assert "авториз" in result["error"].lower()
        assert db.set_finance_account_sync_result.await_args.kwargs["ok"] is False


# ── API /finance/accounts ────────────────────────────────────────


class TestAccountsApi:
    @pytest.mark.asyncio
    async def test_list_adapters_requires_auth(self, anon_client):
        resp = await anon_client.get("/api/v2/finance/adapters")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_adapters(self, client):
        resp = await client.get("/api/v2/finance/adapters")
        assert resp.status_code == 200
        slugs = {a["slug"] for a in resp.json()["items"]}
        assert "billmanager" in slugs

    @pytest.mark.asyncio
    async def test_create_account_encrypts_credentials(self, client):
        db = AsyncMock()
        db.create_finance_account = AsyncMock(return_value={"id": 9, "provider_id": 7})
        with patch("web.backend.api.v2.finance.db_service", db), \
             patch("web.backend.core.crypto.encrypt_field", return_value="ENC") as enc:
            resp = await client.post("/api/v2/finance/accounts", json={
                "provider_id": 7, "adapter": "billmanager",
                "base_url": "https://my.waicore.com",
                "credentials": {"username": "u", "password": "p"},
                "low_balance_threshold": 500,
            })
        assert resp.status_code == 200
        enc.assert_called_once()
        # креды уходят в БД зашифрованными, не в открытую
        assert db.create_finance_account.await_args.kwargs["credentials"] == "ENC"

    @pytest.mark.asyncio
    async def test_create_account_rejects_bad_credentials(self, client):
        resp = await client.post("/api/v2/finance/accounts", json={
            "provider_id": 7, "adapter": "billmanager",
            "base_url": "https://w", "credentials": {"username": "", "password": ""},
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_create_account_requires_base_url_for_billmanager(self, client):
        resp = await client.post("/api/v2/finance/accounts", json={
            "provider_id": 7, "adapter": "billmanager",
            "credentials": {"username": "u", "password": "p"},
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_test_connection_returns_balance(self, client):
        from web.backend.core.finance.adapters.base import SyncResult, Service

        adapter = AsyncMock()
        adapter.validate_credentials = lambda c: None
        adapter.test = AsyncMock(return_value=SyncResult(
            balance=500.0, currency="USD", services=[Service(name="x")],
        ))
        with patch("web.backend.core.finance.adapters.get_adapter", return_value=adapter):
            resp = await client.post("/api/v2/finance/accounts/test", json={
                "adapter": "billmanager", "base_url": "https://w",
                "credentials": {"username": "u", "password": "p"},
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["balance"] == 500.0
        assert len(data["services"]) == 1

    @pytest.mark.asyncio
    async def test_delete_account_requires_permission(self, operator_client):
        resp = await operator_client.delete("/api/v2/finance/accounts/1")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_import_panel_currency_param(self, client):
        importer = AsyncMock(return_value={"providers": 0, "items": 0, "payments": 0, "retagged": 3, "skipped": 0, "errors": []})
        with patch("web.backend.core.finance.importer.import_from_panel", importer):
            resp = await client.post("/api/v2/finance/import-panel?currency=EUR")
        assert resp.status_code == 200
        assert importer.await_args.kwargs["currency"] == "EUR"

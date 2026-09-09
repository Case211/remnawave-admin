"""Тесты DNS-провайдеров (core/dns/*): Cloudflare, Timeweb, reg.ru + реестр/креды."""
import json

import httpx
import pytest
from unittest.mock import patch


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patched_client(handler):
    def factory(**kw):
        kw.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw)
    return factory


# ── Реестр ───────────────────────────────────────────────────────


class TestRegistry:
    def test_providers_registered(self):
        from web.backend.core import dns

        slugs = {p.slug for p in dns.list_providers()}
        assert {"cloudflare", "timeweb", "regru", "selectel", "aeza", "route53", "porkbun"} <= slugs
        assert dns.get_provider("route53").proxyable == []
        assert dns.get_provider("cloudflare").proxyable == ["A", "AAAA", "CNAME"]
        assert dns.get_provider("regru").supports_ttl is False
        assert dns.get_provider("timeweb").proxyable == []

    def test_unknown_raises(self):
        from web.backend.core import dns
        with pytest.raises(dns.DnsProviderError):
            dns.get_provider("nope")


# ── Cloudflare ───────────────────────────────────────────────────


class TestCloudflare:
    @pytest.mark.asyncio
    async def test_verify_zones_records(self):
        from web.backend.core.dns.cloudflare import CloudflareProvider

        def h(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "Bearer T"
            p = request.url.path
            if p == "/client/v4/user/tokens/verify":
                # Account owned tokens этим эндпоинтом отвергаются, хотя для
                # зон/записей валидны — verify НЕ должен на него ходить
                return httpx.Response(400, json={
                    "success": False, "errors": [{"message": "Invalid API Token"}]})
            if p == "/client/v4/zones":
                return httpx.Response(200, json={"success": True, "result": [
                    {"id": "z1", "name": "a.com"}]})
            if p == "/client/v4/zones/z1/dns_records":
                return httpx.Response(200, json={"success": True, "result": [
                    {"id": "r1", "type": "A", "name": "a.com", "content": "1.2.3.4",
                     "ttl": 1, "proxied": True}], "result_info": {"page": 1, "total_pages": 1}})
            return httpx.Response(404)

        prov = CloudflareProvider()
        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await prov.verify({"token": "T"}) is True
            zs = await prov.list_zones({"token": "T"})
            rs = await prov.list_records({"token": "T"}, "z1")
        assert zs[0].name == "a.com"
        assert rs[0].type == "A" and rs[0].proxied is True

    @pytest.mark.asyncio
    async def test_create_sends_proxied(self):
        from web.backend.core.dns.cloudflare import CloudflareProvider

        seen = {}

        def h(request):
            seen.update(json.loads(request.content.decode()))
            return httpx.Response(200, json={"success": True, "result": {
                "id": "n", "type": "A", "name": "x.a.com", "content": "5.6.7.8",
                "proxied": True, "ttl": 1}})

        with patch("httpx.AsyncClient", _patched_client(h)):
            rec = await CloudflareProvider().create_record({"token": "T"}, "z1", {
                "type": "A", "name": "x.a.com", "content": "5.6.7.8", "proxied": True, "ttl": 1})
        assert rec.id == "n" and seen["proxied"] is True and seen["type"] == "A"

    @pytest.mark.asyncio
    async def test_verify_false_on_forbidden(self):
        from web.backend.core.dns.cloudflare import CloudflareProvider

        def h(request):
            return httpx.Response(403, json={"success": False, "errors": [{"message": "bad"}]})

        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await CloudflareProvider().verify({"token": "bad"}) is False


# ── Timeweb Cloud ────────────────────────────────────────────────


class TestTimeweb:
    @pytest.mark.asyncio
    async def test_zones_records_create(self):
        from web.backend.core.dns.timeweb import TimewebProvider

        seen = {}

        def h(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("Authorization") == "Bearer T"
            p, m = request.url.path, request.method
            if p == "/api/v1/domains":
                return httpx.Response(200, json={"domains": [{"fqdn": "a.com"}]})
            if p == "/api/v1/domains/a.com/dns-records" and m == "GET":
                return httpx.Response(200, json={"dns_records": [
                    {"id": 55, "type": "A", "data": {"value": "1.2.3.4", "subdomain": "www"}, "ttl": 3600}]})
            if p == "/api/v1/domains/a.com/dns-records" and m == "POST":
                seen.update(json.loads(request.content.decode()))
                return httpx.Response(201, json={"dns_record": {
                    "id": 66, "type": "A", "data": {"value": "5.6.7.8", "subdomain": "api"}, "ttl": 300}})
            return httpx.Response(404)

        prov = TimewebProvider()
        with patch("httpx.AsyncClient", _patched_client(h)):
            zs = await prov.list_zones({"token": "T"})
            rs = await prov.list_records({"token": "T"}, "a.com")
            rec = await prov.create_record({"token": "T"}, "a.com", {
                "type": "A", "name": "api", "content": "5.6.7.8", "ttl": 300})
        assert zs[0].id == "a.com"
        assert rs[0].name == "www" and rs[0].content == "1.2.3.4"
        assert seen["subdomain"] == "api" and seen["value"] == "5.6.7.8" and seen["ttl"] == 300
        assert rec.id == "66"


# ── reg.ru ───────────────────────────────────────────────────────


class TestRegru:
    @pytest.mark.asyncio
    async def test_zones_records_synthetic_id(self):
        from web.backend.core.dns.regru import RegruProvider, _unid

        def h(request: httpx.Request) -> httpx.Response:
            p = request.url.path
            assert dict(request.url.params).get("username") == "u"
            if p.endswith("/domain/get_list"):
                return httpx.Response(200, json={"result": "success",
                                                 "answer": {"domains": [{"dname": "a.com"}]}})
            if p.endswith("/zone/get_resource_records"):
                return httpx.Response(200, json={"result": "success", "answer": {"domains": [
                    {"dname": "a.com", "rrs": [
                        {"subname": "www", "rectype": "A", "content": "1.2.3.4"}]}]}})
            return httpx.Response(404)

        prov = RegruProvider()
        with patch("httpx.AsyncClient", _patched_client(h)):
            zs = await prov.list_zones({"username": "u", "password": "p"})
            rs = await prov.list_records({"username": "u", "password": "p"}, "a.com")
        assert zs[0].name == "a.com"
        r = rs[0]
        assert r.type == "A" and r.name == "www" and r.content == "1.2.3.4"
        assert _unid(r.id) == ("www", "A", "1.2.3.4")

    @pytest.mark.asyncio
    async def test_create_a_then_delete(self):
        from web.backend.core.dns.regru import RegruProvider

        calls = []

        def h(request):
            p = request.url.path
            input_data = json.loads(dict(request.url.params).get("input_data", "{}"))
            calls.append((p.split("/")[-1], input_data))
            return httpx.Response(200, json={"result": "success", "answer": {}})

        prov = RegruProvider()
        with patch("httpx.AsyncClient", _patched_client(h)):
            rec = await prov.create_record({"username": "u", "password": "p"}, "a.com", {
                "type": "A", "name": "www", "content": "9.9.9.9"})
            await prov.delete_record({"username": "u", "password": "p"}, "a.com", rec.id)

        assert calls[0][0] == "add_alias" and calls[0][1]["ipaddr"] == "9.9.9.9"
        assert calls[1][0] == "remove_record" and calls[1][1]["content"] == "9.9.9.9"

    @pytest.mark.asyncio
    async def test_result_error_raises(self):
        from web.backend.core.dns.regru import RegruProvider
        from web.backend.core.dns import DnsProviderError

        def h(request):
            return httpx.Response(200, json={"result": "error", "error_text": "Auth"})

        with patch("httpx.AsyncClient", _patched_client(h)):
            with pytest.raises(DnsProviderError):
                await RegruProvider().list_zones({"username": "u", "password": "bad"})


# ── Selectel ─────────────────────────────────────────────────────


class TestSelectelDns:
    @pytest.mark.asyncio
    async def test_zones_records_create(self):
        from web.backend.core.dns.selectel import SelectelProvider

        seen = {}

        def h(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("X-Token") == "STATIC"
            p, m = request.url.path, request.method
            if p == "/domains/v1/" and m == "GET":
                return httpx.Response(200, json=[{"id": 101, "name": "a.com"}])
            if p == "/domains/v1/101/records/" and m == "GET":
                return httpx.Response(200, json=[
                    {"id": 9, "type": "A", "name": "www.a.com", "content": "1.2.3.4", "ttl": 3600}])
            if p == "/domains/v1/101/records/" and m == "POST":
                seen.update(json.loads(request.content.decode()))
                return httpx.Response(200, json={
                    "id": 10, "type": "A", "name": "api.a.com", "content": "5.6.7.8", "ttl": 300})
            return httpx.Response(404)

        prov = SelectelProvider()
        with patch("httpx.AsyncClient", _patched_client(h)):
            zs = await prov.list_zones({"token": "STATIC"})
            rs = await prov.list_records({"token": "STATIC"}, "101")
            rec = await prov.create_record({"token": "STATIC"}, "101", {
                "type": "A", "name": "api.a.com", "content": "5.6.7.8", "ttl": 300})
        assert zs[0].id == "101" and zs[0].name == "a.com"
        assert rs[0].name == "www.a.com" and rs[0].content == "1.2.3.4"
        assert seen["type"] == "A" and seen["content"] == "5.6.7.8" and seen["ttl"] == 300
        assert rec.id == "10"

    @pytest.mark.asyncio
    async def test_verify_false_on_forbidden(self):
        from web.backend.core.dns.selectel import SelectelProvider

        def h(request):
            return httpx.Response(401, json={"error": "bad"})

        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await SelectelProvider().verify({"token": "bad"}) is False


# ── Aeza ─────────────────────────────────────────────────────────


class TestAezaDns:
    @pytest.mark.asyncio
    async def test_zones_records_create(self):
        from web.backend.core.dns.aeza import AezaProvider

        seen = {}

        def h(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("X-API-KEY") == "KEY"
            p, m = request.url.path, request.method
            if p == "/api/v2/domains" and m == "GET":
                return httpx.Response(200, json={"data": {"items": [
                    {"id": 3413, "name": "example.com"}]}})
            if p == "/api/v2/domains/3413/records" and m == "GET":
                return httpx.Response(200, json={"data": {"items": [
                    {"id": 1, "type": "A", "name": "www", "content": "1.2.3.4", "ttl": 3600}]}})
            if p == "/api/v2/domains/3413/records" and m == "POST":
                seen.update(json.loads(request.content.decode()))
                return httpx.Response(201, json={"data": {
                    "id": 2, "type": "A", "name": "api", "content": "5.6.7.8"}})
            return httpx.Response(404)

        prov = AezaProvider()
        with patch("httpx.AsyncClient", _patched_client(h)):
            zs = await prov.list_zones({"api_key": "KEY"})
            rs = await prov.list_records({"api_key": "KEY"}, "3413")
            rec = await prov.create_record({"api_key": "KEY"}, "3413", {
                "type": "A", "name": "api", "content": "5.6.7.8"})
        assert zs[0].id == "3413" and zs[0].name == "example.com"
        assert rs[0].name == "www" and rs[0].content == "1.2.3.4"
        assert seen["type"] == "A" and seen["content"] == "5.6.7.8" and seen["name"] == "api"
        assert rec.id == "2"

    @pytest.mark.asyncio
    async def test_verify_false_on_forbidden(self):
        from web.backend.core.dns.aeza import AezaProvider

        def h(request):
            return httpx.Response(403, json={"error": "bad"})

        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await AezaProvider().verify({"api_key": "bad"}) is False


# ── Хранение кредов ──────────────────────────────────────────────


class TestCredsStorage:
    def test_get_creds_decrypts_json(self):
        from web.backend.core import dns
        with patch("web.backend.core.dns.base.decrypt_field", return_value='{"token":"X"}'), \
             patch("shared.config_service.config_service") as cfg:
            cfg.get.return_value = "ENC"
            assert dns.get_creds("cloudflare") == {"token": "X"}

    def test_get_creds_none_when_empty(self):
        from web.backend.core import dns
        with patch("shared.config_service.config_service") as cfg:
            cfg.get.return_value = None
            assert dns.get_creds("cloudflare") is None


class TestTimewebPagination:
    """Timeweb: limit ≤ 500 (limit=1000 давал 400 и «записи не грузятся»)."""

    def _provider(self, pages):
        from unittest.mock import AsyncMock
        from web.backend.core.dns.timeweb import TimewebProvider
        p = TimewebProvider()
        p._req = AsyncMock(side_effect=pages)
        return p

    @pytest.mark.asyncio
    async def test_records_single_page(self):
        pages = [{
            "meta": {"total": 2},
            "dns_records": [
                {"id": 1, "type": "A", "ttl": 600, "data": {"value": "1.2.3.4"}},
                {"id": 2, "type": "TXT", "ttl": 600,
                 "data": {"subdomain": "www", "value": "v=spf1"}},
            ],
        }]
        p = self._provider(pages)
        recs = await p.list_records({"token": "t"}, "stijoin.com")
        assert [r.name for r in recs] == ["@", "www"]
        # запрос ушёл с допустимым лимитом ≤ 500
        url = p._req.await_args_list[0].args[2]
        assert "limit=500" in url and "limit=1000" not in url

    @pytest.mark.asyncio
    async def test_records_paginated(self):
        first = {"meta": {"total": 501},
                 "dns_records": [{"id": i, "type": "A", "data": {"value": "x"}}
                                 for i in range(500)]}
        second = {"meta": {"total": 501},
                  "dns_records": [{"id": 500, "type": "A", "data": {"value": "x"}}]}
        p = self._provider([first, second])
        recs = await p.list_records({"token": "t"}, "z")
        assert len(recs) == 501
        assert p._req.await_count == 2
        assert "offset=500" in p._req.await_args_list[1].args[2]

    @pytest.mark.asyncio
    async def test_zones_paginated(self):
        first = {"meta": {"total": 101},
                 "domains": [{"fqdn": f"d{i}.com"} for i in range(100)]}
        second = {"meta": {"total": 101}, "domains": [{"fqdn": "last.com"}]}
        p = self._provider([first, second])
        zones = await p.list_zones({"token": "t"})
        assert len(zones) == 101
        assert zones[-1].name == "last.com"


# ── Amazon Route 53 ──────────────────────────────────────────────

_R53_NS = "https://route53.amazonaws.com/doc/2013-04-01/"


def _r53_rrset(name, rtype, ttl, values):
    rrs = "".join(f"<ResourceRecord><Value>{v}</Value></ResourceRecord>" for v in values)
    return (f"<ResourceRecordSet><Name>{name}</Name><Type>{rtype}</Type><TTL>{ttl}</TTL>"
            f"<ResourceRecords>{rrs}</ResourceRecords></ResourceRecordSet>")


def _r53_list(sets):
    return (f'<ListResourceRecordSetsResponse xmlns="{_R53_NS}"><ResourceRecordSets>'
            f'{"".join(sets)}</ResourceRecordSets><IsTruncated>false</IsTruncated>'
            "</ListResourceRecordSetsResponse>")


_A_SET = _r53_rrset("www.example.com.", "A", 300, ["1.2.3.4", "5.6.7.8"])
_TXT_SET = _r53_rrset("example.com.", "TXT", 3600, ['"v=spf1 -all"'])
_MX_SET = _r53_rrset("example.com.", "MX", 3600, ["10 mail.example.com."])
_ALIAS_SET = ('<ResourceRecordSet><Name>cdn.example.com.</Name><Type>A</Type>'
              '<AliasTarget><HostedZoneId>Z2</HostedZoneId><DNSName>d1.cloudfront.net.</DNSName>'
              '</AliasTarget></ResourceRecordSet>')


class TestRoute53Dns:
    CREDS = {"access_key_id": "AKIATEST", "secret_access_key": "secret"}

    def _handler(self, changes):
        def h(request: httpx.Request) -> httpx.Response:
            auth = request.headers.get("Authorization", "")
            assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKIATEST/")
            assert "/us-east-1/route53/aws4_request" in auth
            assert request.headers.get("x-amz-date") and request.headers.get("x-amz-content-sha256")
            p, m, q = request.url.path, request.method, dict(request.url.params)
            if p == "/2013-04-01/hostedzone" and m == "GET":
                return httpx.Response(200, text=(
                    f'<ListHostedZonesResponse xmlns="{_R53_NS}"><HostedZones><HostedZone>'
                    "<Id>/hostedzone/Z1</Id><Name>example.com.</Name></HostedZone></HostedZones>"
                    "<IsTruncated>false</IsTruncated></ListHostedZonesResponse>"))
            if p == "/2013-04-01/hostedzone/Z1" and m == "GET":
                return httpx.Response(200, text=(
                    f'<GetHostedZoneResponse xmlns="{_R53_NS}"><HostedZone><Id>/hostedzone/Z1</Id>'
                    "<Name>example.com.</Name></HostedZone></GetHostedZoneResponse>"))
            if p == "/2013-04-01/hostedzone/Z1/rrset" and m == "GET":
                if q.get("name") == "www.example.com." and q.get("type") == "A":
                    return httpx.Response(200, text=_r53_list([_A_SET]))
                if q.get("name") == "example.com." and q.get("type") == "TXT":
                    return httpx.Response(200, text=_r53_list([_TXT_SET]))
                if q.get("name") == "api.example.com.":
                    # Листинг начинается со следующего по алфавиту набора — не наш.
                    return httpx.Response(200, text=_r53_list([_MX_SET]))
                return httpx.Response(200, text=_r53_list([_A_SET, _TXT_SET, _MX_SET, _ALIAS_SET]))
            if p == "/2013-04-01/hostedzone/Z1/rrset/" and m == "POST":
                changes.append(request.content.decode())
                return httpx.Response(200, text=(
                    f'<ChangeResourceRecordSetsResponse xmlns="{_R53_NS}"><ChangeInfo>'
                    "<Id>/change/C1</Id><Status>PENDING</Status></ChangeInfo>"
                    "</ChangeResourceRecordSetsResponse>"))
            return httpx.Response(404, text=(
                f'<ErrorResponse xmlns="{_R53_NS}"><Error><Code>NoSuchHostedZone</Code>'
                "<Message>nope</Message></Error></ErrorResponse>"))
        return h

    @pytest.mark.asyncio
    async def test_zones_and_flattened_records(self):
        from web.backend.core.dns.route53 import Route53Provider

        prov = Route53Provider()
        with patch("httpx.AsyncClient", _patched_client(self._handler([]))):
            assert await prov.verify(self.CREDS) is True
            zs = await prov.list_zones(self.CREDS)
            rs = await prov.list_records(self.CREDS, "Z1")
        assert zs[0].id == "Z1" and zs[0].name == "example.com"
        a = [r for r in rs if r.type == "A" and not r.content.startswith("ALIAS")]
        assert [r.content for r in a] == ["1.2.3.4", "5.6.7.8"]
        assert a[0].name == "www.example.com" and a[0].ttl == 300
        txt = next(r for r in rs if r.type == "TXT")
        assert txt.content == "v=spf1 -all"
        mx = next(r for r in rs if r.type == "MX")
        assert mx.priority == 10 and mx.content == "mail.example.com."
        alias = next(r for r in rs if r.content.startswith("ALIAS"))
        assert alias.id.startswith("alias|") and alias.content == "ALIAS d1.cloudfront.net"
        assert len({r.id for r in rs}) == len(rs)

    @pytest.mark.asyncio
    async def test_create_appends_value_to_existing_set(self):
        from web.backend.core.dns.route53 import Route53Provider

        changes = []
        with patch("httpx.AsyncClient", _patched_client(self._handler(changes))):
            rec = await Route53Provider().create_record(
                self.CREDS, "Z1", {"type": "A", "name": "www", "content": "9.9.9.9"})
        assert len(changes) == 1
        assert "<Action>UPSERT</Action>" in changes[0]
        assert "<Name>www.example.com.</Name>" in changes[0]
        for v in ("1.2.3.4", "5.6.7.8", "9.9.9.9"):
            assert f"<Value>{v}</Value>" in changes[0]
        assert "<TTL>300</TTL>" in changes[0]
        assert rec.name == "www.example.com" and rec.content == "9.9.9.9"

    @pytest.mark.asyncio
    async def test_create_new_set_quotes_txt_and_prefixes_mx_priority(self):
        from web.backend.core.dns.route53 import Route53Provider

        changes = []
        with patch("httpx.AsyncClient", _patched_client(self._handler(changes))):
            txt = await Route53Provider().create_record(
                self.CREDS, "Z1", {"type": "TXT", "name": "api", "content": "hello", "ttl": 60})
            mx = await Route53Provider().create_record(
                self.CREDS, "Z1", {"type": "MX", "name": "api", "content": "mx.example.com", "priority": 20})
        assert '<Value>"hello"</Value>' in changes[0] and "<TTL>60</TTL>" in changes[0]
        assert "<Value>20 mx.example.com</Value>" in changes[1]
        assert txt.content == "hello" and mx.priority == 20 and mx.content == "mx.example.com"

    @pytest.mark.asyncio
    async def test_delete_value_upserts_remaining_and_deletes_last(self):
        from web.backend.core.dns.route53 import Route53Provider, _mkid

        changes = []
        with patch("httpx.AsyncClient", _patched_client(self._handler(changes))):
            prov = Route53Provider()
            await prov.delete_record(self.CREDS, "Z1", _mkid("www.example.com", "A", "1.2.3.4"))
            await prov.delete_record(self.CREDS, "Z1", _mkid("example.com", "TXT", '"v=spf1 -all"'))
        assert "<Action>UPSERT</Action>" in changes[0]
        assert "<Value>5.6.7.8</Value>" in changes[0] and "1.2.3.4" not in changes[0]
        assert "<Action>DELETE</Action>" in changes[1]
        assert '<Value>"v=spf1 -all"</Value>' in changes[1] and "<TTL>3600</TTL>" in changes[1]

    @pytest.mark.asyncio
    async def test_alias_records_are_read_only(self):
        from web.backend.core.dns import DnsProviderError
        from web.backend.core.dns.route53 import Route53Provider

        with pytest.raises(DnsProviderError):
            await Route53Provider().delete_record(self.CREDS, "Z1", "alias|cdn.example.com|A")

    @pytest.mark.asyncio
    async def test_verify_false_on_forbidden(self):
        from web.backend.core.dns.route53 import Route53Provider

        def h(request):
            return httpx.Response(403, text=(
                f'<ErrorResponse xmlns="{_R53_NS}"><Error><Code>InvalidClientTokenId</Code>'
                "<Message>bad</Message></Error></ErrorResponse>"))

        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await Route53Provider().verify(self.CREDS) is False

    def test_signature_is_deterministic(self):
        from datetime import datetime, timezone
        from web.backend.core.dns.route53 import _sign

        now = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        h1 = _sign("GET", "/2013-04-01/hostedzone", "maxitems=1", b"", "AK", "SK", now=now)
        h2 = _sign("GET", "/2013-04-01/hostedzone", "maxitems=1", b"", "AK", "SK", now=now)
        assert h1 == h2
        assert h1["X-Amz-Date"] == "20260908T120000Z"
        assert "Credential=AK/20260908/us-east-1/route53/aws4_request" in h1["Authorization"]
        assert "SignedHeaders=host;x-amz-content-sha256;x-amz-date" in h1["Authorization"]


# ── Porkbun ──────────────────────────────────────────────────────


class TestPorkbunDns:
    CREDS = {"apikey": "pk1_x", "secretapikey": "sk1_y"}

    def _handler(self, seen):
        def h(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode())
            assert body["apikey"] == "pk1_x" and body["secretapikey"] == "sk1_y"
            p = request.url.path
            if p == "/api/json/v3/ping":
                return httpx.Response(200, json={"status": "SUCCESS", "yourIp": "1.1.1.1"})
            if p == "/api/json/v3/domain/listAll":
                return httpx.Response(200, json={"status": "SUCCESS", "domains": [
                    {"domain": "example.com", "status": "ACTIVE"}]})
            if p == "/api/json/v3/dns/retrieve/example.com":
                return httpx.Response(200, json={"status": "SUCCESS", "records": [
                    {"id": "101", "name": "www.example.com", "type": "A", "content": "1.2.3.4",
                     "ttl": "600", "prio": "0"},
                    {"id": "102", "name": "example.com", "type": "MX", "content": "mail.example.com",
                     "ttl": "600", "prio": "10"}]})
            if p == "/api/json/v3/dns/create/example.com":
                seen["created"] = body
                return httpx.Response(200, json={"status": "SUCCESS", "id": 103})
            if p == "/api/json/v3/dns/edit/example.com/101":
                seen["edited"] = body
                return httpx.Response(200, json={"status": "SUCCESS"})
            if p == "/api/json/v3/dns/delete/example.com/101":
                seen["deleted"] = True
                return httpx.Response(200, json={"status": "SUCCESS"})
            return httpx.Response(400, json={"status": "ERROR",
                                             "message": "Domain is not opted in to API access."})
        return h

    @pytest.mark.asyncio
    async def test_zones_records_create_edit_delete(self):
        from web.backend.core.dns.porkbun import PorkbunProvider

        seen = {}
        prov = PorkbunProvider()
        with patch("httpx.AsyncClient", _patched_client(self._handler(seen))):
            assert await prov.verify(self.CREDS) is True
            zs = await prov.list_zones(self.CREDS)
            rs = await prov.list_records(self.CREDS, "example.com")
            rec = await prov.create_record(self.CREDS, "example.com", {
                "type": "A", "name": "api.example.com", "content": "5.6.7.8", "ttl": 60})
            await prov.update_record(self.CREDS, "example.com", "101", {
                "type": "A", "name": "@", "content": "7.7.7.7"})
            await prov.delete_record(self.CREDS, "example.com", "101")
        assert zs[0].id == "example.com" and zs[0].name == "example.com"
        assert rs[0].id == "101" and rs[0].ttl == 600 and rs[0].priority is None
        assert rs[1].type == "MX" and rs[1].priority == 10
        # Имя относительно зоны, TTL поднят до минимума Porkbun (600)
        assert seen["created"]["name"] == "api" and seen["created"]["ttl"] == "600"
        assert rec.id == "103" and rec.name == "api.example.com" and rec.ttl == 600
        assert seen["edited"]["name"] == "" and seen["edited"]["content"] == "7.7.7.7"
        assert seen["deleted"] is True

    @pytest.mark.asyncio
    async def test_api_error_message_surfaces(self):
        from web.backend.core.dns import DnsProviderError
        from web.backend.core.dns.porkbun import PorkbunProvider

        with patch("httpx.AsyncClient", _patched_client(self._handler({}))):
            with pytest.raises(DnsProviderError) as exc:
                await PorkbunProvider().list_records(self.CREDS, "other.com")
        assert "opted in" in str(exc.value)

    @pytest.mark.asyncio
    async def test_verify_false_on_bad_keys(self):
        from web.backend.core.dns.porkbun import PorkbunProvider

        def h(request):
            return httpx.Response(400, json={"status": "ERROR", "message": "Invalid API key."})

        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await PorkbunProvider().verify(self.CREDS) is False

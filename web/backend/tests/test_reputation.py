"""Тесты адаптеров репутации IP (нормализация ответов провайдеров)."""
import httpx
import pytest
from unittest.mock import patch

from web.backend.core.reputation import adapters as ad

_REAL = httpx.AsyncClient


def _patched(handler):
    def factory(**kw):
        kw.pop("transport", None)
        return _REAL(transport=httpx.MockTransport(handler), **kw)
    return factory


class TestAdapters:
    @pytest.mark.asyncio
    async def test_ipapi(self):
        def h(r):
            return httpx.Response(200, json={"status": "success", "countryCode": "US",
                                             "isp": "Google", "org": "Google LLC",
                                             "as": "AS15169 Google", "proxy": False,
                                             "hosting": True, "query": "8.8.8.8"})
        with patch("httpx.AsyncClient", _patched(h)):
            d = await ad.IpApi().lookup("8.8.8.8", None)
        assert d["is_hosting"] is True and d["country"] == "US"
        assert d["asn"] == "AS15169 Google" and d["provider"] == "ipapi"

    @pytest.mark.asyncio
    async def test_ipqs(self):
        def h(r):
            return httpx.Response(200, json={"success": True, "fraud_score": 75, "proxy": True,
                                             "vpn": True, "tor": False, "recent_abuse": True,
                                             "country_code": "NL", "ASN": 1234, "ISP": "Host"})
        with patch("httpx.AsyncClient", _patched(h)):
            d = await ad.Ipqs().lookup("1.2.3.4", "tok")
        assert d["score"] == 75 and d["is_vpn"] is True and d["asn"] == "AS1234"

    @pytest.mark.asyncio
    async def test_abuseipdb(self):
        def h(r):
            return httpx.Response(200, json={"data": {"abuseConfidenceScore": 40, "totalReports": 3,
                                                      "isTor": False, "countryCode": "DE",
                                                      "usageType": "Data Center/Web Hosting/Transit",
                                                      "isp": "Hetzner"}})
        with patch("httpx.AsyncClient", _patched(h)):
            d = await ad.AbuseIpdb().lookup("5.6.7.8", "tok")
        assert d["score"] == 40 and d["recent_abuse"] is True and d["is_hosting"] is True

    @pytest.mark.asyncio
    async def test_ipqs_error(self):
        def h(r):
            return httpx.Response(200, json={"success": False, "message": "Invalid key"})
        with patch("httpx.AsyncClient", _patched(h)):
            with pytest.raises(ad.RepError, match="Invalid"):
                await ad.Ipqs().lookup("1.2.3.4", "bad")

    @pytest.mark.asyncio
    async def test_cheburcheck(self):
        def h(r):
            return httpx.Response(200, json={"blocked": True, "rkn_domain": "rutracker.org",
                                             "blocked_subnets": [], "ips": ["1.2.3.4"],
                                             "cdn_providers": {"cloudflare": []},
                                             "geo": {"asn": 13335, "country_code": "US",
                                                     "organisation": "Cloudflare"}})
        with patch("httpx.AsyncClient", _patched(h)):
            d = await ad.Cheburcheck().lookup("rutracker.org", None)
        assert d["blocked"] is True and d["rkn_domain"] == "rutracker.org"
        assert d["asn"] == "AS13335" and d["country"] == "US"

    @pytest.mark.asyncio
    async def test_vpndetection(self):
        seen = {}

        def h(r):
            seen["auth"] = r.headers.get("Authorization")
            return httpx.Response(200, json={"ip": "146.70.116.130", "is_vpn": True, "is_tor": False,
                                             "is_hosting": True, "is_resproxy": False,
                                             "is_dcproxy": False, "is_mobproxy": False,
                                             "is_pubproxy": True, "location": {"country": "AT"},
                                             "asn": {"asn": 9009, "name": "M247 Europe SRL"},
                                             "company": {"name": "M247 LTD Vienna Infrastructure"}})
        with patch("httpx.AsyncClient", _patched(h)):
            d = await ad.VpnDetection().lookup("146.70.116.130", "tok")
        assert seen["auth"] == "Bearer tok" and d["provider"] == "vpndetection"
        assert d["is_vpn"] is True and d["is_proxy"] is True and d["is_hosting"] is True
        assert d["asn"] == "AS9009" and d["country"] == "AT"
        assert d["org"] == "M247 LTD Vienna Infrastructure"

    @pytest.mark.asyncio
    async def test_vpndetection_bad_token(self):
        def h(r):
            return httpx.Response(401, json={"error": "invalid API key"})
        with patch("httpx.AsyncClient", _patched(h)):
            with pytest.raises(ad.RepError):
                await ad.VpnDetection().lookup("1.2.3.4", "bad")


class TestLookupAll:
    @pytest.mark.asyncio
    async def test_domain_runs_only_domain_providers(self):
        from web.backend.core.reputation import base as repbase

        def h(r):
            return httpx.Response(200, json={"blocked": False, "geo": {"country_code": "DE"}})
        with patch("httpx.AsyncClient", _patched(h)), patch.object(repbase, "get_token", return_value=None):
            res = await repbase.lookup_all("example.com")
        assert {r["provider"] for r in res} == {"cheburcheck"}

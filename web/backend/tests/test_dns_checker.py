"""Tests for web.backend.core.mail.dns_checker module."""
from unittest.mock import patch, MagicMock

import pytest

from web.backend.core.mail.dns_checker import (
    DnsRecord,
    _resolve,
    check_mx_records,
    check_spf_record,
    check_dkim_record,
    check_dmarc_record,
    check_ptr_record,
    get_server_ip,
    get_required_dns_records,
)

MODULE = "web.backend.core.mail.dns_checker"


# ── DnsRecord ────────────────────────────────────────────────


class TestDnsRecord:
    def test_defaults(self):
        rec = DnsRecord(record_type="TXT", host="example.com", value="v=spf1 -all", purpose="SPF")
        assert rec.is_configured is False
        assert rec.current_value is None

    def test_all_fields(self):
        rec = DnsRecord(
            record_type="MX", host="example.com", value="10 mail.example.com.",
            purpose="MX", is_configured=True, current_value="10 mail.example.com.",
        )
        assert rec.is_configured is True


# ── _resolve ─────────────────────────────────────────────────


class TestResolve:
    def test_returns_string_list(self):
        rdata1 = MagicMock(__str__=lambda self: "10 mail.example.com.")
        rdata2 = MagicMock(__str__=lambda self: "20 backup.example.com.")
        fake_resolver = MagicMock()
        fake_resolver.resolve.return_value = [rdata1, rdata2]

        with patch(f"{MODULE}._get_resolver", return_value=fake_resolver):
            result = _resolve("example.com", "MX")
        assert result == ["10 mail.example.com.", "20 backup.example.com."]

    def test_returns_empty_on_error(self):
        fake_resolver = MagicMock()
        fake_resolver.resolve.side_effect = Exception("NXDOMAIN")

        with patch(f"{MODULE}._get_resolver", return_value=fake_resolver):
            result = _resolve("nonexistent.example.com", "TXT")
        assert result == []

    def test_uses_public_nameservers(self):
        from web.backend.core.mail.dns_checker import _get_resolver, PUBLIC_NAMESERVERS
        fake_resolver_cls = MagicMock()
        fake_resolver_instance = MagicMock()
        fake_resolver_cls.return_value = fake_resolver_instance
        mock_dns_resolver = MagicMock(Resolver=fake_resolver_cls)
        mock_dns = MagicMock(resolver=mock_dns_resolver)
        with patch.dict("sys.modules", {"dns": mock_dns, "dns.resolver": mock_dns_resolver}):
            _get_resolver()
        fake_resolver_cls.assert_called_once_with(configure=False)
        assert fake_resolver_instance.nameservers == PUBLIC_NAMESERVERS


# ── check_mx_records ─────────────────────────────────────────


class TestCheckMxRecords:
    @patch(f"{MODULE}._resolve", return_value=["10 mail.example.com."])
    def test_mx_found(self, mock_resolve):
        ok, records = check_mx_records("example.com")
        assert ok is True
        assert records == ["10 mail.example.com."]

    @patch(f"{MODULE}._resolve", return_value=[])
    def test_mx_not_found(self, mock_resolve):
        ok, records = check_mx_records("example.com")
        assert ok is False
        assert records == []


# ── check_spf_record ─────────────────────────────────────────


class TestCheckSpfRecord:
    @patch(f"{MODULE}._resolve", return_value=['"v=spf1 ip4:1.2.3.4 -all"'])
    def test_spf_with_matching_ip(self, mock_resolve):
        ok, val = check_spf_record("example.com", "1.2.3.4")
        assert ok is True

    @patch(f"{MODULE}._resolve", return_value=['"v=spf1 include:_spf.google.com -all"'])
    def test_spf_with_include(self, mock_resolve):
        ok, val = check_spf_record("example.com", "9.9.9.9")
        assert ok is True

    @patch(f"{MODULE}._resolve", return_value=['"v=spf1 ip4:5.6.7.8 -all"'])
    def test_spf_ip_not_found(self, mock_resolve):
        ok, val = check_spf_record("example.com", "1.2.3.4")
        assert ok is False

    @patch(f"{MODULE}._resolve", return_value=[])
    def test_no_txt_records(self, mock_resolve):
        ok, val = check_spf_record("example.com", "1.2.3.4")
        assert ok is False
        assert val is None

    @patch(f"{MODULE}._resolve", return_value=['"google-site-verification=abc"'])
    def test_txt_without_spf(self, mock_resolve):
        ok, val = check_spf_record("example.com", "1.2.3.4")
        assert ok is False
        assert val is None


# ── check_dkim_record ────────────────────────────────────────


class TestCheckDkimRecord:
    @patch(f"{MODULE}._resolve", return_value=['"v=DKIM1; k=rsa; p=AAAA"'])
    def test_dkim_found(self, mock_resolve):
        ok, val = check_dkim_record("example.com", "default")
        assert ok is True
        mock_resolve.assert_called_once_with("default._domainkey.example.com", "TXT")

    @patch(f"{MODULE}._resolve", return_value=['"some unrelated txt"'])
    def test_dkim_wrong_record(self, mock_resolve):
        ok, val = check_dkim_record("example.com", "sel")
        assert ok is False
        assert val == "some unrelated txt"

    @patch(f"{MODULE}._resolve", return_value=[])
    def test_dkim_no_records(self, mock_resolve):
        ok, val = check_dkim_record("example.com", "sel")
        assert ok is False
        assert val is None


# ── check_dmarc_record ───────────────────────────────────────


class TestCheckDmarcRecord:
    @patch(f"{MODULE}._resolve", return_value=['"v=DMARC1; p=quarantine"'])
    def test_dmarc_found(self, mock_resolve):
        ok, val = check_dmarc_record("example.com")
        assert ok is True
        mock_resolve.assert_called_once_with("_dmarc.example.com", "TXT")

    @patch(f"{MODULE}._resolve", return_value=[])
    def test_dmarc_not_found(self, mock_resolve):
        ok, val = check_dmarc_record("example.com")
        assert ok is False
        assert val is None

    @patch(f"{MODULE}._resolve", return_value=['"not a dmarc record"'])
    def test_dmarc_wrong_txt(self, mock_resolve):
        ok, val = check_dmarc_record("example.com")
        assert ok is False
        assert val is None


# ── check_ptr_record ─────────────────────────────────────────


class TestCheckPtrRecord:
    def _setup(self, ptr_value: str):
        rdata = MagicMock(__str__=lambda self: ptr_value)
        fake_resolver = MagicMock()
        fake_resolver.resolve.return_value = [rdata]
        mock_reversename = MagicMock()
        mock_reversename.from_address.return_value = "4.3.2.1.in-addr.arpa."
        mock_dns = MagicMock(reversename=mock_reversename)
        return fake_resolver, mock_dns, mock_reversename

    def test_ptr_matches_domain(self):
        fake_resolver, mock_dns, mock_reversename = self._setup("example.com.")
        with patch(f"{MODULE}._get_resolver", return_value=fake_resolver), \
             patch.dict("sys.modules", {"dns": mock_dns, "dns.reversename": mock_reversename}):
            ok, val = check_ptr_record("1.2.3.4", "example.com")
        assert ok is True
        assert val == "example.com"

    def test_ptr_matches_subdomain(self):
        fake_resolver, mock_dns, mock_reversename = self._setup("mail.example.com.")
        with patch(f"{MODULE}._get_resolver", return_value=fake_resolver), \
             patch.dict("sys.modules", {"dns": mock_dns, "dns.reversename": mock_reversename}):
            ok, val = check_ptr_record("1.2.3.4", "example.com")
        assert ok is True

    def test_ptr_no_match(self):
        fake_resolver, mock_dns, mock_reversename = self._setup("other.domain.com.")
        with patch(f"{MODULE}._get_resolver", return_value=fake_resolver), \
             patch.dict("sys.modules", {"dns": mock_dns, "dns.reversename": mock_reversename}):
            ok, val = check_ptr_record("1.2.3.4", "example.com")
        assert ok is False

    def test_ptr_exception(self):
        mock_reversename = MagicMock()
        mock_reversename.from_address.side_effect = Exception("fail")
        mock_dns = MagicMock()
        mock_dns.reversename = mock_reversename

        with patch.dict("sys.modules", {
            "dns": mock_dns, "dns.reversename": mock_reversename,
        }):
            ok, val = check_ptr_record("1.2.3.4", "example.com")
        assert ok is False
        assert val is None


# ── get_server_ip ────────────────────────────────────────────


class TestGetServerIp:
    def test_ipify_success(self):
        mock_resp = MagicMock()
        mock_resp.text = "  203.0.113.5  "
        mock_httpx = MagicMock()
        mock_httpx.get.return_value = mock_resp

        with patch.dict("sys.modules", {"httpx": mock_httpx}):
            result = get_server_ip()
        assert result == "203.0.113.5"

    def test_fallback_to_socket(self):
        mock_httpx = MagicMock()
        mock_httpx.get.side_effect = Exception("network error")

        with patch.dict("sys.modules", {"httpx": mock_httpx}), \
             patch(f"{MODULE}.socket") as mock_socket:
            mock_socket.gethostname.return_value = "myhost"
            mock_socket.gethostbyname.return_value = "192.168.1.10"
            result = get_server_ip()
        assert result == "192.168.1.10"

    def test_fallback_to_placeholder(self):
        mock_httpx = MagicMock()
        mock_httpx.get.side_effect = Exception("network error")

        with patch.dict("sys.modules", {"httpx": mock_httpx}), \
             patch(f"{MODULE}.socket") as mock_socket:
            mock_socket.gethostname.return_value = "myhost"
            mock_socket.gethostbyname.side_effect = Exception("fail")
            result = get_server_ip()
        assert result == "YOUR_SERVER_IP"


# ── get_required_dns_records ─────────────────────────────────


class TestGetRequiredDnsRecords:
    DOMAIN = "example.com"
    SELECTOR = "default"
    PEM = "-----BEGIN PUBLIC KEY-----\nABC\n-----END PUBLIC KEY-----"
    SERVER_IP = "1.2.3.4"

    @patch(f"{MODULE}.check_ptr_record", return_value=(True, "mail.example.com"))
    @patch(f"{MODULE}.check_dmarc_record", return_value=(True, "v=DMARC1; p=quarantine"))
    @patch(f"{MODULE}.check_dkim_record", return_value=(True, "v=DKIM1; k=rsa; p=KEY"))
    @patch(f"{MODULE}.check_spf_record", return_value=(True, "v=spf1 ip4:1.2.3.4 -all"))
    @patch(f"{MODULE}.check_mx_records", return_value=(True, ["10 example.com."]))
    @patch("web.backend.core.mail.dkim_manager.get_dkim_dns_record", return_value="v=DKIM1; k=rsa; p=PUBKEY")
    def test_all_configured(self, mock_dkim_dns, mock_mx, mock_spf, mock_dkim, mock_dmarc, mock_ptr):
        records = get_required_dns_records(self.DOMAIN, self.SELECTOR, self.PEM, self.SERVER_IP)
        assert len(records) == 5
        purposes = [r.purpose for r in records]
        assert purposes == ["MX", "SPF", "DKIM", "DMARC", "PTR"]
        assert all(r.is_configured for r in records)

    @patch(f"{MODULE}.check_ptr_record", return_value=(False, None))
    @patch(f"{MODULE}.check_dmarc_record", return_value=(False, None))
    @patch(f"{MODULE}.check_dkim_record", return_value=(False, None))
    @patch(f"{MODULE}.check_spf_record", return_value=(False, None))
    @patch(f"{MODULE}.check_mx_records", return_value=(False, []))
    @patch("web.backend.core.mail.dkim_manager.get_dkim_dns_record", return_value="v=DKIM1; k=rsa; p=PUBKEY")
    def test_none_configured(self, mock_dkim_dns, mock_mx, mock_spf, mock_dkim, mock_dmarc, mock_ptr):
        records = get_required_dns_records(self.DOMAIN, self.SELECTOR, self.PEM, self.SERVER_IP)
        assert len(records) == 5
        assert not any(r.is_configured for r in records)

    @patch(f"{MODULE}.get_server_ip", return_value="10.20.30.40")
    @patch(f"{MODULE}.check_ptr_record", return_value=(False, None))
    @patch(f"{MODULE}.check_dmarc_record", return_value=(False, None))
    @patch(f"{MODULE}.check_dkim_record", return_value=(False, None))
    @patch(f"{MODULE}.check_spf_record", return_value=(False, None))
    @patch(f"{MODULE}.check_mx_records", return_value=(False, []))
    @patch("web.backend.core.mail.dkim_manager.get_dkim_dns_record", return_value="v=DKIM1; k=rsa; p=PUBKEY")
    def test_auto_detect_server_ip(self, mock_dkim_dns, mock_mx, mock_spf, mock_dkim, mock_dmarc, mock_ptr, mock_ip):
        records = get_required_dns_records(self.DOMAIN, self.SELECTOR, self.PEM)
        mock_ip.assert_called_once()

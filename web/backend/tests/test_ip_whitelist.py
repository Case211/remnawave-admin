"""Tests for web.backend.core.ip_whitelist — IP/CIDR matching."""
import pytest

from web.backend.core.ip_whitelist import parse_ip_list, is_ip_allowed


class TestParseIPList:
    """Parsing comma-separated IP/CIDR strings."""

    def test_empty_string(self):
        assert parse_ip_list("") == []

    def test_whitespace_only(self):
        assert parse_ip_list("   ") == []

    def test_single_ip(self):
        assert parse_ip_list("1.2.3.4") == ["1.2.3.4"]

    def test_multiple_ips(self):
        result = parse_ip_list("1.2.3.4, 5.6.7.8, 9.10.11.12")
        assert result == ["1.2.3.4", "5.6.7.8", "9.10.11.12"]

    def test_cidr(self):
        result = parse_ip_list("10.0.0.0/8, 192.168.1.0/24")
        assert result == ["10.0.0.0/8", "192.168.1.0/24"]

    def test_trims_whitespace(self):
        result = parse_ip_list("  1.2.3.4  ,  5.6.7.8  ")
        assert result == ["1.2.3.4", "5.6.7.8"]

    def test_skips_empty_entries(self):
        result = parse_ip_list("1.2.3.4,,5.6.7.8,")
        assert result == ["1.2.3.4", "5.6.7.8"]

    def test_none_input(self):
        assert parse_ip_list(None) == []


class TestIsIPAllowed:
    """IP whitelist matching."""

    def test_empty_list_allows_all(self):
        assert is_ip_allowed("1.2.3.4", [])

    def test_exact_match(self):
        assert is_ip_allowed("1.2.3.4", ["1.2.3.4"])

    def test_not_in_list(self):
        assert not is_ip_allowed("5.6.7.8", ["1.2.3.4"])

    def test_cidr_match(self):
        assert is_ip_allowed("192.168.1.50", ["192.168.1.0/24"])

    def test_cidr_no_match(self):
        assert not is_ip_allowed("192.168.2.50", ["192.168.1.0/24"])

    def test_wide_cidr(self):
        assert is_ip_allowed("10.255.255.255", ["10.0.0.0/8"])

    def test_multiple_entries(self):
        allowed = ["1.2.3.4", "10.0.0.0/8", "192.168.0.0/16"]
        assert is_ip_allowed("1.2.3.4", allowed)
        assert is_ip_allowed("10.50.100.200", allowed)
        assert is_ip_allowed("192.168.1.1", allowed)
        assert not is_ip_allowed("172.16.0.1", allowed)

    def test_invalid_client_ip(self):
        assert not is_ip_allowed("not-an-ip", ["1.2.3.4"])

    def test_invalid_whitelist_entry_skipped(self):
        # Invalid entry should be skipped, valid ones still match
        assert is_ip_allowed("1.2.3.4", ["invalid", "1.2.3.4"])

    def test_localhost(self):
        assert is_ip_allowed("127.0.0.1", ["127.0.0.0/8"])

    def test_ipv6(self):
        assert is_ip_allowed("::1", ["::1"])

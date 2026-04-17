"""Tests for UserAgentAnalyzer — classification and SRH-based aggregation logic."""
from datetime import datetime, timedelta, timezone

import pytest

from shared.violation_detector import (
    UserAgentAnalyzer,
    UserAgentClassification,
)


@pytest.fixture
def analyzer():
    return UserAgentAnalyzer()


# ── classify() ────────────────────────────────────────────────


class TestClassifyWhitelist:
    def test_happ(self, analyzer):
        assert analyzer.classify("Happ/4.7.2/ios/") == UserAgentClassification.VALID

    def test_flclash(self, analyzer):
        assert analyzer.classify("FlClash X/v0.2.1 Platform/android") == UserAgentClassification.VALID

    def test_v2rayn(self, analyzer):
        assert analyzer.classify("v2rayN/9.99") == UserAgentClassification.VALID

    def test_koala_clash(self, analyzer):
        assert analyzer.classify("koala-clash/v0.2.8") == UserAgentClassification.VALID

    def test_throne(self, analyzer):
        assert analyzer.classify("Throne/1.0.13 (Prefer ClashMeta Format)") == UserAgentClassification.VALID

    def test_hiddify(self, analyzer):
        assert analyzer.classify("HiddifyNext/2.0.0") == UserAgentClassification.VALID

    def test_clash_verge(self, analyzer):
        assert analyzer.classify("Clash Verge/1.5.0") == UserAgentClassification.VALID

    def test_singbox(self, analyzer):
        assert analyzer.classify("sing-box/1.8.0") == UserAgentClassification.VALID
        assert analyzer.classify("singbox/1.8.0") == UserAgentClassification.VALID

    def test_case_insensitive(self, analyzer):
        assert analyzer.classify("happ/4.7.2") == UserAgentClassification.VALID
        assert analyzer.classify("HAPP/4.7.2") == UserAgentClassification.VALID


class TestClassifyLinkInUA:
    def test_vless(self, analyzer):
        ua = "vless://25fd819e-4f1e-4f3b-85e7-658769db2b2d@host.com:443"
        assert analyzer.classify(ua) == UserAgentClassification.LINK_IN_UA

    def test_vmess(self, analyzer):
        assert analyzer.classify("vmess://eyJhZGQiOiJ...") == UserAgentClassification.LINK_IN_UA

    def test_trojan(self, analyzer):
        assert analyzer.classify("trojan://password@host.com:443") == UserAgentClassification.LINK_IN_UA

    def test_https_url(self, analyzer):
        assert analyzer.classify("https://example.com/sub/foo") == UserAgentClassification.LINK_IN_UA

    def test_hysteria2(self, analyzer):
        assert analyzer.classify("hysteria2://host.com") == UserAgentClassification.LINK_IN_UA


class TestClassifyBotLibrary:
    def test_go_http_client(self, analyzer):
        assert analyzer.classify("Go-http-client/2.0") == UserAgentClassification.BOT_LIBRARY

    def test_curl(self, analyzer):
        assert analyzer.classify("curl/8.0.1") == UserAgentClassification.BOT_LIBRARY

    def test_wget(self, analyzer):
        assert analyzer.classify("Wget/1.21.4") == UserAgentClassification.BOT_LIBRARY

    def test_python_requests(self, analyzer):
        assert analyzer.classify("python-requests/2.31.0") == UserAgentClassification.BOT_LIBRARY

    def test_postman(self, analyzer):
        assert analyzer.classify("PostmanRuntime/7.32.3") == UserAgentClassification.BOT_LIBRARY


class TestClassifyStub:
    def test_mozilla_bare(self, analyzer):
        assert analyzer.classify("Mozilla/5.0") == UserAgentClassification.STUB
        assert analyzer.classify("Mozilla/5.0 ") == UserAgentClassification.STUB

    def test_mozilla_full_not_stub(self, analyzer):
        assert analyzer.classify("Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101") != UserAgentClassification.STUB


class TestClassifyEmpty:
    def test_empty_string(self, analyzer):
        assert analyzer.classify("") == UserAgentClassification.EMPTY

    def test_none(self, analyzer):
        assert analyzer.classify(None) == UserAgentClassification.EMPTY

    def test_whitespace(self, analyzer):
        assert analyzer.classify("   ") == UserAgentClassification.EMPTY


class TestClassifyUnknown:
    def test_unknown_client(self, analyzer):
        assert analyzer.classify("SomeRandomVPN/1.0") == UserAgentClassification.UNKNOWN

    def test_okhttp_is_unknown_not_blacklist(self, analyzer):
        # okhttp намеренно в grey zone, не в blacklist
        assert analyzer.classify("okhttp/4.12.0") == UserAgentClassification.UNKNOWN


# ── extra patterns ────────────────────────────────────────────


class TestExtraPatterns:
    def test_extra_whitelist(self, analyzer):
        analyzer.set_extra_patterns(["^MyCustomClient/"], [])
        assert analyzer.classify("MyCustomClient/2.0") == UserAgentClassification.VALID

    def test_extra_blacklist(self, analyzer):
        analyzer.set_extra_patterns([], ["^SuspiciousBot/"])
        assert analyzer.classify("SuspiciousBot/1.0") == UserAgentClassification.BOT_LIBRARY

    def test_invalid_regex_skipped(self, analyzer):
        # Некорректный regex не должен падать, только warning
        analyzer.set_extra_patterns(["[invalid("], [])
        assert analyzer.classify("Happ/1.0") == UserAgentClassification.VALID


# ── analyze() aggregation over SRH records ─────────────────────


def _srh(ua, request_id=1, ip="1.2.3.4", hours_ago=1):
    return {
        "request_id": request_id,
        "user_agent": ua,
        "request_ip": ip,
        "request_at": datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    }


class TestAnalyze:
    def test_empty_list(self, analyzer):
        result = analyzer.analyze([])
        assert result.score == 0.0
        assert result.total_analyzed == 0

    def test_all_valid(self, analyzer):
        records = [
            _srh("Happ/4.7.2", 1),
            _srh("FlClash X/v0.2.1", 2),
        ]
        result = analyzer.analyze(records)
        assert result.score == 0.0
        assert result.valid_count == 2
        assert len(result.suspicious_agents) == 0

    def test_link_in_ua_detected(self, analyzer):
        records = [_srh("vless://foo@host.com:443", 1)]
        result = analyzer.analyze(records)
        assert result.score == 90.0
        assert result.has_link_in_ua is True
        assert len(result.suspicious_agents) == 1
        assert result.suspicious_agents[0].request_id == 1
        assert result.suspicious_agents[0].request_ip == "1.2.3.4"

    def test_bot_library_detected(self, analyzer):
        records = [_srh("curl/8.0.1", 1)]
        result = analyzer.analyze(records)
        assert result.score == 70.0
        assert result.has_bot_library is True

    def test_mixed_valid_and_link(self, analyzer):
        records = [
            _srh("Happ/4.7.2", 1, ip="1.1.1.1"),
            _srh("vless://foo@host.com", 2, ip="2.2.2.2"),
        ]
        result = analyzer.analyze(records)
        assert result.score == 90.0
        assert result.has_link_in_ua is True
        assert result.valid_count == 1
        # Должна быть причина про mixed pattern
        assert any("смешанные клиенты" in r.lower() for r in result.reasons)

    def test_link_priority_over_bot(self, analyzer):
        records = [
            _srh("curl/8.0.1", 1),
            _srh("vless://foo@host.com", 2),
        ]
        result = analyzer.analyze(records)
        assert result.has_link_in_ua is True
        assert result.score == 90.0

    def test_max_age_filters_old(self, analyzer):
        records = [
            _srh("vless://foo@host.com", 1, hours_ago=24 * 10),  # 10 дней назад
            _srh("Happ/4.7.2", 2, hours_ago=1),
        ]
        # max_age_days=7 — старый vless:// игнорируется
        result = analyzer.analyze(records, max_age_days=7)
        assert result.has_link_in_ua is False
        assert result.valid_count == 1

    def test_max_age_zero_analyzes_all(self, analyzer):
        records = [
            _srh("vless://foo@host.com", 1, hours_ago=24 * 60),  # 60 дней назад
        ]
        result = analyzer.analyze(records, max_age_days=0)
        assert result.has_link_in_ua is True

    def test_empty_ua_reported(self, analyzer):
        records = [_srh(None, 1), _srh("", 2)]
        result = analyzer.analyze(records)
        assert result.score == 40.0
        assert result.total_analyzed == 2

    def test_unknown_ua_reported_lightly(self, analyzer):
        records = [_srh("BrandNewClient/1.0", 1)]
        result = analyzer.analyze(records)
        assert result.score == 25.0
        assert any("неизвестный" in r.lower() for r in result.reasons)

    def test_dedup_same_ua_and_ip(self, analyzer):
        # Один и тот же UA+IP в нескольких запросах — в suspicious только одна запись
        records = [
            _srh("vless://foo@host.com", 1, ip="1.1.1.1"),
            _srh("vless://foo@host.com", 2, ip="1.1.1.1"),
            _srh("vless://foo@host.com", 3, ip="1.1.1.1"),
        ]
        result = analyzer.analyze(records)
        assert len(result.suspicious_agents) == 1
        assert result.total_analyzed == 3
        assert result.has_link_in_ua is True

    def test_dedup_keeps_different_ips(self, analyzer):
        # Один UA но с разных IP — обе записи сохраняются (важная инфа для админа)
        records = [
            _srh("vless://foo@host.com", 1, ip="1.1.1.1"),
            _srh("vless://foo@host.com", 2, ip="2.2.2.2"),
        ]
        result = analyzer.analyze(records)
        assert len(result.suspicious_agents) == 2

    def test_user_agent_truncation(self, analyzer):
        long_ua = "vless://" + "x" * 500
        records = [_srh(long_ua, 1)]
        result = analyzer.analyze(records)
        assert len(result.suspicious_agents[0].user_agent) <= 200

    def test_suspicious_agents_truncated_to_20(self, analyzer):
        # 30 разных подозрительных → максимум 20 в результате
        records = [_srh(f"vless://u{i}@host.com", i, ip=f"10.0.0.{i}") for i in range(30)]
        result = analyzer.analyze(records)
        assert len(result.suspicious_agents) == 20

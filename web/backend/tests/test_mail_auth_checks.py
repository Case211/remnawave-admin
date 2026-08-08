"""Проверка подлинности входящих писем.

Логика тут целиком построена на ответах DNS, поэтому все тесты подменяют
резолвер: настоящие запросы сделали бы набор медленным и — что хуже —
зависящим от чужих зон, которые меняются без нашего ведома.
"""
from unittest.mock import AsyncMock, patch

import pytest

from web.backend.core.mail.auth_checks import (
    AuthVerdict,
    DkimResult,
    SpfResult,
    authenticate,
    authentication_results_header,
    check_dmarc,
    check_spf,
    organizational_domain,
)

MODULE = "web.backend.core.mail.auth_checks"


# ── Домен организации ────────────────────────────────────────

class TestOrganizationalDomain:
    def test_plain_domain(self):
        assert organizational_domain("example.com") == "example.com"

    def test_subdomain_reduced_to_parent(self):
        assert organizational_domain("mail.example.com") == "example.com"
        assert organizational_domain("a.b.c.example.com") == "example.com"

    def test_multi_label_suffix(self):
        """example.co.uk — организация, co.uk — зона."""
        assert organizational_domain("example.co.uk") == "example.co.uk"
        assert organizational_domain("mail.example.co.uk") == "example.co.uk"

    def test_case_and_trailing_dot(self):
        assert organizational_domain("MAIL.Example.COM.") == "example.com"


# ── SPF ──────────────────────────────────────────────────────

def _txt(*records):
    """Подменить выдачу TXT-записей."""
    return patch(f"{MODULE}._resolve_txt", new=AsyncMock(return_value=list(records)))


class TestSpf:
    async def test_no_record_is_none(self):
        with _txt():
            result = await check_spf("1.2.3.4", "user@example.com", "mail.example.com")
        assert result.result == "none"

    async def test_ip4_match_passes(self):
        with _txt("v=spf1 ip4:1.2.3.0/24 -all"):
            result = await check_spf("1.2.3.4", "user@example.com", "helo.example.com")
        assert result.result == "pass"

    async def test_ip4_miss_falls_through_to_all(self):
        with _txt("v=spf1 ip4:9.9.9.0/24 -all"):
            result = await check_spf("1.2.3.4", "user@example.com", "helo.example.com")
        assert result.result == "fail"

    async def test_softfail_qualifier(self):
        with _txt("v=spf1 ip4:9.9.9.9 ~all"):
            result = await check_spf("1.2.3.4", "user@example.com", "helo.example.com")
        assert result.result == "softfail"

    async def test_two_records_is_permerror(self):
        """Какую из двух политик выполнять — стандарт не решает, и домен
        считается сломанным, а не «более строгим»."""
        with _txt("v=spf1 ip4:1.2.3.4 -all", "v=spf1 -all"):
            result = await check_spf("1.2.3.4", "user@example.com", "helo.example.com")
        assert result.result == "permerror"

    async def test_include_delegates(self):
        async def fake_txt(name):
            if name == "example.com":
                return ["v=spf1 include:_spf.provider.net -all"]
            if name == "_spf.provider.net":
                return ["v=spf1 ip4:5.6.7.8 -all"]
            return []

        with patch(f"{MODULE}._resolve_txt", new=AsyncMock(side_effect=fake_txt)):
            result = await check_spf("5.6.7.8", "user@example.com", "helo")
        assert result.result == "pass"

    async def test_include_failure_does_not_fail_whole_check(self):
        """Отказ внутри include — это «у них не сошлось», а не наш вердикт:
        проверка обязана продолжиться следующими механизмами."""
        async def fake_txt(name):
            if name == "example.com":
                return ["v=spf1 include:_spf.provider.net ip4:1.2.3.4 -all"]
            if name == "_spf.provider.net":
                return ["v=spf1 ip4:9.9.9.9 -all"]
            return []

        with patch(f"{MODULE}._resolve_txt", new=AsyncMock(side_effect=fake_txt)):
            result = await check_spf("1.2.3.4", "user@example.com", "helo")
        assert result.result == "pass"

    async def test_lookup_budget_is_shared_across_includes(self):
        """Лимит в десять обращений общий на всю проверку — иначе его
        обходили бы вложенностью."""
        async def fake_txt(name):
            # Каждый include ведёт к следующему: бесконечная лесенка.
            return [f"v=spf1 include:step-{name}.example.net -all"]

        with patch(f"{MODULE}._resolve_txt", new=AsyncMock(side_effect=fake_txt)):
            result = await check_spf("1.2.3.4", "user@example.com", "helo")
        assert result.result == "permerror"

    async def test_empty_mail_from_uses_helo(self):
        """Отчёты о недоставке приходят с пустым обратным адресом — проверять
        нужно домен из HELO, иначе они не прошли бы никогда."""
        seen = {}

        async def fake_txt(name):
            seen["domain"] = name
            return ["v=spf1 ip4:1.2.3.4 -all"]

        with patch(f"{MODULE}._resolve_txt", new=AsyncMock(side_effect=fake_txt)):
            result = await check_spf("1.2.3.4", "", "relay.example.org")
        assert seen["domain"] == "relay.example.org"
        assert result.result == "pass"


# ── DMARC ────────────────────────────────────────────────────

class TestDmarc:
    async def test_no_policy_is_none(self):
        with _txt():
            result = await check_dmarc("example.com", SpfResult("pass", "example.com"),
                                       DkimResult("none"), "example.com")
        assert result.result == "none"

    async def test_passes_by_aligned_dkim(self):
        with _txt("v=DMARC1; p=reject"):
            result = await check_dmarc(
                "example.com", SpfResult("fail", "other.net"),
                DkimResult("pass", ["mail.example.com"]), "other.net",
            )
        assert result.result == "pass"
        assert result.aligned_by == "dkim"

    async def test_passes_by_aligned_spf(self):
        with _txt("v=DMARC1; p=quarantine"):
            result = await check_dmarc("example.com", SpfResult("pass", "example.com"),
                                       DkimResult("none"), "mail.example.com")
        assert result.result == "pass"
        assert result.aligned_by == "spf"

    async def test_spf_pass_for_foreign_domain_is_not_enough(self):
        """Суть DMARC: у рассыльщика может быть безупречный SPF на свой
        домен, но в поле «От» он показывает чужой адрес."""
        with _txt("v=DMARC1; p=reject"):
            result = await check_dmarc("example.com", SpfResult("pass", "spammer.net"),
                                       DkimResult("none"), "spammer.net")
        assert result.result == "fail"
        assert result.policy == "reject"

    async def test_strict_alignment_rejects_subdomain(self):
        with _txt("v=DMARC1; p=none; aspf=s"):
            result = await check_dmarc("example.com", SpfResult("pass", "mail.example.com"),
                                       DkimResult("none"), "mail.example.com")
        assert result.result == "fail"

    async def test_policy_taken_from_organizational_domain(self):
        """Политика родительского домена распространяется на поддомены."""
        async def fake_txt(name):
            return ["v=DMARC1; p=reject"] if name == "_dmarc.example.com" else []

        with patch(f"{MODULE}._resolve_txt", new=AsyncMock(side_effect=fake_txt)):
            result = await check_dmarc("news.example.com", SpfResult("fail"),
                                       DkimResult("fail"), "news.example.com")
        assert result.result == "fail"
        assert result.policy == "reject"


# ── Итоговая оценка ──────────────────────────────────────────

class TestAuthenticate:
    RAW = b"From: Somebody <a@example.com>\r\nSubject: hi\r\n\r\nbody\r\n"

    async def _run(self, spf: SpfResult, dkim: DkimResult, dmarc_record=None, **kwargs):
        with patch(f"{MODULE}.check_spf", new=AsyncMock(return_value=spf)), \
             patch(f"{MODULE}.check_dkim", new=AsyncMock(return_value=dkim)), \
             patch(f"{MODULE}._resolve_txt", new=AsyncMock(
                 return_value=[dmarc_record] if dmarc_record else [])):
            return await authenticate(
                raw=self.RAW, remote_ip="1.2.3.4", mail_from="a@example.com",
                helo="mail.example.com", from_header="Somebody <a@example.com>", **kwargs,
            )

    async def test_clean_mail_scores_zero(self):
        verdict = await self._run(SpfResult("pass", "example.com"),
                                  DkimResult("pass", ["example.com"]),
                                  "v=DMARC1; p=none")
        assert verdict.spam_score == 0
        assert verdict.is_spam is False

    async def test_dmarc_failure_under_reject_marks_spam(self):
        verdict = await self._run(SpfResult("fail", "example.com"),
                                  DkimResult("fail"),
                                  "v=DMARC1; p=reject")
        # 5 за проваленный DMARC с жёсткой политикой + 3 за SPF + 2 за DKIM
        assert verdict.spam_score == 10.0
        assert verdict.is_spam is True

    async def test_no_signatures_at_all_is_suspicious_but_not_spam(self):
        """Предъявить нечего — балл есть, но до порога не дотягивает:
        так выглядят и старые сервера, а не только спамеры."""
        verdict = await self._run(SpfResult("none"), DkimResult("none"))
        assert verdict.spam_score == 2.0
        assert verdict.is_spam is False

    async def test_threshold_is_configurable(self):
        verdict = await self._run(SpfResult("none"), DkimResult("none"), threshold=2.0)
        assert verdict.is_spam is True

    async def test_broken_check_does_not_block_delivery(self):
        """Сбой проверки не должен ронять приём: письмо важнее метки."""
        with patch(f"{MODULE}.check_spf", new=AsyncMock(side_effect=RuntimeError("dns down"))), \
             patch(f"{MODULE}.check_dkim", new=AsyncMock(return_value=DkimResult("none"))):
            verdict = await authenticate(
                raw=self.RAW, remote_ip="1.2.3.4", mail_from="a@example.com",
                helo="h", from_header="a@example.com",
            )
        assert isinstance(verdict, AuthVerdict)
        assert verdict.is_spam is False
        assert "error" in verdict.details


class TestAuthenticationResultsHeader:
    def test_contains_all_three_verdicts(self):
        verdict = AuthVerdict(
            spf="pass", dkim="fail", dmarc="fail",
            details={"spf": {"domain": "example.com"}, "dkim": {"domains": []},
                     "from_domain": "example.com"},
        )
        header = authentication_results_header("mail.example.com", verdict)
        assert header.startswith("mail.example.com;")
        assert "spf=pass smtp.mailfrom=example.com" in header
        assert "dkim=fail" in header
        assert "dmarc=fail header.from=example.com" in header

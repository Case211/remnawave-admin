"""Почтовик: кому верим при отписке, что блокирует подавление, зависшие письма.

Три места, где раньше верили строке, которую назвал сам отправитель, или
молча теряли письмо: отписка по envelope MAIL FROM, ограничение домена
учётки submission по envelope при подписи заголовка From, и статус
``sending``, из которого письмо не возвращалось после рестарта.
"""
import pytest

from shared.mail_queue import TRANSACTIONAL_CATEGORIES, suppression_applies
from web.backend.core.mail.outbound_queue import OutboundMailQueue
from web.backend.core.mail.processor import unsubscribe_sender
from web.backend.core.mail.submission_server import (
    SUBMISSION_BULK_CATEGORY,
    SUBMISSION_CATEGORY,
    sender_domain_allowed,
    submission_category,
)


class TestUnsubscribeSender:
    def test_authenticated_sender_is_accepted(self):
        assert unsubscribe_sender(
            "user@example.org", "User <user@example.org>",
            spf="pass", dkim="none", dmarc="none", is_spam=False,
        ) == "user@example.org"

    def test_address_is_normalised(self):
        assert unsubscribe_sender(
            " User@Example.org ", "", spf="none", dkim="pass", dmarc="pass", is_spam=False,
        ) == "user@example.org"

    def test_aligned_dkim_via_dmarc_is_accepted(self):
        # SPF не прошёл (пересылка), но DMARC pass — значит, есть выровненная подпись.
        assert unsubscribe_sender(
            "user@example.org", "user@example.org",
            spf="softfail", dkim="pass", dmarc="pass", is_spam=False,
        ) == "user@example.org"

    def test_dkim_of_a_foreign_domain_does_not_authenticate_the_sender(self):
        # Envelope и From — адрес жертвы, подпись — d=attacker.example. DKIM pass
        # ставится за любую валидную подпись; у домена жертвы SPF ~all и DMARC
        # p=none, так что письмо не набирает порог подозрительного.
        assert unsubscribe_sender(
            "victim@example.org", "victim@example.org",
            spf="softfail", dkim="pass", dmarc="fail", is_spam=False,
        ) is None

    def test_dkim_pass_alone_is_not_enough(self):
        assert unsubscribe_sender(
            "victim@example.org", "victim@example.org",
            spf="none", dkim="pass", dmarc="none", is_spam=False,
        ) is None

    def test_forged_envelope_without_authentication_is_ignored(self):
        # Любой сервер может назвать чужой MAIL FROM — без SPF/DKIM/DMARC pass не верим.
        assert unsubscribe_sender(
            "victim@example.org", "victim@example.org",
            spf="none", dkim="none", dmarc="none", is_spam=False,
        ) is None

    def test_failed_checks_are_ignored(self):
        assert unsubscribe_sender(
            "victim@example.org", "victim@example.org",
            spf="fail", dkim="fail", dmarc="fail", is_spam=False,
        ) is None

    def test_spam_verdict_wins_over_a_single_pass(self):
        assert unsubscribe_sender(
            "victim@example.org", "victim@example.org",
            spf="pass", dkim="none", dmarc="fail", is_spam=True,
        ) is None

    def test_from_header_from_another_domain_is_ignored(self):
        # SPF pass за домен отправляющего сервера не разрешает отписывать чужой домен.
        assert unsubscribe_sender(
            "bounce@attacker.example", "victim@example.org",
            spf="pass", dkim="none", dmarc="none", is_spam=False,
        ) is None

    def test_missing_or_malformed_envelope(self):
        assert unsubscribe_sender("", "user@example.org", "pass", "pass", "pass", False) is None
        assert unsubscribe_sender("no-at-sign", "", "pass", "pass", "pass", False) is None


class TestSuppressionScope:
    def test_no_record_never_blocks(self):
        assert suppression_applies(None, "users") is False

    def test_bounce_blocks_everything(self):
        for category in ("users", "smtp_submission", "notification", None):
            assert suppression_applies("bounce", category) is True

    def test_unsubscribe_blocks_bulk_but_not_transactional(self):
        assert suppression_applies("unsubscribe", "users") is True
        assert suppression_applies("unsubscribe", "violations") is True
        assert suppression_applies("unsubscribe", None) is True
        for category in TRANSACTIONAL_CATEGORIES:
            assert suppression_applies("unsubscribe", category) is False

    def test_personal_mail_is_not_a_mailing(self):
        # Предупреждение перед мерой и письмо администратора конкретному
        # человеку — личные: отписка от рассылок не должна их глушить.
        assert suppression_applies("unsubscribe", "violation_notice") is False
        assert suppression_applies("unsubscribe", "manual") is False


def _submitted(headers: str):
    import email
    return email.message_from_string(f"From: a@mail.example\nSubject: s\n{headers}\nbody\n")


class TestSubmissionCategory:
    def test_plain_message_is_personal(self):
        assert submission_category(_submitted("")) == SUBMISSION_CATEGORY

    def test_precedence_marks_a_mailing(self):
        for value in ("bulk", "list", "Bulk ", "junk"):
            assert submission_category(_submitted(f"Precedence: {value}\n")) == SUBMISSION_BULK_CATEGORY

    def test_other_precedence_is_personal(self):
        assert submission_category(_submitted("Precedence: first-class\n")) == SUBMISSION_CATEGORY

    def test_list_headers_mark_a_mailing(self):
        assert submission_category(
            _submitted("List-Id: <promo.mail.example>\n")) == SUBMISSION_BULK_CATEGORY
        assert submission_category(
            _submitted("List-Unsubscribe: <mailto:u@mail.example>\n")) == SUBMISSION_BULK_CATEGORY

    def test_unsubscribe_blocks_submitted_mailing_but_not_personal_mail(self):
        assert suppression_applies("unsubscribe", SUBMISSION_BULK_CATEGORY) is True
        assert suppression_applies("unsubscribe", SUBMISSION_CATEGORY) is False
        assert SUBMISSION_CATEGORY in TRANSACTIONAL_CATEGORIES
        assert SUBMISSION_BULK_CATEGORY not in TRANSACTIONAL_CATEGORIES


class TestSenderDomainAllowed:
    def test_empty_restriction_allows_anything(self):
        assert sender_domain_allowed("x@anywhere.example", []) is True
        assert sender_domain_allowed("x@anywhere.example", None) is True

    def test_case_and_whitespace_insensitive(self):
        assert sender_domain_allowed("User@Mail.Example", [" mail.example "]) is True

    def test_foreign_domain_rejected(self):
        assert sender_domain_allowed("user@other.example", ["mail.example"]) is False

    def test_address_without_domain_rejected(self):
        assert sender_domain_allowed("nobody", ["mail.example"]) is False
        assert sender_domain_allowed("", ["mail.example"]) is False


class TestBuildMessageHeaders:
    def test_no_one_click_without_https_uri(self):
        msg = OutboundMailQueue()._build_message({
            "subject": "s", "from_email": "noreply@mail.example", "to_email": "u@example.org",
            "domain": "mail.example", "body_text": "hi",
        })
        assert msg["List-Unsubscribe"] == "<mailto:unsubscribe@mail.example>"
        assert "List-Unsubscribe-Post" not in msg


class _Conn:
    def __init__(self, result: str):
        self.result = result
        self.calls = []

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return self.result


class TestStaleSendingRecovery:
    @pytest.mark.asyncio
    async def test_stale_rows_are_returned_to_the_queue(self):
        conn = _Conn("UPDATE 2")
        recovered = await OutboundMailQueue()._recover_stale_sending(conn)
        assert recovered == 2
        sql, args = conn.calls[0]
        assert "status = 'sending'" in sql
        assert "status = 'failed'" in sql
        assert "next_attempt_at = NOW()" in sql
        assert args == (OutboundMailQueue.STALE_SENDING_MINUTES,)

    @pytest.mark.asyncio
    async def test_nothing_to_recover(self):
        conn = _Conn("UPDATE 0")
        assert await OutboundMailQueue()._recover_stale_sending(conn) == 0

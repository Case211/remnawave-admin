"""Разбор служебной почты: отказы доставки и DMARC-отчёты.

Здесь важна работа с реальными форматами, а не с выдуманными: и отчёт о
недоставке, и агрегированный отчёт DMARC описаны стандартами, но приходят
от чужих серверов, и ошибка разбора обнаруживается не сразу — просто
перестаёт наполняться список мёртвых адресов.
"""
import email
import gzip
import io
import zipfile

from web.backend.core.mail.processor import (
    _unpack_report,
    parse_bounce,
    parse_dmarc_report,
)


def _message(raw: str):
    return email.message_from_string(raw)


HARD_BOUNCE = """From: MAILER-DAEMON@mx.example.net
To: noreply@example.com
Subject: Undelivered Mail Returned to Sender
Content-Type: multipart/report; report-type=delivery-status; boundary="BOUND"

--BOUND
Content-Type: text/plain

This is the mail system at host mx.example.net.

--BOUND
Content-Type: message/delivery-status

Reporting-MTA: dns; mx.example.net

Final-Recipient: rfc822; gone@example.org
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown

--BOUND
Content-Type: message/rfc822

From: noreply@example.com
To: gone@example.org
Message-ID: <original-123@example.com>
Subject: Notification

Body of the original message.

--BOUND--
"""

SOFT_BOUNCE = HARD_BOUNCE.replace("Status: 5.1.1", "Status: 4.2.2").replace(
    "550 5.1.1 User unknown", "452 4.2.2 Mailbox full")

ORDINARY_MAIL = """From: Human <human@example.org>
To: noreply@example.com
Subject: Re: hello
Content-Type: text/plain

Just a normal reply.
"""


class TestParseBounce:
    def test_hard_bounce(self):
        result = parse_bounce(_message(HARD_BOUNCE))
        assert result is not None
        assert result["recipient"] == "gone@example.org"
        assert result["bounce_type"] == "hard"
        assert result["smtp_code"] == "5.1.1"
        assert "User unknown" in result["diagnostic"]

    def test_finds_original_message_id(self):
        """Без Message-ID исходного письма отказ не привязать к строке в
        очереди отправки, и в истории оно навсегда останется «отправленным»."""
        result = parse_bounce(_message(HARD_BOUNCE))
        assert result["original_message_id"] == "<original-123@example.com>"

    def test_soft_bounce_detected_separately(self):
        """Переполненный ящик — не повод закрывать адрес навсегда."""
        result = parse_bounce(_message(SOFT_BOUNCE))
        assert result["bounce_type"] == "soft"
        assert result["smtp_code"] == "4.2.2"

    def test_ordinary_mail_is_not_a_bounce(self):
        assert parse_bounce(_message(ORDINARY_MAIL)) is None

    def test_report_without_recipient_is_ignored(self):
        """Отчёт без адреса бесполезен: закрывать нечего."""
        broken = HARD_BOUNCE.replace("Final-Recipient: rfc822; gone@example.org", "")
        assert parse_bounce(_message(broken)) is None


DMARC_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<feedback>
  <report_metadata>
    <org_name>google.com</org_name>
    <email>noreply-dmarc-support@google.com</email>
    <report_id>1234567890</report_id>
    <date_range><begin>1754438400</begin><end>1754524800</end></date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain>
    <adkim>r</adkim>
    <aspf>r</aspf>
    <p>quarantine</p>
    <pct>100</pct>
  </policy_published>
  <record>
    <row>
      <source_ip>1.2.3.4</source_ip>
      <count>5</count>
      <policy_evaluated>
        <disposition>none</disposition>
        <dkim>pass</dkim>
        <spf>pass</spf>
      </policy_evaluated>
    </row>
    <identifiers><header_from>example.com</header_from></identifiers>
  </record>
  <record>
    <row>
      <source_ip>9.9.9.9</source_ip>
      <count>2</count>
      <policy_evaluated>
        <disposition>quarantine</disposition>
        <dkim>fail</dkim>
        <spf>fail</spf>
      </policy_evaluated>
    </row>
    <identifiers><header_from>example.com</header_from></identifiers>
  </record>
</feedback>
"""


class TestParseDmarcReport:
    def test_metadata(self):
        report = parse_dmarc_report(DMARC_XML)
        assert report["report_id"] == "1234567890"
        assert report["org_name"] == "google.com"
        assert report["domain"] == "example.com"
        assert report["policy"]["p"] == "quarantine"

    def test_counts_split_by_outcome(self):
        """Письмо засчитано, если сошёлся хотя бы один механизм — так же,
        как его считает принимающая сторона."""
        report = parse_dmarc_report(DMARC_XML)
        assert report["total_messages"] == 7
        assert report["passed_messages"] == 5
        assert report["failed_messages"] == 2

    def test_records_keep_source_ip(self):
        report = parse_dmarc_report(DMARC_XML)
        sources = {r["source_ip"]: r for r in report["records"]}
        assert sources["9.9.9.9"]["disposition"] == "quarantine"
        assert sources["1.2.3.4"]["count"] == 5

    def test_malformed_xml_returns_none(self):
        assert parse_dmarc_report(b"<feedback><broken>") is None

    def test_period_parsed_from_unix_time(self):
        report = parse_dmarc_report(DMARC_XML)
        assert report["date_begin"].year == 2025 or report["date_begin"].year == 2026
        assert report["date_end"] > report["date_begin"]


class TestUnpackReport:
    def test_gzip(self):
        blob = gzip.compress(DMARC_XML)
        assert _unpack_report("report.xml.gz", "application/gzip", blob) == DMARC_XML

    def test_zip(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("report.xml", DMARC_XML)
        assert _unpack_report("report.zip", "application/zip", buffer.getvalue()) == DMARC_XML

    def test_plain_xml(self):
        assert _unpack_report("report.xml", "text/xml", DMARC_XML) == DMARC_XML

    def test_unrelated_attachment_ignored(self):
        assert _unpack_report("photo.jpg", "image/jpeg", b"\xff\xd8\xff") is None

    def test_broken_archive_does_not_raise(self):
        """Битый архив — обычное дело при обрыве доставки; разбор должен
        просто пройти мимо, а не уронить весь проход."""
        assert _unpack_report("report.xml.gz", "application/gzip", b"not really gzip") is None

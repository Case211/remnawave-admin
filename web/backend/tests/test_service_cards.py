"""Сервисные карточки: входящее письмо и тревоги бэкапа."""
from types import SimpleNamespace

from web.backend.core.backup_service import _failure_card
from web.backend.core.mail.inbound_server import new_mail_card


def test_mail_quotes_the_beginning_of_the_letter_with_sender():
    card = new_mail_card("Вася <vasya@example.com>", "Не работает VPN", "support@stihost.ru",
                         body_text="Здравствуйте!\n\n  Не подключается   с утра.", attachment_count=2,
                         verdict=SimpleNamespace(spf="pass", dkim="pass", dmarc="fail"))
    quote = next(blk for blk in card.to_blocks() if blk["type"] == "blockquote")
    assert quote["blocks"][0]["text"] == "Здравствуйте! Не подключается с утра."
    assert quote["credit"] == "Вася <vasya@example.com>"
    html = card.to_html()
    assert "<b>Не работает VPN</b>" in html
    assert "Проверки: SPF ✓ · DKIM ✓ · DMARC ✗" in html
    assert "Вложения: 2" in html
    assert "&lt;vasya@example.com&gt;" in html


def test_mail_without_subject_or_text_still_reads():
    card = new_mail_card("x@example.com", "", "a@b.c")
    assert "(без темы)" in card.to_html()
    assert not any(blk["type"] == "blockquote" for blk in card.to_blocks())


def test_backup_failure_shows_the_error_as_code():
    card = _failure_card("notify.backup.db_failed", RuntimeError("pg_dump: connection refused"))
    assert card.title_text() == "Бэкап БД не выполнен"
    pre = next(blk for blk in card.to_blocks() if blk["type"] == "pre")
    assert pre["text"] == "pg_dump: connection refused"

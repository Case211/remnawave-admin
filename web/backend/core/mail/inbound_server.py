"""Inbound SMTP server — receives emails for configured domains."""
import asyncio
import email
import logging
from collections import defaultdict
from datetime import datetime, timezone
from email.header import decode_header as _decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

from shared.db_schema import DOMAIN_CONFIG_TABLE, EMAIL_ATTACHMENTS_TABLE, EMAIL_INBOX_TABLE
from shared.db_query import select_sql, insert_sql

from aiosmtpd.smtp import SMTP as SMTPProtocol, Envelope, Session

logger = logging.getLogger(__name__)


def _decode_mime_header(raw: str) -> str:
    """Decode a MIME-encoded header value (e.g. =?UTF-8?B?...?=) into a plain string."""
    if not raw:
        return raw
    parts = []
    for fragment, charset in _decode_header(raw):
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(fragment)
    return "".join(parts)


def _config(key: str, default):
    """Настройка из config_service с запасным значением."""
    try:
        from shared.config_service import config_service
        return config_service.get(key, default)
    except Exception:
        return default


def _is_service_mail(msg, mail_from: str, rcpt_tos: list) -> bool:
    """Отчёт о недоставке, отписка или DMARC-сводка.

    Такие письма приходят машинам, а не людям: дёргать администратора
    уведомлением из-за каждого DMARC-отчёта — верный способ приучить его
    не читать уведомления вовсе.
    """
    if not mail_from:
        return True  # пустой обратный адрес — признак отчёта о недоставке
    if any((r or "").lower().startswith("unsubscribe@") for r in rcpt_tos):
        return True
    return (msg.get_content_type() or "").lower() == "multipart/report"


async def _notify_new_mail(from_header: str, subject: str, rcpt: str) -> None:
    """Сообщить администратору о новом письме."""
    try:
        from web.backend.core.notification_service import create_notification
        await create_notification(
            title=f"Новое письмо: {subject[:80]}",
            body=f"От {from_header[:120]} на {rcpt}",
            type="info",
            severity="info",
            channels=["in_app", "telegram"],
            topic_type="service",
            source="mailserver",
            link="/admin/mail-server",
            # Поток писем от одного отправителя схлопывается в одно
            # уведомление: рассылка на десяток адресов не должна звонить
            # десять раз.
            group_key=f"mail_in:{from_header[:80]}",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to send new mail notification: %s", e)


def _extract_parts(msg) -> tuple:
    """Разобрать письмо на текст, HTML и вложения.

    Раньше вложения только считались и выбрасывались — файл невозможно было
    ни открыть, ни скачать, а служебная почта вроде DMARC-отчётов, где всё
    содержимое и есть вложение, приходила пустой.

    Возвращает (body_text, body_html, attachments).
    """
    body_text = ""
    body_html = ""
    attachments: list = []
    total_bytes = 0

    parts = msg.walk() if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_maintype() == "multipart":
            continue  # контейнер, содержимое придёт следующими частями

        content_type = part.get_content_type()
        disposition = str(part.get("Content-Disposition", "")).lower()
        filename = part.get_filename()
        content_id = (part.get("Content-ID") or "").strip("<>") or None
        is_attachment = "attachment" in disposition or bool(filename) or bool(content_id)

        if not is_attachment and content_type in ("text/plain", "text/html"):
            try:
                payload = part.get_payload(decode=True)
            except Exception:
                continue
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                decoded = payload.decode(charset, errors="replace")
            except (LookupError, UnicodeDecodeError):
                decoded = payload.decode("utf-8", errors="replace")
            if content_type == "text/plain" and not body_text:
                body_text = decoded
            elif content_type == "text/html" and not body_html:
                body_html = decoded
            continue

        if not is_attachment:
            continue

        if len(attachments) >= _MAX_ATTACHMENTS_COUNT:
            logger.warning("Attachment count limit reached, rest skipped")
            break
        try:
            content = part.get_payload(decode=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to decode attachment: %s", e)
            continue
        if not content:
            continue
        # Проверяем уже раскодированный размер: в base64 письмо выглядит на
        # треть толще, и лимит по сырым байтам отсекал бы годные файлы.
        if len(content) > _MAX_ATTACHMENT_BYTES:
            logger.warning("Attachment %s too large (%d bytes), skipped", filename, len(content))
            continue
        if total_bytes + len(content) > _MAX_ATTACHMENTS_TOTAL:
            logger.warning("Total attachment size limit reached, rest skipped")
            break
        total_bytes += len(content)

        attachments.append({
            "filename": (_decode_mime_header(filename) if filename else None)
                        or f"attachment-{len(attachments) + 1}",
            "content_type": content_type,
            "size_bytes": len(content),
            "content": content,
            "content_id": content_id,
            # Картинка из тела письма — не файл, который прислали, а часть
            # вёрстки; в списке вложений её показывать не нужно.
            "is_inline": bool(content_id) and "attachment" not in disposition,
        })

    return (body_text, body_html, attachments)


# Rate limiting: max 100 messages per IP per hour
_IP_COUNTER: dict = defaultdict(lambda: {"count": 0, "reset_at": datetime.min.replace(tzinfo=timezone.utc)})
_MAX_PER_IP_HOUR = 100
_MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB

# Потолок на одно вложение и на письмо целиком. Письмо и так ограничено
# размером сессии, но декодированные вложения занимают примерно на треть
# меньше исходного base64 — считаем их отдельно, уже после раскодирования.
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
_MAX_ATTACHMENTS_TOTAL = 25 * 1024 * 1024
_MAX_ATTACHMENTS_COUNT = 20


class InboundMailHandler:
    """aiosmtpd handler that stores incoming emails in the database."""

    async def handle_EHLO(self, server, session, envelope, hostname, responses):
        session.host_name = hostname
        return responses

    async def handle_RCPT(self, server, session: Session, envelope: Envelope, address: str, rcpt_options):
        """Accept only addresses for configured inbound domains."""
        domain = address.split("@")[-1].lower() if "@" in address else ""
        if not domain:
            return "550 Invalid recipient"

        try:
            from shared.database import db_service
            async with db_service.acquire() as conn:
                is_configured = await conn.fetchval(
                    select_sql(DOMAIN_CONFIG_TABLE, "1",
                        "WHERE domain = $1 AND inbound_enabled = true AND is_active = true"),
                    domain,
                )
            if not is_configured:
                # SMTP-статус обязан быть ASCII — aiosmtpd.push кодирует в ascii,
                # не-ASCII (напр. тире «—») роняет сессию UnicodeEncodeError
                return "550 Relay denied - domain not configured"
        except Exception as e:
            logger.error("RCPT check error: %s", e)
            return "451 Temporary error, try again later"

        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session: Session, envelope: Envelope):
        """Process received email data and store in database."""
        peer = session.peer
        remote_ip = peer[0] if peer else "unknown"

        # Rate limiting
        if not self._check_ip_rate(remote_ip):
            return "452 Too many messages from this IP"

        # Size check
        raw_data = envelope.content
        if isinstance(raw_data, bytes):
            if len(raw_data) > _MAX_MESSAGE_SIZE:
                return "552 Message too large"
            raw_str = raw_data.decode("utf-8", errors="replace")
        else:
            raw_str = str(raw_data)

        try:
            msg = email.message_from_bytes(envelope.content if isinstance(envelope.content, bytes) else envelope.content.encode())

            from_header = _decode_mime_header(msg.get("From", ""))
            to_header = _decode_mime_header(msg.get("To", ""))
            subject = _decode_mime_header(msg.get("Subject", "")) or "(no subject)"
            message_id = msg.get("Message-ID", "")
            in_reply_to = msg.get("In-Reply-To", "")
            # References нужен, чтобы наш ответ встал в ту же ветку у
            # получателя, а не начал переписку заново.
            refs_header = msg.get("References", "")

            # Parse date
            date_header = None
            date_str = msg.get("Date")
            if date_str:
                try:
                    date_header = parsedate_to_datetime(date_str)
                except Exception:
                    pass

            body_text, body_html, attachments = _extract_parts(msg)
            has_attachments = bool(attachments)
            attachment_count = len(attachments)

            # Remote hostname
            remote_hostname = session.host_name or ""

            # Кто на самом деле прислал письмо. Проверки идут до записи в
            # базу, чтобы отметка о подделке появилась вместе с письмом,
            # а не через минуту после того, как его уже прочитали.
            from web.backend.core.mail.auth_checks import authenticate
            threshold = float(_config("mailserver_spam_threshold", 5) or 5)
            verdict = await authenticate(
                raw=envelope.content if isinstance(envelope.content, bytes) else raw_str.encode(),
                remote_ip=remote_ip,
                mail_from=envelope.mail_from or "",
                helo=remote_hostname,
                from_header=from_header,
                threshold=threshold,
            )

            if verdict.is_spam and _config("mailserver_reject_spam", False):
                # Отказ на этапе приёма честнее тихого выбрасывания: настоящий
                # отправитель получит уведомление о недоставке и поймёт, что
                # письмо не дошло, а не будет ждать ответа впустую.
                logger.info("Rejected suspicious mail from=%s ip=%s score=%.1f",
                            envelope.mail_from, remote_ip, verdict.spam_score)
                return "550 Message rejected by policy (failed authentication checks)"

            # Store in DB for each recipient
            import json

            from shared.database import db_service
            async with db_service.acquire() as conn:
                for rcpt in envelope.rcpt_tos:
                    inbox_id = await conn.fetchval(
                        insert_sql(EMAIL_INBOX_TABLE,
                            ["mail_from", "rcpt_to", "from_header", "to_header", "subject", "date_header",
                             "message_id", "in_reply_to", "refs_header", "body_text", "body_html",
                             "raw_message", "remote_ip", "remote_hostname", "has_attachments",
                             "attachment_count", "spf_result", "dkim_result", "dmarc_result",
                             "auth_details", "is_spam", "spam_score"],
                            returning="id"),
                        envelope.mail_from, rcpt, from_header, to_header, subject,
                        date_header, message_id, in_reply_to, refs_header, body_text, body_html,
                        raw_str[:500_000],  # truncate raw to 500KB
                        remote_ip, remote_hostname, has_attachments, attachment_count,
                        verdict.spf, verdict.dkim, verdict.dmarc,
                        json.dumps(verdict.details), verdict.is_spam, verdict.spam_score,
                    )
                    for att in attachments:
                        await conn.execute(
                            insert_sql(EMAIL_ATTACHMENTS_TABLE,
                                ["inbox_id", "filename", "content_type", "size_bytes",
                                 "content", "content_id", "is_inline"]),
                            inbox_id, att["filename"], att["content_type"], att["size_bytes"],
                            att["content"], att["content_id"], att["is_inline"],
                        )

            logger.info("Inbound email stored: from=%s to=%s subj=%s spf=%s dkim=%s dmarc=%s score=%.1f",
                        envelope.mail_from, envelope.rcpt_tos, subject[:60],
                        verdict.spf, verdict.dkim, verdict.dmarc, verdict.spam_score)

            if (_config("mailserver_notify_new_mail", False)
                    and not verdict.is_spam
                    and not _is_service_mail(msg, envelope.mail_from or "", envelope.rcpt_tos)):
                await _notify_new_mail(from_header, subject, envelope.rcpt_tos[0])

            return "250 Message accepted"

        except Exception as e:
            logger.error("Inbound DATA processing error: %s", e)
            return "451 Processing error"

    def _check_ip_rate(self, ip: str) -> bool:
        """Simple in-memory rate limiter per IP."""
        now = datetime.now(timezone.utc)
        entry = _IP_COUNTER[ip]
        if now >= entry["reset_at"]:
            entry["count"] = 0
            from datetime import timedelta
            entry["reset_at"] = now + timedelta(hours=1)
        entry["count"] += 1
        return entry["count"] <= _MAX_PER_IP_HOUR


class InboundMailServer:
    """Manages the aiosmtpd SMTP server lifecycle.

    Runs the SMTP server in the **main** asyncio event loop (not a separate
    thread) so that asyncpg connections from db_service work correctly.
    """

    def __init__(self, hostname: str = "0.0.0.0", port: int = 2525,
                 tls_hostname: str = "localhost"):
        self.hostname = hostname
        self.port = port
        self.tls_hostname = tls_hostname
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self):
        """Start the inbound SMTP server in the current event loop."""
        try:
            from web.backend.core.mail.tls import get_tls_context

            handler = InboundMailHandler()
            # STARTTLS предлагается, но не требуется: часть отправителей до
            # сих пор его не умеет, а отказать им — значит просто не получить
            # письмо. Те, кто умеет (а это все крупные почтовые системы),
            # переходят на шифрование сами.
            tls_context = get_tls_context(self.tls_hostname)
            loop = asyncio.get_running_loop()
            self._server = await loop.create_server(
                lambda: SMTPProtocol(handler, hostname=self.tls_hostname or "remnawave-mail",
                                     data_size_limit=_MAX_MESSAGE_SIZE,
                                     tls_context=tls_context,
                                     require_starttls=False),
                host=self.hostname,
                port=self.port,
            )
            logger.info("Inbound SMTP server started on %s:%d (STARTTLS: %s)",
                        self.hostname, self.port, "on" if tls_context else "off")
        except Exception as e:
            logger.error("Failed to start inbound SMTP server: %s", e)

    async def stop(self):
        """Stop the inbound SMTP server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("Inbound SMTP server stopped")

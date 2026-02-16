"""Inbound SMTP server — receives emails for configured domains."""
import asyncio
import email
import logging
from collections import defaultdict
from datetime import datetime, timezone
from email.header import decode_header as _decode_header
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

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


# Rate limiting: max 100 messages per IP per hour
_IP_COUNTER: dict = defaultdict(lambda: {"count": 0, "reset_at": datetime.min.replace(tzinfo=timezone.utc)})
_MAX_PER_IP_HOUR = 100
_MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 MB


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
                    "SELECT 1 FROM domain_config WHERE domain = $1 AND inbound_enabled = true AND is_active = true",
                    domain,
                )
            if not is_configured:
                return "550 Relay denied — domain not configured"
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

            # Parse date
            date_header = None
            date_str = msg.get("Date")
            if date_str:
                try:
                    date_header = parsedate_to_datetime(date_str)
                except Exception:
                    pass

            # Extract body parts
            body_text = ""
            body_html = ""
            has_attachments = False
            attachment_count = 0

            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    cd = str(part.get("Content-Disposition", ""))
                    if "attachment" in cd:
                        has_attachments = True
                        attachment_count += 1
                        continue
                    if ct == "text/plain" and not body_text:
                        body_text = part.get_payload(decode=True).decode("utf-8", errors="replace")
                    elif ct == "text/html" and not body_html:
                        body_html = part.get_payload(decode=True).decode("utf-8", errors="replace")
            else:
                ct = msg.get_content_type()
                payload = msg.get_payload(decode=True)
                if payload:
                    decoded = payload.decode("utf-8", errors="replace")
                    if ct == "text/html":
                        body_html = decoded
                    else:
                        body_text = decoded

            # Remote hostname
            remote_hostname = session.host_name or ""

            # Store in DB for each recipient
            from shared.database import db_service
            async with db_service.acquire() as conn:
                for rcpt in envelope.rcpt_tos:
                    await conn.execute(
                        "INSERT INTO email_inbox "
                        "(mail_from, rcpt_to, from_header, to_header, subject, date_header, "
                        " message_id, in_reply_to, body_text, body_html, raw_message, "
                        " remote_ip, remote_hostname, has_attachments, attachment_count) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)",
                        envelope.mail_from, rcpt, from_header, to_header, subject,
                        date_header, message_id, in_reply_to, body_text, body_html,
                        raw_str[:500_000],  # truncate raw to 500KB
                        remote_ip, remote_hostname, has_attachments, attachment_count,
                    )

            logger.info("Inbound email stored: from=%s to=%s subj=%s",
                        envelope.mail_from, envelope.rcpt_tos, subject[:60])
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

    def __init__(self, hostname: str = "0.0.0.0", port: int = 2525):
        self.hostname = hostname
        self.port = port
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self):
        """Start the inbound SMTP server in the current event loop."""
        try:
            handler = InboundMailHandler()
            loop = asyncio.get_running_loop()
            self._server = await loop.create_server(
                lambda: SMTPProtocol(handler, hostname="remnawave-mail",
                                     data_size_limit=_MAX_MESSAGE_SIZE),
                host=self.hostname,
                port=self.port,
            )
            logger.info("Inbound SMTP server started on %s:%d", self.hostname, self.port)
        except Exception as e:
            logger.error("Failed to start inbound SMTP server: %s", e)

    async def stop(self):
        """Stop the inbound SMTP server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("Inbound SMTP server stopped")

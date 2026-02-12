"""Outbound email queue — polls pending emails and delivers via direct MX."""
import asyncio
import logging
import ssl
import uuid
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class OutboundMailQueue:
    """Background queue processor for outgoing emails.

    Polls ``email_queue`` for pending messages and delivers them
    directly to the recipient's MX server with DKIM signing.
    """

    POLL_INTERVAL = 10  # seconds
    BATCH_SIZE = 10

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Outbound mail queue started (poll=%ds)", self.POLL_INTERVAL)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Outbound mail queue stopped")

    # ── Public API ────────────────────────────────────────────────

    async def enqueue(
        self,
        from_email: str,
        to_email: str,
        subject: str,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        from_name: Optional[str] = None,
        category: Optional[str] = None,
        priority: int = 0,
        domain_id: Optional[int] = None,
    ) -> Optional[int]:
        """Add an email to the outbound queue. Returns the queue row id."""
        try:
            from src.services.database import db_service
            async with db_service.acquire() as conn:
                # Auto-resolve domain_id from sender address
                if domain_id is None:
                    sender_domain = from_email.split("@")[-1] if "@" in from_email else None
                    if sender_domain:
                        domain_id = await conn.fetchval(
                            "SELECT id FROM domain_config WHERE domain = $1 AND is_active = true",
                            sender_domain,
                        )

                # Rate limit check
                if domain_id:
                    allowed = await self._check_rate_limit(conn, domain_id)
                    if not allowed:
                        logger.warning("Rate limit exceeded for domain_id=%d", domain_id)
                        return None

                row_id = await conn.fetchval(
                    "INSERT INTO email_queue "
                    "(domain_id, from_email, from_name, to_email, subject, body_text, body_html, "
                    " category, priority, status, next_attempt_at) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending', NOW()) "
                    "RETURNING id",
                    domain_id, from_email, from_name, to_email, subject,
                    body_text, body_html, category, priority,
                )
                logger.info("Enqueued email id=%s to=%s subj=%s", row_id, to_email, subject[:60])
                return row_id
        except Exception as e:
            logger.error("Failed to enqueue email: %s", e)
            return None

    # ── Background loop ───────────────────────────────────────────

    async def _run_loop(self):
        while self._running:
            try:
                await asyncio.sleep(self.POLL_INTERVAL)
                await self._process_queue()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Queue loop error: %s", e)
                await asyncio.sleep(5)

    async def _process_queue(self):
        """Pick up pending emails and attempt delivery."""
        try:
            from src.services.database import db_service
            if not db_service.is_connected:
                return

            async with db_service.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT eq.*, dc.domain, dc.dkim_selector, dc.dkim_private_key, "
                    "  dc.outbound_enabled "
                    "FROM email_queue eq "
                    "LEFT JOIN domain_config dc ON dc.id = eq.domain_id "
                    "WHERE eq.status IN ('pending', 'failed') "
                    "  AND eq.next_attempt_at <= NOW() "
                    "  AND eq.attempts < eq.max_attempts "
                    "ORDER BY eq.priority DESC, eq.created_at ASC "
                    "LIMIT $1 "
                    "FOR UPDATE OF eq SKIP LOCKED",
                    self.BATCH_SIZE,
                )

            for row in rows:
                try:
                    await self._send_one(dict(row))
                except Exception as e:
                    logger.error("Send error for queue id=%s: %s", row["id"], e)

        except Exception as e:
            logger.error("Queue processing error: %s", e)

    async def _send_one(self, row: Dict[str, Any]):
        """Attempt to deliver a single queued email."""
        from src.services.database import db_service

        queue_id = row["id"]
        to_email = row["to_email"]
        from_email = row["from_email"]

        # Mark as sending
        async with db_service.acquire() as conn:
            await conn.execute(
                "UPDATE email_queue SET status = 'sending', attempts = attempts + 1, "
                "last_attempt_at = NOW() WHERE id = $1",
                queue_id,
            )

        try:
            # Build the email message
            msg = self._build_message(row)
            raw_bytes = msg.as_bytes()

            # DKIM sign if domain config available
            if row.get("dkim_private_key") and row.get("dkim_selector") and row.get("domain"):
                from web.backend.core.mail.dkim_manager import sign_message
                raw_bytes = sign_message(
                    raw_bytes, row["domain"], row["dkim_selector"], row["dkim_private_key"],
                )

            # Resolve MX and deliver
            rcpt_domain = to_email.split("@")[-1]
            mx_hosts = await self._resolve_mx(rcpt_domain)
            if not mx_hosts:
                raise RuntimeError(f"No MX records found for {rcpt_domain}")

            smtp_response = await self._deliver_smtp(mx_hosts, from_email, to_email, raw_bytes)

            # Success
            async with db_service.acquire() as conn:
                await conn.execute(
                    "UPDATE email_queue SET status = 'sent', sent_at = NOW(), "
                    "smtp_response = $1, message_id = $2 WHERE id = $3",
                    smtp_response, msg["Message-ID"], queue_id,
                )
            logger.info("Email sent: id=%s to=%s", queue_id, to_email)

        except Exception as e:
            error_msg = str(e)[:500]
            attempts = row.get("attempts", 0) + 1
            max_attempts = row.get("max_attempts", 5)

            if attempts >= max_attempts:
                new_status = "failed"
                next_attempt = None
            else:
                new_status = "failed"
                # Exponential backoff: 2^attempts * 60 seconds
                delay = min(2 ** attempts * 60, 3600)
                next_attempt = datetime.now(timezone.utc) + timedelta(seconds=delay)

            async with db_service.acquire() as conn:
                await conn.execute(
                    "UPDATE email_queue SET status = $1, last_error = $2, next_attempt_at = $3 "
                    "WHERE id = $4",
                    new_status, error_msg, next_attempt, queue_id,
                )
            logger.warning("Email delivery failed: id=%s err=%s (attempt %d/%d)",
                           queue_id, error_msg[:100], attempts, max_attempts)

    def _build_message(self, row: Dict[str, Any]) -> EmailMessage:
        """Build an EmailMessage from a queue row."""
        msg = EmailMessage()
        msg["Subject"] = row["subject"]
        from_name = row.get("from_name")
        if from_name:
            msg["From"] = formataddr((from_name, row["from_email"]))
        else:
            msg["From"] = row["from_email"]
        msg["To"] = row["to_email"]
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=row.get("domain") or "localhost")

        body_text = row.get("body_text") or ""
        body_html = row.get("body_html")

        if body_html:
            msg.set_content(body_text, subtype="plain", charset="utf-8")
            msg.add_alternative(body_html, subtype="html", charset="utf-8")
        else:
            msg.set_content(body_text, subtype="plain", charset="utf-8")

        return msg

    async def _resolve_mx(self, domain: str) -> List[str]:
        """Resolve MX records for a domain, sorted by priority."""
        try:
            import dns.resolver
            answers = dns.resolver.resolve(domain, "MX")
            mx_list = sorted(answers, key=lambda r: r.preference)
            return [str(r.exchange).rstrip(".") for r in mx_list]
        except Exception as e:
            logger.warning("MX resolution failed for %s: %s", domain, e)
            return []

    async def _deliver_smtp(
        self,
        mx_hosts: List[str],
        from_email: str,
        to_email: str,
        raw_bytes: bytes,
    ) -> str:
        """Try delivering to MX hosts in order with opportunistic TLS.

        Attempts STARTTLS without certificate verification first (standard for
        MX delivery — many servers have self-signed or mismatched certs).
        Falls back to plain SMTP if STARTTLS is not supported.
        """
        import aiosmtplib

        # Permissive TLS context: encrypt the connection but don't verify the
        # remote certificate — this is the standard behaviour for MX delivery.
        tls_ctx = ssl.create_default_context()
        tls_ctx.check_hostname = False
        tls_ctx.verify_mode = ssl.CERT_NONE

        last_error = None
        for host in mx_hosts[:3]:
            # 1) Try with opportunistic STARTTLS (no cert verification)
            try:
                response = await aiosmtplib.send(
                    raw_bytes,
                    sender=from_email,
                    recipients=[to_email],
                    hostname=host,
                    port=25,
                    timeout=30,
                    start_tls=True,
                    tls_context=tls_ctx,
                )
                return str(response)
            except aiosmtplib.SMTPResponseException as e:
                last_error = e
                logger.warning("SMTP error from %s: %s", host, e)
                continue
            except Exception as e:
                logger.debug("STARTTLS failed for %s: %s — falling back to plain", host, e)

            # 2) Fallback: plain SMTP (no TLS)
            try:
                response = await aiosmtplib.send(
                    raw_bytes,
                    sender=from_email,
                    recipients=[to_email],
                    hostname=host,
                    port=25,
                    timeout=30,
                    start_tls=False,
                )
                return str(response)
            except Exception as e:
                last_error = e
                logger.warning("Plain SMTP also failed for %s: %s", host, e)

        raise RuntimeError(f"All MX hosts failed: {last_error}")

    async def _check_rate_limit(self, conn, domain_id: int) -> bool:
        """Check if the domain is within its hourly send limit."""
        row = await conn.fetchrow(
            "SELECT max_send_per_hour FROM domain_config WHERE id = $1", domain_id,
        )
        if not row or not row["max_send_per_hour"]:
            return True

        sent_count = await conn.fetchval(
            "SELECT COUNT(*) FROM email_queue "
            "WHERE domain_id = $1 AND created_at > NOW() - INTERVAL '1 hour'",
            domain_id,
        )
        return (sent_count or 0) < row["max_send_per_hour"]


# Global instance
outbound_queue = OutboundMailQueue()

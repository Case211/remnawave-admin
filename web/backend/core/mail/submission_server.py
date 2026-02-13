"""SMTP Submission server — authenticated relay for external SMTP clients.

Listens on port 587 (configurable) and requires SMTP AUTH (PLAIN / LOGIN)
before accepting messages for relay through the outbound queue.
"""
import asyncio
import base64
import hashlib
import hmac
import logging
import secrets
from typing import Optional

from aiosmtpd.smtp import SMTP as SMTPProtocol, AuthResult, LoginPassword, Envelope, Session

logger = logging.getLogger(__name__)

# Rate limiting per credential: in-memory, resets hourly
from collections import defaultdict
from datetime import datetime, timedelta, timezone

_CRED_COUNTER: dict = defaultdict(lambda: {"count": 0, "reset_at": datetime.min.replace(tzinfo=timezone.utc)})


def _hash_password(password: str, salt: str) -> str:
    """Hash password with SHA-256 + salt."""
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def hash_password_for_storage(password: str) -> str:
    """Create a salted hash suitable for storing in smtp_credentials.password_hash."""
    salt = secrets.token_hex(16)
    hashed = _hash_password(password, salt)
    return f"{salt}${hashed}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored salt$hash value."""
    if "$" not in stored_hash:
        return False
    salt, expected = stored_hash.split("$", 1)
    return hmac.compare_digest(_hash_password(password, salt), expected)


class SubmissionAuthenticator:
    """aiosmtpd Authenticator that checks credentials against smtp_credentials table."""

    async def __call__(self, server, session, envelope, mechanism, auth_data):
        """Authenticate SMTP client.

        aiosmtpd calls this with mechanism='LOGIN' or 'PLAIN' and
        auth_data as a LoginPassword namedtuple.
        """
        if not isinstance(auth_data, LoginPassword):
            return AuthResult(success=False, handled=False)

        username = auth_data.login.decode() if isinstance(auth_data.login, bytes) else auth_data.login
        password = auth_data.password.decode() if isinstance(auth_data.password, bytes) else auth_data.password

        try:
            from src.services.database import db_service
            async with db_service.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, password_hash, is_active, max_send_per_hour, allowed_from_domains "
                    "FROM smtp_credentials WHERE username = $1",
                    username,
                )

                if not row:
                    logger.warning("SMTP AUTH failed: unknown user '%s'", username)
                    return AuthResult(success=False, handled=False)

                if not row["is_active"]:
                    logger.warning("SMTP AUTH failed: disabled user '%s'", username)
                    return AuthResult(success=False, handled=False)

                if not verify_password(password, row["password_hash"]):
                    logger.warning("SMTP AUTH failed: bad password for '%s'", username)
                    return AuthResult(success=False, handled=False)

                # Rate limiting
                now = datetime.now(timezone.utc)
                entry = _CRED_COUNTER[row["id"]]
                if now >= entry["reset_at"]:
                    entry["count"] = 0
                    entry["reset_at"] = now + timedelta(hours=1)
                if entry["count"] >= row["max_send_per_hour"]:
                    logger.warning("SMTP AUTH rate limit exceeded for '%s'", username)
                    return AuthResult(success=False, handled=False)

                # Update last login
                peer = session.peer
                remote_ip = peer[0] if peer else "unknown"
                await conn.execute(
                    "UPDATE smtp_credentials SET last_login_at = NOW(), last_login_ip = $1 WHERE id = $2",
                    remote_ip, row["id"],
                )

                # Store credential info on session for use in handler
                session.smtp_credential_id = row["id"]
                session.smtp_username = username
                session.smtp_max_per_hour = row["max_send_per_hour"]
                session.smtp_allowed_domains = row["allowed_from_domains"] or []

                logger.info("SMTP AUTH success: user='%s' from=%s", username, remote_ip)
                return AuthResult(success=True)

        except Exception as e:
            logger.error("SMTP AUTH error: %s", e)
            return AuthResult(success=False, handled=False)


class SubmissionHandler:
    """aiosmtpd handler for authenticated submission — enqueues messages for delivery."""

    async def handle_EHLO(self, server, session, envelope, hostname, responses):
        session.host_name = hostname
        return responses

    async def handle_RCPT(self, server, session: Session, envelope: Envelope, address: str, rcpt_options):
        """Accept recipients — auth is already verified at this point."""
        if not address or "@" not in address:
            return "550 Invalid recipient"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session: Session, envelope: Envelope):
        """Enqueue the submitted message for outbound delivery."""
        # Bump per-credential counter
        cred_id = getattr(session, "smtp_credential_id", None)
        if cred_id:
            _CRED_COUNTER[cred_id]["count"] += 1

        from_email = envelope.mail_from
        allowed_domains = getattr(session, "smtp_allowed_domains", [])

        # Check sender domain restrictions
        if allowed_domains:
            sender_domain = from_email.split("@")[-1].lower() if "@" in from_email else ""
            if sender_domain not in [d.lower() for d in allowed_domains]:
                return "550 Sender domain not allowed for this account"

        # Parse the submitted message
        import email
        raw_data = envelope.content
        if isinstance(raw_data, bytes):
            raw_str = raw_data.decode("utf-8", errors="replace")
        else:
            raw_str = str(raw_data)

        try:
            msg = email.message_from_string(raw_str)
            subject = msg.get("Subject", "(no subject)")
            from_header = msg.get("From", from_email)

            # Extract body
            body_text = ""
            body_html = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    cd = str(part.get("Content-Disposition", ""))
                    if "attachment" in cd:
                        continue
                    payload = part.get_payload(decode=True)
                    if payload is None:
                        continue
                    decoded = payload.decode("utf-8", errors="replace")
                    if ct == "text/plain" and not body_text:
                        body_text = decoded
                    elif ct == "text/html" and not body_html:
                        body_html = decoded
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    decoded = payload.decode("utf-8", errors="replace")
                    if msg.get_content_type() == "text/html":
                        body_html = decoded
                    else:
                        body_text = decoded

            # Parse from_name from From header
            from email.utils import parseaddr
            from_name, parsed_email = parseaddr(from_header)
            if parsed_email:
                from_email = parsed_email

            # Enqueue for each recipient
            from web.backend.core.mail.outbound_queue import outbound_queue
            username = getattr(session, "smtp_username", "unknown")
            queued = 0
            for rcpt in envelope.rcpt_tos:
                queue_id = await outbound_queue.enqueue(
                    from_email=from_email,
                    to_email=rcpt,
                    subject=subject,
                    body_text=body_text or None,
                    body_html=body_html or None,
                    from_name=from_name or None,
                    category="smtp_submission",
                )
                if queue_id:
                    queued += 1

            logger.info(
                "Submission: user='%s' from=%s to=%s queued=%d",
                username, from_email, envelope.rcpt_tos, queued,
            )
            return f"250 OK {queued} message(s) queued"

        except Exception as e:
            logger.error("Submission DATA error: %s", e)
            return "451 Processing error"


class SubmissionServer:
    """Manages the SMTP submission server lifecycle.

    Runs on port 587 (configurable) with required AUTH.
    """

    def __init__(self, hostname: str = "0.0.0.0", port: int = 587):
        self.hostname = hostname
        self.port = port
        self._server: Optional[asyncio.AbstractServer] = None

    async def start(self):
        """Start the SMTP submission server."""
        try:
            handler = SubmissionHandler()
            authenticator = SubmissionAuthenticator()
            loop = asyncio.get_running_loop()
            self._server = await loop.create_server(
                lambda: SMTPProtocol(
                    handler,
                    hostname="remnawave-submission",
                    authenticator=authenticator,
                    auth_required=True,
                    auth_require_tls=False,
                    data_size_limit=25 * 1024 * 1024,  # 25 MB for submissions
                ),
                host=self.hostname,
                port=self.port,
            )
            logger.info("SMTP Submission server started on %s:%d", self.hostname, self.port)
        except Exception as e:
            logger.error("Failed to start SMTP submission server: %s", e)

    async def stop(self):
        """Stop the submission server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            logger.info("SMTP Submission server stopped")

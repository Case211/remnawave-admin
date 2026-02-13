"""Mail service orchestrator — manages outbound queue and inbound server."""
import logging
from typing import Any, Dict, List, Optional

from web.backend.core.mail.outbound_queue import OutboundMailQueue, outbound_queue
from web.backend.core.mail.inbound_server import InboundMailServer
from web.backend.core.mail.submission_server import SubmissionServer

logger = logging.getLogger(__name__)


class MailService:
    """High-level mail service that coordinates queue and inbound server."""

    def __init__(self):
        self.queue: OutboundMailQueue = outbound_queue
        self.inbound: Optional[InboundMailServer] = None
        self.submission: Optional[SubmissionServer] = None

    async def start(self):
        """Start mail subsystems based on configuration.

        Reads settings from config_service (DB > .env > default).
        """
        try:
            from src.services.config_service import config_service

            mail_enabled = config_service.get("mailserver_enabled", False)
            if not mail_enabled:
                logger.info("Mail server disabled (mailserver_enabled=false)")
                return

            # Read queue tuning from config
            poll_interval = config_service.get("mailserver_queue_poll_interval", 10)
            self.queue.POLL_INTERVAL = poll_interval

            # Always start outbound queue
            await self.queue.start()

            # Start inbound server if configured
            inbound_port = config_service.get("mailserver_inbound_port", 2525)
            mail_hostname = config_service.get("mailserver_hostname", "0.0.0.0")
            if inbound_port:
                self.inbound = InboundMailServer(hostname=mail_hostname, port=inbound_port)
                await self.inbound.start()

            # Start submission (relay) server if configured
            submission_enabled = config_service.get("mailserver_submission_enabled", False)
            if submission_enabled:
                submission_port = config_service.get("mailserver_submission_port", 587)
                self.submission = SubmissionServer(hostname=mail_hostname, port=submission_port)
                await self.submission.start()

            logger.info("Mail service started")
        except Exception as e:
            logger.error("Mail service start error: %s", e)

    async def stop(self):
        """Stop all mail subsystems."""
        try:
            await self.queue.stop()
        except Exception:
            pass
        try:
            if self.inbound:
                await self.inbound.stop()
        except Exception:
            pass
        try:
            if self.submission:
                await self.submission.stop()
        except Exception:
            pass
        logger.info("Mail service stopped")

    async def send_email(
        self,
        to_email: str,
        subject: str,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        category: Optional[str] = None,
        priority: int = 0,
    ) -> Optional[int]:
        """Send an email via the outbound queue.

        If from_email is not specified, uses the first active outbound domain.
        Returns the queue item ID.
        """
        if not from_email:
            domain = await self.get_active_outbound_domain()
            if domain:
                from_email = f"noreply@{domain['domain']}"
                from_name = from_name or domain.get("from_name")
            else:
                logger.warning("No active outbound domain configured")
                return None

        return await self.queue.enqueue(
            from_email=from_email,
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            from_name=from_name,
            category=category,
            priority=priority,
        )

    async def setup_domain(self, domain: str) -> Dict[str, Any]:
        """Set up a new domain with DKIM keys.

        Returns the created domain config dict.
        """
        from web.backend.core.mail.dkim_manager import generate_dkim_keypair
        from src.services.database import db_service

        private_pem, public_pem = generate_dkim_keypair()

        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO domain_config (domain, dkim_private_key, dkim_public_key, dkim_selector) "
                "VALUES ($1, $2, $3, 'rw') "
                "ON CONFLICT (domain) DO UPDATE SET "
                "  dkim_private_key = EXCLUDED.dkim_private_key, "
                "  dkim_public_key = EXCLUDED.dkim_public_key, "
                "  updated_at = NOW() "
                "RETURNING *",
                domain, private_pem, public_pem,
            )

        logger.info("Domain setup: %s", domain)
        return dict(row)

    async def check_domain_dns(self, domain_id: int) -> Dict[str, Any]:
        """Run DNS checks for a domain and update status in DB."""
        from web.backend.core.mail.dns_checker import (
            check_mx_records, check_spf_record, check_dkim_record,
            check_dmarc_record, get_server_ip,
        )
        from src.services.database import db_service

        async with db_service.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM domain_config WHERE id = $1", domain_id)
            if not row:
                return {"error": "Domain not found"}

            domain = row["domain"]
            selector = row["dkim_selector"] or "rw"
            server_ip = get_server_ip()

            mx_ok, _ = check_mx_records(domain)
            spf_ok, _ = check_spf_record(domain, server_ip)
            dkim_ok, _ = check_dkim_record(domain, selector)
            dmarc_ok, _ = check_dmarc_record(domain)

            await conn.execute(
                "UPDATE domain_config SET "
                "dns_mx_ok = $1, dns_spf_ok = $2, dns_dkim_ok = $3, dns_dmarc_ok = $4, "
                "dns_checked_at = NOW(), updated_at = NOW() "
                "WHERE id = $5",
                mx_ok, spf_ok, dkim_ok, dmarc_ok, domain_id,
            )

        return {
            "domain": domain,
            "mx_ok": mx_ok,
            "spf_ok": spf_ok,
            "dkim_ok": dkim_ok,
            "dmarc_ok": dmarc_ok,
        }

    async def get_active_outbound_domain(self) -> Optional[Dict[str, Any]]:
        """Return the first active outbound domain config, or None."""
        try:
            from src.services.database import db_service
            async with db_service.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM domain_config "
                    "WHERE is_active = true AND outbound_enabled = true "
                    "ORDER BY id LIMIT 1"
                )
                return dict(row) if row else None
        except Exception:
            return None

    async def refresh_smtp_credentials(self):
        """Trigger an immediate refresh of the SMTP credential cache."""
        if self.submission and self.submission.authenticator:
            await self.submission.authenticator.refresh_credentials()

    async def get_domain_dns_records(self, domain_id: int) -> List[Dict[str, Any]]:
        """Get the required DNS records for a domain."""
        from web.backend.core.mail.dns_checker import get_required_dns_records
        from src.services.database import db_service

        async with db_service.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM domain_config WHERE id = $1", domain_id)
            if not row:
                return []

        from web.backend.core.mail.dns_checker import DnsRecord
        records = get_required_dns_records(
            domain=row["domain"],
            selector=row["dkim_selector"] or "rw",
            public_key_pem=row["dkim_public_key"] or "",
        )
        return [
            {
                "record_type": r.record_type,
                "host": r.host,
                "value": r.value,
                "purpose": r.purpose,
                "is_configured": r.is_configured,
                "current_value": r.current_value,
            }
            for r in records
        ]


# Global service instance
mail_service = MailService()

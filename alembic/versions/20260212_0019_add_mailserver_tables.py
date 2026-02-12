"""Add embedded mail server tables.

Revision ID: 0019
Revises: 0018
Create Date: 2026-02-12

Phase 11 — Embedded Mail Server.
Creates tables for domain config, email queue, and email inbox.
Adds RBAC permissions for the mailserver resource.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MAILSERVER_PERMISSIONS = {
    "superadmin": {
        "mailserver": ["view", "create", "edit", "delete"],
    },
    "manager": {
        "mailserver": ["view"],
    },
}


def upgrade() -> None:
    # ── 1. domain_config ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS domain_config (
            id SERIAL PRIMARY KEY,
            domain VARCHAR(255) NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT false,
            dkim_selector VARCHAR(63) NOT NULL DEFAULT 'rw',
            dkim_private_key TEXT,
            dkim_public_key TEXT,
            inbound_enabled BOOLEAN NOT NULL DEFAULT false,
            outbound_enabled BOOLEAN NOT NULL DEFAULT true,
            max_send_per_hour INTEGER NOT NULL DEFAULT 100,
            dns_mx_ok BOOLEAN DEFAULT false,
            dns_spf_ok BOOLEAN DEFAULT false,
            dns_dkim_ok BOOLEAN DEFAULT false,
            dns_dmarc_ok BOOLEAN DEFAULT false,
            dns_checked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── 2. email_queue ────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_queue (
            id BIGSERIAL PRIMARY KEY,
            domain_id INTEGER REFERENCES domain_config(id) ON DELETE SET NULL,
            from_email VARCHAR(255) NOT NULL,
            from_name VARCHAR(255),
            to_email VARCHAR(255) NOT NULL,
            subject VARCHAR(1024) NOT NULL,
            body_text TEXT,
            body_html TEXT,
            headers JSONB DEFAULT '{}',
            priority INTEGER NOT NULL DEFAULT 0,
            category VARCHAR(50),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            last_attempt_at TIMESTAMPTZ,
            next_attempt_at TIMESTAMPTZ DEFAULT NOW(),
            last_error TEXT,
            message_id VARCHAR(255),
            smtp_response TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_queue_status ON email_queue (status)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_email_queue_next_attempt ON email_queue (next_attempt_at) "
        "WHERE status IN ('pending', 'failed')"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_queue_created_at ON email_queue (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_queue_category ON email_queue (category)")

    # ── 3. email_inbox ────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_inbox (
            id BIGSERIAL PRIMARY KEY,
            mail_from VARCHAR(255),
            rcpt_to VARCHAR(255) NOT NULL,
            from_header VARCHAR(1024),
            to_header VARCHAR(1024),
            subject VARCHAR(1024),
            date_header TIMESTAMPTZ,
            message_id VARCHAR(255),
            in_reply_to VARCHAR(255),
            body_text TEXT,
            body_html TEXT,
            raw_message TEXT,
            remote_ip VARCHAR(45),
            remote_hostname VARCHAR(255),
            is_read BOOLEAN NOT NULL DEFAULT false,
            is_spam BOOLEAN NOT NULL DEFAULT false,
            spam_score FLOAT DEFAULT 0,
            has_attachments BOOLEAN NOT NULL DEFAULT false,
            attachment_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_inbox_rcpt_to ON email_inbox (rcpt_to)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_inbox_is_read ON email_inbox (is_read)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_inbox_created_at ON email_inbox (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_inbox_mail_from ON email_inbox (mail_from)")

    # ── 4. RBAC permissions ───────────────────────────────────────
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name FROM admin_roles")).fetchall()
    role_id_map = {row[1]: row[0] for row in rows}

    for role_name, resources in MAILSERVER_PERMISSIONS.items():
        role_id = role_id_map.get(role_name)
        if not role_id:
            continue
        for resource, actions in resources.items():
            for action in actions:
                conn.execute(
                    sa.text(
                        "INSERT INTO admin_permissions (role_id, resource, action) "
                        "VALUES (:role_id, :resource, :action) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"role_id": role_id, "resource": resource, "action": action},
                )


def downgrade() -> None:
    op.execute("DELETE FROM admin_permissions WHERE resource = 'mailserver'")
    op.execute("DROP TABLE IF EXISTS email_inbox")
    op.execute("DROP TABLE IF EXISTS email_queue")
    op.execute("DROP TABLE IF EXISTS domain_config")

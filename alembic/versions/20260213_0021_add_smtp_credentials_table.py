"""Add SMTP credentials table for submission server.

Revision ID: 0021
Revises: 0020
Create Date: 2026-02-13

Phase 11b — SMTP Submission Server.
Creates smtp_credentials table for authenticating external SMTP clients.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS smtp_credentials (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            description VARCHAR(500),
            is_active BOOLEAN NOT NULL DEFAULT true,
            allowed_from_domains TEXT[] DEFAULT '{}',
            max_send_per_hour INTEGER NOT NULL DEFAULT 100,
            last_login_at TIMESTAMPTZ,
            last_login_ip VARCHAR(45),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_smtp_credentials_username ON smtp_credentials (username)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS smtp_credentials")

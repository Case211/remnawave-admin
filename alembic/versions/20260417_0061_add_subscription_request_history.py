"""Add subscription_request_history table for SRH sync.

Revision ID: 0061
Revises: 0060
Create Date: 2026-04-17

Mirrors Panel API `/api/subscription-request-history` into a local table for
UserAgent analysis and offline review. Primary key `id` matches Panel's record id
for idempotent upserts.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0061"
down_revision: Union[str, None] = "0060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS subscription_request_history (
            id BIGINT PRIMARY KEY,
            user_uuid UUID NOT NULL,
            request_ip VARCHAR(64),
            user_agent TEXT,
            request_at TIMESTAMPTZ NOT NULL,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_srh_user_uuid ON subscription_request_history(user_uuid)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_srh_user_request_at ON subscription_request_history(user_uuid, request_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_srh_request_at ON subscription_request_history(request_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS subscription_request_history")

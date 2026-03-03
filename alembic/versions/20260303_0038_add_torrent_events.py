"""Add torrent_events table for storing raw torrent traffic detections.

Revision ID: 0038
Revises: 0037
Create Date: 2026-03-03

Stores individual torrent traffic events detected by node agents
via Xray access log routing tags.
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0038'
down_revision: Union[str, None] = '0037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS torrent_events (
            id BIGSERIAL PRIMARY KEY,
            user_uuid UUID NOT NULL,
            node_uuid UUID NOT NULL,
            ip_address VARCHAR(45) NOT NULL,
            destination VARCHAR(255) NOT NULL,
            inbound_tag VARCHAR(100) DEFAULT '',
            outbound_tag VARCHAR(100) DEFAULT 'TORRENT',
            detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_te_user_date ON torrent_events (user_uuid, detected_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_te_detected ON torrent_events (detected_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_te_detected")
    op.execute("DROP INDEX IF EXISTS idx_te_user_date")
    op.execute("DROP TABLE IF EXISTS torrent_events")

"""External support contacts for delayed automation rechecks.

Revision ID: 0126
Revises: 0125
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0126"
down_revision: Union[str, None] = "0125"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS external_support_events (
            id BIGSERIAL PRIMARY KEY,
            api_key_id BIGINT NOT NULL,
            idempotency_key VARCHAR(200) NOT NULL,
            source VARCHAR(64) NOT NULL,
            kind VARCHAR(64) NOT NULL DEFAULT 'message',
            user_uuid UUID NOT NULL,
            telegram_id BIGINT,
            occurred_at TIMESTAMPTZ NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (api_key_id, idempotency_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_external_support_events_user_time "
        "ON external_support_events (user_uuid, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_external_support_events_telegram_time "
        "ON external_support_events (telegram_id, occurred_at DESC) WHERE telegram_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS external_support_events")

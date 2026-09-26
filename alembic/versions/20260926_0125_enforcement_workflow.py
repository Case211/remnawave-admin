"""Durable delayed-enforcement cases and support events.

Revision ID: 0125
Revises: 0124
Create Date: 2026-09-26
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0125"
down_revision: Union[str, None] = "0124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE enforcement_cases (
            id BIGSERIAL PRIMARY KEY,
            violation_id BIGINT REFERENCES violations(id) ON DELETE SET NULL,
            user_uuid UUID NOT NULL,
            signal_code TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_notice',
            mode TEXT NOT NULL DEFAULT 'dry_run',
            final_action TEXT NOT NULL DEFAULT 'manual_review',
            deadline_at TIMESTAMPTZ NOT NULL,
            notice_sent_at TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ,
            resolution TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            policy_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_enforcement_case UNIQUE (violation_id, user_uuid, signal_code),
            CONSTRAINT ck_enforcement_case_status CHECK (status IN (
                'pending_notice', 'notifying', 'grace_period', 'due', 'enforcing',
                'enforced', 'manual_review', 'failed', 'cancelled', 'resolved',
                'paused_for_support', 'dry_run'
            )),
            CONSTRAINT ck_enforcement_case_mode CHECK (
                mode IN ('dry_run', 'deliver_only', 'enforce')
            ),
            CONSTRAINT ck_enforcement_case_action CHECK (
                final_action IN ('manual_review', 'disable', 'throttle', 'none')
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_enforcement_cases_due "
        "ON enforcement_cases (status, deadline_at)"
    )
    op.execute(
        "CREATE INDEX ix_enforcement_cases_user "
        "ON enforcement_cases (user_uuid, created_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE enforcement_support_events (
            id BIGSERIAL PRIMARY KEY,
            provider TEXT NOT NULL,
            external_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            matched_users INTEGER NOT NULL DEFAULT 0,
            paused_cases INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_enforcement_support_event UNIQUE (provider, external_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_enforcement_support_events_created "
        "ON enforcement_support_events (created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE enforcement_support_events")
    op.execute("DROP TABLE enforcement_cases")

"""Add violations table for storing violation history and reports.

Revision ID: 0007
Revises: 0006
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id BIGSERIAL PRIMARY KEY,
            user_uuid UUID NOT NULL,
            username VARCHAR(255),
            email VARCHAR(255),
            telegram_id BIGINT,
            score FLOAT NOT NULL,
            recommended_action VARCHAR(50) NOT NULL,
            confidence FLOAT,
            temporal_score FLOAT,
            geo_score FLOAT,
            asn_score FLOAT,
            profile_score FLOAT,
            device_score FLOAT,
            ip_addresses TEXT[],
            countries TEXT[],
            cities TEXT[],
            asn_types TEXT[],
            os_list TEXT[],
            client_list TEXT[],
            reasons TEXT[],
            simultaneous_connections INTEGER,
            unique_ips_count INTEGER,
            device_limit INTEGER,
            impossible_travel BOOLEAN NOT NULL DEFAULT false,
            is_mobile BOOLEAN NOT NULL DEFAULT false,
            is_datacenter BOOLEAN NOT NULL DEFAULT false,
            is_vpn BOOLEAN NOT NULL DEFAULT false,
            action_taken VARCHAR(50),
            action_taken_at TIMESTAMPTZ,
            action_taken_by BIGINT,
            detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            notified_at TIMESTAMPTZ,
            raw_breakdown TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_violations_user_uuid ON violations (user_uuid)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_violations_detected_at ON violations (detected_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_violations_score ON violations (score)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_violations_action ON violations (recommended_action)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_violations_user_date ON violations (user_uuid, detected_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_violations_reports ON violations (detected_at, score, recommended_action)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS violation_reports (
            id BIGSERIAL PRIMARY KEY,
            report_type VARCHAR(20) NOT NULL,
            period_start TIMESTAMPTZ NOT NULL,
            period_end TIMESTAMPTZ NOT NULL,
            total_violations INTEGER NOT NULL DEFAULT 0,
            critical_count INTEGER NOT NULL DEFAULT 0,
            warning_count INTEGER NOT NULL DEFAULT 0,
            monitor_count INTEGER NOT NULL DEFAULT 0,
            unique_users INTEGER NOT NULL DEFAULT 0,
            prev_total_violations INTEGER,
            trend_percent FLOAT,
            top_violators TEXT,
            by_country TEXT,
            by_action TEXT,
            by_asn_type TEXT,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent_at TIMESTAMPTZ,
            message_text TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_violation_reports_type ON violation_reports (report_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_violation_reports_period ON violation_reports (period_start, period_end)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_violation_reports_type_period ON violation_reports (report_type, period_start)")


def downgrade() -> None:
    op.drop_index('idx_violation_reports_type_period', table_name='violation_reports')
    op.drop_index('idx_violation_reports_period', table_name='violation_reports')
    op.drop_index('idx_violation_reports_type', table_name='violation_reports')
    op.drop_table('violation_reports')

    op.drop_index('idx_violations_reports', table_name='violations')
    op.drop_index('idx_violations_user_date', table_name='violations')
    op.drop_index('idx_violations_action', table_name='violations')
    op.drop_index('idx_violations_score', table_name='violations')
    op.drop_index('idx_violations_detected_at', table_name='violations')
    op.drop_index('idx_violations_user_uuid', table_name='violations')
    op.drop_table('violations')

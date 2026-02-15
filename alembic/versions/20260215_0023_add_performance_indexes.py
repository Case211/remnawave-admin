"""Add composite indexes for query performance.

Revision ID: 0023
Revises: 0022
Create Date: 2026-02-15

Adds composite indexes to optimize common query patterns:
- admin_audit_log: (admin_id, created_at DESC) for admin activity logs
- admin_audit_log: (created_at DESC) + id for cursor-based pagination
- violations: (detected_at DESC, score DESC) for recent high-severity
- violations: (user_uuid, detected_at DESC) for user violation timeline
- ip_metadata: (created_at) for geo time-series analytics
- users: (status, created_at DESC) for filtered user listings
- automation_log: (triggered_at DESC) + id for cursor-based pagination
- notifications: (admin_id, is_read, created_at DESC) for bell icon queries
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Index definitions: (index_name, table, columns_sql)
_INDEXES = [
    # Audit log: admin activity feed + cursor pagination
    (
        "ix_audit_admin_created",
        "admin_audit_log",
        "admin_id, created_at DESC",
    ),
    (
        "ix_audit_cursor",
        "admin_audit_log",
        "id DESC",
    ),
    # Violations: recent high-severity + per-user timeline
    (
        "ix_violations_detected_score",
        "violations",
        "detected_at DESC, score DESC",
    ),
    # ip_metadata: geo analytics time-series
    (
        "ix_ip_metadata_created",
        "ip_metadata",
        "created_at",
    ),
    # Users: filtered listings by status
    (
        "ix_users_status_created",
        "users",
        "status, created_at DESC",
    ),
    # Automation log: cursor pagination
    (
        "ix_automation_log_cursor",
        "automation_log",
        "id DESC",
    ),
    # Notifications: unread count per admin (bell icon)
    (
        "ix_notifications_admin_read",
        "notifications",
        "admin_id, is_read, created_at DESC",
    ),
]


def upgrade() -> None:
    for idx_name, table, columns in _INDEXES:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} "
            f"ON {table} ({columns})"
        )


def downgrade() -> None:
    for idx_name, _, _ in reversed(_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {idx_name}")

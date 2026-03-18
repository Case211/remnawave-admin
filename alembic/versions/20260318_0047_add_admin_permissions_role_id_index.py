"""Add index on admin_permissions.role_id to fix seq_scan on permission lookups.

Revision ID: 0047
Revises: 0046
Create Date: 2026-03-18
"""
from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction block; disable autocommit via
    # executing raw DDL through get_bind().
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_admin_permissions_role_id "
        "ON admin_permissions(role_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_admin_permissions_role_id")

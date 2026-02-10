"""Add logs:view permission to system roles.

Revision ID: 0015
Revises: 0014
Create Date: 2026-02-10
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # logs:view for superadmin, manager, operator (viewer intentionally excluded)
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'logs', 'view'
        FROM admin_roles r
        WHERE r.name IN ('superadmin', 'manager', 'operator')
        ON CONFLICT (role_id, resource, action) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM admin_permissions
        WHERE resource = 'logs' AND action = 'view'
    """)

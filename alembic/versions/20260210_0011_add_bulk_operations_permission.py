"""Add bulk_operations permission to users resource for superadmin and manager roles.

Revision ID: 0011
Revises: 0010
Create Date: 2026-02-10
"""
from alembic import op

# revision identifiers
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add users.bulk_operations to superadmin and manager roles
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'users', 'bulk_operations'
        FROM admin_roles r
        WHERE r.name IN ('superadmin', 'manager')
        ON CONFLICT (role_id, resource, action) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM admin_permissions
        WHERE resource = 'users' AND action = 'bulk_operations'
    """)

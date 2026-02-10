"""Add fleet resource with view/edit permissions for appropriate roles.

Revision ID: 0012
Revises: 0011
Create Date: 2026-02-10
"""
from alembic import op

# revision identifiers
revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # fleet.view for superadmin, manager, operator, viewer
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'fleet', 'view'
        FROM admin_roles r
        WHERE r.name IN ('superadmin', 'manager', 'operator', 'viewer')
        ON CONFLICT (role_id, resource, action) DO NOTHING
    """)

    # fleet.edit for superadmin, manager
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'fleet', 'edit'
        FROM admin_roles r
        WHERE r.name IN ('superadmin', 'manager')
        ON CONFLICT (role_id, resource, action) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM admin_permissions
        WHERE resource = 'fleet'
    """)

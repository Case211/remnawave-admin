"""Add RBAC permissions for resources, billing, and reports.

Revision ID: 0028
Revises: 0027
Create Date: 2026-02-16

Adds permissions for Phase 8 features:
- resources (view/create/edit/delete) -> superadmin, manager full; operator, viewer view-only
- billing (view/create/edit/delete) -> superadmin, manager full; operator, viewer view-only
- reports (view/create/edit) -> superadmin, manager full; operator, viewer view-only
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0028'
down_revision: Union[str, None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # resources: full CRUD for superadmin + manager, view for operator + viewer
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'resources', a.action
        FROM admin_roles r
        CROSS JOIN (VALUES ('view'), ('create'), ('edit'), ('delete')) AS a(action)
        WHERE r.name IN ('superadmin', 'manager')
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'resources', 'view'
        FROM admin_roles r
        WHERE r.name IN ('operator', 'viewer')
        ON CONFLICT DO NOTHING
    """)

    # billing: full CRUD for superadmin + manager, view for operator + viewer
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'billing', a.action
        FROM admin_roles r
        CROSS JOIN (VALUES ('view'), ('create'), ('edit'), ('delete')) AS a(action)
        WHERE r.name IN ('superadmin', 'manager')
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'billing', 'view'
        FROM admin_roles r
        WHERE r.name IN ('operator', 'viewer')
        ON CONFLICT DO NOTHING
    """)

    # reports: view/create/edit for superadmin + manager, view for operator + viewer
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'reports', a.action
        FROM admin_roles r
        CROSS JOIN (VALUES ('view'), ('create'), ('edit')) AS a(action)
        WHERE r.name IN ('superadmin', 'manager')
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'reports', 'view'
        FROM admin_roles r
        WHERE r.name IN ('operator', 'viewer')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM admin_permissions
        WHERE resource IN ('resources', 'billing', 'reports')
    """)

"""Add fleet.terminal, fleet.scripts, fleet.provision permissions.

Revision ID: 0026
Revises: 0025
Create Date: 2026-02-15

Adds granular fleet management permissions:
- fleet.terminal  → superadmin only
- fleet.scripts   → superadmin + manager
- fleet.provision → superadmin only
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0026'
down_revision: Union[str, None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # fleet.terminal → superadmin only
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'fleet', 'terminal'
        FROM admin_roles r WHERE r.name = 'superadmin'
        ON CONFLICT DO NOTHING
    """)

    # fleet.scripts → superadmin + manager
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'fleet', 'scripts'
        FROM admin_roles r WHERE r.name IN ('superadmin', 'manager')
        ON CONFLICT DO NOTHING
    """)

    # fleet.provision → superadmin only
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'fleet', 'provision'
        FROM admin_roles r WHERE r.name = 'superadmin'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM admin_permissions
        WHERE resource = 'fleet' AND action IN ('terminal', 'scripts', 'provision')
    """)

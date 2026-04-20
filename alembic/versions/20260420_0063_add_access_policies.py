"""Add access_policies system for scoping admin rights to specific resources.

Revision ID: 0063
Revises: 0062
Create Date: 2026-04-20

Introduces reusable access-policy templates that can be attached to roles
or individual admins. Each policy contains rules that whitelist specific
resources (nodes/hosts/squads) by UUID or tag, with a set of allowed actions.

Policy resolution:
- No policies for admin -> full access (backwards compatible)
- Any policies attached -> whitelist: only resources matching rules are visible
- Rules union: role policies + personal admin policies
- Superadmin bypasses all policy checks
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0063"
down_revision: Union[str, None] = "0062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS access_policies (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            created_by INTEGER REFERENCES admin_accounts(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_access_policies_name
        ON access_policies (LOWER(name))
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS access_policy_rules (
            id SERIAL PRIMARY KEY,
            policy_id INTEGER NOT NULL REFERENCES access_policies(id) ON DELETE CASCADE,
            resource_type VARCHAR(20) NOT NULL,
            scope_type VARCHAR(10) NOT NULL,
            scope_value TEXT NOT NULL,
            actions TEXT[] NOT NULL DEFAULT ARRAY['view']::TEXT[],
            CONSTRAINT ck_apr_resource_type CHECK (resource_type IN ('node','host','squad')),
            CONSTRAINT ck_apr_scope_type CHECK (scope_type IN ('uuid','tag'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_apr_policy ON access_policy_rules (policy_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_apr_resource ON access_policy_rules (resource_type)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS role_access_policies (
            role_id INTEGER NOT NULL REFERENCES admin_roles(id) ON DELETE CASCADE,
            policy_id INTEGER NOT NULL REFERENCES access_policies(id) ON DELETE CASCADE,
            attached_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (role_id, policy_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_rap_policy ON role_access_policies (policy_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS admin_access_policies (
            admin_id INTEGER NOT NULL REFERENCES admin_accounts(id) ON DELETE CASCADE,
            policy_id INTEGER NOT NULL REFERENCES access_policies(id) ON DELETE CASCADE,
            attached_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (admin_id, policy_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_aap_policy ON admin_access_policies (policy_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin_access_policies")
    op.execute("DROP TABLE IF EXISTS role_access_policies")
    op.execute("DROP TABLE IF EXISTS access_policy_rules")
    op.execute("DROP TABLE IF EXISTS access_policies")

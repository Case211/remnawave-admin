"""Allow user rules in access policies.

Revision ID: 0128
Revises: 0127
Create Date: 2026-11-18

The API and policy editor already expose resource_type='user', but migration
0063 restricted access_policy_rules to node, host and squad. Replace that check
constraint so user UUID and tag rules can be stored.

Downgrade is deliberately destructive for user-scoped rules: PostgreSQL cannot
restore the old constraint while such rows exist, so downgrade deletes rules
with resource_type='user'. Policies, their non-user rules and role/admin
attachments remain intact.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0128"
down_revision: Union[str, None] = "0127"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE access_policy_rules DROP CONSTRAINT IF EXISTS ck_apr_resource_type")
    op.execute("""
        ALTER TABLE access_policy_rules
        ADD CONSTRAINT ck_apr_resource_type
        CHECK (resource_type IN ('node', 'host', 'squad', 'user'))
    """)


def downgrade() -> None:
    # User rows would violate the restored constraint. Remove only those rules;
    # empty policies and their attachments remain, as do node/host/squad rules.
    op.execute("DELETE FROM access_policy_rules WHERE resource_type = 'user'")
    op.execute("ALTER TABLE access_policy_rules DROP CONSTRAINT IF EXISTS ck_apr_resource_type")
    op.execute("""
        ALTER TABLE access_policy_rules
        ADD CONSTRAINT ck_apr_resource_type
        CHECK (resource_type IN ('node', 'host', 'squad'))
    """)

"""Add title/body template columns to alert_rules.

Revision ID: 0018
Revises: 0017
Create Date: 2026-02-12

Allows admins to customize alert notification text using templates
with variable substitution ({rule_name}, {metric}, {value}, etc.).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE alert_rules
        ADD COLUMN IF NOT EXISTS title_template VARCHAR(500) DEFAULT 'Alert: {rule_name}',
        ADD COLUMN IF NOT EXISTS body_template TEXT DEFAULT '{metric}: {value} ({operator} {threshold})'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE alert_rules DROP COLUMN IF EXISTS title_template")
    op.execute("ALTER TABLE alert_rules DROP COLUMN IF EXISTS body_template")

"""Add from_name column to domain_config.

Revision ID: 0020
Revises: 0019
Create Date: 2026-02-12

Allows customising the sender display name per domain.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE domain_config ADD COLUMN IF NOT EXISTS from_name VARCHAR(255)"
    )
    # Remove hardcoded 'Remnawave Admin' default from smtp_config
    op.execute(
        "ALTER TABLE smtp_config ALTER COLUMN from_name DROP DEFAULT"
    )
    op.execute(
        "UPDATE smtp_config SET from_name = NULL WHERE from_name = 'Remnawave Admin'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE smtp_config ALTER COLUMN from_name SET DEFAULT 'Remnawave Admin'"
    )
    op.execute("ALTER TABLE domain_config DROP COLUMN IF EXISTS from_name")

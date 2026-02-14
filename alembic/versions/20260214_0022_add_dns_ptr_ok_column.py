"""Add dns_ptr_ok column to domain_config.

Revision ID: 0022
Revises: 0021
Create Date: 2026-02-14

Adds PTR (reverse DNS) check status to the domain configuration table.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE domain_config ADD COLUMN IF NOT EXISTS dns_ptr_ok BOOLEAN DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE domain_config DROP COLUMN IF EXISTS dns_ptr_ok")

"""Widen users.short_uuid from VARCHAR(16) to VARCHAR(64).

Revision ID: 0014
Revises: 0013
Create Date: 2026-02-10

The API returns short_uuid values that exceed 16 characters, causing
'value too long for type character varying(16)' errors on upsert.
"""
from alembic import op

# revision identifiers
revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN short_uuid TYPE VARCHAR(64)")


def downgrade() -> None:
    op.execute("ALTER TABLE users ALTER COLUMN short_uuid TYPE VARCHAR(16)")

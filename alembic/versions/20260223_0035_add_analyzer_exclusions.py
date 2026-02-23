"""Add excluded_analyzers to violation_whitelist.

Revision ID: 0035
Revises: 0034
Create Date: 2026-02-23

Per-user analyzer exclusions: NULL = full whitelist, array = partial.
Valid values: temporal, geo, asn, profile, device, hwid.
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0035'
down_revision: Union[str, None] = '0034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "violation_whitelist"


def upgrade() -> None:
    op.execute(f"""
        ALTER TABLE {TABLE}
        ADD COLUMN IF NOT EXISTS excluded_analyzers TEXT[] DEFAULT NULL
    """)
    op.execute(f"""
        COMMENT ON COLUMN {TABLE}.excluded_analyzers IS
        'NULL = full whitelist (all analyzers skipped). '
        'Array of analyzer names to skip: temporal, geo, asn, profile, device, hwid'
    """)


def downgrade() -> None:
    op.execute(f"""
        ALTER TABLE {TABLE}
        DROP COLUMN IF EXISTS excluded_analyzers
    """)

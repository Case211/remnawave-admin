"""Add agent_token to nodes table for Node Agent authentication.

Revision ID: 0003
Revises: 0002
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS agent_token VARCHAR(255)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_agent_token ON nodes (agent_token)")


def downgrade() -> None:
    op.drop_index('idx_nodes_agent_token', table_name='nodes')
    op.drop_column('nodes', 'agent_token')

"""Add user_agent_score and suspicious_user_agents to violations.

Revision ID: 0060
Revises: 0059
Create Date: 2026-04-17

Adds:
- violations.user_agent_score FLOAT  — UserAgentAnalyzer score (0-100)
- violations.suspicious_user_agents JSONB — список подозрительных UA/HWID
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0060"
down_revision: Union[str, None] = "0059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE violations ADD COLUMN IF NOT EXISTS user_agent_score FLOAT")
    op.execute("ALTER TABLE violations ADD COLUMN IF NOT EXISTS suspicious_user_agents JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE violations DROP COLUMN IF EXISTS user_agent_score")
    op.execute("ALTER TABLE violations DROP COLUMN IF EXISTS suspicious_user_agents")

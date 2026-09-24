"""Автоматизации: цепочка действий и отложенные уведомления.

Revision ID: 0121
Revises: 0120

- automation_rules.extra_actions — действия после основного
  («уведомить + урезать скорость»): [{action_type, action_config}, ...];
- automation_pending_actions.payload — данные отложенного действия: текст
  уведомления, придержанного на тихие часы, уходит утром сводкой.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0121"
down_revision: Union[str, None] = "0120"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE automation_rules ADD COLUMN IF NOT EXISTS extra_actions JSONB NOT NULL DEFAULT '[]'::jsonb")
    op.execute("ALTER TABLE automation_pending_actions ADD COLUMN IF NOT EXISTS payload JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE automation_pending_actions DROP COLUMN IF EXISTS payload")
    op.execute("ALTER TABLE automation_rules DROP COLUMN IF EXISTS extra_actions")

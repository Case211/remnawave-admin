"""Автоматизации: отложенные действия — «заблокировать на время».

Revision ID: 0118
Revises: 0117

Блокировка из правила может быть временной: через N часов юзера надо
включить обратно. Отложенное действие хранится в базе, чтобы пережить
рестарт движка; движок раз в минуту выполняет наступившие.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0118"
down_revision: Union[str, None] = "0117"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS automation_pending_actions (
            id BIGSERIAL PRIMARY KEY,
            rule_id INTEGER REFERENCES automation_rules(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            target TEXT NOT NULL,
            run_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            done_at TIMESTAMPTZ,
            result TEXT
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_pending_due "
        "ON automation_pending_actions (run_at) WHERE done_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS automation_pending_actions")

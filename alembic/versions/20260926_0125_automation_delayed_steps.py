"""Автоматизации: отложенный шаг цепочки — «предупредить, через 12 ч урезать».

Revision ID: 0125
Revises: 0124

Шаг цепочки можно выполнить не сразу, а через N часов после срабатывания:
сначала предупредить клиента, а меру применить, только если за это время
ничего не изменилось. Шаг ждёт в automation_pending_actions (переживает
рестарт) со снимком настроек и контекстом нарушения.

Один и тот же шаг правила по одному клиенту в ожидании может быть только
один: повторное срабатывание (нарушение с большим скором) вторую меру не ставит.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0125"
down_revision: Union[str, None] = "0124"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_pending_chain_step "
        "ON automation_pending_actions (rule_id, target, (payload->>'step')) "
        "WHERE action = 'chain_step' AND done_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_automation_pending_chain_step")

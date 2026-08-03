"""Поля SRR в истории запросов подписки (Remnawave 3.1.0).

Панель 3.1.0 добавила в записи истории `srrResponseType` и `srrRuleName` —
какое правило subscription request routing обработало запрос. Для панелей
2.x колонки остаются пустыми.

Revision ID: 0093
Revises: 0092
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0093"
down_revision: Union[str, None] = "0092"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE subscription_request_history "
        "ADD COLUMN IF NOT EXISTS srr_response_type VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE subscription_request_history "
        "ADD COLUMN IF NOT EXISTS srr_rule_name VARCHAR(255)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE subscription_request_history DROP COLUMN IF EXISTS srr_rule_name")
    op.execute("ALTER TABLE subscription_request_history DROP COLUMN IF EXISTS srr_response_type")

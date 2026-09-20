"""Текст отправленного предупреждения хранится вместе с отметкой.

Revision ID: 0112
Revises: 0111
Create Date: 2026-09-20

Кабинет показывает клиенту то предупреждение, которое он получил. Брать текст
из шаблона нельзя: оператор его правит, и человек увидел бы не то, что ему
присылали. Поэтому текст сохраняется в момент отправки.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0112"
down_revision: Union[str, None] = "0111"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE violation_notices ADD COLUMN IF NOT EXISTS subject VARCHAR(200)")
    op.execute("ALTER TABLE violation_notices ADD COLUMN IF NOT EXISTS body TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE violation_notices DROP COLUMN IF EXISTS body")
    op.execute("ALTER TABLE violation_notices DROP COLUMN IF EXISTS subject")

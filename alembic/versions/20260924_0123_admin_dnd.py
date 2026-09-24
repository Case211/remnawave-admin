"""«Не беспокоить» у админа.

Revision ID: 0123
Revises: 0122

Окно «с — до» по часам панели: в это время внешние каналы админа (Telegram,
почта, вебхук) молчат, кроме критичного; в колокольчике уведомления копятся
как обычно.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0123"
down_revision: Union[str, None] = "0122"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE admin_accounts ADD COLUMN IF NOT EXISTS dnd_from VARCHAR(5)")
    op.execute("ALTER TABLE admin_accounts ADD COLUMN IF NOT EXISTS dnd_to VARCHAR(5)")


def downgrade() -> None:
    op.execute("ALTER TABLE admin_accounts DROP COLUMN IF EXISTS dnd_to")
    op.execute("ALTER TABLE admin_accounts DROP COLUMN IF EXISTS dnd_from")

"""Add functional indexes on users table to fix seq_scans.

Revision ID: 0043
Revises: 0042
Create Date: 2026-03-05

pg_stat_user_tables showed 2.5M seq_scans and 21B rows read on users table.
Root causes:
  1. LOWER(username) queries bypass the plain idx_users_username index
  2. raw_data->>'id' JSONB lookup has no index
  3. LOWER(email) LIKE queries bypass idx_users_email
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0043'
down_revision: Union[str, None] = '0042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Функциональный индекс для LOWER(username) — покрывает:
    #    WHERE LOWER(username) = LOWER($1)
    #    WHERE LOWER(username) = ANY(...)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_username_lower
        ON users (LOWER(username))
    """)

    # 2. Функциональный индекс для LOWER(email) — покрывает LIKE-поиск по email
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email_lower
        ON users (LOWER(email))
        WHERE email IS NOT NULL
    """)

    # 3. Индекс на raw_data->>'id' для поиска по числовому ID из Remnawave Panel
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_raw_data_id
        ON users ((raw_data->>'id'))
        WHERE raw_data IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_username_lower")
    op.execute("DROP INDEX IF EXISTS idx_users_email_lower")
    op.execute("DROP INDEX IF EXISTS idx_users_raw_data_id")

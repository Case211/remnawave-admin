"""Ограничение скорости пользователю — «мягкая блокировка».

Revision ID: 0102
Revises: 0101
Create Date: 2026-08-23

Между «предупредить» и «заблокировать» в шкале нарушений зияла дыра:
soft_block значился как ограничение скорости, которого проект не умел, и
администратору оставался выбор из ничего и полного отключения.

Ограничение живёт на ноде правилами tc и вешается на АДРЕС пользователя:
ни конфиг Xray, ни принадлежность к сквадам не трогаются, поэтому мера
применяется и снимается мгновенно, никого больше не задевая. Адреса
пользователь меняет (медиана — четыре за сутки), так что правила
пересобираются по свежим подключениям, а здесь хранится только решение:
кому, насколько и до каких пор.

``until IS NULL`` — бессрочно, до ручного снятия.

``prev_squads`` — сквады, в которых пользователь состоял до наказания. Если
настроен резервный сквад для нарушителей, наказанный переезжает в него, и
без этой колонки вернуть человека обратно было бы уже некуда: панель хранит
только текущий состав.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0102"
down_revision: Union[str, None] = "0101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_throttles (
            user_uuid UUID PRIMARY KEY,
            rate_kbit INTEGER NOT NULL,
            reason TEXT,
            created_by_admin_id BIGINT,
            created_by_username VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            until TIMESTAMPTZ,
            prev_squads JSONB
        )
        """
    )
    # Синхронизатор раз в минуту спрашивает «кто ограничен прямо сейчас» —
    # частичный индекс по сроку держит этот запрос дешёвым.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_throttles_until "
        "ON user_throttles (until) WHERE until IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_throttles_until")
    op.execute("DROP TABLE IF EXISTS user_throttles")

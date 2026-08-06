"""Ключ истории запросов подписки — пара (id, request_at).

Панель нумерует SRH автоинкрементом и при пересоздании таблицы начинает
счёт заново: 1 июля она откатилась с 65089 на единицу и сейчас идёт по
29-тысячным. Синк тянул записи по правилу ``id > max_local_id``, поэтому
всё, что приходило после отката, считалось уже известным — история молча
перестала наполняться, а вместе с ней ослеп детектор нарушений.

Одного перехода на инкремент по времени мало: пока PRIMARY KEY стоит на
``id``, свежая запись затирает по ``ON CONFLICT (id)`` старую с тем же
номером, но из прошлой эпохи. Ключ становится составным — номер плюс
момент запроса. Одинаковый id из разных эпох сосуществует, а повторная
заливка той же записи по-прежнему сходится в апсерт.

Revision ID: 0095
Revises: 0094
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0095"
down_revision: Union[str, None] = "0094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "subscription_request_history"


def upgrade() -> None:
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, TABLE):
        return

    # request_at входит в ключ, поэтому пустым быть не может. Записей без
    # него в таблице нет (синк такие пропускает), но у старых баз колонка
    # могла остаться nullable.
    conn.execute(text(f"DELETE FROM {TABLE} WHERE request_at IS NULL"))
    conn.execute(text(f"ALTER TABLE {TABLE} ALTER COLUMN request_at SET NOT NULL"))

    conn.execute(text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {TABLE}_pkey"))
    conn.execute(text(f"ALTER TABLE {TABLE} ADD PRIMARY KEY (id, request_at)"))


def downgrade() -> None:
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, TABLE):
        return

    # Возврат к ключу по одному номеру возможен, только если дублей нет:
    # после работы на составном ключе они появиться могли.
    conn.execute(text(f"""
        DELETE FROM {TABLE} a
        USING {TABLE} b
        WHERE a.id = b.id AND a.request_at < b.request_at
    """))
    conn.execute(text(f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {TABLE}_pkey"))
    conn.execute(text(f"ALTER TABLE {TABLE} ADD PRIMARY KEY (id)"))

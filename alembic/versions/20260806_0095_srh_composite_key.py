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

Смена ключа берёт ACCESS EXCLUSIVE, и на живой панели это опасно вдвойне.
Мало того что таблица велика — пока DDL ЖДЁТ блокировку, за ним встают
все остальные запросы к ней. А блокировку он не получит, потому что синк
пишет в эту же таблицу непрерывно. Снаружи это выглядит так: панель
намертво зависла на старте (миграции идут до подъёма API), бот при этом
жив. Поэтому индекс строится без блокировки записи, а короткие DDL берут
блокировку подходами: не досталась за пару секунд — отпускаем очередь и
пробуем снова.

Revision ID: 0095
Revises: 0094
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

revision: str = "0095"
down_revision: Union[str, None] = "0094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "subscription_request_history"
INDEX = "srh_id_request_at_idx"

# Сколько ждать блокировку за подход и сколько подходов делать.
# ~4 минуты суммарно: этого хватает, чтобы попасть в паузу между записями
# синка, и при этом миграция не висит бесконечно молча.
LOCK_TIMEOUT = "3s"
LOCK_ATTEMPTS = 50
PAUSE_BETWEEN = 2


def _retry_ddl(conn, statement: str) -> None:
    """Выполнить DDL, не занимая очередь к таблице на неопределённый срок."""
    for attempt in range(1, LOCK_ATTEMPTS + 1):
        try:
            conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
            conn.execute(text(statement))
            return
        except OperationalError as exc:
            if "lock timeout" not in str(exc).lower() or attempt == LOCK_ATTEMPTS:
                raise
            conn.execute(text(f"SELECT pg_sleep({PAUSE_BETWEEN})"))
        finally:
            conn.execute(text("SET lock_timeout = 0"))


def _drop_invalid_index(conn) -> None:
    """Убрать недостроенный индекс от прерванной попытки.

    CREATE INDEX CONCURRENTLY при обрыве оставляет индекс в состоянии
    invalid: он не используется, но занимает имя и место.
    """
    invalid = conn.execute(
        text(
            "SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE c.relname = :name AND NOT i.indisvalid"
        ),
        {"name": INDEX},
    ).scalar()
    if invalid:
        conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}"))


def upgrade() -> None:
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, TABLE):
        return

    # Вся миграция вне транзакции: CREATE INDEX CONCURRENTLY внутри неё
    # невозможен, а после отбитой блокировки транзакцию пришлось бы ронять
    # целиком вместо повторной попытки.
    with op.get_context().autocommit_block():
        # request_at входит в ключ, поэтому пустым быть не может. Записей без
        # него в таблице нет (синк такие пропускает), но у старых баз колонка
        # могла остаться nullable.
        conn.execute(text(f"DELETE FROM {TABLE} WHERE request_at IS NULL"))

        _drop_invalid_index(conn)
        conn.execute(
            text(f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {INDEX} "
                 f"ON {TABLE} (id, request_at)")
        )

        _retry_ddl(conn, f"ALTER TABLE {TABLE} ALTER COLUMN request_at SET NOT NULL")
        # Обе подкоманды одним ALTER: таблица не остаётся без первичного ключа
        # даже на мгновение, и блокировка берётся один раз, а не дважды
        _retry_ddl(
            conn,
            f"ALTER TABLE {TABLE} "
            f"DROP CONSTRAINT IF EXISTS {TABLE}_pkey, "
            f"ADD PRIMARY KEY USING INDEX {INDEX}",
        )


def downgrade() -> None:
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, TABLE):
        return

    with op.get_context().autocommit_block():
        # Возврат к ключу по одному номеру возможен, только если дублей нет:
        # после работы на составном ключе они появиться могли.
        conn.execute(text(f"""
            DELETE FROM {TABLE} a
            USING {TABLE} b
            WHERE a.id = b.id AND a.request_at < b.request_at
        """))
        _retry_ddl(conn, f"ALTER TABLE {TABLE} DROP CONSTRAINT IF EXISTS {TABLE}_pkey")
        _retry_ddl(conn, f"ALTER TABLE {TABLE} ADD PRIMARY KEY (id)")

"""Журнал аудита: только дописывание.

Revision ID: 0119
Revises: 0118

Записи журнала нельзя изменить или удалить из приложения — триггер отклоняет
UPDATE и DELETE. Исключение одно: очистка по сроку хранения
(`audit_retention_days`), которая помечает свою транзакцию
`SET LOCAL app.audit_cleanup = 'on'`. Восстановление бэкапа пересоздаёт таблицу
целиком (DROP/CREATE) и триггером не задевается.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0119"
down_revision: Union[str, None] = "0118"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION admin_audit_log_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND current_setting('app.audit_cleanup', true) = 'on' THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'admin_audit_log is append-only';
        END
        $$ LANGUAGE plpgsql
    """)
    op.execute("DROP TRIGGER IF EXISTS admin_audit_log_guard ON admin_audit_log")
    op.execute("""
        CREATE TRIGGER admin_audit_log_guard
        BEFORE UPDATE OR DELETE ON admin_audit_log
        FOR EACH ROW EXECUTE FUNCTION admin_audit_log_guard()
    """)
    # Фильтры страницы: по IP и по имени админа (у легаси-админов нет id)
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_ip ON admin_audit_log (ip_address)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_username ON admin_audit_log (admin_username)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_admin_audit_log_username")
    op.execute("DROP INDEX IF EXISTS ix_admin_audit_log_ip")
    op.execute("DROP TRIGGER IF EXISTS admin_audit_log_guard ON admin_audit_log")
    op.execute("DROP FUNCTION IF EXISTS admin_audit_log_guard()")

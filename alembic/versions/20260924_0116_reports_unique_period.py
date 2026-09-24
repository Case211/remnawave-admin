"""Отчёты: один отчёт на тип и период, право reports:delete.

Ручная генерация и повторы планировщика копили дубли: на проде было 53
дневных отчёта на 45 периодов. Оставляем по одному — отправленный, а из
равных самый свежий, — и запрещаем повтор уникальным индексом: сохранение
теперь перезаписывает отчёт за тот же период.

Revision ID: 0116
Revises: 0115
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0116"
down_revision: Union[str, None] = "0115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM violation_reports r
        USING (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY report_type, period_start, period_end
                ORDER BY (sent_at IS NOT NULL) DESC, generated_at DESC, id DESC
            ) AS rn
            FROM violation_reports
        ) d
        WHERE r.id = d.id AND d.rn > 1
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_violation_reports_type_period
        ON violation_reports (report_type, period_start, period_end)
    """)
    # Удалять отчёты может тот, кто может их создавать
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT role_id, 'reports', 'delete'
        FROM admin_permissions
        WHERE resource = 'reports' AND action = 'create'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM admin_permissions WHERE resource = 'reports' AND action = 'delete'")
    op.execute("DROP INDEX IF EXISTS uq_violation_reports_type_period")

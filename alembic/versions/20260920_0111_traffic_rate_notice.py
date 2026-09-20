"""Шаблон предупреждения для анализатора расхода трафика.

Revision ID: 0111
Revises: 0110
Create Date: 2026-09-20

Анализатор `traffic_rate` в системе есть, а шаблона под него не было — такие
нарушения попадали под общий текст про раздачу подписки, хотя речь о другом:
человек не раздал доступ, а выкачивает непомерный объём.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0111"
down_revision: Union[str, None] = "0110"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BODY = (
    "Здравствуйте! На вашей подписке зафиксирован необычно большой расход трафика.\n\n"
    "Проверьте, не работает ли через подключение что-то в фоне — раздача, синхронизация "
    "или загрузки. Если расход не снизится, скорость придётся ограничить.\n\n"
    "Если это ошибка, ответьте на это сообщение, разберёмся."
)


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO violation_notice_templates (kind, min_score, subject_ru, body_ru)
        VALUES ('traffic_rate', 70, 'Расход трафика', '{body}')
        ON CONFLICT (kind) DO NOTHING
        """.format(body=_BODY.replace("'", "''"))
    )


def downgrade() -> None:
    op.execute("DELETE FROM violation_notice_templates WHERE kind = 'traffic_rate'")

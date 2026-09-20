"""Шаблоны предупреждений клиенту о нарушении.

Revision ID: 0110
Revises: 0109
Create Date: 2026-09-20

Текст предупреждения зависит от того, что именно сработало: человеку, который
раздал подписку друзьям, и человеку, качающему торренты, надо сказать разное.
Поэтому шаблон свой на каждый вид нарушения, со своим порогом скора и
собственным выключателем — оператор решает, о чём вообще предупреждать.

Важное в текстах по умолчанию: клиенту не говорят, ЧТО именно увидел детектор
(страны, число устройств, скор). Это инструкция по обходу — человек просто
разнесёт подключения. Наружу идёт факт и последствие, подробности остаются
в панели.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0110"
down_revision: Union[str, None] = "0109"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SHARING = (
    "Здравствуйте! Мы заметили, что ваша подписка используется с нескольких устройств "
    "одновременно способом, который тарифом не предусмотрен.\n\n"
    "Подписка личная: передавать доступ другим людям нельзя. Пожалуйста, отключите "
    "лишние устройства — при повторении мы вынуждены будем ограничить доступ.\n\n"
    "Если это ошибка, ответьте на это сообщение, разберёмся."
)

_DEFAULTS = [
    ("default", 60.0, "Использование подписки", _SHARING),
    ("temporal", 60.0, "Использование подписки", _SHARING),
    ("geo", 60.0, "Использование подписки", _SHARING),
    ("asn", 65.0, "Использование подписки", _SHARING),
    ("profile", 65.0, "Использование подписки", _SHARING),
    ("device", 55.0, "Устройства на подписке", _SHARING),
    ("hwid", 55.0, "Устройства на подписке", _SHARING),
    ("user_agent", 70.0, "Использование подписки", _SHARING),
    (
        "torrent",
        0.0,
        "Торренты на подписке",
        "Здравствуйте! На вашей подписке зафиксирована торрент-активность — правилами "
        "сервиса она запрещена.\n\nПожалуйста, отключите торрент-клиенты. При повторении "
        "доступ будет ограничен.\n\nЕсли это ошибка, ответьте на это сообщение.",
    ),
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS violation_notice_templates (
            id           SERIAL PRIMARY KEY,
            kind         VARCHAR(40) NOT NULL UNIQUE,
            enabled      BOOLEAN NOT NULL DEFAULT true,
            min_score    DOUBLE PRECISION NOT NULL DEFAULT 0,
            send_email   BOOLEAN NOT NULL DEFAULT true,
            subject_ru   VARCHAR(200) NOT NULL DEFAULT '',
            body_ru      TEXT NOT NULL DEFAULT '',
            subject_en   VARCHAR(200),
            body_en      TEXT,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by   VARCHAR(255)
        )
        """
    )

    for kind, min_score, subject, body in _DEFAULTS:
        op.execute(
            """
            INSERT INTO violation_notice_templates (kind, min_score, subject_ru, body_ru)
            VALUES (:kind, :min_score, :subject, :body)
            ON CONFLICT (kind) DO NOTHING
            """.replace(":kind", f"'{kind}'")
            .replace(":min_score", str(min_score))
            .replace(":subject", "'" + subject.replace("'", "''") + "'")
            .replace(":body", "'" + body.replace("'", "''") + "'")
        )

    # Кому и когда уже писали: второй раз об одном и том же обращении человека
    # дёргать незачем, а оператору важно видеть, что предупреждение ушло.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS violation_notices (
            id            BIGSERIAL PRIMARY KEY,
            violation_id  BIGINT NOT NULL REFERENCES violations(id) ON DELETE CASCADE,
            user_uuid     UUID NOT NULL,
            telegram_id   BIGINT,
            kind          VARCHAR(40) NOT NULL,
            channels      TEXT[] NOT NULL DEFAULT '{}',
            sent_by       VARCHAR(255),
            sent_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (violation_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_violation_notices_user ON violation_notices (user_uuid, sent_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS violation_notices")
    op.execute("DROP TABLE IF EXISTS violation_notice_templates")

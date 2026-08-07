"""Почтовый сервер: вложения, подавленные адреса, DMARC-отчёты, аутентификация писем.

Revision ID: 0098
Revises: 0097
Create Date: 2026-08-07

До этой ревизии приёмник считал вложения и выбрасывал их, а результаты
проверок отправителя не сохранял вовсе — колонки is_spam/spam_score стояли
в таблице с самого начала и всегда оставались пустыми. Здесь появляется
место, куда всё это класть.

Три новые таблицы решают три разные задачи:

* email_attachments — файлы писем. Одна таблица на входящие и исходящие:
  у строки заполнена ровно одна ссылка, что и стережёт CHECK. Содержимое
  лежит в BYTEA, а не на диске, чтобы вложения уезжали вместе с дампом БД
  и не требовали отдельного тома.
* email_suppression — адреса, которым больше не пишем. Без неё очередь
  годами долбится в удалённый ящик: письмо уходит, приходит отказ, отказ
  никто не читает, следующее уведомление уходит снова.
* dmarc_reports — сводки от почтовых систем о том, кто слал письма от имени
  наших доменов. Приходят вложением раз в сутки; уникальность по паре
  (домен, идентификатор отчёта) не даёт посчитать один отчёт дважды, если
  обработчик перезапустится на середине.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0098"
down_revision: Union[str, None] = "0097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Вложения ──────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_attachments (
            id BIGSERIAL PRIMARY KEY,
            inbox_id BIGINT REFERENCES email_inbox(id) ON DELETE CASCADE,
            queue_id BIGINT REFERENCES email_queue(id) ON DELETE CASCADE,
            filename VARCHAR(512) NOT NULL,
            content_type VARCHAR(255) NOT NULL DEFAULT 'application/octet-stream',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            content BYTEA NOT NULL,
            content_id VARCHAR(255),
            is_inline BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT email_attachments_one_owner
                CHECK ((inbox_id IS NULL) <> (queue_id IS NULL))
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_email_attachments_inbox
        ON email_attachments(inbox_id) WHERE inbox_id IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_email_attachments_queue
        ON email_attachments(queue_id) WHERE queue_id IS NOT NULL
    """)

    # ── Подавленные адреса ────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_suppression (
            id BIGSERIAL PRIMARY KEY,
            email VARCHAR(320) NOT NULL,
            reason VARCHAR(32) NOT NULL,
            detail TEXT,
            smtp_code VARCHAR(16),
            source_inbox_id BIGINT REFERENCES email_inbox(id) ON DELETE SET NULL,
            hits INTEGER NOT NULL DEFAULT 1,
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    # Регистр в адресе роли не играет: почтовые системы давно сравнивают
    # адреса без учёта регистра, и Ivan@ с ivan@ — один и тот же ящик.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_email_suppression_email
        ON email_suppression(lower(email))
    """)
    # Мягкие отказы живут до expires_at; выборка «кого уже можно снова
    # пробовать» ходит именно по этой колонке.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_email_suppression_expires
        ON email_suppression(expires_at) WHERE expires_at IS NOT NULL
    """)

    # ── DMARC-отчёты ──────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS dmarc_reports (
            id BIGSERIAL PRIMARY KEY,
            report_id VARCHAR(255) NOT NULL,
            org_name VARCHAR(255),
            org_email VARCHAR(320),
            domain VARCHAR(255) NOT NULL,
            date_begin TIMESTAMPTZ NOT NULL,
            date_end TIMESTAMPTZ NOT NULL,
            policy JSONB NOT NULL DEFAULT '{}'::jsonb,
            records JSONB NOT NULL DEFAULT '[]'::jsonb,
            total_messages INTEGER NOT NULL DEFAULT 0,
            passed_messages INTEGER NOT NULL DEFAULT 0,
            failed_messages INTEGER NOT NULL DEFAULT 0,
            source_inbox_id BIGINT REFERENCES email_inbox(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_dmarc_reports_ident
        ON dmarc_reports(domain, report_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_dmarc_reports_period
        ON dmarc_reports(date_begin DESC)
    """)

    # ── Результаты проверки отправителя ───────────────────────────
    op.execute("""
        ALTER TABLE email_inbox
            ADD COLUMN IF NOT EXISTS spf_result VARCHAR(16),
            ADD COLUMN IF NOT EXISTS dkim_result VARCHAR(16),
            ADD COLUMN IF NOT EXISTS dmarc_result VARCHAR(16),
            ADD COLUMN IF NOT EXISTS auth_details JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS refs_header TEXT,
            ADD COLUMN IF NOT EXISTS is_processed BOOLEAN NOT NULL DEFAULT false
    """)
    # Разборщики служебной почты (отказы, отписки, DMARC) выгребают только
    # необработанное, и таких строк всегда единицы против всего архива.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_email_inbox_unprocessed
        ON email_inbox(id) WHERE is_processed = false
    """)

    # ── Отказы в очереди ──────────────────────────────────────────
    op.execute("""
        ALTER TABLE email_queue
            ADD COLUMN IF NOT EXISTS bounced_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS bounce_type VARCHAR(16)
    """)
    # Отказ ссылается на исходное письмо через Message-ID — без индекса
    # каждый разбор означал бы полный проход по всей истории отправки.
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_email_queue_message_id
        ON email_queue(message_id) WHERE message_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dmarc_reports")
    op.execute("DROP TABLE IF EXISTS email_suppression")
    op.execute("DROP TABLE IF EXISTS email_attachments")
    op.execute("DROP INDEX IF EXISTS ix_email_queue_message_id")
    op.execute("""
        ALTER TABLE email_queue
            DROP COLUMN IF EXISTS bounced_at,
            DROP COLUMN IF EXISTS bounce_type
    """)
    op.execute("DROP INDEX IF EXISTS ix_email_inbox_unprocessed")
    op.execute("""
        ALTER TABLE email_inbox
            DROP COLUMN IF EXISTS spf_result,
            DROP COLUMN IF EXISTS dkim_result,
            DROP COLUMN IF EXISTS dmarc_result,
            DROP COLUMN IF EXISTS auth_details,
            DROP COLUMN IF EXISTS refs_header,
            DROP COLUMN IF EXISTS is_processed
    """)

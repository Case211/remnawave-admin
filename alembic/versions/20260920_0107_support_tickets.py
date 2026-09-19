"""Поддержка: проекция тикетов бота и своя обвязка вокруг неё.

Revision ID: 0107
Revises: 0106
Create Date: 2026-09-20

Web API бота умеет отдавать список тикетов и переписку, отвечать и менять
статус — но фильтрует только по статусу, приоритету и юзеру. Ни поиска по
тексту, ни счётчиков очередей, ни сортировки по времени ожидания, ни SLA там
нет, поэтому лента зеркалится к нам (`support_tickets`, `support_ticket_messages`):
по ней строятся очереди оператора и поиск.

Остальные таблицы — то, чего в модели бота нет вообще: кто взял тикет, что уже
прочитано, что отложено, теги, шаблоны ответов и заметка о клиенте.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0107"
down_revision: Union[str, None] = "0106"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_tickets (
            id                  BIGINT PRIMARY KEY,
            bot_user_id         BIGINT NOT NULL,
            telegram_id         BIGINT,
            customer_name       TEXT,
            title               TEXT NOT NULL DEFAULT '',
            status              VARCHAR(20) NOT NULL DEFAULT 'open',
            priority            VARCHAR(20) NOT NULL DEFAULT 'normal',
            user_reply_blocked  BOOLEAN NOT NULL DEFAULT false,
            messages_count      INTEGER NOT NULL DEFAULT 0,
            last_message_at     TIMESTAMPTZ,
            last_message_from   VARCHAR(10),
            last_message_text   TEXT,
            first_response_at   TIMESTAMPTZ,
            waiting_since       TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL,
            updated_at          TIMESTAMPTZ NOT NULL,
            closed_at           TIMESTAMPTZ,
            synced_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            search_text         TEXT NOT NULL DEFAULT ''
        )
        """
    )
    # Очередь «ждут нас» сортируется по waiting_since, поэтому индекс частичный:
    # закрытые тикеты в ней не участвуют и место в индексе не занимают.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_waiting "
        "ON support_tickets (waiting_since) WHERE status <> 'closed'"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_support_tickets_user ON support_tickets (bot_user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_support_tickets_updated ON support_tickets (updated_at DESC)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_support_tickets_search "
        "ON support_tickets USING gin (to_tsvector('simple', search_text))"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_ticket_messages (
            id            BIGINT PRIMARY KEY,
            ticket_id     BIGINT NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
            is_from_admin BOOLEAN NOT NULL DEFAULT false,
            author_name   TEXT,
            text          TEXT NOT NULL DEFAULT '',
            has_media     BOOLEAN NOT NULL DEFAULT false,
            media_type    VARCHAR(20),
            created_at    TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_support_messages_ticket "
        "ON support_ticket_messages (ticket_id, created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_assignments (
            ticket_id  BIGINT PRIMARY KEY REFERENCES support_tickets(id) ON DELETE CASCADE,
            admin_id   INTEGER NOT NULL,
            claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_support_assignments_admin ON support_assignments (admin_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_reads (
            ticket_id            BIGINT NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
            admin_id             INTEGER NOT NULL,
            last_read_message_id BIGINT NOT NULL DEFAULT 0,
            read_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (ticket_id, admin_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_snoozes (
            ticket_id  BIGINT PRIMARY KEY REFERENCES support_tickets(id) ON DELETE CASCADE,
            snooze_to  TIMESTAMPTZ NOT NULL,
            admin_id   INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_tags (
            id    SERIAL PRIMARY KEY,
            name  VARCHAR(64) NOT NULL UNIQUE,
            color VARCHAR(16) NOT NULL DEFAULT 'slate'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_ticket_tags (
            ticket_id BIGINT NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
            tag_id    INTEGER NOT NULL REFERENCES support_tags(id) ON DELETE CASCADE,
            PRIMARY KEY (ticket_id, tag_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_macros (
            id          SERIAL PRIMARY KEY,
            title       VARCHAR(120) NOT NULL,
            body        TEXT NOT NULL,
            shortcut    VARCHAR(32),
            set_status  VARCHAR(20),
            add_tag_id  INTEGER REFERENCES support_tags(id) ON DELETE SET NULL,
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_by  INTEGER,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_customer_notes (
            bot_user_id BIGINT PRIMARY KEY,
            note        TEXT NOT NULL DEFAULT '',
            updated_by  INTEGER,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    for table in (
        "support_customer_notes",
        "support_macros",
        "support_ticket_tags",
        "support_tags",
        "support_snoozes",
        "support_reads",
        "support_assignments",
        "support_ticket_messages",
        "support_tickets",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")

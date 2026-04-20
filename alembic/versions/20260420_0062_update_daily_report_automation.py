"""Update daily_report automation rule: midnight UTC cron + richer message.

Revision ID: 0062
Revises: 0061
Create Date: 2026-04-20

Switch the default Daily Report rule to fire at 00:00 UTC for full-day stats
(traffic, new/expired users, top nodes, violations) instead of the
truncated 23:00 snapshot that relied on Panel's broken bandwidth-stats API.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0062"
down_revision: Union[str, None] = "0061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_MESSAGE = (
    "📊 <b>Дневной отчёт за {report_date}</b>\n"
    "\n"
    "👥 Пользователи: <b>{users_total}</b> всего"
    " (+{users_new_yesterday} новых, {users_expired_yesterday} истекло)\n"
    "🟢 Онлайн сейчас: <b>{users_online}</b>\n"
    "🖥 Ноды: <b>{nodes_online}/{nodes_total}</b> онлайн\n"
    "📡 Трафик: <b>{traffic_yesterday}</b>\n"
    "\n"
    "🏆 Топ нод по трафику:\n"
    "{top_nodes_yesterday}\n"
    "\n"
    "⚠️ Нарушений: <b>{violations_yesterday}</b>"
)

OLD_MESSAGE = (
    "Daily report: {users_total} users, {traffic_today} traffic today, "
    "{violations_today} violations"
)


def _update(cron: str, message: str, description: str) -> None:
    op.get_bind().execute(
        text(
            """
            UPDATE automation_rules
            SET trigger_config = (:cron)::jsonb,
                action_config = jsonb_set(
                    COALESCE(action_config, '{}'::jsonb),
                    '{message}',
                    to_jsonb(:message::text)
                ),
                description = :description,
                updated_at = NOW()
            WHERE name = 'Daily Report'
              AND trigger_type = 'schedule'
              AND action_type = 'notify'
            """
        ),
        {
            "cron": f'{{"cron": "{cron}"}}',
            "message": message,
            "description": description,
        },
    )


def upgrade() -> None:
    _update(
        cron="0 0 * * *",
        message=NEW_MESSAGE,
        description="Ежедневная Telegram-сводка в 00:00 UTC за прошедшие сутки",
    )


def downgrade() -> None:
    _update(
        cron="0 23 * * *",
        message=OLD_MESSAGE,
        description="Ежедневная Telegram-сводка в 23:00",
    )

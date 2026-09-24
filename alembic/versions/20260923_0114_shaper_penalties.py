"""Штрафы шейпера: кого, где и когда урезали за объём.

Revision ID: 0114
Revises: 0113
Create Date: 2026-09-23

Программа на ноде записывает, кого оштрафовала, агент раз в минуту отдаёт
события панели. Здесь они лежат с юзерами, найденными по адресу и времени
в подключениях: из этого собираются уведомление админу, история в окне
шейпера и кулдаун уведомлений.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0114"
down_revision: Union[str, None] = "0113"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS node_shaper_penalties (
            id BIGSERIAL PRIMARY KEY,
            node_uuid UUID NOT NULL,
            ip VARCHAR(45) NOT NULL,
            started_at TIMESTAMPTZ NOT NULL,
            until TIMESTAMPTZ,
            bytes BIGINT NOT NULL DEFAULT 0,
            user_uuids JSONB NOT NULL DEFAULT '[]'::jsonb,
            notified BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_shaper_penalties_node "
        "ON node_shaper_penalties (node_uuid, started_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_shaper_penalties_created "
        "ON node_shaper_penalties (created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS node_shaper_penalties")

"""Шейпер клиентов ноды: настройки и последнее состояние от агента.

Revision ID: 0113
Revises: 0112
Create Date: 2026-09-23

Потолок скорости на каждого клиента и режим штрафа для тех, кто за окно
прокачал больше порога. Настраивается отдельно для каждой ноды: каналы и
аудитория у нод разные.

``status`` — что агент ответил на последнюю команду: включён ли шейпер на
самом деле и что стало с корнем интерфейса. Панель показывает это как есть,
а не то, что хотела поставить.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0113"
down_revision: Union[str, None] = "0112"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS node_shapers (
            node_uuid UUID PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            ports JSONB NOT NULL DEFAULT '[]'::jsonb,
            down_kbit INTEGER NOT NULL DEFAULT 0,
            up_kbit INTEGER NOT NULL DEFAULT 0,
            penalty_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            penalty_mb INTEGER NOT NULL DEFAULT 0,
            penalty_window_sec INTEGER NOT NULL DEFAULT 0,
            penalty_kbit INTEGER NOT NULL DEFAULT 0,
            penalty_minutes INTEGER NOT NULL DEFAULT 0,
            status JSONB,
            status_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by VARCHAR(255)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS node_shapers")

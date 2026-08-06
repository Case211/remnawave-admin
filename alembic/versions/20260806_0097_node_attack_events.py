"""История атак на канал ноды.

Revision ID: 0097
Revises: 0096
Create Date: 2026-08-06

Детектор ставит вердикт по сетевым метрикам агента (0096) и держит здесь
состояние: пока атака идёт, у ноды одно открытое событие с ended_at IS NULL.
Частичный уникальный индекс не даёт развести дубли, если детектор крутится
в нескольких воркерах сразу.

История нужна не только для отчёта: на ней строится коллективная часть радара
— волна атак на одном хостере видна, только когда есть с чем сравнивать.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0097"
down_revision: Union[str, None] = "0096"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS node_attack_events (
            id BIGSERIAL PRIMARY KEY,
            node_uuid UUID NOT NULL REFERENCES nodes(uuid) ON DELETE CASCADE,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ended_at TIMESTAMPTZ,
            severity TEXT NOT NULL DEFAULT 'warning',
            reasons TEXT NOT NULL DEFAULT '',
            peak_rx_bps BIGINT,
            peak_rx_pps BIGINT,
            baseline_rx_bps BIGINT,
            baseline_rx_pps BIGINT
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_nae_active_per_node
        ON node_attack_events(node_uuid) WHERE ended_at IS NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_nae_started
        ON node_attack_events(started_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS node_attack_events")

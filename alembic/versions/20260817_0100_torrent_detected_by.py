"""Торрент-события: чем именно поймали.

Revision ID: 0100
Revises: 0099
Create Date: 2026-08-17

До сих пор источник детекта был один — тег роутинга Xray. Он ставится
только на открытое рукопожатие BitTorrent, а современные клиенты по
умолчанию шифруют поток (MSE/PE) и живут в DHT и uTP поверх UDP, так что
до рукопожатия дело обычно не доходит. Ловился в основном тот, кто качает
старым клиентом с выключенным шифрованием.

Теперь у агента появился второй источник — вердикты nDPI, которому
шифрование потока не мешает. Признаки разной твёрдости, и смешивать их в
одну кучу нельзя: разбирая жалобу «за что заблокировали», нужно видеть,
поймали человека на сигнатуре или на поведении трафика.

Существующие записи получают 'xray_routing': другого источника у них и не
было.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0100"
down_revision: Union[str, None] = "0099"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE torrent_events
            ADD COLUMN IF NOT EXISTS detected_by VARCHAR(32)
            NOT NULL DEFAULT 'xray_routing'
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE torrent_events DROP COLUMN IF EXISTS detected_by")

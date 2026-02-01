"""Add user_hwid_devices table for storing HWID devices.

Revision ID: 0008
Revises: 0007
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Таблица для хранения HWID устройств пользователей
    op.create_table(
        'user_hwid_devices',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True, primary_key=True),
        sa.Column('user_uuid', sa.UUID(), nullable=False, comment='UUID пользователя'),
        sa.Column('hwid', sa.String(255), nullable=False, comment='HWID устройства'),

        # Информация об устройстве
        sa.Column('platform', sa.String(50), nullable=True, comment='Платформа (android, ios, windows, macos, linux)'),
        sa.Column('os_version', sa.String(100), nullable=True, comment='Версия ОС'),
        sa.Column('app_version', sa.String(50), nullable=True, comment='Версия приложения'),

        # Метаданные
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()'), comment='Время добавления устройства'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()'), comment='Время последнего обновления'),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()'), comment='Время последней синхронизации'),

        comment='HWID устройства пользователей'
    )

    # Уникальный индекс на комбинацию user_uuid + hwid
    op.create_index(
        'idx_hwid_devices_user_hwid',
        'user_hwid_devices',
        ['user_uuid', 'hwid'],
        unique=True
    )

    # Индекс для быстрого поиска устройств пользователя
    op.create_index('idx_hwid_devices_user_uuid', 'user_hwid_devices', ['user_uuid'])

    # Индекс для поиска по платформе (для статистики)
    op.create_index('idx_hwid_devices_platform', 'user_hwid_devices', ['platform'])


def downgrade() -> None:
    op.drop_index('idx_hwid_devices_platform', table_name='user_hwid_devices')
    op.drop_index('idx_hwid_devices_user_uuid', table_name='user_hwid_devices')
    op.drop_index('idx_hwid_devices_user_hwid', table_name='user_hwid_devices')
    op.drop_table('user_hwid_devices')

"""Add asn_russia table for storing Russian ASN database.

Revision ID: 0005
Revises: 0004
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Таблица для хранения базы ASN по РФ
    op.create_table(
        'asn_russia',
        sa.Column('asn', sa.Integer(), nullable=False, primary_key=True, comment='ASN номер'),
        sa.Column('org_name', sa.String(500), nullable=False, comment='Название организации'),
        sa.Column('org_name_en', sa.String(500), nullable=True, comment='Название организации (английский)'),
        sa.Column('provider_type', sa.String(20), nullable=True, comment='Тип провайдера: mobile/residential/datacenter/vpn/isp'),
        sa.Column('region', sa.String(100), nullable=True, comment='Регион РФ'),
        sa.Column('city', sa.String(100), nullable=True, comment='Город'),
        sa.Column('country_code', sa.String(2), nullable=False, server_default='RU', comment='Код страны'),
        sa.Column('description', sa.Text(), nullable=True, comment='Описание ASN'),
        sa.Column('ip_ranges', sa.Text(), nullable=True, comment='IP диапазоны (JSON массив)'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true', comment='Активен ли ASN'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()'), comment='Дата создания записи'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()'), comment='Дата последнего обновления'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True, comment='Дата последней синхронизации с RIPE'),
        comment='База данных ASN по РФ для точного определения местоположения и типа провайдера'
    )
    
    # Индексы для быстрого поиска
    op.create_index('idx_asn_russia_org_name', 'asn_russia', ['org_name'])
    op.create_index('idx_asn_russia_provider_type', 'asn_russia', ['provider_type'])
    op.create_index('idx_asn_russia_region', 'asn_russia', ['region'])
    op.create_index('idx_asn_russia_city', 'asn_russia', ['city'])
    op.create_index('idx_asn_russia_is_active', 'asn_russia', ['is_active'])


def downgrade() -> None:
    op.drop_index('idx_asn_russia_is_active', table_name='asn_russia')
    op.drop_index('idx_asn_russia_city', table_name='asn_russia')
    op.drop_index('idx_asn_russia_region', table_name='asn_russia')
    op.drop_index('idx_asn_russia_provider_type', table_name='asn_russia')
    op.drop_index('idx_asn_russia_org_name', table_name='asn_russia')
    op.drop_table('asn_russia')

"""Add ip_metadata table for caching GeoIP data.

Revision ID: 0004
Revises: 0003
Create Date: 2026-01-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Таблица для кэширования метаданных IP адресов
    op.create_table(
        'ip_metadata',
        sa.Column('ip_address', sa.String(45), nullable=False, primary_key=True, comment='IP адрес'),
        sa.Column('country_code', sa.String(2), nullable=True, comment='Код страны (ISO 3166-1 alpha-2)'),
        sa.Column('country_name', sa.String(100), nullable=True, comment='Название страны'),
        sa.Column('region', sa.String(100), nullable=True, comment='Регион/область'),
        sa.Column('city', sa.String(100), nullable=True, comment='Город'),
        sa.Column('latitude', sa.Numeric(9, 6), nullable=True, comment='Широта'),
        sa.Column('longitude', sa.Numeric(9, 6), nullable=True, comment='Долгота'),
        sa.Column('timezone', sa.String(50), nullable=True, comment='Часовой пояс'),
        sa.Column('asn', sa.Integer(), nullable=True, comment='ASN номер'),
        sa.Column('asn_org', sa.String(200), nullable=True, comment='ASN организация'),
        sa.Column('connection_type', sa.String(20), nullable=True, comment='Тип подключения: mobile/residential/datacenter/vpn'),
        sa.Column('is_proxy', sa.Boolean(), nullable=False, server_default='false', comment='Является ли прокси'),
        sa.Column('is_vpn', sa.Boolean(), nullable=False, server_default='false', comment='Является ли VPN'),
        sa.Column('is_tor', sa.Boolean(), nullable=False, server_default='false', comment='Является ли Tor'),
        sa.Column('is_hosting', sa.Boolean(), nullable=False, server_default='false', comment='Является ли хостингом'),
        sa.Column('is_mobile', sa.Boolean(), nullable=False, server_default='false', comment='Является ли мобильным оператором'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()'), comment='Дата создания записи'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()'), comment='Дата последнего обновления'),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True, comment='Дата последней проверки через API'),
        comment='Кэш метаданных IP адресов для GeoIP'
    )
    
    # Индексы для быстрого поиска
    op.create_index('idx_ip_metadata_country', 'ip_metadata', ['country_code'])
    op.create_index('idx_ip_metadata_city', 'ip_metadata', ['city'])
    op.create_index('idx_ip_metadata_asn', 'ip_metadata', ['asn'])
    op.create_index('idx_ip_metadata_connection_type', 'ip_metadata', ['connection_type'])
    op.create_index('idx_ip_metadata_updated_at', 'ip_metadata', ['updated_at'])


def downgrade() -> None:
    op.drop_index('idx_ip_metadata_updated_at', table_name='ip_metadata')
    op.drop_index('idx_ip_metadata_connection_type', table_name='ip_metadata')
    op.drop_index('idx_ip_metadata_asn', table_name='ip_metadata')
    op.drop_index('idx_ip_metadata_city', table_name='ip_metadata')
    op.drop_index('idx_ip_metadata_country', table_name='ip_metadata')
    op.drop_table('ip_metadata')

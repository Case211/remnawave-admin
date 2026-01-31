"""Add bot_config table for dynamic configuration storage.

Revision ID: 0006
Revises: 0005
Create Date: 2026-01-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Таблица для хранения динамической конфигурации бота
    op.create_table(
        'bot_config',
        sa.Column('key', sa.String(100), nullable=False, primary_key=True, comment='Уникальный ключ настройки'),
        sa.Column('value', sa.Text(), nullable=True, comment='Значение настройки'),
        sa.Column('value_type', sa.String(20), nullable=False, server_default='string', comment='Тип значения: string/int/float/bool/json'),
        sa.Column('category', sa.String(50), nullable=False, server_default='general', comment='Категория настройки'),
        sa.Column('subcategory', sa.String(50), nullable=True, comment='Подкатегория настройки'),
        sa.Column('display_name', sa.String(200), nullable=True, comment='Отображаемое имя настройки'),
        sa.Column('description', sa.Text(), nullable=True, comment='Описание настройки'),
        sa.Column('default_value', sa.Text(), nullable=True, comment='Значение по умолчанию'),
        sa.Column('env_var_name', sa.String(100), nullable=True, comment='Связанная переменная окружения'),
        sa.Column('is_secret', sa.Boolean(), nullable=False, server_default='false', comment='Скрывать значение в интерфейсе'),
        sa.Column('is_readonly', sa.Boolean(), nullable=False, server_default='false', comment='Только для чтения (из .env)'),
        sa.Column('validation_regex', sa.String(500), nullable=True, comment='Regex для валидации значения'),
        sa.Column('options_json', sa.Text(), nullable=True, comment='Допустимые значения (JSON массив)'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0', comment='Порядок сортировки'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()'), comment='Дата создания'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()'), comment='Дата обновления'),
        comment='Динамическая конфигурация бота (дополнение к .env)'
    )

    # Индексы для быстрого поиска
    op.create_index('idx_bot_config_category', 'bot_config', ['category'])
    op.create_index('idx_bot_config_subcategory', 'bot_config', ['subcategory'])
    op.create_index('idx_bot_config_env_var_name', 'bot_config', ['env_var_name'])
    op.create_index('idx_bot_config_sort_order', 'bot_config', ['category', 'sort_order'])


def downgrade() -> None:
    op.drop_index('idx_bot_config_sort_order', table_name='bot_config')
    op.drop_index('idx_bot_config_env_var_name', table_name='bot_config')
    op.drop_index('idx_bot_config_subcategory', table_name='bot_config')
    op.drop_index('idx_bot_config_category', table_name='bot_config')
    op.drop_table('bot_config')

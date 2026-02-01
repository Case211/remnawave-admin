"""Add violations table for storing violation history and reports.

Revision ID: 0007
Revises: 0006
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Таблица для хранения истории нарушений
    op.create_table(
        'violations',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True, primary_key=True),
        sa.Column('user_uuid', sa.UUID(), nullable=False, comment='UUID пользователя'),
        sa.Column('username', sa.String(255), nullable=True, comment='Имя пользователя (для быстрого поиска)'),
        sa.Column('email', sa.String(255), nullable=True, comment='Email пользователя'),
        sa.Column('telegram_id', sa.BigInteger(), nullable=True, comment='Telegram ID пользователя'),

        # Скор и действие
        sa.Column('score', sa.Float(), nullable=False, comment='Итоговый скор нарушения (0-100)'),
        sa.Column('recommended_action', sa.String(50), nullable=False, comment='Рекомендуемое действие'),
        sa.Column('confidence', sa.Float(), nullable=True, comment='Уверенность детектора (0-1)'),

        # Компоненты скора
        sa.Column('temporal_score', sa.Float(), nullable=True, comment='Скор временного анализа'),
        sa.Column('geo_score', sa.Float(), nullable=True, comment='Скор географического анализа'),
        sa.Column('asn_score', sa.Float(), nullable=True, comment='Скор ASN анализа'),
        sa.Column('profile_score', sa.Float(), nullable=True, comment='Скор профиля пользователя'),
        sa.Column('device_score', sa.Float(), nullable=True, comment='Скор анализа устройств'),

        # Детали нарушения
        sa.Column('ip_addresses', sa.ARRAY(sa.String()), nullable=True, comment='IP адреса в момент нарушения'),
        sa.Column('countries', sa.ARRAY(sa.String()), nullable=True, comment='Страны подключений'),
        sa.Column('cities', sa.ARRAY(sa.String()), nullable=True, comment='Города подключений'),
        sa.Column('asn_types', sa.ARRAY(sa.String()), nullable=True, comment='Типы провайдеров'),
        sa.Column('os_list', sa.ARRAY(sa.String()), nullable=True, comment='Операционные системы'),
        sa.Column('client_list', sa.ARRAY(sa.String()), nullable=True, comment='Клиентские приложения'),
        sa.Column('reasons', sa.ARRAY(sa.Text()), nullable=True, comment='Причины нарушения'),

        # Количественные показатели
        sa.Column('simultaneous_connections', sa.Integer(), nullable=True, comment='Количество одновременных подключений'),
        sa.Column('unique_ips_count', sa.Integer(), nullable=True, comment='Количество уникальных IP'),
        sa.Column('device_limit', sa.Integer(), nullable=True, comment='Лимит устройств пользователя'),

        # Флаги
        sa.Column('impossible_travel', sa.Boolean(), nullable=False, server_default='false', comment='Обнаружено невозможное перемещение'),
        sa.Column('is_mobile', sa.Boolean(), nullable=False, server_default='false', comment='Мобильный провайдер'),
        sa.Column('is_datacenter', sa.Boolean(), nullable=False, server_default='false', comment='Подключение через датацентр'),
        sa.Column('is_vpn', sa.Boolean(), nullable=False, server_default='false', comment='Подключение через VPN'),

        # Действия
        sa.Column('action_taken', sa.String(50), nullable=True, comment='Принятое действие'),
        sa.Column('action_taken_at', sa.DateTime(timezone=True), nullable=True, comment='Время принятия действия'),
        sa.Column('action_taken_by', sa.BigInteger(), nullable=True, comment='Telegram ID администратора'),

        # Метаданные
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()'), comment='Время обнаружения'),
        sa.Column('notified_at', sa.DateTime(timezone=True), nullable=True, comment='Время отправки уведомления'),
        sa.Column('raw_breakdown', sa.Text(), nullable=True, comment='JSON с полным breakdown'),

        comment='История нарушений пользователей'
    )

    # Индексы для быстрого поиска и агрегации
    op.create_index('idx_violations_user_uuid', 'violations', ['user_uuid'])
    op.create_index('idx_violations_detected_at', 'violations', ['detected_at'])
    op.create_index('idx_violations_score', 'violations', ['score'])
    op.create_index('idx_violations_action', 'violations', ['recommended_action'])
    op.create_index('idx_violations_user_date', 'violations', ['user_uuid', 'detected_at'])

    # Составной индекс для отчётов
    op.create_index(
        'idx_violations_reports',
        'violations',
        ['detected_at', 'score', 'recommended_action']
    )

    # Таблица для хранения сгенерированных отчётов
    op.create_table(
        'violation_reports',
        sa.Column('id', sa.BigInteger(), nullable=False, autoincrement=True, primary_key=True),
        sa.Column('report_type', sa.String(20), nullable=False, comment='Тип отчёта: daily/weekly/monthly'),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False, comment='Начало периода'),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False, comment='Конец периода'),

        # Статистика
        sa.Column('total_violations', sa.Integer(), nullable=False, default=0, comment='Всего нарушений'),
        sa.Column('critical_count', sa.Integer(), nullable=False, default=0, comment='Критичных (score >= 80)'),
        sa.Column('warning_count', sa.Integer(), nullable=False, default=0, comment='Предупреждений (score 50-79)'),
        sa.Column('monitor_count', sa.Integer(), nullable=False, default=0, comment='Мониторинг (score 30-49)'),
        sa.Column('unique_users', sa.Integer(), nullable=False, default=0, comment='Уникальных пользователей'),

        # Сравнение с предыдущим периодом
        sa.Column('prev_total_violations', sa.Integer(), nullable=True, comment='Нарушений в прошлом периоде'),
        sa.Column('trend_percent', sa.Float(), nullable=True, comment='Изменение в %'),

        # Топ нарушителей (JSON)
        sa.Column('top_violators', sa.Text(), nullable=True, comment='JSON с топ нарушителями'),

        # Распределение
        sa.Column('by_country', sa.Text(), nullable=True, comment='JSON распределение по странам'),
        sa.Column('by_action', sa.Text(), nullable=True, comment='JSON распределение по действиям'),
        sa.Column('by_asn_type', sa.Text(), nullable=True, comment='JSON распределение по типам провайдеров'),

        # Метаданные
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()'), comment='Время генерации'),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True, comment='Время отправки'),
        sa.Column('message_text', sa.Text(), nullable=True, comment='Текст отправленного сообщения'),

        comment='Сгенерированные отчёты по нарушениям'
    )

    op.create_index('idx_violation_reports_type', 'violation_reports', ['report_type'])
    op.create_index('idx_violation_reports_period', 'violation_reports', ['period_start', 'period_end'])
    op.create_index('idx_violation_reports_type_period', 'violation_reports', ['report_type', 'period_start'])


def downgrade() -> None:
    op.drop_index('idx_violation_reports_type_period', table_name='violation_reports')
    op.drop_index('idx_violation_reports_period', table_name='violation_reports')
    op.drop_index('idx_violation_reports_type', table_name='violation_reports')
    op.drop_table('violation_reports')

    op.drop_index('idx_violations_reports', table_name='violations')
    op.drop_index('idx_violations_user_date', table_name='violations')
    op.drop_index('idx_violations_action', table_name='violations')
    op.drop_index('idx_violations_score', table_name='violations')
    op.drop_index('idx_violations_detected_at', table_name='violations')
    op.drop_index('idx_violations_user_uuid', table_name='violations')
    op.drop_table('violations')

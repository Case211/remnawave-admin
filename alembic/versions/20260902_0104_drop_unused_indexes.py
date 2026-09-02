"""Снять индексы, которыми никто не пользуется.

Revision ID: 0104
Revises: 0103
Create Date: 2026-09-02

Проверено на живой установке: 105 нод, 1 млн снимков метрик, 104 тыс. записей
геоданных, база работает шестые сутки без сброса статистики. Каждый индекс
ниже снимается только после сверки с кодом — «ноль сканов» сам по себе не
приговор, индекс может просто ждать своего запроса.

idx_nms_node_created (node_uuid, created_at), 81 МБ — самый дорогой в базе.
Все три запроса к node_metrics_snapshots начинаются с диапазона по времени, а
node_uuid идёт вторым условием или вовсе уходит в GROUP BY: история метрик,
почасовая агрегация и базовая линия детектора трафика. Планировщик берёт
idx_nms_created_at (51 508 сканов), а этот не выбрал ни разу.

ip_metadata: пять индексов по стране, городу, ASN, типу подключения и датам,
13 МБ. Таблица читается только по самому адресу — точечно и списком, оба
запроса идут через первичный ключ (929 946 сканов). Фильтров по географии в
коде нет, чистки по датам тоже: строки живут, пока живёт адрес.

Место — не главное. Каждый лишний индекс дописывается при каждой вставке, а в
node_metrics_snapshots они идут непрерывно со всех нод.
"""
from alembic import op


revision = '0104'
down_revision = '0103'
branch_labels = None
depends_on = None


_UNUSED_INDEXES = (
    # Запросы к метрикам всегда начинаются с диапазона created_at
    "idx_nms_node_created",
    # ip_metadata читается только по ip_address (первичный ключ)
    "ix_ip_metadata_created",
    "idx_ip_metadata_updated_at",
    "idx_ip_metadata_asn",
    "idx_ip_metadata_connection_type",
    "idx_ip_metadata_city",
    "idx_ip_metadata_country",
)


def upgrade() -> None:
    for index_name in _UNUSED_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_nms_node_created "
        "ON node_metrics_snapshots (node_uuid, created_at)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ip_metadata_created ON ip_metadata (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ip_metadata_updated_at ON ip_metadata (updated_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ip_metadata_asn ON ip_metadata (asn)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ip_metadata_connection_type ON ip_metadata (connection_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ip_metadata_city ON ip_metadata (city)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ip_metadata_country ON ip_metadata (country_code)")

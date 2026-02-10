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
    op.execute("""
        CREATE TABLE IF NOT EXISTS asn_russia (
            asn INTEGER NOT NULL PRIMARY KEY,
            org_name VARCHAR(500) NOT NULL,
            org_name_en VARCHAR(500),
            provider_type VARCHAR(20),
            region VARCHAR(100),
            city VARCHAR(100),
            country_code VARCHAR(2) NOT NULL DEFAULT 'RU',
            description TEXT,
            ip_ranges TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_synced_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_asn_russia_org_name ON asn_russia (org_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_asn_russia_provider_type ON asn_russia (provider_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_asn_russia_region ON asn_russia (region)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_asn_russia_city ON asn_russia (city)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_asn_russia_is_active ON asn_russia (is_active)")


def downgrade() -> None:
    op.drop_index('idx_asn_russia_is_active', table_name='asn_russia')
    op.drop_index('idx_asn_russia_city', table_name='asn_russia')
    op.drop_index('idx_asn_russia_region', table_name='asn_russia')
    op.drop_index('idx_asn_russia_provider_type', table_name='asn_russia')
    op.drop_index('idx_asn_russia_org_name', table_name='asn_russia')
    op.drop_table('asn_russia')

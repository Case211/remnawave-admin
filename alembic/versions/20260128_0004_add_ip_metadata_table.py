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
    op.execute("""
        CREATE TABLE IF NOT EXISTS ip_metadata (
            ip_address VARCHAR(45) NOT NULL PRIMARY KEY,
            country_code VARCHAR(2),
            country_name VARCHAR(100),
            region VARCHAR(100),
            city VARCHAR(100),
            latitude NUMERIC(9, 6),
            longitude NUMERIC(9, 6),
            timezone VARCHAR(50),
            asn INTEGER,
            asn_org VARCHAR(200),
            connection_type VARCHAR(20),
            is_proxy BOOLEAN NOT NULL DEFAULT false,
            is_vpn BOOLEAN NOT NULL DEFAULT false,
            is_tor BOOLEAN NOT NULL DEFAULT false,
            is_hosting BOOLEAN NOT NULL DEFAULT false,
            is_mobile BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_checked_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_ip_metadata_country ON ip_metadata (country_code)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ip_metadata_city ON ip_metadata (city)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ip_metadata_asn ON ip_metadata (asn)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ip_metadata_connection_type ON ip_metadata (connection_type)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_ip_metadata_updated_at ON ip_metadata (updated_at)")


def downgrade() -> None:
    op.drop_index('idx_ip_metadata_updated_at', table_name='ip_metadata')
    op.drop_index('idx_ip_metadata_connection_type', table_name='ip_metadata')
    op.drop_index('idx_ip_metadata_asn', table_name='ip_metadata')
    op.drop_index('idx_ip_metadata_city', table_name='ip_metadata')
    op.drop_index('idx_ip_metadata_country', table_name='ip_metadata')
    op.drop_table('ip_metadata')

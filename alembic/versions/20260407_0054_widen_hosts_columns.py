"""Widen hosts.remark and hosts.address from VARCHAR(255) to TEXT.

Some Panel configurations have host addresses/remarks exceeding 255 characters,
causing 'value too long for type character varying(255)' errors during sync.
"""

from alembic import op


revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE hosts ALTER COLUMN remark TYPE TEXT")
    op.execute("ALTER TABLE hosts ALTER COLUMN address TYPE TEXT")


def downgrade():
    op.execute("ALTER TABLE hosts ALTER COLUMN remark TYPE VARCHAR(255)")
    op.execute("ALTER TABLE hosts ALTER COLUMN address TYPE VARCHAR(255)")

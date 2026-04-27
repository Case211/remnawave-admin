"""Add plugin_licenses for the in-panel plugin manager.

Revision ID: 0064
Revises: 0063
Create Date: 2026-04-27

Plugins delivered as wheels are installed via the admin UI: the operator
uploads the wheel, pastes the license JWT, and the panel handles the rest.
This table is the persistent home of those JWTs — one row per plugin,
keyed by plugin id (e.g. "smart_support").

Why a dedicated table rather than reusing ``settings``:
- Plugins are addressable units with their own lifecycle (install / disable
  / uninstall). A flat KV would force ad-hoc key naming conventions and
  make uninstall messy.
- License JWTs are sensitive data. Keeping them in their own table makes
  it trivial to audit who can read them and to wipe them on uninstall.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0064"
down_revision: Union[str, None] = "0063"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS plugin_licenses (
            plugin_id   VARCHAR(64) PRIMARY KEY,
            jwt_token   TEXT NOT NULL,
            wheel_name  VARCHAR(255),
            version     VARCHAR(64),
            installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plugin_licenses")

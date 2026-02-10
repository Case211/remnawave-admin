"""Add RBAC tables: admin_roles, admin_permissions, admin_accounts, admin_audit_log.

Revision ID: 0009
Revises: 0008
Create Date: 2026-02-09

Phase 2 — Role-Based Access Control (RBAC) system.
Creates four tables and seeds pre-configured roles with permissions.
Migrates existing admin_credentials into admin_accounts.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── Pre-configured roles & permissions ──────────────────────────

ROLES = [
    {
        "name": "superadmin",
        "display_name": "Super Admin",
        "description": "Full access including admin management",
        "is_system": True,
    },
    {
        "name": "manager",
        "display_name": "Manager",
        "description": "User, node & host management",
        "is_system": True,
    },
    {
        "name": "operator",
        "display_name": "Operator",
        "description": "View all, create & edit users",
        "is_system": True,
    },
    {
        "name": "viewer",
        "display_name": "Viewer",
        "description": "Read-only access",
        "is_system": True,
    },
]

# resource → actions mapping per role
PERMISSIONS = {
    "superadmin": {
        "users": ["view", "create", "edit", "delete"],
        "nodes": ["view", "create", "edit", "delete"],
        "hosts": ["view", "create", "edit", "delete"],
        "violations": ["view", "resolve"],
        "settings": ["view", "edit"],
        "analytics": ["view"],
        "admins": ["view", "create", "edit", "delete"],
        "roles": ["view", "create", "edit", "delete"],
        "audit": ["view"],
    },
    "manager": {
        "users": ["view", "create", "edit", "delete"],
        "nodes": ["view", "edit"],
        "hosts": ["view", "edit"],
        "violations": ["view", "resolve"],
        "settings": ["view"],
        "analytics": ["view"],
        "admins": ["view"],
        "roles": ["view"],
        "audit": ["view"],
    },
    "operator": {
        "users": ["view", "create", "edit"],
        "nodes": ["view"],
        "hosts": ["view"],
        "violations": ["view"],
        "settings": ["view"],
        "analytics": ["view"],
        "admins": [],
        "roles": [],
        "audit": [],
    },
    "viewer": {
        "users": ["view"],
        "nodes": ["view"],
        "hosts": ["view"],
        "violations": ["view"],
        "settings": ["view"],
        "analytics": ["view"],
        "admins": [],
        "roles": [],
        "audit": [],
    },
}


def upgrade() -> None:
    # ── 1. admin_roles ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS admin_roles (
            id SERIAL PRIMARY KEY,
            name VARCHAR(50) NOT NULL UNIQUE,
            display_name VARCHAR(100) NOT NULL,
            description TEXT,
            is_system BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── 2. admin_permissions ────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS admin_permissions (
            id SERIAL PRIMARY KEY,
            role_id INTEGER NOT NULL REFERENCES admin_roles(id) ON DELETE CASCADE,
            resource VARCHAR(50) NOT NULL,
            action VARCHAR(50) NOT NULL
        )
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_admin_permissions_role_resource_action'
            ) THEN
                ALTER TABLE admin_permissions
                ADD CONSTRAINT uq_admin_permissions_role_resource_action
                UNIQUE (role_id, resource, action);
            END IF;
        END $$
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_permissions_role_id ON admin_permissions (role_id)")

    # ── 3. admin_accounts ───────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS admin_accounts (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password_hash VARCHAR(255),
            telegram_id BIGINT UNIQUE,
            role_id INTEGER REFERENCES admin_roles(id) ON DELETE SET NULL,
            max_users INTEGER,
            max_traffic_gb INTEGER,
            max_nodes INTEGER,
            max_hosts INTEGER,
            users_created INTEGER NOT NULL DEFAULT 0,
            traffic_used_bytes BIGINT NOT NULL DEFAULT 0,
            nodes_created INTEGER NOT NULL DEFAULT 0,
            hosts_created INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT true,
            is_generated_password BOOLEAN NOT NULL DEFAULT false,
            created_by INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_accounts_role_id ON admin_accounts (role_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_accounts_telegram_id ON admin_accounts (telegram_id)")

    # ── 4. admin_audit_log ──────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS admin_audit_log (
            id BIGSERIAL PRIMARY KEY,
            admin_id INTEGER,
            admin_username VARCHAR(100) NOT NULL,
            action VARCHAR(100) NOT NULL,
            resource VARCHAR(50),
            resource_id VARCHAR(255),
            details TEXT,
            ip_address VARCHAR(45),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_admin_id ON admin_audit_log (admin_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_action ON admin_audit_log (action)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_resource ON admin_audit_log (resource)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_admin_audit_log_created_at ON admin_audit_log (created_at)")

    # ── 5. Seed roles & permissions ─────────────────────────────
    conn = op.get_bind()

    for role in ROLES:
        conn.execute(
            sa.text(
                "INSERT INTO admin_roles (name, display_name, description, is_system) "
                "VALUES (:name, :display_name, :description, :is_system) "
                "ON CONFLICT (name) DO NOTHING"
            ),
            role,
        )

    # Fetch role IDs
    rows = conn.execute(sa.text("SELECT id, name FROM admin_roles")).fetchall()
    role_id_map = {row[1]: row[0] for row in rows}

    for role_name, resources in PERMISSIONS.items():
        role_id = role_id_map.get(role_name)
        if not role_id:
            continue
        for resource, actions in resources.items():
            for action in actions:
                conn.execute(
                    sa.text(
                        "INSERT INTO admin_permissions (role_id, resource, action) "
                        "VALUES (:role_id, :resource, :action) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"role_id": role_id, "resource": resource, "action": action},
                )

    # ── 6. Migrate admin_credentials → admin_accounts ───────────
    superadmin_role_id = role_id_map.get("superadmin")
    if superadmin_role_id:
        table_exists = conn.execute(
            sa.text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables "
                "  WHERE table_name = 'admin_credentials'"
                ")"
            )
        ).scalar()

        if table_exists:
            existing = conn.execute(
                sa.text(
                    "SELECT username, password_hash, is_generated "
                    "FROM admin_credentials"
                )
            ).fetchall()
            for row in existing:
                conn.execute(
                    sa.text(
                        "INSERT INTO admin_accounts "
                        "(username, password_hash, role_id, is_active, is_generated_password) "
                        "VALUES (:username, :password_hash, :role_id, true, :is_generated) "
                        "ON CONFLICT (username) DO NOTHING"
                    ),
                    {
                        "username": row[0],
                        "password_hash": row[1],
                        "role_id": superadmin_role_id,
                        "is_generated": row[2] if row[2] is not None else False,
                    },
                )


def downgrade() -> None:
    op.drop_table("admin_audit_log")
    op.drop_table("admin_accounts")
    op.drop_table("admin_permissions")
    op.drop_table("admin_roles")

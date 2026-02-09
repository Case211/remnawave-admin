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
    op.create_table(
        "admin_roles",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_system", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # ── 2. admin_permissions ────────────────────────────────────
    op.create_table(
        "admin_permissions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "role_id",
            sa.Integer,
            sa.ForeignKey("admin_roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("resource", sa.String(50), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
    )
    op.create_unique_constraint(
        "uq_admin_permissions_role_resource_action",
        "admin_permissions",
        ["role_id", "resource", "action"],
    )
    op.create_index(
        "ix_admin_permissions_role_id",
        "admin_permissions",
        ["role_id"],
    )

    # ── 3. admin_accounts ───────────────────────────────────────
    op.create_table(
        "admin_accounts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("telegram_id", sa.BigInteger, nullable=True, unique=True),
        sa.Column(
            "role_id",
            sa.Integer,
            sa.ForeignKey("admin_roles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Limits (NULL = unlimited)
        sa.Column("max_users", sa.Integer, nullable=True),
        sa.Column("max_traffic_gb", sa.Integer, nullable=True),
        sa.Column("max_nodes", sa.Integer, nullable=True),
        sa.Column("max_hosts", sa.Integer, nullable=True),
        # Usage counters
        sa.Column("users_created", sa.Integer, nullable=False, server_default="0"),
        sa.Column("traffic_used_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("nodes_created", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hosts_created", sa.Integer, nullable=False, server_default="0"),
        # Status
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_generated_password", sa.Boolean, nullable=False, server_default="false"),
        # Audit
        sa.Column("created_by", sa.Integer, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_admin_accounts_role_id", "admin_accounts", ["role_id"])
    op.create_index("ix_admin_accounts_telegram_id", "admin_accounts", ["telegram_id"])

    # ── 4. admin_audit_log ──────────────────────────────────────
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("admin_id", sa.Integer, nullable=True),
        sa.Column("admin_username", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_admin_audit_log_admin_id", "admin_audit_log", ["admin_id"])
    op.create_index("ix_admin_audit_log_action", "admin_audit_log", ["action"])
    op.create_index("ix_admin_audit_log_resource", "admin_audit_log", ["resource"])
    op.create_index("ix_admin_audit_log_created_at", "admin_audit_log", ["created_at"])

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
    # Copy existing DB-managed password accounts into admin_accounts
    # with superadmin role
    superadmin_role_id = role_id_map.get("superadmin")
    if superadmin_role_id:
        # Check if admin_credentials table exists
        try:
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
        except Exception:
            # Table may not exist — that's fine
            pass


def downgrade() -> None:
    op.drop_table("admin_audit_log")
    op.drop_table("admin_accounts")
    op.drop_table("admin_permissions")
    op.drop_table("admin_roles")

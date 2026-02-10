"""Add automation_rules and automation_log tables with RBAC permissions.

Revision ID: 0013
Revises: 0012
Create Date: 2026-02-10
"""
from alembic import op

# revision identifiers
revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── automation_rules table ────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS automation_rules (
            id              SERIAL PRIMARY KEY,
            name            VARCHAR(200) NOT NULL,
            description     TEXT,
            is_enabled      BOOLEAN NOT NULL DEFAULT false,
            category        VARCHAR(50) NOT NULL,
            trigger_type    VARCHAR(50) NOT NULL,
            trigger_config  JSONB NOT NULL DEFAULT '{}',
            conditions      JSONB NOT NULL DEFAULT '[]',
            action_type     VARCHAR(100) NOT NULL,
            action_config   JSONB NOT NULL DEFAULT '{}',
            last_triggered_at TIMESTAMPTZ,
            trigger_count   INTEGER NOT NULL DEFAULT 0,
            created_by      INTEGER REFERENCES admin_accounts(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_automation_rules_category ON automation_rules (category)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_automation_rules_is_enabled ON automation_rules (is_enabled)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_automation_rules_trigger_type ON automation_rules (trigger_type)")

    # ── automation_log table ──────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS automation_log (
            id              BIGSERIAL PRIMARY KEY,
            rule_id         INTEGER REFERENCES automation_rules(id) ON DELETE CASCADE,
            triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            target_type     VARCHAR(50),
            target_id       VARCHAR(255),
            action_taken    VARCHAR(100) NOT NULL,
            result          VARCHAR(20) NOT NULL,
            details         JSONB
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_automation_log_rule_id ON automation_log (rule_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_automation_log_triggered_at ON automation_log (triggered_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_automation_log_result ON automation_log (result)")

    # ── RBAC permissions for "automation" resource ────────────────
    # superadmin: all 5 actions
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'automation', unnest(ARRAY['view','create','edit','delete','run'])
        FROM admin_roles r
        WHERE r.name = 'superadmin'
        ON CONFLICT (role_id, resource, action) DO NOTHING
    """)

    # manager: all 5 actions
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'automation', unnest(ARRAY['view','create','edit','delete','run'])
        FROM admin_roles r
        WHERE r.name = 'manager'
        ON CONFLICT (role_id, resource, action) DO NOTHING
    """)

    # operator: view only
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'automation', 'view'
        FROM admin_roles r
        WHERE r.name = 'operator'
        ON CONFLICT (role_id, resource, action) DO NOTHING
    """)

    # viewer: view only
    op.execute("""
        INSERT INTO admin_permissions (role_id, resource, action)
        SELECT r.id, 'automation', 'view'
        FROM admin_roles r
        WHERE r.name = 'viewer'
        ON CONFLICT (role_id, resource, action) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM admin_permissions WHERE resource = 'automation'")
    op.execute("DROP TABLE IF EXISTS automation_log")
    op.execute("DROP TABLE IF EXISTS automation_rules")

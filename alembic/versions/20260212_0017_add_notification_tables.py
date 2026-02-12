"""Add notification and alert tables.

Revision ID: 0017
Revises: 0016
Create Date: 2026-02-12

Phase 10 — Notifications and Alerts system.
Creates tables for notifications, delivery channels, alert rules,
and adds RBAC permissions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── RBAC permissions for notifications ──────────────────────────
NOTIFICATION_PERMISSIONS = {
    "superadmin": {
        "notifications": ["view", "create", "edit", "delete"],
    },
    "manager": {
        "notifications": ["view", "create", "edit"],
    },
    "operator": {
        "notifications": ["view"],
    },
    "viewer": {
        "notifications": ["view"],
    },
}


def upgrade() -> None:
    # ── 1. notifications ──────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id BIGSERIAL PRIMARY KEY,
            admin_id INTEGER REFERENCES admin_accounts(id) ON DELETE CASCADE,
            type VARCHAR(50) NOT NULL DEFAULT 'info',
            severity VARCHAR(20) NOT NULL DEFAULT 'info',
            title VARCHAR(255) NOT NULL,
            body TEXT,
            link VARCHAR(512),
            is_read BOOLEAN NOT NULL DEFAULT false,
            source VARCHAR(50),
            source_id VARCHAR(255),
            group_key VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_admin_id ON notifications (admin_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_is_read ON notifications (is_read)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_type ON notifications (type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_group_key ON notifications (group_key)")

    # ── 2. notification_channels ──────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS notification_channels (
            id SERIAL PRIMARY KEY,
            admin_id INTEGER REFERENCES admin_accounts(id) ON DELETE CASCADE,
            channel_type VARCHAR(30) NOT NULL,
            is_enabled BOOLEAN NOT NULL DEFAULT true,
            config JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (admin_id, channel_type)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_notification_channels_admin_id ON notification_channels (admin_id)")

    # ── 3. smtp_config (global SMTP settings) ────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS smtp_config (
            id SERIAL PRIMARY KEY,
            host VARCHAR(255) NOT NULL,
            port INTEGER NOT NULL DEFAULT 587,
            username VARCHAR(255),
            password VARCHAR(255),
            from_email VARCHAR(255) NOT NULL,
            from_name VARCHAR(255) DEFAULT 'Remnawave Admin',
            use_tls BOOLEAN NOT NULL DEFAULT true,
            use_ssl BOOLEAN NOT NULL DEFAULT false,
            is_enabled BOOLEAN NOT NULL DEFAULT false,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # ── 4. alert_rules ────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS alert_rules (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            is_enabled BOOLEAN NOT NULL DEFAULT true,
            rule_type VARCHAR(30) NOT NULL,
            metric VARCHAR(100),
            operator VARCHAR(20),
            threshold DOUBLE PRECISION,
            duration_minutes INTEGER DEFAULT 0,
            channels JSONB NOT NULL DEFAULT '["in_app"]',
            severity VARCHAR(20) NOT NULL DEFAULT 'warning',
            cooldown_minutes INTEGER NOT NULL DEFAULT 30,
            group_key VARCHAR(255),
            escalation_admin_id INTEGER REFERENCES admin_accounts(id) ON DELETE SET NULL,
            escalation_minutes INTEGER DEFAULT 0,
            last_triggered_at TIMESTAMPTZ,
            last_value DOUBLE PRECISION,
            trigger_count INTEGER NOT NULL DEFAULT 0,
            created_by INTEGER REFERENCES admin_accounts(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_rules_is_enabled ON alert_rules (is_enabled)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_rules_rule_type ON alert_rules (rule_type)")

    # ── 5. alert_rule_log ─────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS alert_rule_log (
            id BIGSERIAL PRIMARY KEY,
            rule_id INTEGER REFERENCES alert_rules(id) ON DELETE CASCADE,
            rule_name VARCHAR(255),
            metric_value DOUBLE PRECISION,
            threshold_value DOUBLE PRECISION,
            severity VARCHAR(20),
            channels_notified JSONB DEFAULT '[]',
            acknowledged BOOLEAN NOT NULL DEFAULT false,
            acknowledged_by INTEGER REFERENCES admin_accounts(id) ON DELETE SET NULL,
            acknowledged_at TIMESTAMPTZ,
            details TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_rule_log_rule_id ON alert_rule_log (rule_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_rule_log_created_at ON alert_rule_log (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_alert_rule_log_acknowledged ON alert_rule_log (acknowledged)")

    # ── 6. Seed default SMTP config ──────────────────────────────
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO smtp_config (host, port, from_email, from_name, is_enabled) "
            "VALUES ('localhost', 587, 'admin@remnawave.local', 'Remnawave Admin', false) "
            "ON CONFLICT DO NOTHING"
        )
    )

    # ── 7. Seed default alert rules ──────────────────────────────
    default_rules = [
        {
            "name": "Disk usage > 90%",
            "description": "Alert when node disk usage exceeds 90%",
            "rule_type": "threshold",
            "metric": "disk_usage_percent",
            "operator": "gt",
            "threshold": 90.0,
            "severity": "critical",
            "cooldown_minutes": 60,
            "group_key": "disk_high",
        },
        {
            "name": "Node offline > 5 min",
            "description": "Alert when a node is offline for more than 5 minutes",
            "rule_type": "threshold",
            "metric": "node_offline_minutes",
            "operator": "gt",
            "threshold": 5.0,
            "severity": "critical",
            "cooldown_minutes": 15,
            "group_key": "node_offline",
        },
        {
            "name": "Traffic > 100 GB/day",
            "description": "Alert when daily traffic exceeds 100 GB",
            "rule_type": "threshold",
            "metric": "traffic_today_gb",
            "operator": "gt",
            "threshold": 100.0,
            "severity": "warning",
            "cooldown_minutes": 1440,
            "group_key": "traffic_high",
        },
        {
            "name": "CPU usage > 85%",
            "description": "Alert when node CPU usage exceeds 85%",
            "rule_type": "threshold",
            "metric": "cpu_usage_percent",
            "operator": "gt",
            "threshold": 85.0,
            "severity": "warning",
            "cooldown_minutes": 30,
            "group_key": "cpu_high",
        },
        {
            "name": "RAM usage > 90%",
            "description": "Alert when node RAM usage exceeds 90%",
            "rule_type": "threshold",
            "metric": "ram_usage_percent",
            "operator": "gt",
            "threshold": 90.0,
            "severity": "warning",
            "cooldown_minutes": 30,
            "group_key": "ram_high",
        },
    ]
    for rule in default_rules:
        conn.execute(
            sa.text(
                "INSERT INTO alert_rules (name, description, rule_type, metric, operator, "
                "threshold, severity, cooldown_minutes, group_key, is_enabled) "
                "VALUES (:name, :description, :rule_type, :metric, :operator, "
                ":threshold, :severity, :cooldown_minutes, :group_key, false) "
            ),
            rule,
        )

    # ── 8. Add RBAC permissions for notifications ─────────────────
    rows = conn.execute(sa.text("SELECT id, name FROM admin_roles")).fetchall()
    role_id_map = {row[1]: row[0] for row in rows}

    for role_name, resources in NOTIFICATION_PERMISSIONS.items():
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


def downgrade() -> None:
    # Remove notification permissions
    op.execute("DELETE FROM admin_permissions WHERE resource = 'notifications'")
    op.drop_table("alert_rule_log")
    op.drop_table("alert_rules")
    op.drop_table("smtp_config")
    op.drop_table("notification_channels")
    op.drop_table("notifications")

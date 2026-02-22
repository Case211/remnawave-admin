"""Seed built-in script for remote agent update.

Revision ID: 0030
Revises: 0029
Create Date: 2026-02-22

Adds 'update_agent' built-in script to the script catalog.
Allows admins to update the node-agent remotely via Fleet
without SSH access to each node.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0030'
down_revision: Union[str, None] = '0029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPDATE_AGENT_SCRIPT = {
    "name": "update_agent",
    "display_name": "Update Node Agent",
    "description": "Pull latest agent code, update dependencies and restart the systemd service. Requires agent installed via git clone and running as systemd service.",
    "category": "system",
    "script_content": r"""#!/bin/bash
set -e

AGENT_DIR="${AGENT_DIR:-/opt/node-agent}"
SERVICE_NAME="${SERVICE_NAME:-remnawave-agent}"

echo "=== Updating Remnawave Node Agent ==="

if [ ! -d "$AGENT_DIR" ]; then
    echo "ERROR: Agent directory not found: $AGENT_DIR"
    echo "Set AGENT_DIR env var if installed elsewhere."
    exit 1
fi

cd "$AGENT_DIR"

if [ ! -d ".git" ]; then
    echo "ERROR: $AGENT_DIR is not a git repository"
    exit 1
fi

OLD_VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "Current version: $OLD_VERSION"

echo "Pulling latest changes..."
git fetch --all --quiet
git reset --hard origin/main

NEW_VERSION=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "New version: $NEW_VERSION"

if [ "$OLD_VERSION" = "$NEW_VERSION" ]; then
    echo "Already up to date."
    exit 0
fi

if [ -f "requirements.txt" ]; then
    echo "Updating pip dependencies..."
    pip3 install -r requirements.txt --quiet 2>&1 || pip install -r requirements.txt --quiet 2>&1
fi

echo "Restarting $SERVICE_NAME..."
systemctl restart "$SERVICE_NAME"
sleep 3

if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "Agent updated: $OLD_VERSION -> $NEW_VERSION"
    echo "Service status: running"
else
    echo "WARNING: Service may not have started correctly"
    systemctl status "$SERVICE_NAME" --no-pager -l 2>&1 | tail -20
    exit 1
fi
""",
    "timeout_seconds": 180,
    "requires_root": True,
}


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO node_scripts
                (name, display_name, description, category, script_content,
                 timeout_seconds, requires_root, is_builtin)
            VALUES
                (:name, :display_name, :description, :category, :script_content,
                 :timeout_seconds, :requires_root, true)
            ON CONFLICT (name) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                description = EXCLUDED.description,
                category = EXCLUDED.category,
                script_content = EXCLUDED.script_content,
                timeout_seconds = EXCLUDED.timeout_seconds,
                requires_root = EXCLUDED.requires_root
            """
        ),
        UPDATE_AGENT_SCRIPT,
    )


def downgrade() -> None:
    op.execute("DELETE FROM node_scripts WHERE name = 'update_agent'")

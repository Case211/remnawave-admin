"""Update update_agent script with auto-detection of agent directory.

Revision ID: 0036
Revises: 0035
Create Date: 2026-02-26

The script now auto-searches common installation paths before
falling back to the default /opt/node-agent. This fixes the issue
where AGENT_DIR env var was required but couldn't be passed from
the admin panel to the remote node.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0036'
down_revision: Union[str, None] = '0035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SCRIPT_CONTENT = r"""#!/bin/bash
set -e

SERVICE_NAME="${SERVICE_NAME:-remnawave-agent}"

echo "=== Updating Remnawave Node Agent ==="

# Auto-detect agent directory if not explicitly set
if [ -z "$AGENT_DIR" ]; then
    SEARCH_PATHS=(
        /opt/node-agent
        /opt/remnawave-node
        /opt/remnawave-agent
        /root/node-agent
        /root/remnawave-node
        /home/*/node-agent
        /home/*/remnawave-node
    )
    for candidate in "${SEARCH_PATHS[@]}"; do
        # Expand globs
        for expanded in $candidate; do
            if [ -d "$expanded/.git" ]; then
                AGENT_DIR="$expanded"
                echo "Auto-detected agent at: $AGENT_DIR"
                break 2
            fi
        done
    done
fi

AGENT_DIR="${AGENT_DIR:-/opt/node-agent}"

if [ ! -d "$AGENT_DIR" ]; then
    echo "ERROR: Agent directory not found: $AGENT_DIR"
    echo "Searched common paths but could not find agent installation."
    echo "Specify AGENT_DIR parameter when running this script."
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
"""


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE node_scripts SET script_content = :content, updated_at = NOW() "
            "WHERE name = 'update_agent'"
        ),
        {"content": NEW_SCRIPT_CONTENT},
    )


def downgrade() -> None:
    # Revert to the original script without auto-detection
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE node_scripts SET script_content = :content, updated_at = NOW() "
            "WHERE name = 'update_agent'"
        ),
        {"content": r"""#!/bin/bash
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
"""},
    )

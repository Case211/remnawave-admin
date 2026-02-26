"""Update update_agent script: Docker support + POSIX compatibility.

Revision ID: 0036
Revises: 0035
Create Date: 2026-02-26

Rewrite the update_agent script to:
1. Auto-detect Docker vs bare-metal environment
2. Docker: pull new image + recreate container via docker compose
3. Bare metal: git pull + systemctl restart (original flow)
4. POSIX-compatible (no bash arrays) — fixes /bin/sh syntax errors
5. Default container name: remnawave-node-agent
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0036'
down_revision: Union[str, None] = '0035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_SCRIPT_CONTENT = r"""#!/bin/sh
set -e

CONTAINER_NAME="${CONTAINER_NAME:-remnawave-node-agent}"
SERVICE_NAME="${SERVICE_NAME:-remnawave-node-agent}"

echo "=== Updating Remnawave Node Agent ==="

# --- Detect environment ---
# If running inside Docker container, self-update is not possible
if [ -f "/.dockerenv" ] || grep -qsE '(docker|containerd)' /proc/1/cgroup 2>/dev/null; then
    echo "Running inside Docker container."
    echo ""
    echo "Self-update from inside a container is not supported."
    echo "To update the agent, run on the HOST machine:"
    echo ""
    echo "  cd <agent-compose-directory>"
    echo "  docker compose pull"
    echo "  docker compose up -d"
    echo ""
    echo "Or as a one-liner:"
    echo "  docker pull ghcr.io/case211/remnawave-admin-node-agent:latest && docker restart $CONTAINER_NAME"
    exit 0
fi

# --- Running on HOST ---

# Check if agent runs via Docker on this host
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER_NAME}$"; then
    echo "Docker deployment detected (container: $CONTAINER_NAME)"

    OLD_IMAGE=$(docker inspect --format='{{.Config.Image}}' "$CONTAINER_NAME" 2>/dev/null || echo "unknown")
    echo "Current image: $OLD_IMAGE"

    # Try docker compose
    COMPOSE_DIR=$(docker inspect --format='{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$CONTAINER_NAME" 2>/dev/null || echo "")
    COMPOSE_SERVICE=$(docker inspect --format='{{index .Config.Labels "com.docker.compose.service"}}' "$CONTAINER_NAME" 2>/dev/null || echo "")

    if [ -n "$COMPOSE_DIR" ] && [ -n "$COMPOSE_SERVICE" ]; then
        echo "Pulling latest image..."
        cd "$COMPOSE_DIR"
        docker compose pull "$COMPOSE_SERVICE"

        echo "Recreating container..."
        docker compose up -d --no-deps "$COMPOSE_SERVICE"

        sleep 3

        if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            echo "Agent updated successfully"
            echo "Container status: running"
        else
            echo "WARNING: Container may not have started correctly"
            docker logs --tail 20 "$CONTAINER_NAME" 2>&1
            exit 1
        fi
    else
        echo "Pulling latest image..."
        docker pull "$OLD_IMAGE"

        echo "Restarting container..."
        docker restart "$CONTAINER_NAME"

        sleep 3

        if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            echo "Agent restarted with latest image layer cache"
            echo "NOTE: For full image update use 'docker compose pull && docker compose up -d'"
        else
            echo "WARNING: Container may not have started correctly"
            exit 1
        fi
    fi

    exit 0
fi

# --- Bare metal / systemd deployment ---
echo "Bare metal deployment detected"

# Auto-detect agent directory (POSIX-compatible)
if [ -z "$AGENT_DIR" ]; then
    for candidate in \
        /opt/node-agent \
        /opt/remnawave-node \
        /opt/remnawave-agent \
        /root/node-agent \
        /root/remnawave-node \
        /home/*/node-agent \
        /home/*/remnawave-node
    do
        if [ -d "$candidate/.git" ]; then
            AGENT_DIR="$candidate"
            echo "Auto-detected agent at: $AGENT_DIR"
            break
        fi
    done
fi

AGENT_DIR="${AGENT_DIR:-/opt/node-agent}"

if [ ! -d "$AGENT_DIR" ]; then
    echo "ERROR: Agent directory not found: $AGENT_DIR"
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
            "UPDATE node_scripts SET "
            "script_content = :content, "
            "description = :desc, "
            "updated_at = NOW() "
            "WHERE name = 'update_agent'"
        ),
        {
            "content": NEW_SCRIPT_CONTENT,
            "desc": (
                "Update the node agent. Auto-detects environment: "
                "Docker (compose pull + recreate) or bare metal (git pull + systemctl restart). "
                "Default container: remnawave-node-agent."
            ),
        },
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

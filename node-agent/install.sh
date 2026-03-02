#!/bin/bash
set -euo pipefail

# Remnawave Node Agent — one-line installer
# Usage: curl -sSL https://raw.githubusercontent.com/Case211/remnawave-admin/main/node-agent/install.sh | bash -s -- --uuid UUID --url URL --token TOKEN

INSTALL_DIR="/opt/remnawave-node-agent"
COMPOSE_URL="https://raw.githubusercontent.com/Case211/remnawave-admin/main/node-agent/docker-compose.yml"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${GREEN}[+]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[x]${NC} $1"; exit 1; }

# Parse arguments
NODE_UUID=""
COLLECTOR_URL=""
AUTH_TOKEN=""
INTERVAL=30
COMMAND_ENABLED="true"
HOST_MODE="true"
WS_SECRET=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --uuid)       NODE_UUID="$2";       shift 2 ;;
        --url)        COLLECTOR_URL="$2";    shift 2 ;;
        --token)      AUTH_TOKEN="$2";       shift 2 ;;
        --interval)   INTERVAL="$2";        shift 2 ;;
        --no-command) COMMAND_ENABLED="false"; shift ;;
        --no-host-mode) HOST_MODE="false"; shift ;;
        --ws-secret)  WS_SECRET="$2";       shift 2 ;;
        --dir)        INSTALL_DIR="$2";     shift 2 ;;
        -h|--help)
            echo "Remnawave Node Agent Installer"
            echo ""
            echo "Usage: $0 --uuid NODE_UUID --url COLLECTOR_URL --token AUTH_TOKEN"
            echo ""
            echo "Required:"
            echo "  --uuid       Node UUID from Remnawave Panel"
            echo "  --url        Admin panel URL (e.g. https://admin.example.com)"
            echo "  --token      Agent auth token"
            echo ""
            echo "Optional:"
            echo "  --interval   Batch send interval in seconds (default: 30)"
            echo "  --no-command Disable command channel (WebSocket)"
            echo "  --no-host-mode Disable host mode (run inside container)"
            echo "  --ws-secret  WEB_SECRET_KEY for command signing"
            echo "  --dir        Install directory (default: /opt/remnawave-node-agent)"
            exit 0
            ;;
        *) error "Unknown option: $1. Use --help for usage." ;;
    esac
done

# Validate required params
[[ -z "$NODE_UUID" ]]     && error "Missing --uuid. Use --help for usage."
[[ -z "$COLLECTOR_URL" ]] && error "Missing --url. Use --help for usage."
[[ -z "$AUTH_TOKEN" ]]    && error "Missing --token. Use --help for usage."

# Check Docker
if ! command -v docker &>/dev/null; then
    error "Docker is not installed. Install Docker first: https://docs.docker.com/engine/install/"
fi

if ! docker compose version &>/dev/null && ! docker-compose version &>/dev/null; then
    error "Docker Compose is not available. Install Docker Compose: https://docs.docker.com/compose/install/"
fi

# Determine compose command
COMPOSE_CMD="docker compose"
if ! docker compose version &>/dev/null; then
    COMPOSE_CMD="docker-compose"
fi

log "Installing Remnawave Node Agent..."
log "Directory: $INSTALL_DIR"

# Create install directory
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Download docker-compose.yml
log "Downloading docker-compose.yml..."
if command -v curl &>/dev/null; then
    curl -sSL "$COMPOSE_URL" -o docker-compose.yml
elif command -v wget &>/dev/null; then
    wget -q "$COMPOSE_URL" -O docker-compose.yml
else
    error "Neither curl nor wget found. Install one of them."
fi

# Generate .env
log "Generating .env..."
WS_URL=$(echo "$COLLECTOR_URL" | sed 's|^http|ws|')

cat > .env << ENVEOF
# Remnawave Node Agent config (auto-generated)
AGENT_NODE_UUID=$NODE_UUID
AGENT_COLLECTOR_URL=$COLLECTOR_URL
AGENT_AUTH_TOKEN=$AUTH_TOKEN
AGENT_INTERVAL_SECONDS=$INTERVAL
AGENT_LOG_PARSING_MODE=realtime
AGENT_XRAY_LOG_PATH=/var/log/remnanode/access.log
AGENT_LOG_LEVEL=INFO
AGENT_MAX_UPTIME_HOURS=6
AGENT_COMMAND_ENABLED=$COMMAND_ENABLED
AGENT_HOST_MODE=$HOST_MODE
AGENT_WS_URL=$WS_URL
ENVEOF

if [[ -n "$WS_SECRET" ]]; then
    echo "AGENT_WS_SECRET_KEY=$WS_SECRET" >> .env
fi

# Stop existing container if running
if $COMPOSE_CMD ps -q 2>/dev/null | grep -q .; then
    warn "Stopping existing agent..."
    $COMPOSE_CMD down 2>/dev/null || true
fi

# Pull and start
log "Starting agent..."
$COMPOSE_CMD pull --quiet
$COMPOSE_CMD up -d

# Verify
sleep 2
if $COMPOSE_CMD ps --format '{{.Status}}' 2>/dev/null | grep -qi 'up\|running'; then
    log "Node Agent installed and running!"
    echo ""
    echo -e "  ${GREEN}Directory:${NC} $INSTALL_DIR"
    echo -e "  ${GREEN}Node UUID:${NC} $NODE_UUID"
    echo -e "  ${GREEN}Collector:${NC} $COLLECTOR_URL"
    echo ""
    echo -e "  Logs:    ${YELLOW}cd $INSTALL_DIR && $COMPOSE_CMD logs -f${NC}"
    echo -e "  Stop:    ${YELLOW}cd $INSTALL_DIR && $COMPOSE_CMD stop${NC}"
    echo -e "  Update:  ${YELLOW}cd $INSTALL_DIR && $COMPOSE_CMD pull && $COMPOSE_CMD up -d${NC}"
    echo ""
elif $COMPOSE_CMD ps 2>/dev/null | grep -qi 'up\|running'; then
    log "Node Agent installed and running!"
else
    warn "Container may still be starting. Check logs:"
    echo "  cd $INSTALL_DIR && $COMPOSE_CMD logs -f"
fi

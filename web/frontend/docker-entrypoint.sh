#!/bin/sh
# Generate runtime config from environment variables.
# This replaces Vite's build-time VITE_* variables with runtime injection
# so that pre-built Docker images can be configured per deployment.

CONFIG_FILE="/usr/share/nginx/html/config.js"

cat <<EOF > "$CONFIG_FILE"
window.__ENV = {
  TELEGRAM_BOT_USERNAME: "${TELEGRAM_BOT_USERNAME:-}",
  API_URL: "${API_URL:-}",
  WS_URL: "${WS_URL:-}"
};
EOF

echo "Runtime config generated at $CONFIG_FILE"

exec "$@"

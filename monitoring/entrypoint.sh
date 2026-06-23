#!/bin/sh
# Генерирует /tmp/prometheus.yml из шаблона, подставляя METRICS_AUTH_TOKEN
# из окружения. Если токен пуст — режет блок authorization целиком.
set -e

TMPL=/etc/prometheus/prometheus.yml.tmpl
OUT=/tmp/prometheus.yml
# Backend admin port: 8081 in full mode, 8082 when APP_MODE=api (split).
PORT="${WEB_BACKEND_PORT:-8081}"

if [ -z "${METRICS_AUTH_TOKEN:-}" ]; then
  # Вырезаем блок authorization (токен пуст) + подставляем порт бэкенда
  sed -e '/^    authorization:$/,/^      credentials: /d' \
      -e "s|__WEB_BACKEND_PORT__|${PORT}|g" "$TMPL" > "$OUT"
else
  # Подставляем токен (| как разделитель — токен может содержать /) и порт
  sed -e "s|__METRICS_AUTH_TOKEN__|${METRICS_AUTH_TOKEN}|g" \
      -e "s|__WEB_BACKEND_PORT__|${PORT}|g" "$TMPL" > "$OUT"
fi

exec /bin/prometheus \
  --config.file="$OUT" \
  --storage.tsdb.path=/prometheus \
  --storage.tsdb.retention.time="${PROMETHEUS_RETENTION:-30d}" \
  --web.console.libraries=/usr/share/prometheus/console_libraries \
  --web.console.templates=/usr/share/prometheus/consoles \
  --web.enable-lifecycle

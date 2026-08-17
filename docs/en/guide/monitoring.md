# Monitoring

The panel exposes metrics in Prometheus format at `GET /metrics` — nothing to enable, it works out of the box. An external scraper (Prometheus, VictoriaMetrics, vmagent) collects them on a schedule, Grafana draws them.

```bash
curl -s https://admin.example.com/metrics | head
```

```
# HELP panel_http_requests_total Total HTTP requests handled by the panel backend.
# TYPE panel_http_requests_total counter
panel_http_requests_total{method="GET",path="/api/v2/analytics/overview",status="200"} 142.0
```

## The short path: built-in Prometheus

A ready Prometheus is already in the compose file, behind a profile:

```bash
docker compose --profile monitoring up -d
```

The `remnawave-prometheus` container comes up on port 9090, already configured to scrape the panel over the internal DNS name — no URLs to edit.

Then add Grafana as a datasource:

| Field | Value |
|-------|-------|
| Type | Prometheus |
| URL, Grafana in the same Docker network | `http://remnawave-prometheus:9090` |
| URL, Grafana outside | `http://server_ip:9090` |
| Auth | none, Prometheus is on the internal network |

Dashboards fill up in 15–30 seconds, after the first scrape.

## Grafana dashboards

Five linked dashboards live in [`docs/grafana/`](https://github.com/Case211/remnawave-admin/tree/main/docs/grafana). Import them via **Dashboards → New → Import → Upload JSON file**, choosing the datasource each time.

| File | About |
|------|-------|
| `overview.json` | KPI wall: online, open violations, expiring subscriptions, traffic limits, HWID, DB pool |
| `http-performance.json` | RPS, latency, in-flight, 5xx and 4xx share, heavy endpoints |
| `users-subscriptions.json` | users by status, devices by platform, who expires soon |
| `nodes.json` | per node: CPU, memory, disk, last seen, cumulative traffic |
| `anti-abuse-sync.json` | violations by action, torrent events, collector rejections, sync lag |

They are cross-linked — each has a row of links to its neighbours at the top. The `$instance` variable is shared: if several panels report to one Prometheus, it switches between them. Start with `overview.json`.

## Protecting the endpoint

```ini
# openssl rand -hex 32
METRICS_AUTH_TOKEN=2c9d...e1
```

After a restart the endpoint answers `401` without the header:

```bash
curl -s -H "Authorization: Bearer 2c9d...e1" https://admin.example.com/metrics
```

For the built-in Prometheus, uncomment the `authorization:` block in `monitoring/prometheus.yml`, put the same token there and restart:

```bash
docker compose --profile monitoring restart prometheus
```

If the scraper comes from a private network (WireGuard, NetBird, Tailscale), closing the endpoint at the proxy is simpler:

```nginx
location = /metrics {
    allow 10.0.0.0/8;       # WireGuard / NetBird
    allow 100.64.0.0/10;    # Tailscale
    deny all;
    proxy_pass http://web-backend:8081;
}
```

## External scraper

::: code-group

```yaml [prometheus.yml]
scrape_configs:
  - job_name: remnawave-panel
    scrape_interval: 15s
    metrics_path: /metrics
    scheme: https
    bearer_token: 2c9d...e1   # if METRICS_AUTH_TOKEN is set
    static_configs:
      - targets: ["admin.example.com"]
        labels:
          env: production
          instance_name: main
```

```yaml [vmagent-scrape.yml]
scrape_configs:
  - job_name: remnawave-panel
    scrape_interval: 15s
    metrics_path: /metrics
    scheme: https
    bearer_token: 2c9d...e1
    static_configs:
      - targets: ["admin.example.com"]
```

:::

Check **Status → Targets**: the `remnawave-panel` job should be `UP`.

If the panel and the metrics store are joined by a private mesh, point the target inside it and skip the authorization:

```yaml
scrape_configs:
  - job_name: remnawave-panel
    static_configs:
      - targets: ["100.79.x.y:8081"]
```

## Metrics catalogue

### HTTP, collected automatically

| Name | Type | Labels | What it is |
|------|------|--------|------------|
| `panel_http_requests_total` | counter | `method, path, status` | every request; `path` is the route template |
| `panel_http_request_duration_seconds` | histogram | `method, path` | processing time, buckets from 5 ms to 10 s |
| `panel_http_requests_in_progress` | gauge | `method` | requests in flight right now |

The `path` label is the route template (`/api/v2/users/{user_id}`), not the raw URL: otherwise user UUIDs would blow up cardinality.

### Panel state, refreshed every 15 seconds

| Name | What it shows |
|------|---------------|
| `panel_online_users` | unique users seen in connections in the last 2 minutes |
| `panel_total_users`, `panel_active_users` | total and ACTIVE |
| `panel_total_nodes`, `panel_online_nodes` | nodes total and connected |
| `panel_violations_open` | violations with no decision taken |
| `panel_db_pool_size`, `panel_db_pool_used` | connection pool size and usage |

### Events

| Name | Labels | When it grows |
|------|--------|---------------|
| `panel_collector_batches_received_total` | — | a batch from a node agent accepted |
| `panel_collector_batches_rejected_total` | `reason` | rejected: rate limit, auth, malformed |
| `panel_violations_detected_total` | `severity` | a violation was recorded |
| `panel_notifications_sent_total` | `channel` | a notification was delivered |

A counter only appears in the output after it first increments — until an agent sends a batch, the batch metrics are absent.

## Useful queries

```text
# Busiest endpoints
topk(10, sum by (path) (rate(panel_http_requests_total[5m])))

# Server errors, a decent alert condition
sum(rate(panel_http_requests_total{status=~"5.."}[5m])) > 0.5

# p95 per endpoint
histogram_quantile(
  0.95,
  sum by (path, le) (rate(panel_http_request_duration_seconds_bucket[5m]))
)

# Database pool under pressure
panel_db_pool_used / panel_db_pool_size > 0.8

# Sharp online drop against an hour ago
(panel_online_users - panel_online_users offset 1h) / panel_online_users offset 1h < -0.3
```

## Alerts

The built-in Prometheus picks up a ready rule set from [`monitoring/alerts.yml`](https://github.com/Case211/remnawave-admin/blob/main/monitoring/alerts.yml): backend availability, 5xx spikes, p95 latency, DB pool saturation, node offline, silent agent, node CPU, memory and disk, sync lag, rejected batches, notification delivery failures.

Look at them in **Prometheus UI → Alerts**. Delivery (Telegram, Slack, email) goes through your Alertmanager or Grafana Alerting; the rules work with both. The thresholds are deliberately conservative — tune them to your SLO and restart Prometheus.

If you scrape with an external collector, copy `alerts.yml` into your own `rule_files`.

## Adding a metric

```python
# web/backend/core/metrics.py
TORRENT_DETECTIONS = Counter(
    "panel_torrent_detections_total",
    "Torrent traffic detection events.",
    ["node"],
)
```

```python
from web.backend.core.metrics import TORRENT_DETECTIONS
TORRENT_DETECTIONS.labels(node=node_name).inc()
```

After a restart the metric shows up in `/metrics`.

## When something is off

**`/metrics` returns 401.** The token is set but the scraper does not send it — check `bearer_token` in the config.

**`panel_db_pool_size` is always 0.** The backend runs without a database: no `DATABASE_URL`, or the pool failed to open. Check the `web-backend` logs at startup.

**The dashboard is empty.** In Grafana → Explore run `up{job="remnawave-panel"}`. One means data is flowing and the dashboard datasource points elsewhere. Zero means Prometheus never reached the panel — check Targets.

**Cardinality is growing.** If `panel_http_requests_total` has labels containing UUIDs, some route is not registered through FastAPI and the middleware could not substitute a template.

## What is deliberately missing

A bundled Grafana — an external one is cleaner and less intrusive. A bundled Alertmanager — the rules ship, but notification routing depends on your infrastructure. And `/metrics` stays out of the OpenAPI schema: no reason to advertise it in Swagger.

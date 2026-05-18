# Remnawave Admin - Documentation

User-facing docs for integrators and operators.

## Public API (`/api/v3`)

- **[API.md](./API.md)** - overview, authentication, scopes, rate limits, rotation
- **[API-ENDPOINTS.md](./API-ENDPOINTS.md)** - per-endpoint reference
- **[API-ERRORS.md](./API-ERRORS.md)** - status codes, error shapes, retry guidance

## Webhooks

- **[WEBHOOKS.md](./WEBHOOKS.md)** - concept, subscription setup, delivery, retry, SSRF
- **[WEBHOOKS-EVENTS.md](./WEBHOOKS-EVENTS.md)** - event catalog with payload shapes
- **[WEBHOOKS-SIGNATURES.md](./WEBHOOKS-SIGNATURES.md)** - v1 / v2 HMAC, receiver examples
  (Python, Node, Go, PHP)

## Monitoring

- **Prometheus / VictoriaMetrics** — см. раздел ниже
- **Grafana dashboard** — [`grafana-dashboard.json`](./grafana-dashboard.json) (импорт в Grafana → Dashboards → New → Import)

## Other docs

- [anti-abuse.md](./anti-abuse.md) - violation detection internals (if present)
- [DEVELOPMENT_PLAN.md](./DEVELOPMENT_PLAN.md) - roadmap

---

# Prometheus / VictoriaMetrics integration

Панель отдаёт метрики в стандартном Prometheus text-формате на эндпоинте
`GET /metrics`. Внешний сборщик (Prometheus / VictoriaMetrics / vmagent) скрейпит
их по расписанию и пишет в TSDB; визуализация — в Grafana по готовому дашборду
[`grafana-dashboard.json`](./grafana-dashboard.json).

## Что внутри

- HTTP-метрики (RPS / latency / in-flight) собираются автоматически Starlette-middleware
- Кастомные `panel_*` gauges обновляются фоновой задачей каждые 15 секунд
- Counter-ы под события (батчи коллектора, нарушения, нотификации) — определены и
  готовы к инкременту, экспорт работает с нуля

Cardinality safe: HTTP-метрики используют шаблон роута (`/api/v2/users/{user_id}`),
а не raw URL — иначе UUID-ы юзеров взорвали бы лейблы.

## 1. Включить эндпоинт

Бэкенд уже отдаёт `/metrics` без авторизации сразу после деплоя — ничего включать
не нужно. Проверь руками:

```bash
curl -s https://panel.example.com/metrics | head
```

Должны прийти строки вида:

```
# HELP panel_http_requests_total Total HTTP requests handled by the panel backend.
# TYPE panel_http_requests_total counter
panel_http_requests_total{method="GET",path="/api/v2/analytics/overview",status="200"} 142.0
```

### Защитить токеном (рекомендуется в проде)

В `.env`:

```bash
# Сгенерировать: openssl rand -hex 32
METRICS_AUTH_TOKEN=2c9d...e1
```

Перезапустить бэкенд. Теперь без `Authorization: Bearer ...` эндпоинт отвечает `401`:

```bash
curl -s -H "Authorization: Bearer 2c9d...e1" https://panel.example.com/metrics
```

### Закрыть от внешнего мира (reverse proxy)

Если скрейпер ходит из приватной сети (NetBird, WireGuard, Tailscale) — лучше
закрыть `/metrics` на уровне nginx/Caddy. Пример nginx:

```nginx
location = /metrics {
    allow 10.0.0.0/8;       # NetBird / WireGuard mesh
    allow 100.64.0.0/10;    # Tailscale
    deny all;
    proxy_pass http://web-backend:8081;
}
```

## 2. Подключить скрейпер

### Prometheus

```yaml
# prometheus.yml
scrape_configs:
  - job_name: remnawave-panel
    scrape_interval: 15s
    metrics_path: /metrics
    scheme: https
    bearer_token: 2c9d...e1   # совпадает с METRICS_AUTH_TOKEN, опционально
    static_configs:
      - targets:
          - panel.example.com
        labels:
          env: production
          instance_name: main
```

Перезапустить Prometheus → проверить **Status → Targets**, что job
`remnawave-panel` в состоянии `UP`.

### vmagent / VictoriaMetrics

```yaml
# vmagent-scrape.yml
scrape_configs:
  - job_name: remnawave-panel
    scrape_interval: 15s
    metrics_path: /metrics
    scheme: https
    bearer_token: 2c9d...e1
    static_configs:
      - targets: ['panel.example.com']
```

Запуск:

```bash
vmagent \
  -promscrape.config=/etc/vmagent/scrape.yml \
  -remoteWrite.url=https://vmselect.example.com/api/v1/write
```

### Внутри NetBird-mesh

Если панель и VictoriaMetrics соединены через NetBird — target укажи на
NetBird-IP бэкенда, авторизация не нужна:

```yaml
scrape_configs:
  - job_name: remnawave-panel
    static_configs:
      - targets: ['100.79.x.y:8081']
```

## 3. Импортировать дашборд в Grafana

1. Открыть Grafana → **Dashboards → New → Import**
2. **Upload JSON file** → выбрать [`grafana-dashboard.json`](./grafana-dashboard.json)
3. В диалоге выбрать datasource (Prometheus / VictoriaMetrics)
4. **Import**

Дашборд содержит 10 панелей:

| Панель | Что показывает |
|---|---|
| Online users | Уникальные подключённые юзеры за последние 2 мин |
| Users & nodes — current | Total/active users, online/total nodes, open violations |
| HTTP RPS by status | Запросы в секунду со stacked-разбивкой по status (200/4xx/5xx) |
| HTTP latency (p50/p95/p99) | Перцентили из histogram-бакетов |
| 5xx error rate | Отдельная панель под алертинг |
| Requests in flight | Сколько запросов прямо сейчас в обработке |
| DB pool usage | Used vs size asyncpg-пула |
| Top endpoints by RPS | bargauge top-10 |
| Top endpoints by p95 latency | bargauge top-10 |
| Collector / violations / notifications | Counter-метрики событий (появятся после первого `.inc()`) |

Переменная `$instance` — фильтр по конкретной панели (если их несколько за одним
скрейпером). Datasource выбирается в Grafana при импорте.

## 4. Каталог метрик

### HTTP (автоматически)

| Имя | Тип | Лейблы | Описание |
|---|---|---|---|
| `panel_http_requests_total` | Counter | `method, path, status` | Все HTTP-запросы. `path` — шаблон роута. |
| `panel_http_request_duration_seconds` | Histogram | `method, path` | Время обработки. Бакеты 5ms → 10s. |
| `panel_http_requests_in_progress` | Gauge | `method` | Сколько запросов сейчас в обработке. |

### Состояние панели (Gauge, refresh каждые 15с)

| Имя | Описание |
|---|---|
| `panel_online_users` | Уникальные `user_uuid` в `user_connections` за последние 2 мин |
| `panel_total_users` / `panel_active_users` | Всего юзеров / в статусе ACTIVE |
| `panel_total_nodes` / `panel_online_nodes` | Всего нод / `is_connected AND NOT is_disabled` |
| `panel_violations_open` | Нарушения со status=ACTIVE |
| `panel_db_pool_size` / `panel_db_pool_used` | Размер пула / занято |

### События (Counter — экспортируются, инкременты добавляются по мере необходимости)

| Имя | Лейблы | Когда инкрементится |
|---|---|---|
| `panel_collector_batches_received_total` | — | Успешный `/collector/batch` от node-agent |
| `panel_collector_batches_rejected_total` | `reason` | Rate-limit / auth-fail / malformed batch |
| `panel_violations_detected_total` | `severity` | Pipeline зафиксировал нарушение |
| `panel_notifications_sent_total` | `channel` | Telegram / push / email / webhook доставлен |

## 5. Полезные PromQL запросы

**Аномалия по запросам в секунду на эндпоинт:**

```promql
topk(10, sum by (path) (rate(panel_http_requests_total[5m])))
```

**5xx за последние 5 минут (для алертов):**

```promql
sum(rate(panel_http_requests_total{status=~"5.."}[5m])) > 0.5
```

**Latency p95 на горячих эндпоинтах:**

```promql
histogram_quantile(
  0.95,
  sum by (path, le) (rate(panel_http_request_duration_seconds_bucket[5m]))
)
```

**DB pool под давлением:**

```promql
panel_db_pool_used / panel_db_pool_size > 0.8
```

**Резкий drop онлайн-юзеров (сравнение с часом назад):**

```promql
(panel_online_users - panel_online_users offset 1h) / panel_online_users offset 1h < -0.3
```

## 6. Troubleshooting

### `/metrics` отвечает 401
`METRICS_AUTH_TOKEN` задан, но скрейпер не шлёт `Authorization: Bearer`. Проверь
`bearer_token` в scrape config либо временно убери `METRICS_AUTH_TOKEN` из `.env`
и перезапусти.

### `panel_db_pool_size` всегда 0
Бэкенд запущен без подключения к БД (нет `DATABASE_URL` или пул не инициализировался).
Проверь логи `web-backend` при старте.

### Метрики `panel_collector_batches_received_total` нет в выводе
Counter появится в `/metrics` только после первого `inc()`. Если node-agent ещё ни
одного батча не прислал — метрика будет отсутствовать. Подожди или сгенерируй
тестовый батч.

### Cardinality взрывается
Если в `panel_http_requests_total` появились лейблы с UUID-ами — значит где-то роут
не зарегистрирован через декораторы FastAPI и middleware вернул `other`. Это плохой
запрос: добавь регистрацию роута либо игнорируй такие запросы на уровне reverse-proxy.

### Дашборд показывает `No data`
1. В Grafana → Explore → выполни `up{job="remnawave-panel"}` — должна быть 1.
2. Если 0 — Prometheus не достал target. Проверь Status → Targets.
3. Если нет даже `up` — datasource в дашборде указывает не на тот Prometheus.

## 7. Кастомизация

Чтобы добавить свою метрику, например счётчик «сколько раз срабатывал детектор
торрентов»:

```python
# web/backend/core/metrics.py
TORRENT_DETECTIONS = Counter(
    "panel_torrent_detections_total",
    "Torrent traffic detection events.",
    ["node"],
)
```

```python
# где-то в обработчике
from web.backend.core.metrics import TORRENT_DETECTIONS
TORRENT_DETECTIONS.labels(node=node_name).inc()
```

После перезапуска метрика начнёт публиковаться в `/metrics`. Добавь панель в
Grafana руками (или через export-update-import).

## 8. Что осознанно не сделано

- Нет встроенной Grafana внутри панели — внешняя инсталляция чище и менее
  навязчива.
- Нет алертов из коробки — алертинг живёт в Grafana / Prometheus / VictoriaMetrics
  Alertmanager, набор правил зависит от твоего SLO.
- Нет автоматического include в API spec — `/metrics` помечен
  `include_in_schema=False`, чтобы не светить его в OpenAPI/Swagger.

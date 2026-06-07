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
- **Grafana dashboards** — [`grafana/`](./grafana/) (5 дашбордов: Overview, HTTP & Performance, Users & Subscriptions, Nodes, Anti-abuse & Sync)

---

# Prometheus / VictoriaMetrics integration

Панель отдаёт метрики в стандартном Prometheus text-формате на эндпоинте
`GET /metrics`. Внешний сборщик (Prometheus / VictoriaMetrics / vmagent) скрейпит
их по расписанию и пишет в TSDB; визуализация — в Grafana по готовым дашбордам
из [`grafana/`](./grafana/) (5 шт.: Overview, HTTP & Performance, Users &
Subscriptions, Nodes, Anti-abuse & Sync — они кросс-линкованы через Dashboard
links).

## Что внутри

- HTTP-метрики (RPS / latency / in-flight) собираются автоматически Starlette-middleware
- Кастомные `panel_*` gauges обновляются фоновой задачей каждые 15 секунд
- Counter-ы под события (батчи коллектора, нарушения, нотификации) — определены и
  готовы к инкременту, экспорт работает с нуля

Cardinality safe: HTTP-метрики используют шаблон роута (`/api/v2/users/{user_id}`),
а не raw URL — иначе UUID-ы юзеров взорвали бы лейблы.

## Быстрый старт (5 минут)

В репозитории уже есть готовый Prometheus как опциональный docker-compose сервис.
Поднимается одной командой:

```bash
docker compose --profile monitoring up -d
```

Это поднимет `remnawave-prometheus` на порту `9090`. Конфиг сразу настроен на
скрейп `/metrics` панели (через docker DNS — никаких URL править не надо).

Дальше подключи свою Grafana как datasource:

| Поле | Значение |
|---|---|
| Type | Prometheus |
| URL (Grafana в той же docker network) | `http://remnawave-prometheus:9090` |
| URL (Grafana снаружи) | `http://server_ip:9090` |
| Auth | без авторизации (Prometheus на внутренней сети) |

После Save & Test → импорт дашбордов:

1. Grafana → **Dashboards → New → Import**
2. **Upload JSON file** → выбрать поочерёдно файлы из [`grafana/`](./grafana/)
   (рекомендуемый порядок: `overview.json` → `http-performance.json` →
   `users-subscriptions.json` → `nodes.json` → `anti-abuse-sync.json`)
3. На каждом импорте выбрать datasource → **Import**

Дашборды кросс-линкованы — на каждом сверху есть строка перехода в соседние.
Overview достаточно открыть в первую очередь — оттуда видно все ключевые KPI.

Дашборды начнут заполняться через 15-30 секунд (первый scrape interval).

Если хочется защитить `/metrics` Bearer-токеном — см. ниже «Защитить токеном».

---

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

Если используешь встроенный Prometheus (`--profile monitoring`) — раскомментируй
блок `authorization:` в `monitoring/prometheus.yml` и подставь тот же токен,
затем перезапусти Prometheus:

```bash
docker compose --profile monitoring restart prometheus
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

## 3. Импортировать дашборды в Grafana

В [`grafana/`](./grafana/) лежит 5 связанных дашбордов. Импортируй их
все через **Dashboards → New → Import → Upload JSON file** — datasource
выбирается на каждом импорте.

| Файл | Назначение |
|---|---|
| `overview.json` | KPI-витрина: online users, открытые violations, expiring, traffic-limit, HWID, DB pool |
| `http-performance.json` | HTTP RPS/latency/in-flight, 5xx/4xx, top-endpoints, DB pool saturation |
| `users-subscriptions.json` | Users by status, HWID by platform, expiring soon, traffic-limit-reached |
| `nodes.json` | Per-node CPU/Memory/Disk/last-seen + cumulative traffic + connection status |
| `anti-abuse-sync.json` | Violations by action, torrent events, collector reject reasons, notifications, sync lag |

Все дашборды кросс-линкованы (Dashboard links сверху), переменная `$instance`
общая — фильтр по конкретной панели если их несколько за одним Prometheus.

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
| `panel_violations_open` | Нарушения с `action_taken IS NULL` (не закрытые) |
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

## 6. Алерты из коробки

Встроенный Prometheus автоматически подхватывает готовый набор правил из
[`monitoring/alerts.yml`](../monitoring/alerts.yml) — 12 алертов: доступность
бэкенда, всплеск 5xx, p95 latency, насыщение пула БД, нода офлайн / агент
молчит / CPU / RAM / диск, отставание sync, отклонённые батчи коллектора,
фейлы доставки уведомлений.

Смотреть: **Prometheus UI → Alerts** (`http://server:9090/alerts`).

Доставка уведомлений (Telegram / Slack / email) — через внешний
Alertmanager или Grafana Alerting; правила совместимы с обоими. Пороги
консервативные — правь `monitoring/alerts.yml` под свой SLO, Prometheus
перечитает их при рестарте контейнера:

```bash
docker compose --profile monitoring restart prometheus
```

Если скрейпишь панель внешним Prometheus / vmagent — просто скопируй
`monitoring/alerts.yml` к себе в `rule_files`.

## 7. Troubleshooting

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

## 8. Кастомизация

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

## 9. Что осознанно не сделано

- Нет встроенной Grafana внутри панели — внешняя инсталляция чище и менее
  навязчива.
- Нет встроенного Alertmanager — правила алертов поставляются
  (см. раздел 6), но доставка уведомлений живёт в твоём Alertmanager /
  Grafana Alerting: маршрутизация и каналы зависят от твоей инфраструктуры.
- Нет автоматического include в API spec — `/metrics` помечен
  `include_in_schema=False`, чтобы не светить его в OpenAPI/Swagger.

# Мониторинг

Панель отдаёт метрики в формате Prometheus на `GET /metrics` — включать ничего не нужно, эндпоинт работает сразу. Внешний сборщик (Prometheus, VictoriaMetrics, vmagent) забирает их по расписанию, рисует Grafana.

```bash
curl -s https://admin.example.com/metrics | head
```

```
# HELP panel_http_requests_total Total HTTP requests handled by the panel backend.
# TYPE panel_http_requests_total counter
panel_http_requests_total{method="GET",path="/api/v2/analytics/overview",status="200"} 142.0
```

## Быстрый путь: встроенный Prometheus

В compose уже лежит готовый Prometheus, поднимается профилем:

```bash
docker compose --profile monitoring up -d
```

Контейнер `remnawave-prometheus` встанет на порт 9090, конфиг уже настроен на скрейп панели через внутренний DNS — URL править не надо.

Дальше подключите Grafana как datasource:

| Поле | Значение |
|------|----------|
| Type | Prometheus |
| URL, если Grafana в той же сети Docker | `http://remnawave-prometheus:9090` |
| URL, если снаружи | `http://server_ip:9090` |
| Auth | не нужна, Prometheus во внутренней сети |

Дашборды заполнятся через 15–30 секунд, после первого скрейпа.

## Дашборды Grafana

Пять связанных дашбордов лежат в [`docs/grafana/`](https://github.com/Case211/remnawave-admin/tree/main/docs/grafana). Импорт: **Dashboards → New → Import → Upload JSON file**, datasource выбирается при каждом импорте.

| Файл | О чём |
|------|-------|
| `overview.json` | витрина KPI: онлайн, открытые нарушения, истекающие подписки, лимиты трафика, HWID, пул БД |
| `http-performance.json` | RPS, задержки, in-flight, доля 5xx и 4xx, тяжёлые эндпоинты |
| `users-subscriptions.json` | пользователи по статусам, устройства по платформам, кто скоро истечёт |
| `nodes.json` | по каждой ноде: CPU, память, диск, последняя связь, накопленный трафик |
| `anti-abuse-sync.json` | нарушения по действиям, торрент-события, отказы коллектора, отставание синхронизации |

Они кросс-линкованы — сверху на каждом строка перехода в соседние. Переменная `$instance` общая: если за одним Prometheus живёт несколько панелей, фильтр переключает между ними. Начинать стоит с `overview.json`.

## Защита эндпоинта

```ini
# openssl rand -hex 32
METRICS_AUTH_TOKEN=2c9d...e1
```

После перезапуска без заголовка эндпоинт отвечает `401`:

```bash
curl -s -H "Authorization: Bearer 2c9d...e1" https://admin.example.com/metrics
```

Для встроенного Prometheus раскомментируйте блок `authorization:` в `monitoring/prometheus.yml`, положите туда тот же токен и перезапустите:

```bash
docker compose --profile monitoring restart prometheus
```

Если скрейпер ходит из приватной сети (WireGuard, NetBird, Tailscale), проще закрыть эндпоинт на прокси:

```nginx
location = /metrics {
    allow 10.0.0.0/8;       # WireGuard / NetBird
    allow 100.64.0.0/10;    # Tailscale
    deny all;
    proxy_pass http://web-backend:8081;
}
```

## Внешний скрейпер

::: code-group

```yaml [prometheus.yml]
scrape_configs:
  - job_name: remnawave-panel
    scrape_interval: 15s
    metrics_path: /metrics
    scheme: https
    bearer_token: 2c9d...e1   # если задан METRICS_AUTH_TOKEN
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

Проверка: **Status → Targets**, job `remnawave-panel` должен быть `UP`.

Если панель и хранилище метрик соединены через приватный mesh, target указывается на адрес внутри него, и авторизация не нужна:

```yaml
scrape_configs:
  - job_name: remnawave-panel
    static_configs:
      - targets: ["100.79.x.y:8081"]
```

## Каталог метрик

### HTTP — собираются сами

| Имя | Тип | Лейблы | Что это |
|-----|-----|--------|---------|
| `panel_http_requests_total` | counter | `method, path, status` | все запросы; `path` — шаблон роута |
| `panel_http_request_duration_seconds` | histogram | `method, path` | время обработки, бакеты от 5 мс до 10 с |
| `panel_http_requests_in_progress` | gauge | `method` | сколько запросов в работе прямо сейчас |

Лейбл `path` — именно шаблон (`/api/v2/users/{user_id}`), а не сырой URL: иначе UUID пользователей разнесли бы кардинальность в клочья.

### Состояние панели — обновляются каждые 15 секунд

| Имя | Что показывает |
|-----|----------------|
| `panel_online_users` | уникальные пользователи в подключениях за последние 2 минуты |
| `panel_total_users`, `panel_active_users` | всего и в статусе ACTIVE |
| `panel_total_nodes`, `panel_online_nodes` | всего нод и на связи |
| `panel_violations_open` | нарушения, по которым не принято решение |
| `panel_db_pool_size`, `panel_db_pool_used` | размер пула соединений и занятая часть |

### События

| Имя | Лейблы | Когда растёт |
|-----|--------|--------------|
| `panel_collector_batches_received_total` | — | принят батч от агента ноды |
| `panel_collector_batches_rejected_total` | `reason` | отказ: лимит, авторизация, битый батч |
| `panel_violations_detected_total` | `severity` | зафиксировано нарушение |
| `panel_notifications_sent_total` | `channel` | доставлено уведомление |

Счётчик появляется в выводе только после первого срабатывания — пока агент не прислал ни одного батча, метрики батчей в `/metrics` не будет.

## Полезные запросы

```text
# Самые нагруженные эндпоинты
topk(10, sum by (path) (rate(panel_http_requests_total[5m])))

# Пятисотки — годится как условие алерта
sum(rate(panel_http_requests_total{status=~"5.."}[5m])) > 0.5

# p95 по эндпоинтам
histogram_quantile(
  0.95,
  sum by (path, le) (rate(panel_http_request_duration_seconds_bucket[5m]))
)

# Пул базы под давлением
panel_db_pool_used / panel_db_pool_size > 0.8

# Резкий обвал онлайна против часа назад
(panel_online_users - panel_online_users offset 1h) / panel_online_users offset 1h < -0.3
```

## Алерты

Встроенный Prometheus подхватывает готовый набор правил из [`monitoring/alerts.yml`](https://github.com/Case211/remnawave-admin/blob/main/monitoring/alerts.yml): доступность бэкенда, всплеск 5xx, p95 задержек, насыщение пула БД, нода офлайн, молчащий агент, CPU, память и диск ноды, отставание синхронизации, отклонённые батчи, ошибки доставки уведомлений.

Смотреть в **Prometheus UI → Alerts**. Доставка (Telegram, Slack, почта) — через ваш Alertmanager или Grafana Alerting; правила совместимы с обоими. Пороги намеренно консервативные: правьте под свой SLO и перезапускайте Prometheus.

Если скрейпите внешним сборщиком — просто скопируйте `alerts.yml` к себе в `rule_files`.

## Своя метрика

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

После перезапуска метрика появится в `/metrics`.

## Если что-то не так

**`/metrics` отвечает 401.** Токен задан, а скрейпер его не шлёт — проверьте `bearer_token` в конфиге.

**`panel_db_pool_size` всегда 0.** Бэкенд работает без базы: нет `DATABASE_URL` или пул не поднялся. Смотрите логи `web-backend` при старте.

**Дашборд пустой.** В Grafana → Explore выполните `up{job="remnawave-panel"}`. Единица — данные идут, значит datasource в дашборде указывает не туда. Ноль — Prometheus не достучался до панели, смотрите Targets.

**Растёт кардинальность.** Если в `panel_http_requests_total` появились лейблы с UUID, значит какой-то роут не зарегистрирован через FastAPI и middleware не смог подставить шаблон.

## Чего здесь намеренно нет

Встроенной Grafana — внешняя чище и не навязывается. Встроенного Alertmanager — правила поставляются, а маршрутизация уведомлений зависит от вашей инфраструктуры. И `/metrics` не попадает в OpenAPI-схему: незачем светить его в Swagger.

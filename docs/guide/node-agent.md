# Node Agent

Агент ставится на каждую ноду и делает три вещи: читает `access.log` Xray и шлёт подключения в панель, снимает метрики хоста и сети, держит канал команд (терминал, скрипты, списки блокировок).

Без агента не работает [анти-абуз](/guide/anti-abuse) — панели просто неоткуда узнать, кто и откуда подключается.

## Установка одной командой

Панель собирает команду сама, вместе с токеном:

1. **Ноды** → нужная нода → **Токен агента** → **Установить агент**
2. Скопировать готовую строку и выполнить её на ноде:

```bash
curl -fsSL --retry 3 --retry-delay 2 \
  https://raw.githubusercontent.com/Case211/remnawave-admin/main/node-agent/install.sh \
  -o /tmp/rwa-node-agent-install.sh \
  && bash /tmp/rwa-node-agent-install.sh --uuid UUID --url URL --token TOKEN
```

Скрипт создаст `/opt/remnawave-node-agent/`, положит туда `docker-compose.yml`, соберёт `.env` и поднимет контейнер.

| Параметр | Зачем | По умолчанию |
|----------|-------|--------------|
| `--uuid` | UUID ноды | обязателен |
| `--url` | адрес панели | обязателен |
| `--token` | токен агента | обязателен |
| `--interval` | как часто слать данные, секунды | `30` |
| `--ws-secret` | ключ подписи команд (`WEB_SECRET_KEY` панели) | — |
| `--no-command` | не поднимать канал команд | — |
| `--no-host-mode` | не выполнять команды на хосте | — |
| `--dir` | куда ставить | `/opt/remnawave-node-agent` |

## Установка руками

Токен генерируется в панели (**Ноды → нода → Токен агента**) или в боте. Показывается один раз.

```bash
mkdir -p /opt/remnawave-node-agent && cd /opt/remnawave-node-agent
curl -fsSLO --retry 3 --retry-delay 2 https://raw.githubusercontent.com/Case211/remnawave-admin/main/node-agent/docker-compose.yml
nano .env
docker compose up -d
```

```ini
AGENT_NODE_UUID=fd3a2983-4f68-45eb-8652-7557d7e15f7a
AGENT_COLLECTOR_URL=https://admin.example.com
AGENT_AUTH_TOKEN=токен_из_панели
AGENT_INTERVAL_SECONDS=30
AGENT_XRAY_LOG_PATH=/var/log/remnanode/access.log
```

Образ тянется готовый: `ghcr.io/case211/remnawave-admin-node-agent:latest`.

### Переменные агента

| Переменная | Что задаёт | По умолчанию |
|------------|-----------|--------------|
| `AGENT_NODE_UUID` | UUID ноды из панели Remnawave | обязательна |
| `AGENT_COLLECTOR_URL` | адрес панели Remnawave Admin | обязательна |
| `AGENT_AUTH_TOKEN` | токен этой ноды | обязательна |
| `AGENT_INTERVAL_SECONDS` | интервал отправки батчей | `30` |
| `AGENT_LOG_PARSING_MODE` | `realtime` или `polling` | `realtime` |
| `AGENT_XRAY_LOG_PATH` | путь к `access.log` | `/var/log/remnanode/access.log` |
| `AGENT_MAX_BUFFER_SIZE` | потолок буфера подключений | `50000` |
| `AGENT_SEND_MAX_RETRIES` | попыток отправить батч | `3` |
| `AGENT_SEND_RETRY_DELAY_SECONDS` | пауза между попытками | `5.0` |
| `AGENT_LOG_LEVEL` | уровень логов | `INFO` |
| `AGENT_COMMAND_ENABLED` | канал команд от панели | `false` |
| `AGENT_WS_URL` | адрес WebSocket, если отличается | = `AGENT_COLLECTOR_URL` |
| `AGENT_WS_SECRET_KEY` | ключ проверки подписи команд | — |

Переменные `AGENT_NDPI_*` описаны в разделе [Детект торрентов](/guide/torrents).

## Проверка

```bash
docker compose logs -f
```

Как выглядит здоровый старт:

```
INFO: Collector API OK: https://admin.example.com/api/v2/collector/health
INFO: Log file found: /var/log/remnanode/access.log (size: X bytes)
INFO: Node Agent started: node_uuid=..., mode=realtime, interval=30s
INFO: Real-time parsing: new_lines=X accepted_lines=X connections=X
```

При остановке агент досылает накопленное, а не бросает его:

```
INFO: Shutdown: sending remaining X accumulated connections...
INFO: Node Agent stopped
```

## Прокси перед коллектором

Агент ходит в `/api/v2/collector/*` и держит WebSocket на `/api/v2/agent/ws`. Оба пути должны проходить через ваш reverse proxy — примеры конфигов в разделе [Веб-панель и reverse proxy](/guide/web-panel).

## Что агент читает

Строка лога Remnawave выглядит так:

```
2026/01/28 11:23:18.306521 from 188.170.87.33:20129 accepted tcp:accounts.google.com:443 [Sweden1 >> DIRECT] email: 154
```

`email: 154` — это идентификатор пользователя, а не почта: коллектор ищет по `short_uuid`, email или ID. Поддерживаются IPv4 и IPv6. Если формат логов у вас другой, разбор правится в `node-agent/src/collectors/xray_log.py`.

## Обновление

```bash
cd /opt/remnawave-node-agent
docker compose pull
docker compose up -d
```

Если агент когда-то ставился локальной сборкой (`build: .` в compose), перейдите на готовый образ: остановите контейнер, сохраните `.env`, возьмите свежий `docker-compose.yml` из репозитория и поднимитесь заново. В новых версиях появились healthcheck, лимиты ресурсов, аккуратная остановка и проверка связи при старте.

## Если данные не идут

- **Агент не видит лог.** Проверьте, что путь в `AGENT_XRAY_LOG_PATH` существует внутри контейнера и примонтирован в `docker-compose.yml`
- **`Collector API` не отвечает.** Адрес в `AGENT_COLLECTOR_URL` должен открываться с ноды: `curl https://admin.example.com/api/v2/collector/health`
- **`server rejected WebSocket connection: HTTP 404`.** Reverse proxy не пропускает `/api/v2/agent/ws` — терминал и живой статус ноды не заработают
- **Команды отклоняются.** `AGENT_WS_SECRET_KEY` на ноде должен совпадать с `WEB_SECRET_KEY` панели: команды подписываются HMAC

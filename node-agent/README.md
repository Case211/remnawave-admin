# Remnawave Node Agent

Агент для сбора данных о подключениях с нод (Xray) и отправки в Web Backend (Collector API).

Без этого агента Anti-Abuse система не может работать.

---

## Как это работает

1. Агент читает `access.log` Xray на ноде
2. Парсит строки с подключениями пользователей
3. Периодически отправляет батч в Web Backend: `POST /api/v2/collector/batch`

## Требования

- Python 3.12+ (или Docker)
- Доступ к файлу логов Xray: `/var/log/remnanode/access.log`
- Токен агента (генерируется в веб-панели или Admin Bot)
- UUID ноды (из Remnawave Panel)

---

## Установка

### Шаг 1: Получение токена агента

**Вариант А** — через веб-панель:
1. Откройте веб-панель → **Ноды** → выберите ноду → **Токен агента** → **Сгенерировать**

**Вариант Б** — через Admin Bot в Telegram:
1. Откройте Admin Bot → **Ноды** → выберите ноду → **Редактировать** → **Токен агента** → **Сгенерировать**

Скопируйте токен — он показывается только один раз.

### Шаг 2: Настройка .env

```bash
cd node-agent
cp .env.example .env
nano .env
```

```env
AGENT_NODE_UUID=fd3a2983-4f68-45eb-8652-7557d7e15f7a
AGENT_COLLECTOR_URL=https://admin.yourdomain.com
AGENT_AUTH_TOKEN=your-generated-token-here
AGENT_INTERVAL_SECONDS=30
AGENT_XRAY_LOG_PATH=/var/log/remnanode/access.log
# AGENT_LOG_LEVEL=INFO
```

| Переменная | Описание | По умолчанию |
|------------|----------|-------------|
| `AGENT_NODE_UUID` | UUID ноды (из Remnawave Panel) | **обязательно** |
| `AGENT_COLLECTOR_URL` | URL Web Backend (порт 8081) | **обязательно** |
| `AGENT_AUTH_TOKEN` | Токен агента для этой ноды | **обязательно** |
| `AGENT_INTERVAL_SECONDS` | Интервал отправки батчей (секунды) | `30` |
| `AGENT_LOG_PARSING_MODE` | Режим парсинга: `realtime` или `polling` | `realtime` |
| `AGENT_XRAY_LOG_PATH` | Путь к `access.log` | `/var/log/remnanode/access.log` |
| `AGENT_MAX_BUFFER_SIZE` | Макс. размер буфера подключений (защита от утечки памяти) | `50000` |
| `AGENT_SEND_MAX_RETRIES` | Количество попыток отправки батча | `3` |
| `AGENT_SEND_RETRY_DELAY_SECONDS` | Задержка между попытками (секунды) | `5.0` |
| `AGENT_LOG_LEVEL` | Уровень логов: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `AGENT_COMMAND_ENABLED` | Включить WebSocket-канал команд от веб-панели | `false` |
| `AGENT_WS_URL` | WebSocket URL (по умолчанию = `AGENT_COLLECTOR_URL`) | — |
| `AGENT_WS_SECRET_KEY` | Ключ для проверки HMAC-подписи команд (= `WEB_SECRET_KEY`) | — |

### Шаг 3: Запуск

#### Docker Compose (рекомендуется)

```bash
cd node-agent
docker compose up -d
docker compose logs -f
```

Агент автоматически скачает готовый образ из GHCR (`ghcr.io/case211/remnawave-admin-node-agent:latest`).

#### Docker напрямую

```bash
docker run -d \
  --name remnawave-node-agent \
  --restart unless-stopped \
  --env-file node-agent/.env \
  -v /var/log/remnanode:/var/log/remnanode:ro \
  --network remnawave-network \
  --memory 128m \
  --stop-timeout 15 \
  ghcr.io/case211/remnawave-admin-node-agent:latest
```

#### Локально (без Docker)

```bash
cd node-agent
pip install -r requirements.txt
python -m src.main
```

#### Systemd (автозапуск без Docker)

Создай `/etc/systemd/system/remnawave-node-agent.service`:

```ini
[Unit]
Description=Remnawave Node Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/remnawave-node-agent/node-agent
EnvironmentFile=/opt/remnawave-node-agent/node-agent/.env
ExecStart=/usr/bin/python3 -m src.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now remnawave-node-agent
sudo systemctl status remnawave-node-agent
```

### Шаг 4: Проверка

Ожидаемые логи при работе:
```
INFO: Collector API OK: https://admin.yourdomain.com/api/v2/collector/health
INFO: Log file found: /var/log/remnanode/access.log (size: X bytes)
INFO: Node Agent started: node_uuid=..., collector=..., mode=realtime, interval=30s
INFO: Real-time parsing: new_lines=X accepted_lines=X matched_lines=X connections=X
DEBUG: Batch OK: X connections
```

При корректной остановке (`docker compose stop`) агент отправит оставшиеся данные:
```
INFO: Received shutdown signal, finishing current cycle...
INFO: Shutdown: sending remaining X accumulated connections...
INFO: Shutdown: remaining batch sent successfully
INFO: Node Agent stopped
```

---

## Настройка Caddy (reverse proxy)

Если Web Backend за обратным прокси (Caddy), добавьте проксирование Collector API:

```caddyfile
admin.yourdomain.com {
    # Collector API для Node Agent
    reverse_proxy /api/v2/collector/* web-backend:8081 {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }

    # Web Backend API
    reverse_proxy /api/v2/* web-backend:8081 {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
    }

    # Webhook для Remnawave Panel → Bot
    reverse_proxy /webhook bot:8080 {
        header_up X-Real-IP {remote_host}
    }
}
```

---

## Контракт с Collector API

- **POST** `{COLLECTOR_URL}/api/v2/collector/batch`
- **Header:** `Authorization: Bearer {AGENT_AUTH_TOKEN}`
- **Body:**

```json
{
  "node_uuid": "uuid",
  "timestamp": "2026-01-28T12:00:00Z",
  "connections": [
    {
      "user_email": "154",
      "ip_address": "1.2.3.4",
      "node_uuid": "uuid",
      "connected_at": "2026-01-28T12:00:00Z",
      "bytes_sent": 0,
      "bytes_received": 0
    }
  ]
}
```

---

## Формат логов Xray

Агент парсит строки формата Remnawave:
```
2026/01/28 11:23:18.306521 from 188.170.87.33:20129 accepted tcp:accounts.google.com:443 [Sweden1 >> DIRECT] email: 154
```

Регулярное выражение (поддерживает IPv4 и IPv6):
```regex
(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+from\s+(?:\[?([0-9a-fA-F:\.]+)\]?):(\d+)\s+accepted.*?email:\s*(\d+)
```

В логах Remnawave `email: 154` — это ID пользователя, не email. Collector API автоматически ищет пользователя по `short_uuid`, email или ID.

Если формат логов другой — обновите регулярное выражение в `src/collectors/xray_log.py`.

---

## Обновление со старой версии (миграция на GHCR-образ)

Если агент был установлен через `docker-compose build` (локальная сборка из исходников), выполните следующие шаги для перехода на готовый GHCR-образ.

### Что изменилось

| Было (старая версия) | Стало (новая версия) |
|---------------------|---------------------|
| Локальная сборка `build: .` | Готовый образ `ghcr.io/case211/remnawave-admin-node-agent:latest` |
| `version: '3.8'` в docker-compose | Убран (deprecated) |
| Нет healthcheck | Healthcheck встроен |
| Нет лимитов ресурсов | Memory: 128M, CPU: 0.5 |
| Нет graceful shutdown | Агент корректно завершается и отправляет оставшиеся данные |
| Нет проверки связи при старте | Connectivity check при запуске |
| Только IPv4 в логах | IPv4 + IPv6 |

### Пошаговый план миграции

**1. Остановить старый агент**

```bash
cd /path/to/node-agent
docker-compose down
```

> Старая версия не поддерживала graceful shutdown, поэтому просто останавливаем.

**2. Сделать бэкап .env (на всякий случай)**

```bash
cp .env .env.backup
```

**3. Обновить файлы**

Вариант А — если клонирован весь репозиторий:

```bash
cd /path/to/remnawave-admin
git pull origin main
```

Вариант Б — если скопирована только папка `node-agent`:

Скачайте обновлённые файлы и замените:
- `docker-compose.yml`
- `docker-compose.local.yml` (если используется)
- `.env.example` (для справки по новым параметрам)

Dockerfile и `src/` больше **не нужны** на сервере — образ скачивается из GHCR.

**4. Проверить .env — добавить новые переменные (опционально)**

Новые переменные необязательны (есть разумные значения по умолчанию), но можно добавить:

```bash
# Сравнить с актуальным примером
diff .env .env.example
```

Новые доступные настройки:
```env
# Максимальный размер буфера (защита от утечки памяти при недоступном API)
# AGENT_MAX_BUFFER_SIZE=50000

# Retry настройки
# AGENT_SEND_MAX_RETRIES=3
# AGENT_SEND_RETRY_DELAY_SECONDS=5.0
```

**5. Удалить старый локально собранный образ**

```bash
# Посмотреть старый образ
docker images | grep node-agent

# Удалить старый образ (имя может отличаться)
docker rmi node-agent-node-agent:latest 2>/dev/null
docker rmi remnawave-node-agent:latest 2>/dev/null
```

**6. Запустить новую версию**

```bash
cd /path/to/node-agent
docker compose up -d
```

Docker автоматически скачает образ из GHCR.

**7. Проверить работу**

```bash
# Логи — должно быть "Collector API connectivity check passed"
docker compose logs -f

# Healthcheck — должен быть "healthy"
docker inspect remnawave-node-agent | grep -A3 Health
```

Ожидаемый вывод при успешном старте:
```
INFO: Collector API OK: https://admin.yourdomain.com/api/v2/collector/health
INFO: Log file found: /var/log/remnanode/access.log (size: X bytes)
INFO: Node Agent started: node_uuid=..., collector=..., mode=realtime, interval=30s
```

### Миграция Systemd → Docker Compose

Если агент работал через systemd:

```bash
# 1. Остановить и отключить systemd сервис
sudo systemctl stop remnawave-node-agent
sudo systemctl disable remnawave-node-agent
sudo rm /etc/systemd/system/remnawave-node-agent.service
sudo systemctl daemon-reload

# 2. Создать папку и .env
mkdir -p /opt/remnawave-node-agent
cd /opt/remnawave-node-agent

# Скопировать docker-compose.yml и .env из репозитория
# или скачать напрямую

# 3. Запустить через Docker Compose
docker compose up -d
docker compose logs -f
```

### Откат на старую версию

Если что-то пошло не так:

```bash
# Остановить новую версию
docker compose down

# Восстановить .env
cp .env.backup .env

# Если есть старый docker-compose.yml с build:
# docker-compose -f docker-compose.old.yml up -d --build
```

### Обновление в будущем

После миграции обновление до новых версий — одна команда:

```bash
docker compose pull && docker compose up -d
```

---

## Миграция: перенос Collector API с бота на Web Backend

С этой версии обработка подключений и детекция нарушений перенесена из Telegram Bot в Web Backend. Node Agent теперь отправляет данные напрямую в Web Backend (`/api/v2/collector/batch`) вместо бота (`/api/v1/connections/batch`).

### Что изменилось

| Было (старая схема) | Стало (новая схема) |
|---------------------|---------------------|
| Agent → Bot (порт 8080) → `/api/v1/connections/batch` | Agent → Web Backend (порт 8081) → `/api/v2/collector/batch` |
| Детекция нарушений в боте | Детекция нарушений в Web Backend |
| Уведомления только в Telegram | Уведомления в Telegram + in-app (веб-панель) |
| `AGENT_COLLECTOR_URL` = URL бота | `AGENT_COLLECTOR_URL` = URL Web Backend |

### Пошаговая миграция

**1. Убедитесь, что веб-панель запущена**

```bash
docker compose --profile web up -d
```

Web Backend должен быть доступен и healthy:
```bash
curl http://localhost:8081/api/v2/collector/health
# Ответ: {"status":"ok","service":"collector","database_connected":true}
```

**2. Добавьте переменные уведомлений в web-backend** (если ещё не добавлены)

В `docker-compose.yml` в секции `web-backend.environment` должны быть:
```yaml
- NOTIFICATIONS_CHAT_ID=${NOTIFICATIONS_CHAT_ID:-}
- NOTIFICATIONS_TOPIC_ID=${NOTIFICATIONS_TOPIC_ID:-}
- NOTIFICATIONS_TOPIC_VIOLATIONS=${NOTIFICATIONS_TOPIC_VIOLATIONS:-}
- NOTIFICATIONS_TOPIC_SERVICE=${NOTIFICATIONS_TOPIC_SERVICE:-}
- NOTIFICATIONS_TOPIC_ERRORS=${NOTIFICATIONS_TOPIC_ERRORS:-}
```

Перезапустите web-backend после изменений:
```bash
docker compose --profile web up -d
```

**3. Обновите `.env` на каждой ноде**

Измените `AGENT_COLLECTOR_URL`:

```bash
# Было:
AGENT_COLLECTOR_URL=https://admin.yourdomain.com
# или
AGENT_COLLECTOR_URL=http://host.docker.internal:8080

# Стало (если агент в Docker на том же хосте):
AGENT_COLLECTOR_URL=http://remnawave-web-backend:8081

# Стало (если через reverse proxy):
AGENT_COLLECTOR_URL=https://admin.yourdomain.com

# Стало (если по IP напрямую):
AGENT_COLLECTOR_URL=http://your-server-ip:8081
```

> **Важно**: Если используете reverse proxy (Caddy, Nginx), обновите конфигурацию — проксируйте `/api/v2/collector/*` на `web-backend:8081` вместо `bot:8080`.

**4. Перезапустите агент**

```bash
cd /path/to/node-agent
docker compose restart
```

**5. Проверьте подключение**

```bash
docker compose logs -f
```

Ожидаемый вывод:
```
INFO: Collector API OK: https://admin.yourdomain.com/api/v2/collector/health
INFO: Node Agent started: ...
```

Если видите ошибку 404 — агент всё ещё стучится на старый endpoint. Убедитесь, что обновили образ агента (`docker compose pull`).

**6. Обновите Caddy/Nginx (если используется reverse proxy)**

Caddy:
```caddyfile
admin.yourdomain.com {
    # Collector API (Node Agent → Web Backend)
    reverse_proxy /api/v2/collector/* web-backend:8081 {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }

    # Остальные API
    reverse_proxy /api/v2/* web-backend:8081
}
```

Nginx:
```nginx
location /api/v2/collector/ {
    proxy_pass http://web-backend:8081;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### Откат

Откат на старую схему **не поддерживается** — endpoint `/api/v1/connections/batch` удалён из бота. Если Web Backend недоступен, агент будет буферизовать данные (до `AGENT_MAX_BUFFER_SIZE`) и повторять попытки отправки. При восстановлении Web Backend все накопленные данные будут отправлены автоматически.

---

## Agent v2: Command Channel

По умолчанию агент работает только в режиме **сбора метрик** — читает логи и отправляет данные о подключениях в Collector API.

Для управления нодой через веб-панель (терминал, запуск скриптов, провижининг) необходимо включить **Command Channel** — постоянное WebSocket-соединение между агентом и бэкендом.

### Что даёт Command Channel

- **Веб-терминал** — SSH-подобный доступ к ноде прямо из браузера (xterm.js + PTY)
- **Запуск скриптов** — выполнение предустановленных скриптов на ноде (fail2ban, UFW, BBR, обновление Xray и т.д.)
- **Провижининг** — автоматическая настройка нового VPS как VPN-ноды в один клик

### Как включить

1. Добавьте в `.env` агента:

```env
AGENT_COMMAND_ENABLED=true
AGENT_WS_SECRET_KEY=тот_же_ключ_что_WEB_SECRET_KEY_на_бэкенде
```

2. `AGENT_WS_SECRET_KEY` **должен совпадать** с `WEB_SECRET_KEY` из `.env` основного проекта. Этот ключ используется для HMAC-подписи: бэкенд подписывает каждую команду, агент проверяет подпись перед выполнением.

3. Перезапустите агент:

```bash
docker compose restart
```

4. В логах должно появиться:

```
INFO: Agent v2 command channel enabled
```

Если канал выключен, в логах будет:

```
INFO: Agent v2 command channel disabled (AGENT_COMMAND_ENABLED=false)
```

### Безопасность

- Все команды подписываются HMAC-SHA256 с использованием `WEB_SECRET_KEY`
- Агент отклоняет команды с невалидной подписью
- Защита от replay-атак: команды содержат timestamp, агент принимает команды только в окне 60 секунд

---

## Устранение проблем

### Агент не отправляет данные

1. Установите `AGENT_LOG_LEVEL=DEBUG` в `.env` и перезапустите
2. Проверьте наличие файла логов: `ls -la /var/log/remnanode/access.log`
3. Проверьте формат: `tail -n 5 /var/log/remnanode/access.log` — строки должны содержать `accepted` и `email:`
4. Проверьте доступность Collector API: `curl https://admin.yourdomain.com/api/v2/collector/health`

### "Invalid token" / 403

- Токен скопирован полностью (без пробелов)?
- Токен не отозван в веб-панели / Admin Bot?
- `AGENT_NODE_UUID` соответствует ноде, для которой выдан токен?

### "User not found"

- Синхронизация пользователей работает в Web Backend?
- Email/ID в логах Xray совпадает с данными в БД?

### Логи не читаются

```bash
# Проверьте права
ls -la /var/log/remnanode/access.log

# Проверьте монтирование в Docker
docker inspect remnawave-node-agent | grep -A5 Mounts
```

### Отзыв скомпрометированного токена

1. Веб-панель или Admin Bot: **Ноды** → **Токен агента** → **Отозвать**
2. Сгенерируйте новый токен
3. Обновите `.env` на ноде
4. Перезапустите агент

---

## Полезные команды

```bash
docker compose logs -f                    # Логи
docker compose restart                    # Перезапуск
docker compose stop                       # Остановка (graceful, отправит оставшиеся данные)
docker compose down                       # Удаление контейнера
docker compose pull && docker compose up -d  # Обновление до последней версии
docker compose config                     # Проверка конфигурации
docker inspect remnawave-node-agent | grep -A3 Health  # Проверка healthcheck
```

# Remnawave Node Agent

Лёгкий агент для сбора данных о подключениях с нод (Xray) и отправки в Remnawave Admin Bot (Collector API).

Живёт в монорепо: `remnawave-admin/node-agent/`.

## Назначение

- Читает **access.log** Xray на ноде.
- Парсит строки с `accepted` (подключения пользователей).
- Периодически отправляет батч в **Admin Bot**: `POST /api/v1/connections/batch`.

Без этого агента (или альтернативного источника данных) Anti-Abuse в Admin Bot не может работать.

## Требования

- Python 3.12+
- Доступ к файлу логов на ноде: `/var/log/remnanode/access.log` (или смонтированный том в Docker).

## Конфигурация

Переменные окружения (префикс `AGENT_`):

| Переменная | Описание |
|------------|----------|
| `AGENT_NODE_UUID` | UUID ноды (из Remnawave/Admin Bot) |
| `AGENT_COLLECTOR_URL` | URL Admin Bot, например `https://admin.example.com` |
| `AGENT_AUTH_TOKEN` | **Токен агента** для этой ноды (см. `TOKEN_SETUP.md`) |
| `AGENT_INTERVAL_SECONDS` | Интервал отправки (по умолчанию 30) |
| `AGENT_XRAY_LOG_PATH` | Путь к `access.log` (по умолчанию `/var/log/remnanode/access.log`) |

**Важно:** Токен агента (`AGENT_AUTH_TOKEN`) нужно получить в Admin Bot для каждой ноды.  
См. `.env.example` и `TOKEN_SETUP.md` для инструкций по генерации токена.

## Установка

📖 **Подробная инструкция:** см. [INSTALLATION.md](INSTALLATION.md)

### Быстрый старт

1. **Получи токен агента** в Admin Bot (Ноды → Редактировать → Токен агента → Сгенерировать)
2. **Создай `.env`** файл с настройками (см. `.env.example`)
3. **Запусти агент** (Docker или локально)

```bash
# Локально
cd node-agent
pip install -r requirements.txt
cp .env.example .env
# отредактировать .env
python -m src.main
```

## Запуск в Docker

### Вариант 1: Docker Compose (рекомендуется)

```bash
cd node-agent

# 1. Создай .env файл
cp .env.example .env
nano .env  # отредактируй настройки

# 2. Запусти
docker-compose up -d

# 3. Проверь логи
docker-compose logs -f

# 4. Останови
docker-compose down
```

**Для локального тестирования** (Admin Bot на хосте):
```bash
# 1. Создай тестовый лог (опционально)
mkdir -p test-logs
cp test-logs/access.log.example test-logs/access.log
# Добавь реальные строки из Xray в test-logs/access.log

# 2. В .env укажи:
# AGENT_COLLECTOR_URL=http://host.docker.internal:8000

# 3. Запусти с локальным compose файлом
docker-compose -f docker-compose.local.yml up -d

# 4. Проверь логи
docker-compose -f docker-compose.local.yml logs -f
```

### Вариант 2: Docker напрямую

```bash
# Собери образ
docker build -f node-agent/Dockerfile -t remnawave-node-agent ./node-agent

# Запусти с переменными
docker run -d \
  --name remnawave-node-agent \
  --restart unless-stopped \
  --env-file node-agent/.env \
  -v /var/log/remnanode:/var/log/remnanode:ro \
  --network remnawave-network \
  remnawave-node-agent
```

## Настройка Caddy для Admin Bot

**Важно:** Если Admin Bot работает за обратным прокси (Caddy), необходимо настроить проксирование для Collector API.

В конфигурации Caddy для домена Admin Bot добавь правило:

```caddy
admin.domen.com {
    # Collector API - проксируем на webhook сервер бота
    reverse_proxy /api/v1/connections/* bot:8080 {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }
    
    # Webhook от Remnawave панели
    reverse_proxy /webhook bot:8080 {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }
}
```

**Примечания:**
- `bot:8080` — имя сервиса Docker и порт webhook сервера (по умолчанию 8080)
- Правило для `/api/v1/connections/*` должно быть **выше** правила для `/webhook`
- После изменения конфигурации перезагрузи Caddy: `sudo caddy reload`

📖 **Подробнее:** см. [CADDY_SETUP.md](CADDY_SETUP.md)

## Контракт с Collector API

Формат запроса (должен совпадать с Admin Bot):

- **POST** `{COLLECTOR_URL}/api/v1/connections/batch`
- **Header:** `Authorization: Bearer {AGENT_AUTH_TOKEN}`
- **Body (JSON):**
  - `node_uuid` — UUID ноды
  - `timestamp` — ISO 8601
  - `connections` — массив объектов: `user_email`, `ip_address`, `node_uuid`, `connected_at`, `disconnected_at?`, `bytes_sent`, `bytes_received`

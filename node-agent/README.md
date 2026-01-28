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

Собрать образ из корня репозитория:

```bash
docker build -f node-agent/Dockerfile -t remnawave-node-agent ./node-agent
```

Запуск с монтированием логов и переменными:

```bash
docker run -d \
  -e AGENT_NODE_UUID=xxx \
  -e AGENT_COLLECTOR_URL=http://host.docker.internal:8000 \
  -e AGENT_AUTH_TOKEN=yyy \
  -v /path/on/host/to/xray/logs:/var/log/xray:ro \
  remnawave-node-agent
```

## Контракт с Collector API

Формат запроса (должен совпадать с Admin Bot):

- **POST** `{COLLECTOR_URL}/api/v1/connections/batch`
- **Header:** `Authorization: Bearer {AGENT_AUTH_TOKEN}`
- **Body (JSON):**
  - `node_uuid` — UUID ноды
  - `timestamp` — ISO 8601
  - `connections` — массив объектов: `user_email`, `ip_address`, `node_uuid`, `connected_at`, `disconnected_at?`, `bytes_sent`, `bytes_received`

Подробнее см. `DEVELOPMENT_PLAN.md` и реализацию Collector в Admin Bot.

# Remnawave Node Agent

Агент для сбора данных о подключениях с нод (Xray) и отправки в Admin Bot (Collector API).

Без этого агента Anti-Abuse система Admin Bot не может работать.

---

## Как это работает

1. Агент читает `access.log` Xray на ноде
2. Парсит строки с подключениями пользователей
3. Периодически отправляет батч в Admin Bot: `POST /api/v1/connections/batch`

## Требования

- Python 3.12+ (или Docker)
- Доступ к файлу логов Xray: `/var/log/remnanode/access.log`
- Токен агента (генерируется в Admin Bot)
- UUID ноды (из Remnawave / Admin Bot)

---

## Установка

### Шаг 1: Получение токена агента

1. Открой Admin Bot в Telegram
2. **Ноды** → выбери ноду → **Редактировать** → **Токен агента** → **Сгенерировать**
3. **Скопируй токен** — он показывается только один раз

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

| Переменная | Описание |
|------------|----------|
| `AGENT_NODE_UUID` | UUID ноды (из Remnawave/Admin Bot) |
| `AGENT_COLLECTOR_URL` | URL Admin Bot |
| `AGENT_AUTH_TOKEN` | Токен агента для этой ноды |
| `AGENT_INTERVAL_SECONDS` | Интервал отправки (по умолчанию 30) |
| `AGENT_XRAY_LOG_PATH` | Путь к `access.log` (по умолчанию `/var/log/remnanode/access.log`) |

### Шаг 3: Запуск

#### Docker Compose (рекомендуется)

```bash
cd node-agent
docker-compose up -d
docker-compose logs -f
```

#### Docker напрямую

```bash
docker build -f node-agent/Dockerfile -t remnawave-node-agent ./node-agent

docker run -d \
  --name remnawave-node-agent \
  --restart unless-stopped \
  --env-file node-agent/.env \
  -v /var/log/remnanode:/var/log/remnanode:ro \
  --network remnawave-network \
  remnawave-node-agent
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
INFO: Node Agent started: node_uuid=..., collector=..., interval=30s
INFO: Log file found: /var/log/remnanode/access.log (size: X bytes)
INFO: Log parsing: total_lines=X accepted_lines=X connections=X
INFO: Batch sent successfully: X connections
```

---

## Настройка Caddy для Admin Bot

Если Admin Bot за обратным прокси (Caddy), добавь проксирование Collector API:

```caddyfile
admin.yourdomain.com {
    reverse_proxy /api/v1/connections/* bot:8080 {
        header_up X-Real-IP {remote_host}
        header_up X-Forwarded-For {remote_host}
        header_up X-Forwarded-Proto {scheme}
    }

    reverse_proxy /webhook bot:8080 {
        header_up X-Real-IP {remote_host}
    }
}
```

---

## Контракт с Collector API

- **POST** `{COLLECTOR_URL}/api/v1/connections/batch`
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

Регулярное выражение:
```regex
(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+from\s+(\d+\.\d+\.\d+\.\d+):(\d+)\s+accepted.*?email:\s*(\d+)
```

В логах Remnawave `email: 154` — это ID пользователя, не email. Collector API автоматически ищет пользователя по `short_uuid`, email или ID.

Если формат логов другой — обновите регулярное выражение в `src/collectors/xray_log.py`.

---

## Устранение проблем

### Агент не отправляет данные

1. Установите `AGENT_LOG_LEVEL=DEBUG` в `.env` и перезапустите
2. Проверьте наличие файла логов: `ls -la /var/log/remnanode/access.log`
3. Проверьте формат: `tail -n 5 /var/log/remnanode/access.log` — строки должны содержать `accepted` и `email:`
4. Проверьте доступность Collector API: `curl https://admin.yourdomain.com/api/v1/connections/health`

### "Invalid token" / 403

- Токен скопирован полностью (без пробелов)?
- Токен не отозван в Admin Bot?
- `AGENT_NODE_UUID` соответствует ноде, для которой выдан токен?

### "User not found"

- Синхронизация пользователей работает в Admin Bot?
- Email/ID в логах Xray совпадает с данными в БД?

### Логи не читаются

```bash
# Проверьте права
ls -la /var/log/remnanode/access.log

# Проверьте монтирование в Docker
docker inspect remnawave-node-agent | grep -A5 Mounts
```

### Отзыв скомпрометированного токена

1. Admin Bot: **Ноды** → **Редактировать** → **Токен агента** → **Отозвать**
2. Сгенерируйте новый токен
3. Обновите `.env` на ноде
4. Перезапустите агент

---

## Полезные команды

```bash
docker-compose logs -f          # Логи
docker-compose restart          # Перезапуск
docker-compose down             # Остановка
docker-compose build --no-cache # Пересборка
docker-compose config           # Проверка конфигурации
```

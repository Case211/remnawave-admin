# Установка Node Agent

Пошаговая инструкция по установке и настройке Node Agent на ноде.

## Предварительные требования

1. ✅ **Токен агента** — сгенерирован в Admin Bot для этой ноды
2. ✅ **UUID ноды** — из Remnawave/Admin Bot
3. ✅ **URL Collector API** — адрес Admin Bot (например, `https://admin.example.com` или `http://host.docker.internal:8000` для локального теста)
4. ✅ **Доступ к логам** — путь к `access.log` на ноде (обычно `/var/log/remnanode/access.log`)

## Шаг 1: Получение токена агента

1. Открой Admin Bot в Telegram
2. Перейди в **Ноды** → выбери нужную ноду
3. Нажми **✏️ Редактировать**
4. Нажми **🔑 Токен агента**
5. Нажми **➕ Сгенерировать**
6. **Скопируй токен** — он показывается только один раз!

## Шаг 2: Подготовка окружения

### Вариант A: Docker (рекомендуется)

```bash
# 1. Скопируй node-agent на сервер ноды
scp -r node-agent/ user@node-server:/opt/remnawave-node-agent/

# 2. Подключись к серверу
ssh user@node-server
cd /opt/remnawave-node-agent/node-agent

# 3. Создай .env файл
cp .env.example .env
nano .env
```

### Вариант B: Локальная установка

```bash
# 1. Установи зависимости
cd node-agent
pip install -r requirements.txt

# 2. Создай .env файл
cp .env.example .env
nano .env
```

## Шаг 3: Настройка .env

Отредактируй `.env` файл:

```env
# UUID ноды (из Admin Bot)
AGENT_NODE_UUID=fd3a2983-4f68-45eb-8652-7557d7e15f7a

# URL Collector API (Admin Bot)
# Для локального теста: http://host.docker.internal:8000
# Для продакшена: https://admin.yourdomain.com
AGENT_COLLECTOR_URL=https://admin.yourdomain.com

# Токен агента (скопирован из Admin Bot)
AGENT_AUTH_TOKEN=your-generated-token-here

# Интервал отправки батчей (секунды)
AGENT_INTERVAL_SECONDS=30

# Путь к access.log на ноде
AGENT_XRAY_LOG_PATH=/var/log/remnanode/access.log

# Уровень логов (опционально)
# AGENT_LOG_LEVEL=INFO
```

## Шаг 4: Запуск агента

### Docker

```bash
# Собери образ (из корня репозитория)
docker build -f node-agent/Dockerfile -t remnawave-node-agent ./node-agent

# Запусти контейнер с монтированием логов
docker run -d \
  --name remnawave-node-agent \
  --restart unless-stopped \
  -v /var/log/remnanode:/var/log/remnanode:ro \
  --env-file node-agent/.env \
  remnawave-node-agent
```

### Локально

```bash
cd node-agent
python -m src.main
```

### Systemd (для автозапуска)

Создай файл `/etc/systemd/system/remnawave-node-agent.service`:

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

Затем:

```bash
sudo systemctl daemon-reload
sudo systemctl enable remnawave-node-agent
sudo systemctl start remnawave-node-agent
sudo systemctl status remnawave-node-agent
```

## Шаг 5: Проверка работы

### Проверка логов агента

```bash
# Docker
docker logs -f remnawave-node-agent

# Systemd
sudo journalctl -u remnawave-node-agent -f
```

Ожидаемые логи:
```
INFO: Node Agent started: node_uuid=..., collector=..., interval=30s
DEBUG: Collected X connections from log
DEBUG: Batch sent: X connections, response {...}
```

### Проверка Collector API

В Admin Bot проверь логи webhook сервера — должны появляться записи о полученных батчах:

```
INFO: Batch processed: node=... connections=X processed=X errors=0
```

### Проверка данных в БД

Подключись к PostgreSQL и проверь таблицу `user_connections`:

```sql
SELECT * FROM user_connections 
WHERE node_uuid = 'your-node-uuid' 
ORDER BY connected_at DESC 
LIMIT 10;
```

## Устранение проблем

### Агент не отправляет данные

1. **Проверь токен**: убедись, что токен правильный и не был отозван
2. **Проверь URL**: `AGENT_COLLECTOR_URL` должен быть доступен с ноды
3. **Проверь логи**: смотри ошибки в логах агента
4. **Проверь сеть**: убедись, что нода может достучаться до Admin Bot

### Ошибка "Invalid token"

1. Проверь, что токен скопирован полностью (без пробелов)
2. Убедись, что токен не был отозван в Admin Bot
3. Проверь, что `AGENT_NODE_UUID` соответствует ноде, для которой был выдан токен

### Ошибка "User not found"

Агент находит подключения, но пользователи не найдены в БД:
- Убедись, что синхронизация пользователей работает в Admin Bot
- Проверь, что email в логах Xray совпадает с email в БД

### Логи не читаются

1. Проверь права доступа к файлу логов:
   ```bash
   ls -la /var/log/remnanode/access.log
   ```

2. Если используешь Docker, убедись, что том смонтирован:
   ```bash
   docker inspect remnawave-node-agent | grep Mounts
   ```

3. Проверь путь в `.env`: `AGENT_XRAY_LOG_PATH`

## Обновление агента

```bash
# Останови агент
docker stop remnawave-node-agent
# или
sudo systemctl stop remnawave-node-agent

# Обнови код
git pull
# или скопируй новую версию

# Пересобери образ (если Docker)
docker build -f node-agent/Dockerfile -t remnawave-node-agent ./node-agent

# Запусти снова
docker start remnawave-node-agent
# или
sudo systemctl start remnawave-node-agent
```

## Отзыв токена

Если токен скомпрометирован:

1. В Admin Bot: **Ноды** → **Редактировать** → **Токен агента** → **🚫 Отозвать**
2. Сгенерируй новый токен
3. Обнови `.env` файл на ноде
4. Перезапусти агент

---

**Готово!** Агент должен начать отправлять данные о подключениях в Collector API.

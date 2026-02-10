# Веб-панель Remnawave Admin

Веб-интерфейс для управления Remnawave ботом.

## Структура

```
web/
├── backend/          # FastAPI бэкенд
│   ├── api/          # API эндпоинты
│   ├── core/         # Конфигурация, безопасность
│   ├── schemas/      # Pydantic схемы
│   └── Dockerfile
├── frontend/         # React + TypeScript фронтенд
│   ├── src/
│   └── Dockerfile
└── README.md
```

## Быстрый старт

### 1. Настройка .env

```bash
# Скопируйте .env.example в .env и настройте:
cp .env.example .env

# Сгенерируйте секретный ключ для JWT:
openssl rand -hex 32
```

Обязательные переменные для веб-панели:
```env
WEB_SECRET_KEY=ваш_сгенерированный_ключ
TELEGRAM_BOT_USERNAME=username_вашего_бота
ADMINS=123456789  # Ваш Telegram ID
```

### 2. Запуск

```bash
# Бот + веб-панель
docker compose --profile web up -d

# Или только бот (без веб-панели)
docker compose up -d
```

### 3. Настройка домена

Настройте домен в Telegram BotFather:
1. Откройте @BotFather
2. /mybots → выберите бота → Bot Settings → Domain
3. Добавьте ваш домен ПАНЕЛИ (например: `admin.yourdomain.com`)

## Порты

| Сервис | Порт | Описание |
|--------|------|----------|
| Frontend | 3000 | React (Nginx) |
| Backend | 8081 | FastAPI API |
| PostgreSQL | 5432 | База данных |

## Архитектура

```
                    ┌─────────────────────────────────────┐
                    │        PostgreSQL (общая БД)        │
                    └────────────────┬────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
              ▼                      ▼                      ▼
        ┌───────────┐         ┌───────────┐         ┌───────────┐
        │    Bot    │         │  Backend  │         │ Frontend  │
        │   :8080   │         │   :8081   │         │   :3000   │
        └───────────┘         └───────────┘         └───────────┘
```

## Настройка реверс-прокси

### Вариант 1: Caddy (рекомендуется)

Caddy автоматически получает SSL сертификаты от Let's Encrypt.

Создайте файл `Caddyfile`:

```caddyfile
admin.yourdomain.com {
    # Frontend
    handle {
        reverse_proxy web-frontend:80
    }

    # Backend API
    handle /api/* {
        reverse_proxy web-backend:8081
    }

    # WebSocket
    handle /ws/* {
        reverse_proxy web-backend:8081
    }
}
```

Запуск:
```bash
docker run -d \
  --name caddy \
  --network remnawave-network \
  -p 80:80 -p 443:443 \
  -v $(pwd)/Caddyfile:/etc/caddy/Caddyfile \
  -v caddy_data:/data \
  caddy:alpine
```

### Вариант 2: Nginx

Создайте файл `nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server web-backend:8081;
    }

    upstream frontend {
        server web-frontend:80;
    }

    server {
        listen 80;
        server_name admin.yourdomain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name admin.yourdomain.com;

        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;

        # Frontend
        location / {
            proxy_pass http://frontend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        # Backend API
        location /api/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # WebSocket
        location /ws/ {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
        }
    }
}
```

Запуск:
```bash
docker run -d \
  --name nginx \
  --network remnawave-network \
  -p 80:80 -p 443:443 \
  -v $(pwd)/nginx.conf:/etc/nginx/nginx.conf:ro \
  -v $(pwd)/ssl:/etc/nginx/ssl:ro \
  nginx:alpine
```

## Аутентификация

Используется Telegram Login Widget. Доступ имеют только пользователи из списка `ADMINS`.

### Как узнать свой Telegram ID

1. Напишите боту @userinfobot в Telegram
2. Он пришлёт ваш ID
3. Добавьте его в `ADMINS` в .env

## API эндпоинты

| Эндпоинт | Метод | Описание |
|----------|-------|----------|
| `/api/v2/auth/telegram` | POST | Вход через Telegram |
| `/api/v2/auth/refresh` | POST | Обновление токена |
| `/api/v2/auth/me` | GET | Информация о текущем админе |
| `/api/v2/users` | GET | Список пользователей |
| `/api/v2/nodes` | GET | Список нод |
| `/api/v2/health` | GET | Проверка здоровья |

## Частые проблемы

### "Not an admin" при входе

Убедитесь, что ваш Telegram ID добавлен в `ADMINS` в .env файле.

### Telegram Login Widget не работает

1. Проверьте, что `TELEGRAM_BOT_USERNAME` указан правильно (без @)
2. Убедитесь, что домен добавлен в настройках бота в BotFather
3. Сайт должен работать по HTTPS

### Ошибка подключения к базе данных

Убедитесь, что `DATABASE_URL` в .env совпадает с `POSTGRES_USER` и `POSTGRES_PASSWORD`.

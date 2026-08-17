# Веб-панель и reverse proxy

Панель поднимается вместе с ботом обычным `docker compose up -d` — отдельный профиль для неё не нужен.

| Контейнер | Порт | Что это |
|-----------|------|---------|
| `web-frontend` | 3000 | статика React за nginx |
| `web-backend` | 8081 | API и WebSocket |
| `bot` | 8080 | приём webhook от панели Remnawave |
| `remnawave-admin-db` | 5432 | PostgreSQL |

Наружу эти порты выставлять не нужно: перед панелью ставится Caddy или nginx, он же занимается сертификатом.

## Домен в BotFather

Без этого шага вход через Telegram работать не будет: виджет проверяет, что сайт — тот самый.

1. Откройте [@BotFather](https://t.me/BotFather) → `/mybots` → ваш бот
2. Bot Settings → Domain
3. Укажите домен панели, например `admin.example.com`

Сайт должен открываться по HTTPS.

## Caddy

Сам получает сертификат Let's Encrypt, поэтому в большинстве установок это самый короткий путь.

```nginx
admin.example.com {
    handle /api/* {
        reverse_proxy web-backend:8081 {
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
        }
    }

    # WebSocket: браузер и агенты нод
    handle /ws/* {
        reverse_proxy web-backend:8081
    }

    handle {
        reverse_proxy web-frontend:80
    }
}
```

```bash
docker run -d \
  --name caddy \
  --network remnawave-network \
  -p 80:80 -p 443:443 \
  -v $(pwd)/Caddyfile:/etc/caddy/Caddyfile \
  -v caddy_data:/data \
  caddy:alpine
```

## nginx

```nginx
server {
    listen 443 ssl http2;
    server_name admin.example.com;

    ssl_certificate     /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;

    location / {
        proxy_pass http://web-frontend:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://web-backend:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket агентов нод — без этого блока агент не подключится
    location /api/v2/agent/ws {
        proxy_pass http://web-backend:8081;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # WebSocket браузера — живые обновления в интерфейсе
    location /ws/ {
        proxy_pass http://web-backend:8081;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

::: warning Забытый WebSocket — самая частая поломка
Если агент отвечает `server rejected WebSocket connection: HTTP 404`, значит прокси не пропускает `/api/v2/agent/ws`. Без постоянного соединения не работают терминал, живой статус ноды и рассылка настроек на ноды.
:::

::: warning За Cloudflare или чужим прокси
Панель обязана знать настоящий адрес клиента: на нём держатся блокировки по IP и разбор нарушений. Пропишите доверенные прокси в `WEB_TRUSTED_PROXIES`, иначе все запросы будут выглядеть пришедшими с адреса прокси.
:::

## Split-режим для больших установок

Агенты нод шлют данные пачками, и на крупных установках их поток мешает интерфейсу. Тогда коллектор выносится в отдельный контейнер:

```bash
# в .env
APP_MODE=api

docker compose --profile collector up -d
```

Порт API при этом меняется на **8082**, а `/api/v2/collector/*` обслуживает контейнер `web-collector:8081`:

```nginx
admin.example.com {
    handle /api/v2/collector/* {
        reverse_proxy web-collector:8081 {
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
        }
    }

    handle /api/* {
        reverse_proxy web-backend:8082 {
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
        }
    }

    handle /ws/* {
        reverse_proxy web-backend:8082
    }

    handle {
        reverse_proxy web-frontend:80
    }
}
```

::: danger Не берите этот конфиг «на всякий случай»
Без реально поднятого `web-collector` ссылки на него и на порт 8082 дадут `502 Bad Gateway`: в обычном режиме бэкенд слушает 8081, а контейнера `web-collector` попросту нет.
:::

## Секретный путь

Панель можно спрятать за префиксом — она откроется только по нему:

```ini
WEB_SECRET_PATH=my-secret-path
```

Это не замена аутентификации, но убирает панель из поля зрения сканеров. Рядом полезен `WEB_ALLOWED_IPS` — белый список сетей в формате CIDR.

# Web panel and reverse proxy

The panel starts together with the bot via a plain `docker compose up -d` — no separate profile needed.

| Container | Port | What it is |
|-----------|------|------------|
| `web-frontend` | 3000 | React build served by nginx |
| `web-backend` | 8081 | API and WebSocket |
| `bot` | 8080 | receives webhooks from the Remnawave panel |
| `remnawave-admin-db` | 5432 | PostgreSQL |

None of these should face the internet directly: put Caddy or nginx in front and let it handle certificates.

## Domain in BotFather

Without this step Telegram login will not work: the widget verifies the site is the one it expects.

1. Open [@BotFather](https://t.me/BotFather) → `/mybots` → your bot
2. Bot Settings → Domain
3. Enter the panel domain, e.g. `admin.example.com`

The site must be served over HTTPS.

## Caddy

Gets a Let's Encrypt certificate on its own, which makes it the shortest path for most setups.

```nginx
admin.example.com {
    handle /api/* {
        reverse_proxy web-backend:8081 {
            header_up X-Real-IP {remote_host}
            header_up X-Forwarded-For {remote_host}
            header_up X-Forwarded-Proto {scheme}
        }
    }

    # WebSocket: browser and node agents
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

    # Node agent WebSocket — without this block agents cannot connect
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

    # Browser WebSocket — live updates in the interface
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

::: warning The forgotten WebSocket is the most common breakage
If an agent reports `server rejected WebSocket connection: HTTP 404`, the proxy is not passing `/api/v2/agent/ws`. Without that persistent connection there is no terminal, no live node status and no settings push to nodes.
:::

::: warning Behind Cloudflare or someone else's proxy
The panel has to know the real client address — IP blocks and violation analysis depend on it. List your trusted proxies in `WEB_TRUSTED_PROXIES`, otherwise every request looks like it came from the proxy.
:::

## Split mode for large installs

Node agents send data in batches, and on big installs that traffic competes with the interface. The collector can be moved into its own container:

```bash
# in .env
APP_MODE=api

docker compose --profile collector up -d
```

The API port becomes **8082**, and `/api/v2/collector/*` is served by `web-collector:8081`:

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

::: danger Do not copy this config "just in case"
Without an actual `web-collector` container, references to it and to port 8082 return `502 Bad Gateway`: in normal mode the backend listens on 8081 and `web-collector` does not exist.
:::

## Secret path

The panel can hide behind a prefix and open only under it:

```ini
WEB_SECRET_PATH=my-secret-path
```

This is not a replacement for authentication, but it does take the panel out of scanners' sight. `WEB_ALLOWED_IPS` — a CIDR allowlist — pairs well with it.

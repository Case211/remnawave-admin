# Environment variables

Few of them are required — everything else has sensible defaults. Most settings are changed in the panel interface without a restart; `.env` only provides the starting value. Everything configurable from the interface is broken down in [Panel settings](/en/reference/settings).

The order of precedence is **database → `.env` → defaults**. Once a setting has been changed in the interface, it stops depending on `.env`.

## Core

| Variable | Required | Default | What it sets |
|----------|----------|---------|--------------|
| `BOT_TOKEN` | yes | — | bot token from [@BotFather](https://t.me/BotFather) |
| `API_BASE_URL` | yes | — | Remnawave panel API address |
| `API_TOKEN` | yes | — | panel API token |
| `ADMINS` | yes | — | administrator Telegram IDs, comma-separated |
| `DEFAULT_LOCALE` | — | `ru` | interface language: `ru` or `en` |
| `LOG_LEVEL` | — | `INFO` | logging level |
| `BOT_API_ROOT` | — | `https://api.telegram.org` | custom Bot API server |
| `BOT_PROXY_URL` | — | — | proxy to Telegram: `socks5://`, `socks4://`, `http://`, credentials allowed. `socks5h://` and `https://` are not supported |
| `PANEL_API_KEY` | — | — | extra key if the panel requires one |

## Database

| Variable | Required | Default | What it sets |
|----------|----------|---------|--------------|
| `POSTGRES_USER` | yes | — | PostgreSQL user |
| `POSTGRES_PASSWORD` | yes | — | its password |
| `POSTGRES_DB` | yes | — | database name |
| `DATABASE_URL` | yes | — | full connection string |
| `DB_POOL_MIN_SIZE` | — | `2` | lower bound of the connection pool |
| `DB_POOL_MAX_SIZE` | — | `10` | upper bound |
| `SYNC_INTERVAL_SECONDS` | — | `300` | how often to sync with the panel |

::: warning Three places that drift apart
The password inside `DATABASE_URL` must match `POSTGRES_PASSWORD`. This is the most common cause of a database connection error right after installation.
:::

## Web panel

| Variable | Required | Default | What it sets |
|----------|----------|---------|--------------|
| `WEB_SECRET_KEY` | yes | — | session signing key, at least 32 characters |
| `TELEGRAM_BOT_USERNAME` | yes | — | bot username without `@`, needed for Telegram login |
| `WEB_CORS_ORIGINS` | — | — | domains allowed to call the API |
| `WEB_JWT_EXPIRE_MINUTES` | — | `30` | access token lifetime |
| `WEB_JWT_REFRESH_HOURS` | — | `6` | refresh token lifetime |
| `WEB_BACKEND_PORT` | — | `8081` | backend port |
| `WEB_FRONTEND_PORT` | — | `3000` | frontend port |
| `WEB_ALLOWED_IPS` | — | — | allowlist of addresses and CIDR ranges |
| `WEB_TRUSTED_PROXIES` | — | — | which proxies to trust in `X-Forwarded-For` |
| `WEB_SECRET_PATH` | — | — | secret URL prefix for the panel |
| `WEB_ADMIN_LOGIN` | — | — | fallback administrator login |
| `WEB_ADMIN_PASSWORD` | — | — | fallback password |
| `APP_MODE` | — | `full` | `api` moves the collector into its own container |
| `REDIS_URL` | — | — | shared cache and limits across instances |
| `INTERNAL_API_SECRET` | — | — | key for internal calls between bot and backend |
| `INTERNAL_API_BACKEND_URL` | — | `http://web-backend:8081` | backend address for those calls |

## Public API

| Variable | Default | What it sets |
|----------|---------|--------------|
| `EXTERNAL_API_ENABLED` | `false` | enables [API v3](/en/reference/api) |
| `EXTERNAL_API_DOCS` | `false` | serves Swagger UI for it |

## Panel webhook

| Variable | Default | What it sets |
|----------|---------|--------------|
| `WEBHOOK_PORT` | `8080` | receiving port |
| `WEBHOOK_SECRET` | — | signature key, same as in the panel |

Details: [Panel webhook](/en/guide/webhook-setup).

## Notifications

| Variable | What it sets |
|----------|--------------|
| `NOTIFICATIONS_CHAT_ID` | chat or channel for notifications |
| `NOTIFICATIONS_TOPIC_ID` | fallback topic |
| `NOTIFICATIONS_TOPIC_USERS` | users |
| `NOTIFICATIONS_TOPIC_NODES` | nodes |
| `NOTIFICATIONS_TOPIC_SERVICE` | service events |
| `NOTIFICATIONS_TOPIC_HWID` | devices |
| `NOTIFICATIONS_TOPIC_CRM` | billing |
| `NOTIFICATIONS_TOPIC_FINANCE` | finance |
| `NOTIFICATIONS_TOPIC_ERRORS` | errors |
| `NOTIFICATIONS_TOPIC_VIOLATIONS` | violations |

## GeoIP (MaxMind GeoLite2)

| Variable | Default | What it sets |
|----------|---------|--------------|
| `MAXMIND_LICENSE_KEY` | — | MaxMind key; when set, databases download and refresh themselves |
| `MAXMIND_CITY_DB` | `/app/geoip/GeoLite2-City.mmdb` | city database path |
| `MAXMIND_ASN_DB` | `/app/geoip/GeoLite2-ASN.mmdb` | ASN database path |

Without MaxMind the panel queries ip-api.com — free, but around a thousand requests a day. With a local database lookups are instant and unlimited.

To get a key: sign up at [maxmind.com](https://www.maxmind.com/en/geolite2/signup) → Account → Manage License Keys → Generate New License Key. The databases download at startup and refresh daily.

## Mail server

| Variable | Default | What it sets |
|----------|---------|--------------|
| `MAIL_SERVER_ENABLED` | `false` | enables the [mail server](/en/guide/mail) |
| `MAIL_INBOUND_PORT` | `2525` | inbound mail port |
| `MAIL_SUBMISSION_PORT` | `587` | submission port |
| `MAIL_SERVER_HOSTNAME` | `0.0.0.0` | address to listen on |
| `MAIL_TLS_CERT_PATH` | — | certificate for STARTTLS |
| `MAIL_TLS_KEY_PATH` | — | its key |

## Monitoring

| Variable | Default | What it sets |
|----------|---------|--------------|
| `METRICS_AUTH_TOKEN` | — | protects `/metrics` with a bearer token |
| `PROMETHEUS_PORT` | `9090` | built-in Prometheus port |
| `PROMETHEUS_RETENTION` | `30d` | metric retention |

## Bedolaga Bot

| Variable | What it sets |
|----------|--------------|
| `BEDOLAGA_API_URL` | Bedolaga Bot API address |
| `BEDOLAGA_API_TOKEN` | its access token |

## Node Agent

Agent variables are set on the node itself: see [Node Agent](/en/guide/node-agent#agent-variables) and [Torrent detection](/en/guide/torrents#fine-tuning).

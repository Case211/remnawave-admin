# Server requirements

## Hardware

Numbers assume the bot, the web panel and PostgreSQL on one server.

| | Up to 1,000 users | 1,000–5,000 | 5,000–20,000 | 20,000+ |
|---|---|---|---|---|
| CPU | 2 vCPU | 4 vCPU | 8 vCPU | 8–16 vCPU |
| RAM | 4 GB | 8 GB | 16+ GB | 32+ GB |
| Disk | 40 GB SSD | 80 GB SSD | 240 GB NVMe | 240+ GB NVMe |
| PostgreSQL | defaults | tuning advised | tuning required | dedicated server |

The Node Agent takes about 50 MB of RAM on each node.

::: tip When to change what
Past 5,000 users, plug in [MaxMind GeoIP](/en/reference/env#geoip-maxmind-geolite2) — a local database instead of calls to ip-api.com. Past 20,000, move PostgreSQL to its own server.
:::

## Software

- Docker and Docker Compose
- PostgreSQL 15+ (comes up inside compose)
- A Remnawave panel with the API enabled

Images are built for both `linux/amd64` and `linux/arm64`.

## Get these ready

| What | Where from |
|------|-----------|
| Telegram bot token | [@BotFather](https://t.me/BotFather) → `/newbot` |
| Remnawave API token | Panel → Settings → API |
| Your Telegram ID | [@userinfobot](https://t.me/userinfobot) replies with the numeric ID |
| Two A records | one for the web panel, one for the bot webhook |

## Ports

| Port | Listener | Exposed |
|------|----------|---------|
| 3000 | web panel frontend | behind a reverse proxy |
| 8081 | web panel backend | behind a reverse proxy |
| 8080 | bot webhook server | behind a reverse proxy |
| 2525 | inbound mail, if the [mail server](/en/guide/mail) is on | published as 25 |
| 587 | SMTP submission | if needed |

Nothing needs to be exposed directly: the panel expects to sit behind Caddy or nginx.

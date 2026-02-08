# Remnawave Admin Bot

<div align="center">

**Telegram bot and web panel for managing Remnawave panel**

[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.12+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

[English](README_EN.md) | [Русский](README.md)

</div>

---

## Features

### Telegram Bot
- **Users** — search, create, edit, HWID devices, statistics, bulk operations
- **Nodes** — view, enable/disable, restart, traffic monitoring, statistics
- **Hosts** — view, create, edit, bulk operations
- **Resources** — subscription templates, snippets, API tokens, configs
- **Billing** — payment history, providers, billing nodes
- **System** — health checks, statistics, traffic

### Web Panel
- Dashboard with system overview and violation charts
- User, node, and host management
- Violation viewer with IP Lookup (provider, city, connection type)
- Settings with auto-save (priority: DB > .env > defaults)
- Telegram Login Widget + JWT authentication
- Dark theme, responsive design

### Anti-Abuse System
- Multi-factor connection analysis (temporal, geographic, ASN, profile, device)
- "Impossible travel" detection, 60+ Russian metropolitan area recognition
- Automatic actions based on scoring thresholds
- Integration with [Node Agent](node-agent/README.md) for data collection

### Additional
- Dynamic settings without restart (Telegram and web panel)
- Webhook notifications with topic routing
- Russian and English language support
- PostgreSQL with graceful degradation (works without DB too)

---

## Quick Start

### Prerequisites

- **Docker** and **Docker Compose** (recommended) or **Python 3.12+**
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- Remnawave API access token

### 1. Clone and configure

```bash
git clone https://github.com/case211/remnawave-admin.git
cd remnawave-admin
cp .env.example .env
nano .env
```

**Required variables:**

```env
BOT_TOKEN=your_telegram_bot_token
API_BASE_URL=http://remnawave:3000       # Docker network
API_TOKEN=your_api_token
ADMINS=123456789,987654321               # Administrator IDs
```

**Optional (notifications, webhook):**

```env
NOTIFICATIONS_CHAT_ID=-1001234567890
WEBHOOK_SECRET=your_secret_key           # Must match WEBHOOK_SECRET_HEADER in panel
WEBHOOK_PORT=8080
```

> Get your Telegram ID: [@userinfobot](https://t.me/userinfobot)

### 2. Deploy

```bash
docker network create remnawave-network

# Bot only
docker compose up -d

# Bot + web panel
docker compose --profile web up -d
```

### 3. Configure webhook (optional)

Detailed instructions: [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md)

Quick setup: in Remnawave panel set webhook URL to `http://bot:8080/webhook` and set `WEBHOOK_SECRET_HEADER` equal to bot's `WEBHOOK_SECRET`.

---

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: API_BASE_URL=https://your-panel-domain.com/api
python -m src.main
```

---

## Configuration

### Core Environment Variables

| Variable | Req. | Default | Description |
|----------|------|---------|-------------|
| `BOT_TOKEN` | Yes | — | Telegram bot token |
| `API_BASE_URL` | Yes | — | Remnawave API URL |
| `API_TOKEN` | Yes | — | API authentication token |
| `ADMINS` | Yes | — | Comma-separated administrator IDs |
| `DEFAULT_LOCALE` | — | `ru` | Language (`ru` / `en`) |
| `LOG_LEVEL` | — | `INFO` | Logging level |
| `DATABASE_URL` | — | — | PostgreSQL connection URL |
| `SYNC_INTERVAL_SECONDS` | — | `300` | Data sync interval with API (sec) |

### Notifications

| Variable | Description |
|----------|-------------|
| `NOTIFICATIONS_CHAT_ID` | Group/channel ID |
| `NOTIFICATIONS_TOPIC_ID` | General topic (fallback) |
| `NOTIFICATIONS_TOPIC_USERS` | User notifications topic |
| `NOTIFICATIONS_TOPIC_NODES` | Node notifications topic |
| `NOTIFICATIONS_TOPIC_SERVICE` | Service notifications |
| `NOTIFICATIONS_TOPIC_HWID` | HWID notifications |
| `NOTIFICATIONS_TOPIC_CRM` | Billing notifications |
| `NOTIFICATIONS_TOPIC_ERRORS` | Error notifications |
| `NOTIFICATIONS_TOPIC_VIOLATIONS` | Violation notifications |

### Webhook

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_SECRET` | — | Webhook verification key (HMAC-SHA256) |
| `WEBHOOK_PORT` | `8080` | Webhook server port |

---

## Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Main menu |
| `/help` | Help |
| `/health` | System health status |
| `/stats` | Panel statistics |
| `/bandwidth` | Traffic statistics |
| `/config` | Dynamic settings |
| `/user <username\|id>` | User information |
| `/node <uuid>` | Node information |
| `/host <uuid>` | Host information |

---

## Logging

Two-tier system: **files** (full history) and **console** (WARNING+ only).

| File | Level | Contents |
|------|-------|----------|
| `adminbot_INFO.log` | INFO+ | Everything: API calls, sync, actions |
| `adminbot_WARNING.log` | WARNING+ | Problems: timeouts, errors |
| `web_INFO.log` | INFO+ | Web backend logs |
| `web_WARNING.log` | WARNING+ | Web backend problems |

Rotation: 50 MB per file, 5 backups (gzip). Files in `./logs/`.

```bash
docker compose logs -f bot                    # Live logs
tail -100 ./logs/adminbot_INFO.log            # Last 100 lines
```

---

## Project Structure

```
remnawave-admin/
├── src/                        # Telegram bot
│   ├── handlers/               # Handlers (users, nodes, hosts, billing, ...)
│   ├── keyboards/              # Inline keyboards
│   ├── services/               # API client, database, violation detector, webhook, ...
│   └── utils/                  # i18n, logging, formatting
├── web/                        # Web panel
│   ├── frontend/               # React + TypeScript + Tailwind
│   └── backend/                # FastAPI backend
├── node-agent/                 # Node data collection agent
├── alembic/                    # DB migrations
├── locales/                    # Localization (ru, en)
└── docker-compose.yml          # Docker Compose (profiles: bot, web)
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md) | Webhook setup guide |
| [docs/anti-abuse.md](docs/anti-abuse.md) | Anti-Abuse system, ASN database, provider classification |
| [web/README.md](web/README.md) | Web panel: setup, reverse proxy, API |
| [web/SECURITY_AUDIT.md](web/SECURITY_AUDIT.md) | Web panel security audit |
| [node-agent/README.md](node-agent/README.md) | Node Agent: installation, configuration, troubleshooting |

---

## Troubleshooting

### Bot not responding

```bash
docker compose ps                    # Container status
docker compose logs -f bot           # Logs (WARNING+)
docker compose config                # Check configuration
```

### API connection issues

- Check `API_BASE_URL` and `API_TOKEN`
- Docker network exists: `docker network ls | grep remnawave-network`

### Access denied

- Telegram ID in `ADMINS`? Check via [@userinfobot](https://t.me/userinfobot)

### Webhook not working

- `WEBHOOK_SECRET` matches `WEBHOOK_SECRET_HEADER` in panel?
- Webhook URL accessible from panel?
- Details: [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md)

---

## Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature/amazing-feature`
3. Commit and push
4. Open a Pull Request

---

## License

MIT License — see [LICENSE](LICENSE).

## Support

- [GitHub Issues](https://github.com/case211/remnawave-admin/issues)
- [Telegram chat](https://t.me/remnawave_admin)

Support the author:
- TON: `UQDDe-jyFTbQsPHqyojdFeO1_m7uPF-q1w0g_MfbSOd3l1sC`
- USDT TRC20: `TGyHJj2PsYSUwkBbWdc7BFfsAxsE6SGGJP`
- BTC: `bc1qusrj5rxd3kv6eepzpdn0muy6zsl3c24xunz2xn`

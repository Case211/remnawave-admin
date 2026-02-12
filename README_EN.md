# 🤖 Remnawave Admin Bot

<div align="center">

**Telegram bot and web panel for managing Remnawave panel**

[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.12+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

[English](README_EN.md) | [Русский](README.md)

</div>

---

## ✨ Features

### 🤖 Telegram Bot
- **👥 Users** — search, create, edit, HWID devices, statistics, bulk operations
- **🛰 Nodes** — view, enable/disable, restart, traffic monitoring, statistics
- **🖥 Hosts** — view, create, edit, bulk operations
- **🧰 Resources** — subscription templates, snippets, API tokens, configs
- **💰 Billing** — payment history, providers, billing nodes
- **📊 System** — health checks, statistics, traffic

### 🌐 Web Panel
- 📊 Dashboard with system overview and violation charts
- 👥 User, node, and host management
- 🛡 Violation viewer with IP Lookup (provider, city, connection type)
- ⚙️ Settings with auto-save (priority: DB > .env > defaults)
- 🔐 Telegram Login Widget + JWT authentication
- 🎨 Dark theme, responsive design

### 🛡 Anti-Abuse System
- 🔍 Multi-factor connection analysis (temporal, geographic, ASN, profile, device)
- 🌍 "Impossible travel" detection, 60+ Russian metropolitan area recognition
- ⚡ Automatic actions based on scoring thresholds
- 📡 Integration with [Node Agent](node-agent/README.md) for data collection

### 📧 Built-in Mail Server
- 📤 Direct MX delivery without external SMTP providers
- 🔏 DKIM signing (RSA-2048) + automatic SPF/DKIM/DMARC verification
- 📥 Inbound email receiving (embedded SMTP server)
- 📊 Outbound queue with retries, rate limiting, and monitoring
- ✍️ Built-in compose editor + inbox viewer

### 🔧 Additional
- ⚙️ Dynamic settings without restart (Telegram and web panel)
- 🔔 Webhook notifications with topic routing
- 🌍 Russian and English language support
- 🗄 PostgreSQL with graceful degradation (works without DB too)

---

## 🚀 Quick Start

### 📋 What you'll need

| What | Where to get |
|------|-------------|
| 🐳 **Docker** + **Docker Compose** | [docker.com](https://www.docker.com/) |
| 🤖 **Telegram bot token** | Create a bot with [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token |
| 🔑 **Remnawave API token** | Remnawave Panel → Settings → API → copy the token |
| 🆔 **Your Telegram ID** | Message [@userinfobot](https://t.me/userinfobot) → it will reply with your numeric ID |

---

### Step 1️⃣ — Clone the repository

```bash
git clone https://github.com/case211/remnawave-admin.git
cd remnawave-admin
```

### Step 2️⃣ — Create the `.env` file

```bash
cp .env.example .env
nano .env          # or vim, or any editor
```

Fill in the **required** fields (bot won't start without them):

```env
# 🤖 Bot token (from @BotFather)
BOT_TOKEN=1234567890:ABCdefGHIjklmNOPqrstUVWxyz

# 🌐 Remnawave API address
# If bot and panel are on the same Docker network:
API_BASE_URL=http://remnawave:3000
# If the panel is on a different server:
# API_BASE_URL=https://panel.yourdomain.com/api

# 🔑 API token from Remnawave panel
API_TOKEN=your_token_from_panel

# 👤 Telegram IDs of administrators (comma-separated)
ADMINS=123456789
```

Configure the **database** (PostgreSQL starts automatically in Docker):

```env
# 🗄 PostgreSQL — choose a password
POSTGRES_USER=remnawave
POSTGRES_PASSWORD=choose_a_secure_password
POSTGRES_DB=remnawave_bot

# ⚠️ Password here must match POSTGRES_PASSWORD above!
DATABASE_URL=postgresql://remnawave:choose_a_secure_password@remnawave-admin-db:5432/remnawave_bot
```

### Step 3️⃣ — Start the bot

```bash
# Create Docker network (once)
docker network create remnawave-network

# Pull images and start
docker compose up -d

# Check that everything is working
docker compose logs -f bot
```

✅ **Done!** Open the bot in Telegram and send `/start`.

---

### Step 4️⃣ — Web Panel (optional)

If you want the web interface — add to `.env`:

```env
# 🌐 Web panel
# JWT secret key (generate: openssl rand -hex 32)
WEB_SECRET_KEY=generated_key_minimum_32_characters

# Bot username (without @) — needed for Telegram Login Widget
TELEGRAM_BOT_USERNAME=your_bot_username

# Web panel domain (for CORS)
WEB_CORS_ORIGINS=https://admin.yourdomain.com
```

Start with the `web` profile:

```bash
docker compose --profile web up -d
```

Web panel will be available on ports: **frontend :3000**, **backend :8081**.

> 📖 More on domain setup and reverse proxy: [web/README.md](web/README.md)

---

### Step 5️⃣ — Webhook Notifications (optional)

To get bot notifications when things change in the panel — add to `.env`:

```env
# 🔔 Notification chat
NOTIFICATIONS_CHAT_ID=-1001234567890    # Your group/channel ID

# 🔐 Webhook secret (generate: openssl rand -hex 64)
WEBHOOK_SECRET=your_secret_key
```

Then in the **Remnawave panel** set:
- **WEBHOOK_URL** = `http://bot:8080/webhook` (if on the same Docker network)
- **WEBHOOK_SECRET_HEADER** = same key as `WEBHOOK_SECRET` in the bot's `.env`

> 📖 Detailed guide with nginx/Caddy examples: [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md)

---

### Step 6️⃣ — Topic Notifications (optional)

If you have a forum-group in Telegram, you can split notifications by topics:

```env
NOTIFICATIONS_TOPIC_USERS=456       # 👥 User events
NOTIFICATIONS_TOPIC_NODES=789       # 🛰 Node events
NOTIFICATIONS_TOPIC_SERVICE=101     # ⚙️ Service events
NOTIFICATIONS_TOPIC_HWID=102        # 💻 HWID devices
NOTIFICATIONS_TOPIC_CRM=103         # 💰 Billing
NOTIFICATIONS_TOPIC_ERRORS=104      # ❌ Errors
NOTIFICATIONS_TOPIC_VIOLATIONS=105  # 🛡 Violations
```

> 💡 If a topic is not set — the notification goes to `NOTIFICATIONS_TOPIC_ID` (general fallback).

---

### Step 7️⃣ — Built-in Mail Server (optional)

The web panel includes an embedded mail server with DKIM signing, direct MX delivery, and inbound email receiving — no external SMTP providers needed.

#### Enabling

Go to **Settings** in the web panel → **"Mail Server"** section → enable **"Mail Server Enabled"**. Restart the container.

Or via `.env`:

```env
MAIL_SERVER_ENABLED=true
MAIL_INBOUND_PORT=2525          # Inbound SMTP port (default 2525)
MAIL_SERVER_HOSTNAME=0.0.0.0    # SMTP server bind address
```

> 💡 All settings can be changed from the web UI (Settings page). `.env` values serve as fallback.

#### Adding a domain

1. Go to **Mail Server** → **Domains** tab → **Add Domain**
2. Enter your domain (e.g. `example.com`)
3. The system will auto-generate DKIM keys (RSA-2048)

#### DNS configuration

Click **"DNS Records"** on your domain — the system shows 4 records to add at your DNS provider:

| Type | Host | Purpose |
|------|------|---------|
| **MX** | `example.com` | Routes incoming mail to your server |
| **TXT** | `example.com` | SPF — authorizes your IP to send email |
| **TXT** | `rw._domainkey.example.com` | DKIM — email signature verification |
| **TXT** | `_dmarc.example.com` | DMARC — policy for unverified emails |

Values can be copied from the interface. After adding, click **"Check DNS"** to verify.

#### Network ports

```
Port 25   — outbound (for direct MX delivery to recipient servers)
Port 2525 — inbound (receiving emails, configurable)
```

Add to `docker-compose.yml`:

```yaml
ports:
  - "25:2525"    # inbound email
```

> ⚠️ Many cloud providers (AWS, GCP, Azure) block port 25 by default. Use a VPS with open port 25 (Hetzner, OVH, DigitalOcean).

#### Testing

1. Activate the domain (toggle switch on the domain card)
2. Go to the **Compose** tab → select domain → enter address → **Send Test**
3. Check the **Queue** tab — status should become `sent`

> 📬 When an active outbound domain is configured, the notification system automatically uses the built-in mail server (falls back to SMTP relay).

---

## 💻 Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: API_BASE_URL=https://your-panel-domain.com/api
python -m src.main
```

---

## ⚙️ Environment Variables Reference

### Core

| Variable | Req. | Default | Description |
|----------|------|---------|-------------|
| `BOT_TOKEN` | ✅ | — | Telegram bot token |
| `API_BASE_URL` | ✅ | — | Remnawave API URL |
| `API_TOKEN` | ✅ | — | API authentication token |
| `ADMINS` | ✅ | — | Comma-separated administrator IDs |
| `DEFAULT_LOCALE` | — | `ru` | Language (`ru` / `en`) |
| `LOG_LEVEL` | — | `INFO` | Logging level |

### 🗄 Database

| Variable | Req. | Default | Description |
|----------|------|---------|-------------|
| `POSTGRES_USER` | ✅ | — | PostgreSQL user |
| `POSTGRES_PASSWORD` | ✅ | — | PostgreSQL password |
| `POSTGRES_DB` | ✅ | — | Database name |
| `DATABASE_URL` | ✅ | — | PostgreSQL connection URL |
| `SYNC_INTERVAL_SECONDS` | — | `300` | Data sync interval with API (sec) |

### 🔔 Notifications

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

### 🔗 Webhook

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_SECRET` | — | Webhook verification key (HMAC-SHA256) |
| `WEBHOOK_PORT` | `8080` | Webhook server port |

### 🌍 GeoIP (MaxMind GeoLite2)

| Variable | Req. | Default | Description |
|----------|------|---------|-------------|
| `MAXMIND_LICENSE_KEY` | — | — | MaxMind license key (free). When set — databases download automatically |
| `MAXMIND_CITY_DB` | — | `/app/geoip/GeoLite2-City.mmdb` | Path to GeoLite2-City database |
| `MAXMIND_ASN_DB` | — | `/app/geoip/GeoLite2-ASN.mmdb` | Path to GeoLite2-ASN database |

> **Without MaxMind** — uses ip-api.com (free but limited to ~1000 requests/day).
> **With MaxMind** — local database, instant lookups, no rate limits.
>
> How to set up:
> 1. Sign up at [maxmind.com/en/geolite2/signup](https://www.maxmind.com/en/geolite2/signup) (free)
> 2. Account → Manage License Keys → Generate New License Key
> 3. Add to `.env`: `MAXMIND_LICENSE_KEY=your_key`
> 4. Databases will download automatically on startup and update every 24 hours

### 🌐 Web Panel

| Variable | Req.* | Default | Description |
|----------|-------|---------|-------------|
| `WEB_SECRET_KEY` | ✅ | — | JWT secret key |
| `TELEGRAM_BOT_USERNAME` | ✅ | — | Bot username (without @) |
| `WEB_CORS_ORIGINS` | — | — | Allowed domains (CORS) |
| `WEB_JWT_EXPIRE_MINUTES` | — | `30` | Access token lifetime (min) |
| `WEB_JWT_REFRESH_HOURS` | — | `6` | Refresh token lifetime (h) |
| `WEB_BACKEND_PORT` | — | `8081` | Backend port |
| `WEB_FRONTEND_PORT` | — | `3000` | Frontend port |
| `WEB_ALLOWED_IPS` | — | — | IP whitelist (CIDR) |

*\* Required only when running with `--profile web`*

### 📧 Mail Server

| Variable | Default | Description |
|----------|---------|-------------|
| `MAIL_SERVER_ENABLED` | `false` | Enable the built-in mail server |
| `MAIL_INBOUND_PORT` | `2525` | Inbound SMTP server port |
| `MAIL_SERVER_HOSTNAME` | `0.0.0.0` | SMTP server bind address |

> 💡 These variables are fallbacks. Settings can be changed from the web panel (Settings → Mail Server).

---

## 🤖 Bot Commands

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

## 📝 Logging

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

## 📂 Project Structure

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

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [CHANGELOG.md](CHANGELOG.md) | Version history |
| [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md) | Webhook setup guide |
| [docs/anti-abuse.md](docs/anti-abuse.md) | Anti-Abuse system, ASN database, provider classification |
| [web/README.md](web/README.md) | Web panel: setup, reverse proxy, API |
| [web/SECURITY_AUDIT.md](web/SECURITY_AUDIT.md) | Web panel security audit |
| [node-agent/README.md](node-agent/README.md) | Node Agent: installation, configuration, troubleshooting |

---

## 🔧 Troubleshooting

### Bot not responding

```bash
docker compose ps                    # Container status
docker compose logs -f bot           # Logs
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

## 🤝 Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature/amazing-feature`
3. Commit and push
4. Open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE).

---

## 💖 Support

- [GitHub Issues](https://github.com/case211/remnawave-admin/issues)
- [Telegram chat](https://t.me/remnawave_admin)

Support the author:
- TON: `UQDDe-jyFTbQsPHqyojdFeO1_m7uPF-q1w0g_MfbSOd3l1sC`
- USDT TRC20: `TGyHJj2PsYSUwkBbWdc7BFfsAxsE6SGGJP`
- BTC: `bc1qusrj5rxd3kv6eepzpdn0muy6zsl3c24xunz2xn`

---

<div align="center">

Made with ❤️ for the Remnawave community

</div>

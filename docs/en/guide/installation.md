# Installation

The minimum working set is the bot and the web panel sharing a database. Mail, monitoring and the node agent are added later, one at a time.

Check the [requirements](/en/guide/requirements) first: you will need a bot token, a Remnawave API token and your Telegram ID.

## 1. Clone the repository

```bash
git clone https://github.com/Case211/remnawave-admin.git
cd remnawave-admin
```

## 2. Fill in `.env`

```bash
cp .env.example .env
nano .env
```

The bot will not start without these:

```ini
# Token from @BotFather
BOT_TOKEN=1234567890:ABCdefGHIjklmNOPqrstUVWxyz

# Remnawave panel API.
# Same Docker network:
API_BASE_URL=http://remnawave:3000
# Different server:
# API_BASE_URL=https://panel.example.com

API_TOKEN=token_from_the_panel

# Telegram IDs of administrators, comma-separated
ADMINS=123456789
```

The database comes up with everything else, but you pick the password:

```ini
POSTGRES_USER=remnawave
POSTGRES_PASSWORD=a_strong_password
POSTGRES_DB=remnawave_bot

# This password must match POSTGRES_PASSWORD above
DATABASE_URL=postgresql://remnawave:a_strong_password@remnawave-admin-db:5432/remnawave_bot
```

For the web panel, add:

```ini
# Session signing key: openssl rand -hex 32
WEB_SECRET_KEY=generated_key

# Bot username without @ — required for Telegram login
TELEGRAM_BOT_USERNAME=your_bot_username

# Panel domain, otherwise the browser rejects API calls via CORS
WEB_CORS_ORIGINS=https://admin.example.com

# Optional: the panel only opens under /secret-path/
# WEB_SECRET_PATH=my-secret-path
```

The full list lives in the [environment reference](/en/reference/env).

## 3. Start it

```bash
# The network is created once
docker network create remnawave-network

docker compose up -d
docker compose logs -f bot
```

Open the bot in Telegram and send `/start`. The web panel comes up from the same compose file: frontend on `:3000`, backend on `:8081`.

Next, put [a reverse proxy in front of it](/en/guide/web-panel) — those ports should not face the internet.

::: warning First login
The first login creates the admin account. If you lose access later, the password can be [reset from the CLI](/en/guide/troubleshooting#lost-access-to-the-panel) without reinstalling anything.
:::

## 4. Panel notifications

To have the bot relay panel events (subscription renewals, user changes), add:

```ini
NOTIFICATIONS_CHAT_ID=-1001234567890
WEBHOOK_SECRET=key_from_openssl_rand_-hex_64
```

Then point the Remnawave panel at the bot with the same secret. Details, with Caddy and nginx examples: [Panel webhook](/en/guide/webhook-setup).

If your Telegram group is a forum, notifications can be split across topics — see the [`NOTIFICATIONS_TOPIC_*` variables](/en/reference/env#notifications).

## 5. Agent on the nodes

Required for anti-abuse, host metrics, the terminal and torrent detection. The panel builds the install command for you: **Nodes → node → Agent token → Install agent**.

Details and manual installation: [Node Agent](/en/guide/node-agent).

## What next

- [Anti-abuse](/en/guide/anti-abuse) — thresholds and automatic actions
- [Mail server](/en/guide/mail) — if you want to send mail yourself
- [Monitoring](/en/guide/monitoring) — Prometheus and Grafana dashboards
- [Backups](/en/guide/backups) — schedule and restore checks

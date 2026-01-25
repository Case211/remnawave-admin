# 🤖 Remnawave Admin Bot

<div align="center">

**Telegram bot for managing Remnawave panel**

[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.12+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

[English](README_EN.md) | [Русский](README.md)

</div>

---

## ✨ Features

### 👥 User Management
- 🔍 Search users by username, email, Telegram ID, description
- ➕ Create users with step-by-step input
- ✏️ Edit profile (traffic, limits, contacts, squads)
- 💻 Manage HWID devices (add, delete, limits)
- 📊 User statistics (traffic, subscription history, node usage)
- 🔄 Bulk operations with users

### 🛰 Node Management
- 📋 View node list with real-time data
- 🔄 Enable/disable nodes
- 🔁 Restart nodes
- 📊 Monitor traffic and usage
- ⚙️ Assign configuration profiles
- 📈 Node statistics

### 🖥 Host Management
- 📋 View host list
- ➕ Create and edit hosts
- 🔄 Bulk operations

### 🧰 Resources
- 📑 **Templates** - create and manage subscription templates
- ✂️ **Snippets** - manage configuration snippets
- 🔑 **API Tokens** - manage access tokens
- 📄 **Configs** - view configurations

### 💰 Billing
- 📜 Payment history
- 🏢 Provider management
- 🖥 Billing node management
- 📊 Billing statistics

### 📊 Statistics and Monitoring
- 📈 Panel statistics (users, nodes, hosts)
- 🖥 Server statistics (CPU, memory, uptime)
- 📶 Traffic statistics
- 🔔 Event notifications via webhook

### 🌐 Additional Features
- 🌍 Russian and English language support
- 🔔 Webhook notifications for events (user creation, modification, deletion)
- 🔐 Secure webhook authentication via HMAC-SHA256
- 🎨 Intuitive interface with inline buttons
- 🐳 Ready for deployment via Docker Compose

---

## 🆕 What's New

### Version 1.5

**🗄 PostgreSQL Integration**
- Local data caching to reduce API panel load
- Automatic data synchronization with configurable interval (`SYNC_INTERVAL_SECONDS`)
- Real-time updates through webhook events

**📖 Data Reading Optimization**
- Read operations now use local database: subscriptions, user searches, host lists, node information, panel statistics, configuration profiles
- Node status continues pulling real-time data from the API

**📋 Diff Notifications**
- When data changes through the panel, the bot displays exactly what was modified
- Shows before-and-after values for affected fields

**🔀 Notification Topic Routing**
- Ability to route different notification types to different Telegram topics
- Separate topics for: users, nodes, service, HWID, billing, errors
- Fallback to general topic if specific one is not set

**🛡 Graceful Degradation**
- System continues functioning through the API if database becomes unavailable
- Full backward compatibility — PostgreSQL is optional

---

## 🚀 Quick Start

### 📋 Prerequisites

- **Docker** and **Docker Compose** (recommended)
- Or **Python 3.12+** (for local development)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Remnawave API access token

### 🔧 Installation

#### 1. Clone the repository

```bash
git clone https://github.com/case211/remnawave-admin.git
cd remnawave-admin
```

#### 2. Configure environment variables

Create `.env` file based on `.env.example`:

```bash
cp .env.example .env
nano .env
```

**Required variables:**

```env
# Telegram Bot
BOT_TOKEN=your_telegram_bot_token

# Remnawave API
API_BASE_URL=http://remnawave:3000  # For Docker network
# or
API_BASE_URL=https://your-panel-domain.com/api  # For external API
API_TOKEN=your_api_token

# Administrators
ADMINS=123456789,987654321  # Administrator IDs separated by commas

# Localization
DEFAULT_LOCALE=ru  # ru or en
LOG_LEVEL=INFO
```

**Optional variables:**

```env
# Telegram Notifications
NOTIFICATIONS_CHAT_ID=-1001234567890  # Group/channel ID
NOTIFICATIONS_TOPIC_ID=123  # Topic ID (optional)

# Webhook (for receiving notifications from panel)
WEBHOOK_SECRET=your_secret_key  # Must match WEBHOOK_SECRET_HEADER in panel
WEBHOOK_PORT=8080  # Port for webhook server
```

> 💡 **Tip:** Get your Telegram ID by messaging [@userinfobot](https://t.me/userinfobot)

#### 3. Deploy with Docker Compose

```bash
# Create Docker network (if not exists)
docker network create remnawave-network

# Start the bot
docker compose pull
docker compose up -d

# Check logs
docker compose logs -f bot
```

#### 4. Configure webhook in Remnawave panel

Detailed webhook setup instructions are available in [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md)

**Quick setup:**
1. In Remnawave panel, set webhook URL: `http://bot:8080/webhook` (for Docker) or `https://your-bot-domain.com/webhook` (for external)
2. Set `WEBHOOK_SECRET_HEADER` in panel equal to `WEBHOOK_SECRET` in bot

---

## 💻 Local Development

### 1. Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
nano .env
```

For local development, use:
```env
API_BASE_URL=https://your-panel-domain.com/api
```

### 4. Run the bot

```bash
python -m src.main
```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | ✅ Yes | - | Telegram bot token from @BotFather |
| `API_BASE_URL` | ✅ Yes | - | Remnawave API base URL |
| `API_TOKEN` | ✅ Yes | - | API authentication token |
| `ADMINS` | ✅ Yes | - | Comma-separated list of administrator IDs |
| `DEFAULT_LOCALE` | ❌ No | `ru` | Default language (`ru` or `en`) |
| `LOG_LEVEL` | ❌ No | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `NOTIFICATIONS_CHAT_ID` | ❌ No | - | Group/channel ID for notifications |
| `NOTIFICATIONS_TOPIC_ID` | ❌ No | - | Topic ID in group (for forums, fallback) |
| `NOTIFICATIONS_TOPIC_USERS` | ❌ No | - | Topic for user notifications |
| `NOTIFICATIONS_TOPIC_NODES` | ❌ No | - | Topic for node notifications |
| `NOTIFICATIONS_TOPIC_SERVICE` | ❌ No | - | Topic for service notifications |
| `NOTIFICATIONS_TOPIC_HWID` | ❌ No | - | Topic for HWID notifications |
| `NOTIFICATIONS_TOPIC_CRM` | ❌ No | - | Topic for billing notifications |
| `NOTIFICATIONS_TOPIC_ERRORS` | ❌ No | - | Topic for error notifications |
| `WEBHOOK_SECRET` | ❌ No | - | Secret key for webhook verification (HMAC-SHA256) |
| `WEBHOOK_PORT` | ❌ No | `8080` | Port for webhook server |
| `DATABASE_URL` | ❌ No | - | PostgreSQL connection URL |
| `SYNC_INTERVAL_SECONDS` | ❌ No | `300` | Data sync interval with API (seconds) |

### Docker Network

The bot requires access to the `remnawave-network` Docker network. If it doesn't exist, create it:

```bash
docker network create remnawave-network
```

---

## 📱 Bot Commands

### Basic Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and show main menu |
| `/help` | Show command help |
| `/health` | Show system health status |
| `/stats` | Show panel and server statistics |
| `/bandwidth` | Show traffic statistics |

### User Management Commands

| Command | Description |
|---------|-------------|
| `/user <username\|telegram_id>` | View user information |
| `/user_create <username> <expire_iso> [telegram_id]` | Create new user |

### Infrastructure Commands

| Command | Description |
|---------|-------------|
| `/node <uuid>` | View node information |
| `/host <uuid>` | View host information |
| `/sub <short_uuid>` | Open subscription link |

### Menu Navigation

The bot uses inline keyboards for navigation. Main sections:

- **👥 Users** - User management, search, creation, editing, statistics, HWID
- **🛰 Nodes** - Node management and monitoring, traffic statistics
- **🖥 Hosts** - Host management, bulk operations
- **🧰 Resources** - Templates, snippets, API tokens, configs
- **💰 Billing** - Payment history, providers, billing nodes
- **📊 System** - System health, statistics, management

---

## 📁 Project Structure

```
remnawave-admin/
├── src/
│   ├── main.py                 # Application entry point
│   ├── config.py               # Configuration management
│   ├── handlers/               # Event handlers
│   │   ├── basic.py            # Basic handlers
│   │   ├── commands.py         # Command handlers
│   │   ├── users.py            # User management
│   │   ├── nodes.py            # Node management
│   │   ├── hosts.py            # Host management
│   │   ├── resources.py        # Resources (templates, snippets)
│   │   ├── billing.py          # Billing
│   │   ├── system.py           # System information
│   │   ├── navigation.py       # Navigation
│   │   ├── bulk.py             # Bulk operations
│   │   ├── common.py           # Common utilities
│   │   ├── errors.py           # Error handling
│   │   └── state.py            # State management
│   ├── keyboards/              # Inline keyboards
│   │   ├── main_menu.py        # Main menu
│   │   ├── user_actions.py    # User actions
│   │   ├── nodes_menu.py       # Node menu
│   │   └── ...                 # Other keyboards
│   ├── services/               # Services
│   │   ├── api_client.py       # Remnawave API client
│   │   └── webhook.py          # Webhook server (FastAPI)
│   └── utils/                   # Utilities
│       ├── formatters.py       # Data formatting
│       ├── notifications.py     # Notifications
│       ├── auth.py              # Authentication
│       ├── logger.py            # Logging
│       └── i18n.py              # Internationalization
├── locales/                     # Localization
│   ├── ru/                      # Russian language
│   │   └── messages.json
│   └── en/                      # English language
│       └── messages.json
├── docker-compose.yml          # Docker Compose configuration
├── Dockerfile                  # Docker image definition
├── requirements.txt            # Python dependencies
├── WEBHOOK_SETUP.md           # Webhook setup instructions
└── README.md                   # This file
```

---

## 🔔 Webhook Notifications

The bot supports receiving webhook notifications from Remnawave panel about various events:

- **Users**: creation, modification, deletion, disabling, subscription expiration
- **Nodes**: creation, modification, deletion, connection loss/restoration
- **HWID Devices**: addition, deletion
- **Service**: panel events, login attempts

Detailed setup instructions are available in [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md)

---

## 🔧 Troubleshooting

### Bot not responding

1. **Check bot status:**
   ```bash
   docker compose ps
   ```

2. **Check logs for errors:**
   ```bash
   docker compose logs -f bot
   ```

3. **Check environment variables:**
   ```bash
   docker compose config
   ```

### API connection issues

1. Make sure `API_BASE_URL` is set correctly
2. Check if Docker network exists:
   ```bash
   docker network ls | grep remnawave-network
   ```
3. For external API, ensure URL is accessible and token is valid

### Access denied

- Make sure your Telegram ID is listed in `ADMINS` environment variable
- Get your ID by messaging [@userinfobot](https://t.me/userinfobot)

### Webhook issues

- Check that `WEBHOOK_SECRET` in bot matches `WEBHOOK_SECRET_HEADER` in panel
- Ensure webhook URL is accessible from panel
- Check logs for authentication errors
- See [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md) for more details

---

## 🤝 Contributing

We welcome contributions to the project!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make changes and commit (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 💬 Support

For questions and issues, create an [issue](https://github.com/case211/remnawave-admin/issues) on GitHub.

Join our Telegram chat - https://t.me/remnawave_admin

---

<div align="center">

**Made with ❤️ for Remnawave management**

</div>
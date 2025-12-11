# Remnawave Admin Bot
**Available languages:** [Русский](README.md)

Telegram bot for managing Remnawave panel. Supports RU/EN localization, inline buttons, Docker Compose deployment.

## Features

- **User Management**: View, create, edit users, manage subscriptions, bulk operations
- **Node Management**: Monitor nodes, enable/disable, restart, reset traffic, assign profiles
- **Host Management**: Manage hosts, bulk operations
- **Templates**: Create and manage subscription templates
- **Snippets**: Manage configuration snippets
- **API Tokens**: Manage API access tokens
- **Billing**: Track billing history, manage providers and billing nodes
- **Statistics**: Panel and server statistics with detailed metrics
- **Multi-language**: Russian and English support

## Quick Start

### Prerequisites

- Python 3.12+ (for local development)
- Docker and Docker Compose (for deployment)
- Telegram Bot Token from [@BotFather](https://t.me/BotFather)
- Remnawave API access token

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/case211/remnawave-admin.git
   ```
   ```bash
   cd remnawave-admin
   ```

2. **Copy environment file:**
   ```bash
   cp .env.example .env
   ```

3. **Edit `.env` file:**
   ```bash
   nano .env
   ```

   Required variables:
   ```env
   BOT_TOKEN=your_telegram_bot_token
   API_BASE_URL=http://remnawave:3000
   API_TOKEN=your_api_token
   ADMINS=123456789,987654321
   DEFAULT_LOCALE=ru
   LOG_LEVEL=INFO
   ```

   **For Docker deployment**, use:
   - `API_BASE_URL=http://remnawave:3000` (if bot is in the same Docker network)
   - `API_BASE_URL=https://your-panel-domain.com/api` (if bot is external)

4. **Deploy with Docker Compose:**
   ```bash
   docker compose pull
   docker compose up -d
   ```

5. **Check logs:**
   ```bash
   docker compose logs -f bot
   ```

## Local Development

1. **Create virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # or
   .venv\Scripts\activate  # Windows
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment:**
   ```bash
   cp .env.example .env
   nano .env
   ```

   For local development, use:
   ```env
   API_BASE_URL=https://your-panel-domain.com
   ```

4. **Run the bot:**
   ```bash
   python -m src.main
   ```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BOT_TOKEN` | Yes | - | Telegram bot token from @BotFather |
| `API_BASE_URL` | Yes | - | Remnawave API base URL |
| `API_TOKEN` | Yes | - | API authentication token |
| `ADMINS` | Yes | - | Comma-separated list of Telegram user IDs |
| `DEFAULT_LOCALE` | No | `ru` | Default language (`ru` or `en`) |
| `LOG_LEVEL` | No | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

### Docker Network

The bot requires access to the `remnawave-network` Docker network. If it doesn't exist, create it:

```bash
docker network create remnawave-network
```

## Commands

### Bot Commands

- `/start` - Start the bot and show main menu
- `/help` - Show help information
- `/health` - Show system health status
- `/stats` - Show panel and server statistics
- `/bandwidth` - Show bandwidth statistics
- `/user <username|telegram_id>` - View user details
- `/user_create <username> <expire_iso> [telegram_id]` - Create new user
- `/sub <short_uuid>` - Open subscription link
- `/node <uuid>` - View node details
- `/host <uuid>` - View host details

### Menu Navigation

The bot uses inline keyboards for navigation. Main sections:

- **Users** - User management, subscriptions, bulk operations
- **Nodes** - Node management and monitoring
- **Hosts** - Host management
- **Resources** - Templates, snippets, API tokens, configs
- **Billing** - Billing history, providers, billing nodes
- **System** - Health, statistics, node management

## Project Structure

```
remnawave-admin/
├── src/
│   ├── main.py              # Entry point
│   ├── config.py            # Configuration management
│   ├── handlers/
│   │   ├── basic.py         # Command and callback handlers
│   │   └── errors.py       # Error handlers
│   ├── keyboards/          # Inline keyboard definitions
│   ├── services/
│   │   └── api_client.py  # Remnawave API client
│   └── utils/              # Utilities (formatters, i18n, logger, auth)
├── locales/
│   ├── ru/                 # Russian translations
│   └── en/                 # English translations
├── docker-compose.yml      # Docker Compose configuration
├── Dockerfile              # Docker image definition
└── requirements.txt        # Python dependencies
```

## Docker Image

The bot image is automatically built and published to GitHub Container Registry:

```
ghcr.io/case211/remnawave-admin:latest
```

Build workflow: `.github/workflows/docker.yml`

## Troubleshooting

### Bot doesn't respond

1. Check if the bot is running:
   ```bash
   docker compose ps
   ```

2. Check logs for errors:
   ```bash
   docker compose logs -f bot
   ```

3. Verify environment variables:
   ```bash
   docker compose config
   ```

### API connection issues

1. Verify `API_BASE_URL` is correct
2. Check if the Docker network exists:
   ```bash
   docker network ls | grep remnawave-network
   ```
3. For external API, ensure the URL is accessible

### Permission denied

- Ensure your Telegram user ID is in the `ADMINS` environment variable
- Get your user ID by messaging [@userinfobot](https://t.me/userinfobot)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

[Add your license here]

## Support

For issues and questions, please open an issue on GitHub.


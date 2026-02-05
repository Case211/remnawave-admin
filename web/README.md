# Remnawave Admin Web Panel

Web-based admin panel for Remnawave bot management.

## Structure

```
web/
├── backend/          # FastAPI backend
│   ├── api/          # API endpoints
│   ├── core/         # Core functionality (config, security)
│   ├── schemas/      # Pydantic schemas
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/         # React + TypeScript frontend
│   ├── src/
│   ├── Dockerfile
│   └── package.json
├── nginx/            # Nginx reverse proxy config
├── caddy/            # Caddy reverse proxy config
└── docker-compose.yml
```

## Quick Start

### Development

```bash
# From project root
docker compose -f web/docker-compose.yml --profile dev up
```

This starts:
- Backend API on port 8081
- Frontend (Vite dev server) on port 3000
- PostgreSQL on port 5432

### Production

```bash
# From project root
docker compose -f web/docker-compose.yml --profile prod up -d
```

### With Nginx

```bash
docker compose -f web/docker-compose.yml --profile prod --profile nginx up -d
```

### With Caddy (auto HTTPS)

```bash
docker compose -f web/docker-compose.yml --profile prod --profile caddy up -d
```

## Configuration

Copy `.env.example` to `.env` and configure:

```env
# Required for web panel
WEB_SECRET_KEY=your_jwt_secret_key_here
TELEGRAM_BOT_USERNAME=your_bot_username
ADMINS=123456789,987654321

# Optional
WEB_DEBUG=true  # Enable dev bypass for testing
```

## Authentication

Uses Telegram Login Widget for authentication. Only users listed in `ADMINS` can access the panel.

### Development Bypass

When `WEB_DEBUG=true`, you can bypass Telegram authentication:
1. On the login page, click "Show Development Bypass"
2. Enter your Telegram ID
3. Click "Dev Login"

This is useful for testing without setting up the Telegram Login Widget.

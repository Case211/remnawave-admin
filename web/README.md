# Remnawave Admin Web Panel

Web-based admin panel for Remnawave bot management.

## Structure

```
web/
├── backend/          # FastAPI backend
│   ├── api/          # API endpoints (auth, users, nodes, analytics)
│   ├── core/         # Core functionality (config, security)
│   ├── schemas/      # Pydantic schemas
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/         # React + TypeScript frontend
│   ├── src/
│   │   ├── api/      # API client
│   │   ├── components/
│   │   ├── pages/
│   │   └── store/
│   ├── Dockerfile
│   └── package.json
├── nginx/            # Nginx reverse proxy config
├── caddy/            # Caddy reverse proxy config
├── docker-compose.yml  # Standalone web dev
└── README.md
```

## Quick Start

### Option 1: Run with Bot (Recommended)

Use the main `docker-compose.yml` to run bot + web panel together. They share the same database.

```bash
# Development (bot + web panel with hot-reload)
docker compose --profile web-dev up

# Production (bot + web panel production build)
docker compose --profile web up

# Production with Caddy (auto HTTPS)
docker compose --profile web --profile caddy up -d

# Production with Nginx
docker compose --profile web --profile nginx up -d
```

### Option 2: Standalone Web Development

Use `web/docker-compose.yml` for web panel development without the bot. Creates its own PostgreSQL instance.

```bash
docker compose -f web/docker-compose.yml up
```

## Ports

| Service | Port | Description |
|---------|------|-------------|
| Frontend | 3000 | React dev server / Nginx |
| Backend | 8081 | FastAPI API |
| PostgreSQL | 5432 | Database |
| Nginx/Caddy | 80/443 | Reverse proxy |

## Configuration

Copy `.env.example` to `.env` and configure:

```env
# Required for web panel
WEB_SECRET_KEY=your_jwt_secret_key_here   # openssl rand -hex 32
TELEGRAM_BOT_USERNAME=your_bot_username    # Without @
ADMINS=123456789,987654321                 # Telegram IDs

# Optional
WEB_DEBUG=true                             # Enable dev bypass
```

## Authentication

Uses Telegram Login Widget. Only users listed in `ADMINS` can access the panel.

### Development Bypass

When `WEB_DEBUG=true`:

1. On login page, click "Show Development Bypass"
2. Enter your Telegram ID
3. Click "Dev Login"

This bypasses Telegram signature verification for local testing.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Caddy / Nginx (reverse proxy)                   │
│                    :80 / :443                                │
└─────────────────────────────────────────────────────────────┘
                    │                   │
                    ▼                   ▼
┌─────────────────────────┐  ┌─────────────────────────┐
│   Frontend (React)      │  │   Backend (FastAPI)     │
│        :3000            │  │        :8081            │
└─────────────────────────┘  └─────────────────────────┘
                                        │
                                        ▼
                    ┌─────────────────────────────────────┐
                    │        PostgreSQL (shared)          │
                    │             :5432                   │
                    └─────────────────────────────────────┘
                                        ▲
                                        │
                    ┌─────────────────────────────────────┐
                    │     Telegram Bot (Python)           │
                    │           :8080                     │
                    └─────────────────────────────────────┘
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v2/auth/telegram` | POST | Telegram login |
| `/api/v2/auth/refresh` | POST | Refresh token |
| `/api/v2/auth/me` | GET | Current admin info |
| `/api/v2/users` | GET | List users |
| `/api/v2/users/{id}` | GET | Get user |
| `/api/v2/nodes` | GET | List nodes |
| `/api/v2/analytics/*` | GET | Analytics data |
| `/api/v2/health` | GET | Health check |

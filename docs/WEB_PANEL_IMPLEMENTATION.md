# 🌐 План внедрения веб-панели Remnawave Admin

> **Версия:** 1.0
> **Дата:** 01.02.2026
> **Оценка времени:** 8-12 недель

---

## 📋 Содержание

1. [Обзор архитектуры](#обзор-архитектуры)
2. [Этап 1: Подготовка инфраструктуры](#этап-1-подготовка-инфраструктуры)
3. [Этап 2: Backend API](#этап-2-backend-api)
4. [Этап 3: Аутентификация](#этап-3-аутентификация)
5. [Этап 4: Frontend базовый](#этап-4-frontend-базовый)
6. [Этап 5: Основные страницы](#этап-5-основные-страницы)
7. [Этап 6: Real-time функции](#этап-6-real-time-функции)
8. [Этап 7: Продвинутые функции](#этап-7-продвинутые-функции)
9. [Чеклист готовности](#чеклист-готовности)

---

## 🏗 Обзор архитектуры

### Текущее состояние

```
┌─────────────────────────────────────────────────────────────┐
│                    ТЕКУЩАЯ АРХИТЕКТУРА                       │
│                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │   Telegram   │────▶│  Aiogram Bot │────▶│   Services   │ │
│  │    Users     │◀────│   Handlers   │◀────│              │ │
│  └──────────────┘     └──────────────┘     │ - api_client │ │
│                                            │ - database   │ │
│  ┌──────────────┐     ┌──────────────┐     │ - violation  │ │
│  │  Remnawave   │────▶│   FastAPI    │────▶│ - geoip      │ │
│  │    Panel     │     │   Webhook    │     │ - sync       │ │
│  └──────────────┘     └──────────────┘     └──────────────┘ │
│                                                     │        │
│                                            ┌────────▼───────┐│
│                                            │   PostgreSQL   ││
│                                            └────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Целевая архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                      ЦЕЛЕВАЯ АРХИТЕКТУРА                             │
│                                                                      │
│  ┌──────────────┐     ┌──────────────┐                              │
│  │   Telegram   │────▶│  Aiogram Bot │──────┐                       │
│  │    Users     │◀────│   Handlers   │      │                       │
│  └──────────────┘     └──────────────┘      │                       │
│                                             ▼                        │
│  ┌──────────────┐     ┌──────────────┐  ┌──────────────┐            │
│  │  Remnawave   │────▶│   FastAPI    │──│   Services   │            │
│  │    Panel     │     │   Webhook    │  │  (shared)    │            │
│  └──────────────┘     └──────────────┘  └──────────────┘            │
│                              │                 ▲                     │
│  ┌──────────────┐     ┌──────▼─────────────────┴───┐                │
│  │    React     │────▶│      FastAPI Web API       │                │
│  │   Frontend   │◀────│   /api/v2/* endpoints      │                │
│  │              │     │   + WebSocket /ws          │                │
│  └──────────────┘     └────────────────────────────┘                │
│        │                          │                                  │
│        │              ┌───────────▼───────────┐                     │
│        │              │      PostgreSQL       │                     │
│        │              └───────────────────────┘                     │
│        │                                                            │
│        └───────────── Telegram Login Widget ◀─── Auth ──────────────│
└─────────────────────────────────────────────────────────────────────┘
```

### Структура директорий

```
remnawave-admin/
├── src/                          # Telegram бот (существующий)
│   ├── handlers/
│   ├── keyboards/
│   ├── services/                 # ← SHARED сервисы
│   └── utils/
│
├── web/                          # ← НОВОЕ
│   ├── backend/
│   │   ├── api/
│   │   │   ├── v2/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py       # Telegram Login + JWT
│   │   │   │   ├── users.py
│   │   │   │   ├── nodes.py
│   │   │   │   ├── hosts.py
│   │   │   │   ├── violations.py
│   │   │   │   ├── analytics.py
│   │   │   │   ├── settings.py
│   │   │   │   └── websocket.py
│   │   │   └── deps.py           # Dependencies (auth, db)
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py       # JWT, password hashing
│   │   │   └── permissions.py    # RBAC
│   │   ├── schemas/
│   │   │   ├── auth.py
│   │   │   ├── user.py
│   │   │   ├── node.py
│   │   │   └── common.py
│   │   ├── main.py               # FastAPI app
│   │   └── requirements.txt
│   │
│   └── frontend/
│       ├── src/
│       │   ├── components/
│       │   │   ├── common/       # Button, Input, Modal, Table
│       │   │   ├── layout/       # Sidebar, Header, Footer
│       │   │   ├── users/
│       │   │   ├── nodes/
│       │   │   └── violations/
│       │   ├── pages/
│       │   │   ├── Dashboard.tsx
│       │   │   ├── Users.tsx
│       │   │   ├── UserDetail.tsx
│       │   │   ├── Nodes.tsx
│       │   │   ├── Violations.tsx
│       │   │   ├── Analytics.tsx
│       │   │   ├── Settings.tsx
│       │   │   └── Login.tsx
│       │   ├── hooks/
│       │   │   ├── useAuth.ts
│       │   │   ├── useWebSocket.ts
│       │   │   └── useApi.ts
│       │   ├── api/
│       │   │   ├── client.ts     # Axios/fetch wrapper
│       │   │   ├── users.ts
│       │   │   ├── nodes.ts
│       │   │   └── auth.ts
│       │   ├── store/            # Zustand
│       │   │   ├── authStore.ts
│       │   │   └── uiStore.ts
│       │   ├── types/
│       │   ├── utils/
│       │   ├── App.tsx
│       │   └── main.tsx
│       ├── public/
│       ├── index.html
│       ├── package.json
│       ├── tsconfig.json
│       ├── vite.config.ts
│       └── tailwind.config.js
│
├── docker-compose.yml            # Обновить
├── docker-compose.web.yml        # ← НОВОЕ (для веб-панели)
└── nginx/
    └── nginx.conf                # ← НОВОЕ (reverse proxy)
```

---

## 🚀 Этап 1: Подготовка инфраструктуры

**Длительность:** 3-5 дней

### 1.1 Создание структуры директорий

```bash
mkdir -p web/backend/{api/v2,core,schemas}
mkdir -p web/frontend/src/{components,pages,hooks,api,store,types,utils}
mkdir -p web/frontend/src/components/{common,layout,users,nodes,violations}
mkdir -p nginx
```

### 1.2 Backend: Базовая настройка FastAPI

**Файл:** `web/backend/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.backend.api.v2 import auth, users, nodes, hosts, violations, analytics
from web.backend.core.config import settings

app = FastAPI(
    title="Remnawave Admin Web API",
    version="2.0.0",
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/v2/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/v2/users", tags=["users"])
app.include_router(nodes.router, prefix="/api/v2/nodes", tags=["nodes"])
app.include_router(hosts.router, prefix="/api/v2/hosts", tags=["hosts"])
app.include_router(violations.router, prefix="/api/v2/violations", tags=["violations"])
app.include_router(analytics.router, prefix="/api/v2/analytics", tags=["analytics"])

@app.get("/api/v2/health")
async def health_check():
    return {"status": "ok", "version": "2.0.0"}
```

### 1.3 Конфигурация

**Файл:** `web/backend/core/config.py`

```python
from pydantic_settings import BaseSettings
from typing import List

class WebSettings(BaseSettings):
    # App
    debug: bool = False
    secret_key: str

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours
    jwt_refresh_days: int = 7

    # CORS
    cors_origins: List[str] = ["http://localhost:3000"]

    # Telegram
    telegram_bot_token: str

    # Database (shared with bot)
    database_url: str

    class Config:
        env_prefix = "WEB_"
        env_file = ".env"

settings = WebSettings()
```

### 1.4 Docker Compose для веб-панели

**Файл:** `docker-compose.web.yml`

```yaml
version: '3.8'

services:
  web-backend:
    build:
      context: .
      dockerfile: web/backend/Dockerfile
    environment:
      - WEB_SECRET_KEY=${WEB_SECRET_KEY}
      - WEB_TELEGRAM_BOT_TOKEN=${BOT_TOKEN}
      - WEB_DATABASE_URL=${DATABASE_URL}
      - WEB_DEBUG=true
      - WEB_CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
    ports:
      - "8081:8081"
    depends_on:
      - postgres
    volumes:
      - ./src:/app/src:ro  # Shared services
      - ./web/backend:/app/web/backend

  web-frontend:
    build:
      context: ./web/frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://localhost:8081
    volumes:
      - ./web/frontend:/app
      - /app/node_modules

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - web-backend
      - web-frontend
```

### 1.5 Nginx конфигурация

**Файл:** `nginx/nginx.conf`

```nginx
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server web-backend:8081;
    }

    upstream frontend {
        server web-frontend:3000;
    }

    server {
        listen 80;
        server_name localhost;

        # API requests
        location /api/ {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        # WebSocket
        location /ws {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        # Frontend
        location / {
            proxy_pass http://frontend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
```

### Задачи этапа 1:

```
[ ] Создать структуру директорий
[ ] Настроить web/backend/main.py
[ ] Настроить web/backend/core/config.py
[ ] Создать Dockerfile для backend
[ ] Создать Dockerfile для frontend
[ ] Настроить docker-compose.web.yml
[ ] Настроить nginx.conf
[ ] Добавить переменные окружения в .env.example
[ ] Проверить запуск инфраструктуры
```

---

## 🔐 Этап 2: Backend API

**Длительность:** 1-2 недели

### 2.1 Схемы данных (Pydantic)

**Файл:** `web/backend/schemas/user.py`

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class UserBase(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    telegram_id: Optional[int] = None
    status: str

class UserListItem(UserBase):
    uuid: UUID
    short_uuid: str
    expire_at: Optional[datetime]
    traffic_limit_bytes: Optional[int]
    used_traffic_bytes: int = 0
    hwid_device_limit: int
    created_at: datetime

class UserDetail(UserListItem):
    subscription_uuid: Optional[str]
    online_at: Optional[datetime]
    sub_last_user_agent: Optional[str]
    # Anti-abuse info
    trust_score: Optional[int]
    violation_count_30d: int = 0
    active_connections: int = 0
    unique_ips_24h: int = 0

class UserListResponse(BaseModel):
    items: List[UserListItem]
    total: int
    page: int
    per_page: int
    pages: int

class UserUpdate(BaseModel):
    status: Optional[str] = None
    traffic_limit_bytes: Optional[int] = None
    expire_at: Optional[datetime] = None
    hwid_device_limit: Optional[int] = None
```

### 2.2 API эндпоинты

**Файл:** `web/backend/api/v2/users.py`

```python
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from uuid import UUID

from web.backend.api.deps import get_current_admin, get_db
from web.backend.schemas.user import UserListResponse, UserDetail, UserUpdate
from src.services.api_client import api_client
from src.services.database import DatabaseService

router = APIRouter()

@router.get("/", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    admin = Depends(get_current_admin),
    db: DatabaseService = Depends(get_db),
):
    """Список пользователей с пагинацией и фильтрацией."""
    # Получаем из кэша БД или API
    users = await db.get_all_users()

    # Фильтрация
    if search:
        users = [u for u in users if search.lower() in (u.get('username', '') or '').lower()]
    if status:
        users = [u for u in users if u.get('status') == status]

    # Сортировка
    reverse = sort_order == "desc"
    users.sort(key=lambda x: x.get(sort_by, ''), reverse=reverse)

    # Пагинация
    total = len(users)
    start = (page - 1) * per_page
    end = start + per_page
    items = users[start:end]

    return UserListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )

@router.get("/{user_uuid}", response_model=UserDetail)
async def get_user(
    user_uuid: UUID,
    admin = Depends(get_current_admin),
):
    """Детальная информация о пользователе."""
    user = await api_client.get_user(str(user_uuid))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Добавляем Anti-Abuse информацию
    # ...

    return user

@router.patch("/{user_uuid}", response_model=UserDetail)
async def update_user(
    user_uuid: UUID,
    data: UserUpdate,
    admin = Depends(get_current_admin),
):
    """Обновление пользователя."""
    update_data = data.model_dump(exclude_unset=True)
    user = await api_client.update_user(str(user_uuid), **update_data)
    return user

@router.post("/{user_uuid}/disable")
async def disable_user(
    user_uuid: UUID,
    admin = Depends(get_current_admin),
):
    """Отключить пользователя."""
    await api_client.disable_user(str(user_uuid))
    return {"status": "ok"}

@router.post("/{user_uuid}/enable")
async def enable_user(
    user_uuid: UUID,
    admin = Depends(get_current_admin),
):
    """Включить пользователя."""
    await api_client.enable_user(str(user_uuid))
    return {"status": "ok"}

@router.delete("/{user_uuid}")
async def delete_user(
    user_uuid: UUID,
    admin = Depends(get_current_admin),
):
    """Удалить пользователя."""
    await api_client.delete_user(str(user_uuid))
    return {"status": "ok"}
```

### 2.3 Список всех API эндпоинтов

```
# Auth
POST   /api/v2/auth/telegram          # Telegram Login Widget callback
POST   /api/v2/auth/refresh           # Refresh JWT token
POST   /api/v2/auth/logout            # Logout (invalidate token)
GET    /api/v2/auth/me                # Current admin info

# Users
GET    /api/v2/users                  # List users (paginated)
POST   /api/v2/users                  # Create user
GET    /api/v2/users/{uuid}           # Get user detail
PATCH  /api/v2/users/{uuid}           # Update user
DELETE /api/v2/users/{uuid}           # Delete user
POST   /api/v2/users/{uuid}/enable    # Enable user
POST   /api/v2/users/{uuid}/disable   # Disable user
POST   /api/v2/users/{uuid}/reset-traffic    # Reset traffic
POST   /api/v2/users/{uuid}/revoke    # Revoke subscription
GET    /api/v2/users/{uuid}/connections      # User connections history
GET    /api/v2/users/{uuid}/violations       # User violations

# Nodes
GET    /api/v2/nodes                  # List nodes
POST   /api/v2/nodes                  # Create node
GET    /api/v2/nodes/{uuid}           # Get node detail
PATCH  /api/v2/nodes/{uuid}           # Update node
DELETE /api/v2/nodes/{uuid}           # Delete node
POST   /api/v2/nodes/{uuid}/restart   # Restart node
GET    /api/v2/nodes/{uuid}/stats     # Node statistics

# Hosts
GET    /api/v2/hosts                  # List hosts
POST   /api/v2/hosts                  # Create host
GET    /api/v2/hosts/{uuid}           # Get host detail
PATCH  /api/v2/hosts/{uuid}           # Update host
DELETE /api/v2/hosts/{uuid}           # Delete host

# Violations
GET    /api/v2/violations             # List violations
GET    /api/v2/violations/{id}        # Get violation detail
POST   /api/v2/violations/{id}/resolve # Resolve violation
GET    /api/v2/violations/pending     # Pending violations

# Analytics
GET    /api/v2/analytics/overview     # Dashboard stats
GET    /api/v2/analytics/users        # User statistics
GET    /api/v2/analytics/traffic      # Traffic statistics
GET    /api/v2/analytics/violations   # Violation statistics
GET    /api/v2/analytics/connections  # Connection statistics
POST   /api/v2/analytics/export       # Export report

# Settings
GET    /api/v2/settings               # Get all settings
PATCH  /api/v2/settings               # Update settings
GET    /api/v2/settings/anti-abuse    # Anti-abuse settings
PATCH  /api/v2/settings/anti-abuse    # Update anti-abuse settings

# WebSocket
WS     /api/v2/ws                     # Real-time updates
```

### Задачи этапа 2:

```
[ ] Создать schemas/ (user.py, node.py, host.py, violation.py, common.py)
[ ] Создать api/deps.py (dependencies)
[ ] Реализовать api/v2/users.py
[ ] Реализовать api/v2/nodes.py
[ ] Реализовать api/v2/hosts.py
[ ] Реализовать api/v2/violations.py
[ ] Реализовать api/v2/analytics.py
[ ] Реализовать api/v2/settings.py
[ ] Добавить OpenAPI документацию
[ ] Написать тесты для API
```

---

## 🔑 Этап 3: Аутентификация

**Длительность:** 3-5 дней

### 3.1 Telegram Login Widget

Telegram Login Widget позволяет пользователям входить через их Telegram аккаунт.

**Файл:** `web/backend/core/security.py`

```python
import hmac
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError

from web.backend.core.config import settings

def verify_telegram_auth(auth_data: dict) -> bool:
    """
    Проверяет подлинность данных от Telegram Login Widget.
    https://core.telegram.org/widgets/login#checking-authorization
    """
    check_hash = auth_data.pop('hash', None)
    if not check_hash:
        return False

    # Проверяем что данные не устарели (не старше 24 часов)
    auth_date = auth_data.get('auth_date')
    if auth_date and int(time.time()) - int(auth_date) > 86400:
        return False

    # Создаем data-check-string
    data_check_arr = [f"{k}={v}" for k, v in sorted(auth_data.items())]
    data_check_string = "\n".join(data_check_arr)

    # Создаем secret key из bot token
    secret_key = hashlib.sha256(settings.telegram_bot_token.encode()).digest()

    # Вычисляем hash
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(calculated_hash, check_hash)

def create_access_token(telegram_id: int, username: str) -> str:
    """Создает JWT access token."""
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(telegram_id),
        "username": username,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

def create_refresh_token(telegram_id: int) -> str:
    """Создает JWT refresh token."""
    expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_days)
    payload = {
        "sub": str(telegram_id),
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

def decode_token(token: str) -> Optional[dict]:
    """Декодирует JWT token."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except JWTError:
        return None
```

### 3.2 Auth API

**Файл:** `web/backend/api/v2/auth.py`

```python
from fastapi import APIRouter, HTTPException, Depends, Response
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from typing import Optional

from web.backend.core.security import (
    verify_telegram_auth,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from src.config import get_settings

router = APIRouter()
security = HTTPBearer()

class TelegramAuthData(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str

@router.post("/telegram", response_model=TokenResponse)
async def telegram_login(data: TelegramAuthData):
    """
    Аутентификация через Telegram Login Widget.
    """
    # Проверяем подпись
    auth_dict = data.model_dump()
    if not verify_telegram_auth(auth_dict.copy()):
        raise HTTPException(status_code=401, detail="Invalid Telegram auth data")

    # Проверяем что пользователь в списке админов
    settings = get_settings()
    if data.id not in settings.admins:
        raise HTTPException(status_code=403, detail="Not an admin")

    # Создаем токены
    username = data.username or data.first_name
    access_token = create_access_token(data.id, username)
    refresh_token = create_refresh_token(data.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )

@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(data: RefreshRequest):
    """
    Обновление access token через refresh token.
    """
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    telegram_id = int(payload["sub"])

    # Проверяем что все еще админ
    settings = get_settings()
    if telegram_id not in settings.admins:
        raise HTTPException(status_code=403, detail="Not an admin")

    access_token = create_access_token(telegram_id, "admin")
    refresh_token = create_refresh_token(telegram_id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )

@router.get("/me")
async def get_current_user(admin = Depends(get_current_admin)):
    """
    Информация о текущем администраторе.
    """
    return {
        "telegram_id": admin.telegram_id,
        "username": admin.username,
        "role": admin.role,
    }

@router.post("/logout")
async def logout(response: Response):
    """
    Выход (на клиенте нужно удалить токены).
    """
    # В будущем можно добавить blacklist токенов
    return {"status": "ok"}
```

### 3.3 Dependencies

**Файл:** `web/backend/api/deps.py`

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from dataclasses import dataclass

from web.backend.core.security import decode_token
from src.config import get_settings
from src.services.database import db_service

security = HTTPBearer()

@dataclass
class AdminUser:
    telegram_id: int
    username: str
    role: str = "admin"

async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AdminUser:
    """
    Dependency для проверки аутентификации.
    """
    token = credentials.credentials
    payload = decode_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    telegram_id = int(payload["sub"])

    # Проверяем что в списке админов
    settings = get_settings()
    if telegram_id not in settings.admins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not an admin",
        )

    return AdminUser(
        telegram_id=telegram_id,
        username=payload.get("username", "admin"),
    )

async def get_db():
    """
    Dependency для доступа к базе данных.
    """
    return db_service
```

### 3.4 Frontend: Login Page

**Файл:** `web/frontend/src/pages/Login.tsx`

```tsx
import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';

declare global {
  interface Window {
    TelegramLoginWidget: {
      dataOnauth: (user: TelegramUser) => void;
    };
  }
}

interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

export default function Login() {
  const containerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { login, isAuthenticated } = useAuthStore();

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/');
      return;
    }

    // Telegram Login Widget callback
    window.TelegramLoginWidget = {
      dataOnauth: async (user: TelegramUser) => {
        try {
          await login(user);
          navigate('/');
        } catch (error) {
          console.error('Login failed:', error);
        }
      },
    };

    // Добавляем скрипт Telegram Login Widget
    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.setAttribute('data-telegram-login', import.meta.env.VITE_TELEGRAM_BOT_USERNAME);
    script.setAttribute('data-size', 'large');
    script.setAttribute('data-onauth', 'TelegramLoginWidget.dataOnauth(user)');
    script.setAttribute('data-request-access', 'write');
    script.async = true;

    containerRef.current?.appendChild(script);

    return () => {
      if (containerRef.current?.contains(script)) {
        containerRef.current.removeChild(script);
      }
    };
  }, [isAuthenticated, navigate, login]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900">
      <div className="bg-gray-800 p-8 rounded-lg shadow-xl text-center">
        <h1 className="text-2xl font-bold text-white mb-6">
          Remnawave Admin
        </h1>
        <p className="text-gray-400 mb-6">
          Войдите через Telegram для доступа к панели
        </p>
        <div ref={containerRef} className="flex justify-center" />
      </div>
    </div>
  );
}
```

### Задачи этапа 3:

```
[ ] Реализовать web/backend/core/security.py
[ ] Реализовать web/backend/api/v2/auth.py
[ ] Реализовать web/backend/api/deps.py
[ ] Создать Login.tsx страницу
[ ] Создать authStore.ts (Zustand)
[ ] Добавить protected routes
[ ] Тестирование аутентификации
[ ] Добавить logout и refresh логику
```

---

## ⚛️ Этап 4: Frontend базовый

**Длительность:** 1 неделя

### 4.1 Инициализация проекта

```bash
cd web/frontend
npm create vite@latest . -- --template react-ts
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p

# Зависимости
npm install react-router-dom zustand axios react-query @tanstack/react-query
npm install react-icons date-fns
npm install -D @types/react-router-dom
```

### 4.2 Tailwind Config

**Файл:** `web/frontend/tailwind.config.js`

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
        },
        dark: {
          100: '#1e293b',
          200: '#0f172a',
          300: '#020617',
        }
      }
    },
  },
  plugins: [],
}
```

### 4.3 Структура приложения

**Файл:** `web/frontend/src/App.tsx`

```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useAuthStore } from './store/authStore';

import Layout from './components/layout/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Users from './pages/Users';
import UserDetail from './pages/UserDetail';
import Nodes from './pages/Nodes';
import Violations from './pages/Violations';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';

const queryClient = new QueryClient();

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/*"
            element={
              <ProtectedRoute>
                <Layout>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/users" element={<Users />} />
                    <Route path="/users/:uuid" element={<UserDetail />} />
                    <Route path="/nodes" element={<Nodes />} />
                    <Route path="/violations" element={<Violations />} />
                    <Route path="/analytics" element={<Analytics />} />
                    <Route path="/settings" element={<Settings />} />
                  </Routes>
                </Layout>
              </ProtectedRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
```

### 4.4 Layout компоненты

**Файл:** `web/frontend/src/components/layout/Sidebar.tsx`

```tsx
import { Link, useLocation } from 'react-router-dom';
import {
  HiHome, HiUsers, HiServer, HiShieldExclamation,
  HiChartBar, HiCog, HiLogout
} from 'react-icons/hi';
import { useAuthStore } from '../../store/authStore';

const navigation = [
  { name: 'Dashboard', href: '/', icon: HiHome },
  { name: 'Users', href: '/users', icon: HiUsers },
  { name: 'Nodes', href: '/nodes', icon: HiServer },
  { name: 'Violations', href: '/violations', icon: HiShieldExclamation },
  { name: 'Analytics', href: '/analytics', icon: HiChartBar },
  { name: 'Settings', href: '/settings', icon: HiCog },
];

export default function Sidebar() {
  const location = useLocation();
  const { logout, user } = useAuthStore();

  return (
    <div className="flex flex-col w-64 bg-dark-200 border-r border-gray-700">
      {/* Logo */}
      <div className="flex items-center h-16 px-4 border-b border-gray-700">
        <span className="text-xl font-bold text-white">Remnawave</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-4 space-y-1">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href;
          return (
            <Link
              key={item.name}
              to={item.href}
              className={`flex items-center px-4 py-2 text-sm rounded-lg transition-colors ${
                isActive
                  ? 'bg-primary-600 text-white'
                  : 'text-gray-300 hover:bg-dark-100'
              }`}
            >
              <item.icon className="w-5 h-5 mr-3" />
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* User info */}
      <div className="p-4 border-t border-gray-700">
        <div className="flex items-center">
          <div className="flex-1">
            <p className="text-sm font-medium text-white">{user?.username}</p>
            <p className="text-xs text-gray-400">Administrator</p>
          </div>
          <button
            onClick={logout}
            className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-dark-100"
          >
            <HiLogout className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  );
}
```

### 4.5 API Client

**Файл:** `web/frontend/src/api/client.ts`

```typescript
import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '../store/authStore';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8081';

const client = axios.create({
  baseURL: `${API_URL}/api/v2`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - добавляем токен
client.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = useAuthStore.getState().accessToken;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - обрабатываем ошибки
client.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Попытка refresh token
      const refreshToken = useAuthStore.getState().refreshToken;
      if (refreshToken) {
        try {
          const response = await axios.post(`${API_URL}/api/v2/auth/refresh`, {
            refresh_token: refreshToken,
          });

          const { access_token, refresh_token } = response.data;
          useAuthStore.getState().setTokens(access_token, refresh_token);

          // Повторяем оригинальный запрос
          const config = error.config!;
          config.headers.Authorization = `Bearer ${access_token}`;
          return client(config);
        } catch {
          // Refresh failed - logout
          useAuthStore.getState().logout();
        }
      }
    }
    return Promise.reject(error);
  }
);

export default client;
```

### Задачи этапа 4:

```
[ ] Инициализировать Vite проект
[ ] Настроить Tailwind CSS
[ ] Создать структуру компонентов
[ ] Реализовать Layout (Sidebar, Header)
[ ] Создать API client с interceptors
[ ] Создать authStore (Zustand)
[ ] Реализовать роутинг с protected routes
[ ] Создать базовые UI компоненты (Button, Input, Modal, Table)
```

---

## 📄 Этап 5: Основные страницы

**Длительность:** 2-3 недели

### 5.1 Dashboard

```tsx
// Карточки статистики
- Всего пользователей
- Онлайн сейчас
- Активных нод
- Нарушений сегодня

// Графики
- Connections за 24 часа
- Traffic за неделю

// Live Activity (последние события)
- Подключения
- Нарушения
- Блокировки
```

### 5.2 Users Page

```tsx
// Таблица пользователей
- Поиск по username/email/UUID
- Фильтры по статусу
- Сортировка
- Пагинация

// Bulk actions
- Выбор нескольких
- Массовые операции

// Quick actions
- Enable/Disable
- Reset traffic
- View details
```

### 5.3 User Detail Page

```tsx
// Profile info
- Основные данные
- Subscription info
- Traffic usage

// Anti-Abuse section
- Trust Score
- Violation history
- Active connections
- Connection map

// Actions
- Edit user
- Block/Unblock
- Reset traffic
- Delete
```

### 5.4 Nodes Page

```tsx
// Таблица нод
- Статус (online/offline)
- Traffic usage
- Connections count

// Node detail
- Configuration
- Statistics
- Agent token
```

### 5.5 Violations Page

```tsx
// Список нарушений
- Фильтр по severity
- Фильтр по статусу
- Поиск по пользователю

// Violation detail
- Score breakdown
- IP addresses
- Actions taken
- Resolve options
```

### Задачи этапа 5:

```
[ ] Dashboard страница
    [ ] Stats cards
    [ ] Charts (recharts или chart.js)
    [ ] Live activity feed

[ ] Users страница
    [ ] Table component
    [ ] Search и filters
    [ ] Pagination
    [ ] Bulk actions

[ ] User Detail страница
    [ ] Profile section
    [ ] Anti-abuse info
    [ ] Connection history
    [ ] Action buttons

[ ] Nodes страница
    [ ] Nodes table
    [ ] Node detail modal
    [ ] Status indicators

[ ] Violations страница
    [ ] Violations list
    [ ] Violation detail
    [ ] Resolve actions

[ ] Settings страница
    [ ] Config sections
    [ ] Save/Reset buttons
```

---

## ⚡ Этап 6: Real-time функции

**Длительность:** 1 неделя

### 6.1 WebSocket Backend

**Файл:** `web/backend/api/v2/websocket.py`

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Set
import asyncio
import json

from web.backend.api.deps import get_current_admin_ws

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections.copy():
            try:
                await connection.send_json(message)
            except:
                self.active_connections.discard(connection)

manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    admin = Depends(get_current_admin_ws),
):
    await manager.connect(websocket)
    try:
        while True:
            # Получаем сообщения от клиента (ping/pong)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# Функция для отправки событий (вызывается из других частей приложения)
async def broadcast_event(event_type: str, data: dict):
    await manager.broadcast({
        "type": event_type,
        "data": data,
    })
```

### 6.2 WebSocket Hook (Frontend)

**Файл:** `web/frontend/src/hooks/useWebSocket.ts`

```typescript
import { useEffect, useRef, useCallback } from 'react';
import { useAuthStore } from '../store/authStore';

type MessageHandler = (data: any) => void;

export function useWebSocket(onMessage: MessageHandler) {
  const wsRef = useRef<WebSocket | null>(null);
  const { accessToken } = useAuthStore();

  const connect = useCallback(() => {
    if (!accessToken) return;

    const wsUrl = `${import.meta.env.VITE_WS_URL || 'ws://localhost:8081'}/api/v2/ws?token=${accessToken}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected');
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      onMessage(data);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      // Reconnect после 3 секунд
      setTimeout(connect, 3000);
    };

    wsRef.current = ws;
  }, [accessToken, onMessage]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  return wsRef.current;
}
```

### 6.3 Live Activity Component

```tsx
import { useState } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';

interface Activity {
  id: string;
  type: 'connection' | 'violation' | 'block';
  message: string;
  timestamp: Date;
}

export default function LiveActivity() {
  const [activities, setActivities] = useState<Activity[]>([]);

  useWebSocket((message) => {
    if (message.type === 'activity') {
      setActivities((prev) => [message.data, ...prev].slice(0, 50));
    }
  });

  return (
    <div className="bg-dark-100 rounded-lg p-4">
      <h3 className="text-lg font-semibold text-white mb-4">
        Live Activity
      </h3>
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {activities.map((activity) => (
          <div
            key={activity.id}
            className="flex items-center text-sm text-gray-300"
          >
            <span className="w-2 h-2 rounded-full mr-2 bg-green-500" />
            <span>{activity.message}</span>
            <span className="ml-auto text-gray-500">
              {activity.timestamp.toLocaleTimeString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### Задачи этапа 6:

```
[ ] Реализовать WebSocket endpoint
[ ] Интегрировать с событиями (violations, connections)
[ ] Создать useWebSocket hook
[ ] Добавить Live Activity на Dashboard
[ ] Добавить real-time обновления на страницах
[ ] Reconnect логика
[ ] Ping/pong для keep-alive
```

---

## 🚀 Этап 7: Продвинутые функции

**Длительность:** 2-3 недели

### 7.1 Карта подключений

```tsx
// Интерактивная карта мира
- Показывать точки подключений
- Цвет по статусу (normal/suspicious/blocked)
- Tooltip с информацией
- Zoom и pan

// Библиотеки:
- react-simple-maps
- или leaflet
```

### 7.2 Графики и диаграммы

```tsx
// Recharts для графиков
- Line chart (traffic, connections)
- Bar chart (violations by severity)
- Pie chart (user distribution)
- Area chart (bandwidth)
```

### 7.3 Экспорт отчётов

```tsx
// Генерация отчётов
- Выбор периода
- Выбор метрик
- Формат (CSV, JSON, PDF)
- Скачивание файла
```

### 7.4 Dark/Light Theme

```tsx
// Theme switcher
- Сохранение в localStorage
- CSS variables
- Tailwind dark mode
```

### Задачи этапа 7:

```
[ ] Карта подключений (react-simple-maps)
[ ] Графики (recharts)
[ ] Экспорт отчётов
[ ] Dark/Light theme
[ ] Responsive design (mobile)
[ ] Keyboard shortcuts
[ ] Notifications (toast)
[ ] Error boundaries
[ ] Loading states
[ ] Empty states
```

---

## ✅ Чеклист готовности

### MVP (Minimum Viable Product)

```
Backend:
[ ] FastAPI приложение работает
[ ] Аутентификация через Telegram
[ ] API для users, nodes, hosts
[ ] Базовая документация (Swagger)

Frontend:
[ ] Login через Telegram
[ ] Dashboard с основными метриками
[ ] Users list с поиском
[ ] User detail страница
[ ] Nodes list
[ ] Базовый responsive design

Infrastructure:
[ ] Docker Compose работает
[ ] Nginx настроен
[ ] HTTPS (в production)
```

### Production Ready

```
[ ] Все API endpoints реализованы
[ ] WebSocket для real-time
[ ] Полное покрытие тестами
[ ] Error handling везде
[ ] Logging и мониторинг
[ ] Rate limiting
[ ] CORS настроен правильно
[ ] Security headers
[ ] Документация пользователя
[ ] CI/CD pipeline
```

---

## 📚 Технологический стек

### Backend
- **FastAPI** — web framework
- **Pydantic** — validation
- **python-jose** — JWT
- **uvicorn** — ASGI server
- **asyncpg** — PostgreSQL (shared with bot)

### Frontend
- **React 18** — UI library
- **TypeScript** — type safety
- **Vite** — build tool
- **Tailwind CSS** — styling
- **React Router** — routing
- **Zustand** — state management
- **TanStack Query** — data fetching
- **Recharts** — charts
- **React Icons** — icons

### Infrastructure
- **Docker** — containerization
- **Nginx** — reverse proxy
- **PostgreSQL** — database (shared)

---

## 🔗 Полезные ссылки

- [Telegram Login Widget](https://core.telegram.org/widgets/login)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)
- [Tailwind CSS](https://tailwindcss.com/)
- [Zustand](https://zustand-demo.pmnd.rs/)
- [TanStack Query](https://tanstack.com/query)
- [Recharts](https://recharts.org/)

---

*План версии 1.0. Создан: 01.02.2026*

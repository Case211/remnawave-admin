# 📋 План развития Remnawave Admin Bot

> **Версия документа:** 1.0
> **Дата создания:** 26.01.2026
> **Текущая версия проекта:** 1.5.x

---

## 📊 Текущее состояние проекта

### ✅ Что уже реализовано:
- Telegram бот на aiogram 3.12 с админ-панелью
- PostgreSQL база с таблицами users, nodes, hosts, user_connections
- REST API клиент к Remnawave (~60 методов)
- Webhook сервер для real-time событий
- HWID устройства (добавление/удаление/лимиты)
- Таблица `user_connections` для хранения IP адресов
- Система уведомлений с разделением по топикам
- Кэширование и синхронизация данных

### ❌ Чего не хватает:
- Автоматический мониторинг IP в реальном времени
- Детектирование превышения лимита устройств по IP
- Система временной блокировки
- Веб-интерфейс для управления

---

## 🎯 Стратегические цели

1. **Anti-Abuse система** — защита от шаринга аккаунтов
2. **Веб-панель управления** — полноценный UI для администраторов
3. **Расширенная аналитика** — мониторинг и отчёты
4. **Автоматизация** — правила и триггеры без ручного вмешательства

---

## 🚀 Фаза 1: Anti-Abuse система (Временная блокировка)

### 1.1 Мониторинг IP подключений

**Цель:** Отслеживание активных IP адресов пользователя в реальном времени

**Задачи:**

```
[ ] Расширить webhook обработчик для событий подключения
    - Добавить обработку user.connected / user.disconnected событий
    - Записывать IP, время, ноду в user_connections

[ ] Создать сервис ConnectionMonitor
    - Периодическая проверка активных подключений (каждые 30-60 сек)
    - Запрос к Remnawave API для получения online пользователей
    - Сопоставление IP адресов с HWID лимитом

[ ] Добавить методы в database.py:
    - get_active_connections_count(user_uuid) -> int
    - get_unique_ips_in_window(user_uuid, window_minutes=5) -> int
    - is_user_over_device_limit(user_uuid) -> bool
```

**Структура данных:**
```python
class ConnectionEvent:
    user_uuid: str
    ip_address: str
    node_uuid: str
    connected_at: datetime
    device_fingerprint: Optional[str]  # дополнительная идентификация

class DeviceLimitViolation:
    user_uuid: str
    hwid_limit: int
    actual_ips: int
    ip_addresses: List[str]
    detected_at: datetime
    auto_action: str  # 'warn', 'temp_block', 'permanent_block'
```

### 1.2 Система детектирования нарушений

**Цель:** Выявление случаев превышения лимита устройств

**Логика детектирования:**
```
ЕСЛИ hwid_device_limit = 3 И уникальных_IP_за_5_минут >= 5
ТО это нарушение (шаринг аккаунта)
```

**Задачи:**

```
[ ] Создать сервис ViolationDetector (services/violation_detector.py)
    - check_user_violations(user_uuid) -> Optional[Violation]
    - get_all_violations(since_hours=24) -> List[Violation]
    - calculate_severity(violation) -> ViolationSeverity

[ ] Определить уровни нарушений:
    - LOW: IP = limit + 1 (возможно, смена сети)
    - MEDIUM: IP = limit + 2 (вероятный шаринг)
    - HIGH: IP >= limit * 2 (явный шаринг)
    - CRITICAL: IP >= limit * 3 (массовый шаринг)

[ ] Добавить таблицу violations в БД:
    CREATE TABLE violations (
        id SERIAL PRIMARY KEY,
        user_uuid UUID NOT NULL,
        violation_type VARCHAR(50),
        severity VARCHAR(20),
        hwid_limit INT,
        detected_ips INT,
        ip_addresses JSONB,
        action_taken VARCHAR(50),
        created_at TIMESTAMP DEFAULT NOW(),
        resolved_at TIMESTAMP,
        resolved_by BIGINT  -- admin telegram_id
    );
```

### 1.3 Механизм временной блокировки

**Цель:** Автоматическая временная блокировка нарушителей

**Задачи:**

```
[ ] Создать сервис AutoBlocker (services/auto_blocker.py)
    - schedule_temp_block(user_uuid, duration_hours, reason)
    - execute_block(user_uuid) -> bool
    - schedule_unblock(user_uuid, unblock_at)
    - execute_unblock(user_uuid) -> bool

[ ] Добавить таблицу temp_blocks в БД:
    CREATE TABLE temp_blocks (
        id SERIAL PRIMARY KEY,
        user_uuid UUID NOT NULL,
        reason VARCHAR(255),
        violation_id INT REFERENCES violations(id),
        blocked_at TIMESTAMP DEFAULT NOW(),
        unblock_at TIMESTAMP NOT NULL,
        actual_unblock_at TIMESTAMP,
        blocked_by VARCHAR(50),  -- 'auto' или admin telegram_id
        is_active BOOLEAN DEFAULT TRUE
    );

[ ] Интегрировать с Remnawave API:
    - Использовать disable_user() для блокировки
    - Использовать enable_user() для разблокировки
    - Добавить в описание причину блокировки

[ ] Создать фоновую задачу UnblockScheduler:
    - Проверка каждую минуту
    - Автоматическая разблокировка по расписанию
    - Уведомление в Telegram при разблокировке
```

**Правила автоблокировки:**

| Нарушение | Действие | Длительность |
|-----------|----------|--------------|
| Первое (LOW) | Предупреждение | — |
| Первое (MEDIUM+) | Блокировка | 1 час |
| Второе | Блокировка | 6 часов |
| Третье | Блокировка | 24 часа |
| Четвёртое+ | Блокировка | 7 дней |

### 1.4 Настройки Anti-Abuse

**Задачи:**

```
[ ] Добавить таблицу anti_abuse_settings:
    CREATE TABLE anti_abuse_settings (
        id SERIAL PRIMARY KEY,
        setting_key VARCHAR(100) UNIQUE,
        setting_value JSONB,
        updated_at TIMESTAMP DEFAULT NOW(),
        updated_by BIGINT
    );

[ ] Реализовать настраиваемые параметры:
    - detection_window_minutes: 5 (окно проверки)
    - ip_tolerance: 1 (допустимое превышение)
    - auto_block_enabled: true
    - first_violation_action: 'warn' | 'block_1h'
    - notification_on_violation: true
    - whitelist_user_uuids: []  (исключения)

[ ] Добавить команды в Telegram бот:
    - /antiabuse_settings — просмотр настроек
    - /antiabuse_stats — статистика нарушений
    - /antiabuse_whitelist — управление исключениями
```

### 1.5 Уведомления о нарушениях

**Задачи:**

```
[ ] Добавить новый топик notifications_topic_violations

[ ] Формат уведомлений:
    🚨 Обнаружено нарушение лимита устройств

    👤 Пользователь: @username
    📊 Лимит HWID: 3
    🌐 Активных IP: 5
    📍 IP адреса:
       • 185.xxx.xxx.1 (RU, Moscow)
       • 185.xxx.xxx.2 (RU, SPB)
       • 91.xxx.xxx.3 (DE, Berlin)
       • 91.xxx.xxx.4 (DE, Frankfurt)
       • 45.xxx.xxx.5 (NL, Amsterdam)

    ⚠️ Уровень: MEDIUM
    🔒 Действие: Временная блокировка на 1 час
    ⏰ Разблокировка: 26.01.2026 15:30 UTC

[ ] Добавить inline-кнопки в уведомление:
    [✅ Разблокировать] [⏰ Продлить блок] [🚫 Пермабан]
```

### 1.6 Интерфейс управления в Telegram

**Задачи:**

```
[ ] Новый раздел в меню: "🛡 Anti-Abuse"
    ├── 📊 Статистика нарушений
    │   ├── За сегодня
    │   ├── За неделю
    │   └── За месяц
    ├── 🔴 Активные блокировки
    │   └── [Список с возможностью разблокировки]
    ├── 📋 История нарушений
    │   └── [Поиск по пользователю/дате]
    ├── ⚙️ Настройки
    │   ├── Окно детектирования
    │   ├── Допуск IP
    │   ├── Автоблокировка вкл/выкл
    │   └── Длительность блокировок
    └── 📝 Whitelist
        ├── Добавить пользователя
        └── Список исключений

[ ] Добавить в карточку пользователя:
    - Секция "История нарушений"
    - Кнопка "Добавить в whitelist"
    - Статус текущей блокировки (если есть)
```

---

## 🚀 Фаза 2: Расширенная аналитика

### 2.1 Геолокация IP

**Задачи:**

```
[ ] Интегрировать GeoIP базу (MaxMind GeoLite2 или ip-api.com)

[ ] Добавить в user_connections:
    - country_code VARCHAR(2)
    - city VARCHAR(100)
    - asn VARCHAR(100)  -- провайдер

[ ] Детектирование подозрительных паттернов:
    - Одновременные подключения из разных стран
    - VPN/Proxy детекция по ASN
    - Impossible travel (нереальное перемещение)
```

### 2.2 Дашборд статистики

**Задачи:**

```
[ ] Расширить /system команду:
    - Топ-10 пользователей по количеству IP
    - Топ-10 нарушителей за период
    - График нарушений по дням
    - Карта подключений по странам

[ ] Добавить экспорт отчётов:
    - CSV экспорт нарушений
    - Сводный отчёт за период
```

### 2.3 Система скоринга пользователей

**Задачи:**

```
[ ] Добавить trust_score для пользователей:
    - Начальный скор: 100
    - Нарушение LOW: -5
    - Нарушение MEDIUM: -15
    - Нарушение HIGH: -30
    - Месяц без нарушений: +10

[ ] Автоматические действия по скору:
    - < 50: автоматическое снижение HWID лимита
    - < 20: требуется ручная проверка
    - 0: автоматический бан
```

---

## 🚀 Фаза 3: Веб-панель управления

### 3.1 Архитектура веб-панели

**Технологический стек:**
```
Backend:  FastAPI (уже частично есть для webhook)
Frontend: React/Vue.js + TailwindCSS
Auth:     Telegram Login Widget + JWT
DB:       PostgreSQL (существующая)
Realtime: WebSocket для live-обновлений
```

**Структура проекта:**
```
remnawave-admin/
├── src/                    # Существующий Telegram бот
├── web/                    # Новая веб-панель
│   ├── backend/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── auth.py
│   │   │   │   ├── users.py
│   │   │   │   ├── nodes.py
│   │   │   │   ├── violations.py
│   │   │   │   ├── analytics.py
│   │   │   │   └── settings.py
│   │   │   ├── middleware/
│   │   │   ├── schemas/
│   │   │   └── main.py
│   │   ├── core/
│   │   │   ├── security.py
│   │   │   └── config.py
│   │   └── requirements.txt
│   └── frontend/
│       ├── src/
│       │   ├── components/
│       │   ├── pages/
│       │   ├── hooks/
│       │   ├── api/
│       │   └── App.tsx
│       ├── package.json
│       └── vite.config.ts
└── docker-compose.yml      # Обновлённый с веб-сервисами
```

### 3.2 Аутентификация и авторизация

**Задачи:**

```
[ ] Telegram Login Widget интеграция
    - Проверка hash от Telegram
    - Проверка telegram_id в списке админов
    - Генерация JWT токена

[ ] Ролевая модель:
    - SUPER_ADMIN: полный доступ
    - ADMIN: управление пользователями и нодами
    - MODERATOR: только просмотр + блокировки
    - VIEWER: только просмотр

[ ] Таблица admin_sessions:
    CREATE TABLE admin_sessions (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        jwt_token_hash VARCHAR(64),
        created_at TIMESTAMP DEFAULT NOW(),
        expires_at TIMESTAMP,
        ip_address INET,
        user_agent TEXT,
        is_active BOOLEAN DEFAULT TRUE
    );
```

### 3.3 Основные страницы веб-панели

**Dashboard (Главная)**
```
┌─────────────────────────────────────────────────────────────┐
│  📊 Dashboard                                    [Admin ▼]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 1,234    │ │ 45       │ │ 12       │ │ 3        │       │
│  │ Users    │ │ Online   │ │ Nodes    │ │ Alerts   │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                                                             │
│  ┌─────────────────────────────┐ ┌────────────────────────┐│
│  │ Traffic (24h)               │ │ Violations (7d)        ││
│  │ [=========== Graph ======]  │ │ [====== Chart ======]  ││
│  └─────────────────────────────┘ └────────────────────────┘│
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Recent Activity                                         ││
│  │ • User @john connected from 185.x.x.x          2m ago  ││
│  │ • ⚠️ Violation detected for @alice             5m ago  ││
│  │ • Node DE-1 restarted                         10m ago  ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

**Задачи страниц:**

```
[ ] Dashboard
    - Ключевые метрики в реальном времени
    - Графики трафика и подключений
    - Лента активности
    - Карта подключений по странам

[ ] Users Management
    - Таблица пользователей с фильтрами
    - Поиск (username, email, telegram_id)
    - Inline редактирование
    - Bulk операции
    - Детальная карточка пользователя

[ ] Nodes Management
    - Список нод с статусами
    - Управление (вкл/выкл/рестарт)
    - Графики нагрузки по нодам
    - Назначение config profiles

[ ] Anti-Abuse Center
    - Live-монитор активных подключений
    - Список нарушений с фильтрами
    - Управление блокировками
    - Настройки детектирования
    - Whitelist управление

[ ] Analytics
    - Отчёты по трафику
    - География пользователей
    - Тренды использования
    - Экспорт данных

[ ] Settings
    - Общие настройки системы
    - Управление админами
    - API токены
    - Webhook настройки
    - Уведомления
```

### 3.4 Real-time функционал

**Задачи:**

```
[ ] WebSocket сервер для live-обновлений:
    - Подключения пользователей
    - Статусы нод
    - Новые нарушения
    - Системные события

[ ] Интеграция с существующим webhook:
    - Broadcast событий в WebSocket
    - Кэширование последних событий
```

### 3.5 API для веб-панели

**Эндпоинты:**

```
# Auth
POST   /api/v1/auth/telegram      # Telegram Login
POST   /api/v1/auth/refresh       # Refresh JWT
POST   /api/v1/auth/logout        # Logout

# Users
GET    /api/v1/users              # List users (paginated)
GET    /api/v1/users/:uuid        # Get user details
PATCH  /api/v1/users/:uuid        # Update user
POST   /api/v1/users/:uuid/block  # Block user
POST   /api/v1/users/:uuid/unblock# Unblock user
GET    /api/v1/users/:uuid/connections  # User connections history

# Nodes
GET    /api/v1/nodes              # List nodes
GET    /api/v1/nodes/:uuid        # Node details
POST   /api/v1/nodes/:uuid/restart# Restart node
PATCH  /api/v1/nodes/:uuid/status # Enable/disable

# Violations
GET    /api/v1/violations         # List violations
GET    /api/v1/violations/:id     # Violation details
POST   /api/v1/violations/:id/resolve  # Resolve violation

# Blocks
GET    /api/v1/blocks             # Active blocks
POST   /api/v1/blocks             # Create manual block
DELETE /api/v1/blocks/:id         # Remove block

# Analytics
GET    /api/v1/analytics/traffic  # Traffic stats
GET    /api/v1/analytics/connections  # Connection stats
GET    /api/v1/analytics/violations   # Violation stats
GET    /api/v1/analytics/geo      # Geo distribution

# Settings
GET    /api/v1/settings           # All settings
PATCH  /api/v1/settings/:key      # Update setting

# WebSocket
WS     /api/v1/ws                 # Real-time events
```

---

## 🚀 Фаза 4: Продвинутые функции

### 4.1 Автоматизация и правила

**Задачи:**

```
[ ] Система правил (Rules Engine):
    - IF condition THEN action
    - Визуальный конструктор правил
    - Примеры:
      * IF unique_ips > hwid_limit * 2 THEN block_24h
      * IF country NOT IN ['RU', 'UA', 'BY'] THEN notify
      * IF traffic_today > 100GB THEN warn

[ ] Scheduled tasks:
    - Ежедневные отчёты
    - Автоматическая очистка старых данных
    - Бэкапы настроек
```

### 4.2 Интеграции

**Задачи:**

```
[ ] Discord webhook для уведомлений
[ ] Email уведомления (SMTP)
[ ] Slack интеграция
[ ] Prometheus метрики для Grafana
[ ] API для внешних систем (с rate limiting)
```

### 4.3 Мобильная версия

**Задачи:**

```
[ ] PWA (Progressive Web App)
    - Работа offline
    - Push уведомления
    - Установка на телефон

[ ] Адаптивный дизайн для мобильных
```

---

## 📅 Приоритеты и порядок реализации

### Высокий приоритет (Фаза 1)
1. **Мониторинг IP подключений** — основа для детектирования
2. **Детектирование нарушений** — выявление шаринга
3. **Механизм временной блокировки** — автоматическая защита
4. **Уведомления о нарушениях** — информирование админов

### Средний приоритет (Фаза 2-3)
5. **Настройки Anti-Abuse** — гибкость системы
6. **Геолокация IP** — дополнительная аналитика
7. **Веб-панель Backend** — API для UI
8. **Веб-панель Frontend** — визуальный интерфейс

### Низкий приоритет (Фаза 4)
9. **Rules Engine** — автоматизация
10. **Дополнительные интеграции** — расширение возможностей
11. **PWA** — мобильный доступ

---

## 🗃️ Миграции базы данных

### Миграция 0003: Anti-Abuse система

```sql
-- Таблица нарушений
CREATE TABLE violations (
    id SERIAL PRIMARY KEY,
    user_uuid UUID NOT NULL,
    violation_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    hwid_limit INT NOT NULL,
    detected_ips INT NOT NULL,
    ip_addresses JSONB NOT NULL,
    action_taken VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by BIGINT,
    notes TEXT
);

CREATE INDEX idx_violations_user_uuid ON violations(user_uuid);
CREATE INDEX idx_violations_created_at ON violations(created_at);
CREATE INDEX idx_violations_severity ON violations(severity);

-- Таблица временных блокировок
CREATE TABLE temp_blocks (
    id SERIAL PRIMARY KEY,
    user_uuid UUID NOT NULL,
    reason VARCHAR(255) NOT NULL,
    violation_id INT REFERENCES violations(id),
    blocked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    unblock_at TIMESTAMP WITH TIME ZONE NOT NULL,
    actual_unblock_at TIMESTAMP WITH TIME ZONE,
    blocked_by VARCHAR(50) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_temp_blocks_user_uuid ON temp_blocks(user_uuid);
CREATE INDEX idx_temp_blocks_unblock_at ON temp_blocks(unblock_at);
CREATE INDEX idx_temp_blocks_is_active ON temp_blocks(is_active);

-- Настройки Anti-Abuse
CREATE TABLE anti_abuse_settings (
    id SERIAL PRIMARY KEY,
    setting_key VARCHAR(100) UNIQUE NOT NULL,
    setting_value JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_by BIGINT
);

-- Whitelist пользователей
CREATE TABLE anti_abuse_whitelist (
    id SERIAL PRIMARY KEY,
    user_uuid UUID UNIQUE NOT NULL,
    added_by BIGINT NOT NULL,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reason TEXT
);

-- Расширение user_connections для гео-данных
ALTER TABLE user_connections
ADD COLUMN IF NOT EXISTS country_code VARCHAR(2),
ADD COLUMN IF NOT EXISTS city VARCHAR(100),
ADD COLUMN IF NOT EXISTS asn VARCHAR(100);
```

### Миграция 0004: Веб-панель

```sql
-- Админ роли
CREATE TYPE admin_role AS ENUM ('super_admin', 'admin', 'moderator', 'viewer');

-- Сессии админов
CREATE TABLE admin_sessions (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    role admin_role NOT NULL DEFAULT 'viewer',
    jwt_token_hash VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_activity_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address INET,
    user_agent TEXT,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_admin_sessions_telegram_id ON admin_sessions(telegram_id);
CREATE INDEX idx_admin_sessions_is_active ON admin_sessions(is_active);

-- Логи действий админов
CREATE TABLE admin_audit_log (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50),
    target_id VARCHAR(100),
    details JSONB,
    ip_address INET,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_log_telegram_id ON admin_audit_log(telegram_id);
CREATE INDEX idx_audit_log_created_at ON admin_audit_log(created_at);
```

---

## 📝 Конфигурация

### Новые переменные окружения

```env
# Anti-Abuse
ANTI_ABUSE_ENABLED=true
ANTI_ABUSE_DETECTION_WINDOW_MINUTES=5
ANTI_ABUSE_IP_TOLERANCE=1
ANTI_ABUSE_AUTO_BLOCK_ENABLED=true
ANTI_ABUSE_NOTIFICATION_TOPIC=violations

# GeoIP
GEOIP_ENABLED=true
GEOIP_DATABASE_PATH=/data/GeoLite2-City.mmdb
# или
GEOIP_API_URL=http://ip-api.com/json

# Web Panel
WEB_PANEL_ENABLED=true
WEB_PANEL_PORT=8081
WEB_PANEL_HOST=0.0.0.0
WEB_PANEL_SECRET_KEY=your-secret-key
WEB_PANEL_JWT_EXPIRY_HOURS=24
WEB_PANEL_CORS_ORIGINS=["http://localhost:3000"]
```

---

## 🔧 Технические заметки

### Интеграция с существующим кодом

1. **api_client.py** — добавить методы для получения online пользователей
2. **webhook.py** — расширить обработку событий подключения
3. **database.py** — добавить новые таблицы и методы
4. **notifications.py** — добавить топик для нарушений
5. **main.py** — добавить запуск новых сервисов (ViolationDetector, AutoBlocker)

### Совместимость

- Все новые функции должны быть опциональными (feature flags)
- Веб-панель не должна влиять на работу Telegram бота
- Graceful degradation если новые сервисы недоступны

---

## 📚 Документация

При реализации каждой фазы обновлять:
- README.md — описание новых функций
- CHANGELOG.md — история изменений
- API документация (OpenAPI/Swagger)
- Примеры конфигурации

---

*Документ будет обновляться по мере развития проекта.*

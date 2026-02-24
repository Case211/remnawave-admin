# План интеграции remnawave-bedolaga-telegram-bot в remnawave-admin

## Анализ проектов

### remnawave-admin (текущий проект)
- **Фокус**: Администрирование, мониторинг, anti-abuse
- **Пользователи**: Админы
- **Стек**: Python/aiogram + FastAPI + React/TS + AsyncPG (raw SQL)
- **Есть**: Детекция нарушений (5 анализаторов), мониторинг нод, аналитика трафика, RBAC, аудит, веб-терминал, бэкапы
- **Нет**: Платежей, тикетов поддержки, реферальной системы, промо-кодов, клиентского MiniApp

### bedolaga-bot (внешний проект)
- **Фокус**: Продажа подписок, клиентский self-service
- **Пользователи**: Конечные клиенты
- **Стек**: Python/aiogram + FastAPI + SQLAlchemy ORM + Redis
- **Есть**: 11+ платёжных провайдеров, подписки, промо-коды, рефералы, тикеты поддержки, MiniApp, маркетинг, аналитика продаж
- **API**: ~500 эндпоинтов (Web API + Cabinet API + Webhooks)
- **Нет**: Anti-abuse, мониторинга нод, RBAC, веб-панели для админа

### Общее
- Оба работают с Remnawave Panel API (пользователи, ноды, хосты)
- Оба используют Python + aiogram + FastAPI + PostgreSQL
- Оба используют Docker для деплоя

---

## Стратегия: Гибридная API-интеграция

**Ключевая идея**: Bedolaga остаётся отдельным сервисом, а remnawave-admin подключается к его Web API. Данные делятся на два типа:

### Статические данные → синхронизация в локальную БД
Данные, которые нужны для аналитики и не требуют актуальности в реальном времени:
- **Статистика** (`/stats/overview`) → `bedolaga_stats_snapshots`
- **Пользователи** (`/users`) → `bedolaga_users_cache`
- **Подписки** (`/subscriptions`) → `bedolaga_subscriptions_cache`
- **Транзакции** (`/transactions`) → `bedolaga_transactions_cache`

Синхронизация каждые 5 минут (настраивается через `BEDOLAGA_SYNC_INTERVAL`).

### Динамические данные → real-time прокси через API
Данные, которые требуют актуальности или операций записи:
- **Тикеты** (`/tickets`) — нужны свежие, операции ответа/статуса
- **Промо-группы** (`/promo-groups`) — CRUD операции
- **Промо-коды** (`/promo-codes`) — CRUD операции
- **Промо-офферы** (`/promo-offers`) — CRUD операции
- **Опросы** (`/polls`) — CRUD + статистика
- **Партнёры** (`/partners/referrers`) — статистика и управление
- **Рассылки** (`/broadcasts`) — создание и управление
- **Настройки** (`/settings`) — чтение/обновление
- **Логи** (`/logs/monitoring`, `/logs/support`) — чтение

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                        │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ remnawave-   │  │  bedolaga-   │  │  remnawave-  │  │
│  │ admin bot    │  │  bot         │  │  panel       │  │
│  │ (admin TG)   │  │ (client TG)  │  │  (VPN mgmt)  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                  │          │
│  ┌──────┴─────────────────┴──────────────────┘          │
│  │                                                      │
│  │  ┌──────────────┐      ┌──────────────┐             │
│  │  │ web-backend  │─HTTP─►│ bedolaga API │             │
│  │  │ (FastAPI)    │◄─────│ (port 8080)  │             │
│  │  │ unified API  │      └──────────────┘             │
│  │  └──────┬───────┘                                    │
│  │         │           ┌──────────────┐                 │
│  │         ├──────────►│ web-frontend  │                 │
│  │         │           │ (React SPA)   │                 │
│  │  ┌──────┴───────┐  └──────────────┘                 │
│  │  │  PostgreSQL   │                                   │
│  │  │ + cache tables│                                   │
│  │  └──────────────┘                                   │
│  │                                                      │
│  └──────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────┘
```

---

## Реализованные компоненты

### 1. HTTP клиент для Bedolaga API (`shared/bedolaga_client.py`)
- Async httpx клиент с retry и exponential backoff
- Авторизация через `X-API-Key` заголовок
- Методы для всех нужных эндпоинтов Bedolaga
- Кастомные исключения: `BedolagaNotFoundError`, `BedolagaUnauthorizedError`, etc.
- Глобальный инстанс `bedolaga_client`

### 2. Сервис синхронизации (`shared/bedolaga_sync.py`)
- Периодический синк (по умолчанию каждые 5 минут)
- Пагинация при синке больших коллекций
- Upsert в кэш-таблицы (ON CONFLICT DO UPDATE)
- Удаление устаревших записей
- Запись метаданных синка в `sync_metadata`
- Глобальный инстанс `bedolaga_sync_service`

### 3. Миграция БД (`alembic/versions/20260224_0036_add_bedolaga_cache_tables.py`)
Кэш-таблицы:
- `bedolaga_stats_snapshots` — исторические снепшоты статистики
- `bedolaga_users_cache` — кэш пользователей
- `bedolaga_subscriptions_cache` — кэш подписок
- `bedolaga_transactions_cache` — кэш транзакций
Индексы на ключевые поля для быстрых запросов.

### 4. API роутер (`web/backend/api/v2/bedolaga.py`)
Гибридные эндпоинты под `/api/v2/bedolaga/`:

**Из локального кэша (статика):**
- `GET /status` — статус интеграции
- `POST /sync` — ручной запуск синхронизации
- `GET /sync/status` — статус синхронизации
- `GET /overview` — последний снепшот статистики
- `GET /overview/history` — история снепшотов для графиков
- `GET /users` — список пользователей с поиском и пагинацией
- `GET /users/{id}` — детали пользователя (fallback на API)
- `GET /subscriptions` — список подписок с фильтрами
- `GET /transactions` — список транзакций с фильтрами
- `GET /transactions/stats` — аналитика по транзакциям
- `GET /revenue` — аналитика доходов (today/week/month/by_provider)

**Real-time прокси к Bedolaga:**
- `GET/POST /tickets/*` — тикеты поддержки
- `GET/POST/PATCH/DELETE /promo-groups/*` — промо-группы
- `GET/POST/PATCH/DELETE /promo-codes/*` — промо-коды
- `GET/POST /promo-offers/*` — промо-офферы
- `GET/POST/DELETE /polls/*` — опросы
- `GET /partners/*` — реферальная программа
- `GET/POST /broadcasts/*` — рассылки
- `GET/PUT /settings/*` — настройки бота
- `GET /logs/*` — логи мониторинга и поддержки

### 5. RBAC (`bedolaga` ресурс)
- `bedolaga:view` — просмотр данных
- `bedolaga:edit` — операции записи (синк, ответы на тикеты, промо, настройки)

### 6. Pydantic схемы (`web/backend/schemas/bedolaga.py`)
Типизированные модели для всех ответов API.

### 7. Коды ошибок (`web/backend/core/errors.py`)
- `BEDOLAGA_NOT_CONFIGURED` — интеграция не настроена
- `BEDOLAGA_UNAVAILABLE` — API недоступен
- `BEDOLAGA_INVALID_ENTITY` — неизвестная сущность для синка

### 8. Frontend
- **API клиент** (`web/frontend/src/api/bedolaga.ts`) — типизированные методы
- **Страница** (`web/frontend/src/pages/Bedolaga.tsx`) — полная страница с табами:
  - Overview (статистика + доход по провайдерам)
  - Users (таблица с поиском и пагинацией)
  - Subscriptions (таблица с фильтрами)
  - Transactions (таблица с фильтрами)
  - Tickets (real-time)
  - Promo Codes (real-time)
  - Partners (real-time)
- **Навигация** — пункт "Bedolaga" в сайдбаре (с иконкой Bot)
- **Роутинг** — `/bedolaga` маршрут в App.tsx
- **i18n** — переводы EN/RU

### 9. Конфигурация
Переменные окружения (`.env.example`):
- `BEDOLAGA_API_URL` — URL Web API бота Bedolaga
- `BEDOLAGA_API_KEY` — API-ключ для авторизации
- `BEDOLAGA_SYNC_INTERVAL` — интервал синхронизации (секунды, default: 300)

---

## Преимущества гибридного подхода

| Аспект | Shared DB (Вариант C) | Гибридный API (текущий) |
|--------|----------------------|------------------------|
| Зависимость от схемы БД | Ломается при обновлениях | Не зависит |
| Обновление Bedolaga | Нужно проверять схему | Обновляется свободно |
| Аналитика | Быстрая (локальная БД) | Быстрая (кэш) |
| Свежесть данных | Зависит от репликации | Статика: ~5 мин, динамика: real-time |
| Настройка | Сложная (shared DB, users, schema) | Простая (URL + API key) |
| Write-операции | Рискованно (конфликты) | Безопасно (через API) |

---

## Дальнейшее развитие

### Фаза 2: Расширенная аналитика
- Графики на основе recharts (revenue chart, user growth)
- Корреляция нарушений (anti-abuse) и оттока
- LTV пользователя (доход + срок жизни подписки)
- ROI промо-кампаний

### Фаза 3: Межсервисные уведомления
- Webhook от Bedolaga при новых тикетах → уведомление в admin-бот
- Webhook от admin при обнаружении нарушений → уведомление пользователю через Bedolaga
- Real-time обновления через WebSocket

### Фаза 4: Единый профиль пользователя
- Объединение данных: подписки + трафик + нарушения + платежи + тикеты
- Scoring: риск (anti-abuse) + ценность (LTV)

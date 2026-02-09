# Web Panel — Roadmap

План развития веб-панели Remnawave Admin.

---

## Текущее состояние (v1.7)

**Реализовано:**
- Dashboard со статистикой (пользователи, ноды, нарушения, трафик)
- CRUD пользователей с фильтрацией, сортировкой, пагинацией
- Детальная карточка пользователя (трафик, HWID, нарушения)
- Управление нодами (статус, перезапуск, агент-токены)
- Управление хостами (создание, редактирование, включение/выключение)
- Просмотр нарушений с IP Lookup и скор-разбивкой
- Настройки с динамическим сохранением в БД
- Авторизация: Telegram Login Widget + логин/пароль + JWT
- WebSocket для real-time обновлений
- Тёмная тема, адаптивный дизайн

**Стек:** React 18, TypeScript, Tailwind CSS, Vite, React Query, Zustand, Recharts, Axios

---

## Фаза 1 — Миграция на shadcn/ui ✅ ВЫПОЛНЕНО

**Зачем:** Сейчас весь UI написан на голом Tailwind (inline классы в страницах). shadcn/ui даёт готовую библиотеку компонентов на базе Radix UI + Tailwind с единым дизайном, доступностью (a11y) и полной кастомизацией (код копируется в проект).

**Что даст:**
- Консистентный дизайн-система (Button, Card, Dialog, Table, Select, Badge, Tabs, Input, ...)
- Встроенная доступность (клавиатурная навигация, ARIA)
- Упрощение кода страниц (вместо 20 строк Tailwind — 1 компонент)
- Единая тема с CSS-переменными (проще менять цвета)

### Задачи

| # | Задача | Описание | Статус |
|---|--------|----------|--------|
| 1.1 | Инициализация shadcn/ui | `components.json`, алиасы путей, `cn()` утилита, CSS-переменные для темы | ✅ |
| 1.2 | Базовые компоненты | Button, Card, Badge, Input, Label, Select, Dialog, Table, Tabs, Tooltip, DropdownMenu, Sheet, Separator, Skeleton, ScrollArea, Switch, Popover (17 компонентов) | ✅ |
| 1.3 | Рефакторинг Layout | Sidebar → lucide-react + Button/ScrollArea/Tooltip/Separator, Header → Button/Input/Badge | ✅ |
| 1.4 | Рефакторинг Dashboard | Card, Badge, Button, Skeleton, Separator + lucide-react иконки | ✅ |
| 1.5 | Рефакторинг Users + UserDetail | Table, Dialog, DropdownMenu, Badge, Button, Input, Select, Skeleton, Tabs | ✅ |
| 1.6 | Рефакторинг остальных страниц | Nodes, Hosts, Violations, Settings, Login — полный рефакторинг на shadcn/ui + lucide-react | ✅ |
| 1.7 | Удаление react-icons/hi | Полная замена react-icons/hi на lucide-react, исправление TS-ошибок | ✅ |

**Зависимости (установлены):** `@radix-ui/*` (dialog, dropdown-menu, select, tabs, tooltip, separator, label, popover, scroll-area, switch, slot), `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `tailwindcss-animate`

**Результат:** Все 8 страниц + Layout мигрированы на shadcn/ui. Единая дизайн-система с CSS-переменными (Remnawave тёмная тема с teal/cyan акцентами). Иконки: lucide-react вместо react-icons.

---

## Фаза 2 — Система ролей и прав администраторов (RBAC) ✅ ВЫПОЛНЕНО

**Зачем:** Сейчас все админы равноправны (проверяется только `telegram_id in ADMINS`). Нужен конструктор для создания админов с разными правами и лимитами.

### 2.1 Модель данных ✅

Новые таблицы в PostgreSQL:

```sql
-- Роли администраторов
CREATE TABLE admin_roles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,        -- "superadmin", "manager", "viewer", custom
    display_name VARCHAR(200),                 -- "Супер-администратор"
    description TEXT,
    is_system BOOLEAN DEFAULT false,           -- системные роли нельзя удалить
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Права (permissions)
CREATE TABLE admin_permissions (
    id SERIAL PRIMARY KEY,
    role_id INTEGER REFERENCES admin_roles(id) ON DELETE CASCADE,
    resource VARCHAR(50) NOT NULL,             -- "users", "nodes", "hosts", "violations", "settings", "admins"
    action VARCHAR(50) NOT NULL,               -- "view", "create", "edit", "delete", "bulk_operations"
    UNIQUE(role_id, resource, action)
);

-- Администраторы с ролями и лимитами
CREATE TABLE admin_accounts (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE,                 -- NULL для password-only
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255),
    role_id INTEGER REFERENCES admin_roles(id),

    -- Лимиты (NULL = без ограничений)
    max_users INTEGER,                         -- макс. количество создаваемых пользователей
    max_traffic_gb INTEGER,                    -- макс. суммарный трафик для его пользователей
    max_nodes INTEGER,                         -- макс. нод
    max_hosts INTEGER,                         -- макс. хостов

    -- Счётчики использования
    users_created INTEGER DEFAULT 0,
    traffic_used_bytes BIGINT DEFAULT 0,

    is_active BOOLEAN DEFAULT true,
    created_by INTEGER REFERENCES admin_accounts(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Реализация:** Alembic миграция `20260209_0009_add_rbac_tables.py` — все 4 таблицы (`admin_roles`, `admin_permissions`, `admin_accounts`, `admin_audit_log`) созданы с индексами и ограничениями. Автоматическая миграция существующих записей из `admin_credentials`.

### 2.2 Предустановленные роли ✅

| Роль | Описание | Права |
|------|----------|-------|
| **superadmin** | Полный доступ, управление другими админами | Всё |
| **manager** | Управление пользователями, нодами, хостами | users.*, nodes.view/edit, hosts.view/edit |
| **operator** | Только просмотр + базовые действия | *.view, users.create/edit |
| **viewer** | Только просмотр | *.view |

**Реализация:** 4 системные роли (is_system=true) с полной матрицей прав засеяны в миграции. 9 ресурсов × 5 действий.

### 2.3 Backend

| # | Задача | Описание | Статус |
|---|--------|----------|--------|
| 2.3.1 | Миграция БД | Alembic: создать таблицы admin_roles, admin_permissions, admin_accounts | ✅ |
| 2.3.2 | Middleware прав | Декоратор `@require_permission("users", "create")` для эндпоинтов | ✅ |
| 2.3.3 | Проверка лимитов | Middleware: при создании пользователя проверять `users_created < max_users` | ✅ |
| 2.3.4 | API: Админы | CRUD `/api/v2/admins` — список, создание, редактирование, удаление | ✅ |
| 2.3.5 | API: Роли | CRUD `/api/v2/roles` — управление ролями и правами | ✅ |
| 2.3.6 | Аудит действий | Логирование: кто, когда, что сделал (таблица `admin_audit_log`) | ✅ |
| 2.3.7 | Миграция auth | Переход от `admin_credentials` к `admin_accounts` (обратная совместимость) | ✅ |

**Детали реализации:**
- `rbac.py` (613 строк): `require_permission()`, `require_superadmin()`, кеширование прав (TTL 60с), `AdminUser` dataclass
- `deps.py` (304 строки): резолвинг админа с fallback на legacy `admin_credentials` и `.env`
- `admins.py` (266 строк): 6 эндпоинтов (CRUD + audit-log), валидация паролей, аудит всех действий
- `roles.py` (224 строки): 6 эндпоинтов (CRUD + resources), защита системных ролей, инвалидация кеша
- Права применены на **всех** API v2 эндпоинтах: users, nodes, hosts, violations, settings, analytics, admins, roles

**2.3.3:** Dependency `require_quota()` в `deps.py` проверяет лимиты перед созданием. Подключён к POST-эндпоинтам users, nodes, hosts. После успешного создания вызывается `increment_usage_counter()`. Superadmin и legacy-админы обходят проверку.

### 2.4 Frontend — Страница «Администраторы»

| # | Задача | Описание | Статус |
|---|--------|----------|--------|
| 2.4.1 | Список админов | Таблица: имя, роль, лимиты, использование, статус, дата создания | ✅ |
| 2.4.2 | Конструктор админа | Форма создания: имя, Telegram ID (опц.), роль, лимиты (ползунки/инпуты) | ✅ |
| 2.4.3 | Редактирование | Изменение роли, лимитов, включение/выключение | ✅ |
| 2.4.4 | Конструктор ролей | Матрица прав: ресурс × действие (чекбоксы), название роли | ✅ |
| 2.4.5 | Визуализация лимитов | Прогресс-бары: 23/50 пользователей, 450/1000 ГБ трафика | ✅ |
| 2.4.6 | Permission-aware UI | Скрывать/блокировать кнопки, на которые у админа нет прав | ✅ |

**Детали реализации:**
- `Admins.tsx`: страница с 3 вкладками (Админы, Роли, Журнал аудита), адаптивный дизайн (таблица + мобильные карточки)
- `QuotaBar`: прогресс-бары с цветовой индикацией (зелёный/жёлтый/красный), поддержка ∞
- `RoleBadge`: цветные бейджи ролей (superadmin=красный, manager=синий, operator=жёлтый, viewer=серый)
- `PermissionGate.tsx`: компонент + хук `useHasPermission()` для условного рендеринга
- `permissionStore.ts` (Zustand): загрузка прав из `/auth/me`, bypass для superadmin
- `Sidebar.tsx`: фильтрация навигации по правам
- `admins.ts`: TypeScript API-клиент для всех RBAC-эндпоинтов

**Результат:** Полная RBAC-система с 4 системными ролями, матрицей прав (9 ресурсов × 5 действий), CRUD для админов и ролей, журнал аудита, Permission-aware UI на всех страницах. Обратная совместимость с legacy-авторизацией.

---

## Фаза 3 — Улучшение Dashboard ✅ ВЫПОЛНЕНО

**Вдохновение:** Панель «Решала» — живые графики, карточки серверов с метриками, дельта-индикаторы.

### 3.1 Графики трафика и подключений ✅

| # | Задача | Описание | Статус |
|---|--------|----------|--------|
| 3.1.1 | Backend: временные ряды | Новый эндпоинт `/analytics/timeseries` — трафик и подключения по часам/дням | ✅ |
| 3.1.2 | График трафика | Line/Area chart: трафик за 24ч/7д/30д с переключателем периода | ✅ |
| 3.1.3 | График подключений | Area chart: активные подключения по нодам (stacked) | ✅ |
| 3.1.4 | Дельта-индикаторы | На карточках статистики: "+12% за сутки", "-3 ноды за неделю" | ✅ |

**Детали реализации:**
- `GET /analytics/timeseries` — период (24h/7d/30d), метрика (traffic/connections). Данные из upstream `/api/bandwidth-stats/nodes` с series. Для трафика — stacked AreaChart по нодам (при наличии series) или LineChart (fallback). Для подключений — текущий snapshot users_online по нодам.
- `GET /analytics/deltas` — сравнение today vs yesterday для трафика (%) и нарушений (абсолютно)
- `DeltaIndicator` компонент: зелёная стрелка вверх / красная вниз, показывает % или абсолют
- `PeriodSwitcher` — компактный переключатель 24ч/7д/30д
- Кастомные Recharts tooltip'ы с форматированием байт/подключений

### 3.2 Node Fleet (карточки серверов) ✅

| # | Задача | Описание | Статус |
|---|--------|----------|--------|
| 3.2.1 | Backend: метрики нод | `GET /analytics/node-fleet` — все ноды с uptime, Xray версия, скорость DL/UL, CPU, RAM | ✅ |
| 3.2.2 | Карточки нод на Dashboard | Компактные карточки: статус-индикатор, IP, пользователей онлайн, трафик сегодня, uptime | ✅ |
| 3.2.3 | Быстрые действия | На карточках: перезапуск, включить/выключить (без перехода на страницу Nodes) | ✅ |
| 3.2.4 | Группировка | По статусу: сначала проблемные (offline), потом рабочие, затем отключённые | ✅ |

**Детали реализации:**
- `NodeFleetCard` — компактная карточка ноды с сеткой метрик 2×N, иконки lucide-react
- Метрики: онлайн пользователи, трафик сегодня, uptime, Xray версия, DL/UL скорость, CPU, RAM
- Быстрые действия через Tooltip + Button: перезапуск, вкл/выкл (useMutation + invalidateQueries)
- Сортировка: offline → online → disabled. Badge статуса с цветовой индикацией
- Обогащение данных: traffic today из date-range API, скорость из realtime API

### 3.3 Системный статус ✅

| # | Задача | Описание | Статус |
|---|--------|----------|--------|
| 3.3.1 | Расширенный health check | `GET /analytics/system/components` — Remnawave API (response time), PostgreSQL (pool), Nodes (online/total), WebSocket (sessions) | ✅ |
| 3.3.2 | Карточка системы | Блок: компоненты с статусами (online/offline/degraded), версия, uptime сервиса | ✅ |

**Детали реализации:**
- `SystemStatusCard` — список компонентов с иконками, статус-бейджами, метриками
- 4 компонента: Remnawave API (с замером response time), PostgreSQL (pool size/free), Nodes (online/total), WebSocket (active connections)
- Статусы: online (зелёный пульс), offline (красный), degraded (жёлтый), unknown (серый)
- Uptime процесса через psutil, версия из конфига

**Результат:** Dashboard полностью обновлён: графики трафика с переключателем периода, stacked area chart по нодам, дельта-индикаторы на статистических карточках, парк серверов с компактными карточками и быстрыми действиями, расширенный системный статус с метриками компонентов. WebSocket-интеграция обновлена для инвалидации новых query keys.

---

## Фаза 4 — Улучшение существующих функций

### 4.1 Массовые операции

| # | Задача | Описание |
|---|--------|----------|
| 4.1.1 | Выбор нескольких пользователей | Чекбоксы в таблице Users, кнопки "Выбрать всё / Снять" |
| 4.1.2 | Массовые действия | Включить / Выключить / Удалить / Изменить лимит трафика / Продлить подписку |
| 4.1.3 | Backend: batch endpoints | `POST /users/batch/enable`, `/batch/disable`, `/batch/update` |
| 4.1.4 | Подтверждение | Диалог: "Вы уверены? Затронуто N пользователей" с предпросмотром |

### 4.2 Экспорт данных

| # | Задача | Описание |
|---|--------|----------|
| 4.2.1 | Экспорт пользователей | CSV/JSON: текущая выборка (с фильтрами) или все |
| 4.2.2 | Экспорт нарушений | CSV: дата, пользователь, скор, severity, причины, IP |
| 4.2.3 | Экспорт статистики | PDF/PNG: текущий dashboard (для отчётов) |

### 4.3 Улучшенный поиск

| # | Задача | Описание |
|---|--------|----------|
| 4.3.1 | Глобальный поиск | Command Palette (Cmd+K): поиск пользователей, нод, хостов из любой страницы |
| 4.3.2 | Сохранённые фильтры | Возможность сохранить набор фильтров и быстро переключаться |
| 4.3.3 | Расширенный поиск нарушений | По IP, по стране, по ASN, по диапазону дат |

### 4.4 Улучшения UX

| # | Задача | Описание |
|---|--------|----------|
| 4.4.1 | Toast-уведомления | Уведомления о действиях (создано, обновлено, ошибка) вместо alert |
| 4.4.2 | Skeleton-загрузки | Скелетоны при загрузке данных вместо спиннеров |
| 4.4.3 | Keyboard shortcuts | Горячие клавиши: Esc закрыть модал, Enter подтвердить, навигация по таблице |
| 4.4.4 | Breadcrumbs | Навигация: Dashboard > Users > user@email |

---

## Фаза 5 — Новые функции

### 5.1 Журнал аудита (Audit Log)

| # | Задача | Описание |
|---|--------|----------|
| 5.1.1 | Таблица `audit_log` | admin_id, action, resource, resource_id, details (JSON), ip, timestamp |
| 5.1.2 | Backend: автоматическая запись | Middleware: логировать все мутирующие действия (POST/PUT/DELETE) |
| 5.1.3 | Страница «Журнал» | Timeline с фильтрами: по админу, по ресурсу, по периоду |
| 5.1.4 | На карточке пользователя | Вкладка "История": кто и когда менял настройки пользователя |

### 5.2 Системные логи

| # | Задача | Описание |
|---|--------|----------|
| 5.2.1 | API для чтения логов | Стриминг логов бота и бэкенда через WebSocket |
| 5.2.2 | Страница «Логи» | Real-time просмотр логов с фильтрами по уровню (INFO/WARNING/ERROR) |
| 5.2.3 | Поиск по логам | Grep-подобный поиск по содержимому |

### 5.3 Проверка обновлений

| # | Задача | Описание |
|---|--------|----------|
| 5.3.1 | Backend: version check | Сравнение текущей версии с GitHub Releases API |
| 5.3.2 | Блок на Dashboard | Текущая версия + доступное обновление + changelog |
| 5.3.3 | Проверка зависимостей | Версии Xray на нодах, версия PostgreSQL, Python |

### 5.4 Расширенная аналитика

| # | Задача | Описание |
|---|--------|----------|
| 5.4.1 | Географическая карта | Карта подключений пользователей (heatmap по странам) |
| 5.4.2 | Топ пользователей по трафику | Рейтинг с графиками потребления |
| 5.4.3 | Анализ тенденций | Рост пользователей, трафика, нарушений за период |

---

## Фаза 6 — Автоматизации (конструктор правил)

**Зачем:** Сейчас все действия выполняются вручную. Нужна возможность задать правила «если X → сделать Y», которые срабатывают автоматически. Не система плагинов со сторонним кодом — а встроенный движок правил с визуальным конструктором.

### 6.1 Модель данных

```sql
-- Правила автоматизации
CREATE TABLE automation_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,              -- "Блокировка при превышении трафика"
    description TEXT,
    is_enabled BOOLEAN DEFAULT true,
    category VARCHAR(50) NOT NULL,           -- "users", "nodes", "violations", "system"

    -- Триггер: что запускает правило
    trigger_type VARCHAR(50) NOT NULL,       -- "event", "schedule", "threshold"
    trigger_config JSONB NOT NULL,           -- конфигурация триггера (см. ниже)

    -- Условия (опционально, дополнительные фильтры)
    conditions JSONB,                        -- [{"field": "traffic_gb", "op": ">", "value": 100}]

    -- Действие: что делать
    action_type VARCHAR(50) NOT NULL,        -- "disable_user", "notify", "restart_node", "block_user", ...
    action_config JSONB NOT NULL,            -- параметры действия

    -- Мета
    last_triggered_at TIMESTAMPTZ,
    trigger_count INTEGER DEFAULT 0,
    created_by INTEGER REFERENCES admin_accounts(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Лог срабатываний
CREATE TABLE automation_log (
    id SERIAL PRIMARY KEY,
    rule_id INTEGER REFERENCES automation_rules(id),
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    target_type VARCHAR(50),                 -- "user", "node"
    target_id VARCHAR(200),                  -- UUID пользователя/ноды
    action_taken VARCHAR(100),
    result VARCHAR(50),                      -- "success", "error", "skipped"
    details JSONB
);
```

### 6.2 Типы триггеров

| Триггер | trigger_type | trigger_config | Пример |
|---------|-------------|----------------|--------|
| Событие | `event` | `{"event": "user.traffic_exceeded"}` | Трафик превышен |
| Событие | `event` | `{"event": "node.went_offline"}` | Нода ушла в offline |
| Событие | `event` | `{"event": "violation.detected", "min_score": 80}` | Нарушение с высоким скором |
| Расписание | `schedule` | `{"cron": "0 3 * * *"}` | Каждый день в 3:00 |
| Расписание | `schedule` | `{"interval_minutes": 60}` | Каждый час |
| Порог | `threshold` | `{"metric": "users_online", "op": ">", "value": 1000}` | Онлайн > 1000 |

### 6.3 Типы действий

| Действие | action_type | Описание |
|----------|-------------|----------|
| Отключить пользователя | `disable_user` | Выключить аккаунт |
| Заблокировать пользователя | `block_user` | Блокировка через Anti-Abuse |
| Уведомить | `notify` | Отправить в Telegram/webhook |
| Перезапустить ноду | `restart_node` | Рестарт Xray |
| Удалить просроченных | `cleanup_expired` | Удалить пользователей с истёкшей подпиской |
| Сбросить трафик | `reset_traffic` | Обнулить счётчик трафика |
| Запустить синхронизацию | `force_sync` | Принудительная синхронизация с API |

### 6.4 Предустановленные шаблоны

Готовые правила, которые можно включить одной кнопкой:

| Шаблон | Триггер | Действие |
|--------|---------|----------|
| Автоблокировка шаринга | Нарушение с скором > 80 | Заблокировать пользователя |
| Мониторинг нод | Нода offline > 5 мин | Уведомление в Telegram |
| Очистка просроченных | Каждый день в 3:00 | Удалить expired > 30 дней |
| Уведомление о трафике | Трафик пользователя > 90% лимита | Уведомить админа |
| Авто-рестарт | Нода offline > 15 мин | Перезапустить ноду |
| Отчёт за день | Каждый день в 23:00 | Сводка за день в Telegram |

### 6.5 Backend

| # | Задача | Описание |
|---|--------|----------|
| 6.5.1 | Миграция БД | Таблицы automation_rules, automation_log |
| 6.5.2 | Движок правил | `AutomationEngine` — обработка событий, проверка условий, выполнение действий |
| 6.5.3 | Планировщик | APScheduler или asyncio-задачи для cron/interval триггеров |
| 6.5.4 | Интеграция с событиями | Хуки в существующих сервисах: при создании нарушения → проверить правила |
| 6.5.5 | API: CRUD правил | `/api/v2/automations` — список, создание, редактирование, включение/выключение |
| 6.5.6 | API: лог и шаблоны | `/api/v2/automations/log`, `/api/v2/automations/templates` |

### 6.6 Frontend — Страница «Автоматизации»

| # | Задача | Описание |
|---|--------|----------|
| 6.6.1 | Карточки правил | Grid карточек: название, категория, триггер, статус (вкл/выкл), счётчик срабатываний |
| 6.6.2 | Конструктор правил | Пошаговая форма: 1) Триггер → 2) Условия → 3) Действие → 4) Название |
| 6.6.3 | Шаблоны | Галерея готовых правил с кнопкой «Включить» |
| 6.6.4 | Лог срабатываний | Timeline: когда, какое правило, что сделало, результат |
| 6.6.5 | Тестирование | Кнопка «Тест» — запустить правило вручную, показать что бы произошло (dry run) |

---

## Фаза 7 — Визард первого запуска и компоненты системы

**Зачем:** Сейчас вся настройка через `.env` — для новых пользователей это неудобно. Визард проведёт по шагам при первом запуске, а страница «Компоненты» покажет статус всех частей системы.

### 7.1 Визард первого запуска (Setup Wizard)

При первом входе в веб-панель (если нет настроенных админов) — показывать пошаговый визард:

| Шаг | Что делает |
|-----|-----------|
| 1. Приветствие | Описание системы, что будет настроено |
| 2. Подключение к API | Ввод API_BASE_URL и API_TOKEN, кнопка «Проверить соединение» |
| 3. Настройка бота | BOT_TOKEN, проверка что бот отвечает |
| 4. Создание админа | Имя, пароль, привязка Telegram (опционально) |
| 5. Webhook (опционально) | Включить/выключить, настроить WEBHOOK_SECRET, тест |
| 6. Anti-Abuse (опционально) | Включить/выключить, базовые пороги |
| 7. Готово | Сводка настроек, кнопка «Перейти в панель» |

Настройки из визарда сохраняются в БД (динамические настройки), т.е. `.env` не нужно редактировать вручную для базовой настройки.

### 7.2 Страница «Компоненты системы»

Карточки всех компонентов с статусом и быстрыми действиями:

| Компонент | Статус | Метрики | Действия |
|-----------|--------|---------|----------|
| Telegram Bot | Online/Offline | Uptime, команд обработано | Перезапуск, логи |
| Web Backend | Online/Offline | Uptime, запросов/мин, активные сессии | Логи |
| PostgreSQL | Connected/Error | Размер БД, кол-во записей, pool usage | Бэкап, очистка |
| Remnawave API | Connected/Error | Время отклика, последняя синхронизация | Тест, синхронизация |
| Webhook Server | Active/Inactive | Принято событий, последнее событие | Тест, настройка |
| Anti-Abuse | Enabled/Disabled | Нарушений за сутки, средний скор | Настройка порогов |
| Node Agent(s) | N online / M total | Подключений за час по каждому | Токены, настройка |

### 7.3 Задачи

| # | Задача | Описание |
|---|--------|----------|
| 7.3.1 | Backend: health endpoints | Расширенный `/system/components` — статус каждого компонента |
| 7.3.2 | Backend: setup wizard API | `/api/v2/setup/status`, `/api/v2/setup/step/{n}` — проверка и сохранение |
| 7.3.3 | Frontend: Setup Wizard | Многошаговая форма с валидацией на каждом шаге |
| 7.3.4 | Frontend: Components page | Карточки компонентов с real-time статусом |
| 7.3.5 | Определение первого запуска | Проверка: есть ли админы в БД? Настроен ли API? → показать wizard |

---

## Приоритетность фаз

```
Фаза 1 (shadcn/ui)          ██████████  Фундамент — делается первой        ✅
Фаза 2 (RBAC)               █████████   Ключевая фича — сразу после UI      ✅
Фаза 3 (Dashboard)          ████████    Улучшение главной страницы           ✅
Фаза 4 (Improvements)       ███████     Параллельно с Фазой 3
Фаза 5 (New features)       ██████      После стабилизации основы
Фаза 6 (Automations)        ██████      Конструктор правил
Фаза 7 (Setup + Components) █████       Удобство первого запуска
```

### Порядок реализации

1. **Фаза 1** — сначала, потому что все дальнейшие страницы будут строиться на shadcn/ui
2. **Фаза 2** — RBAC нужен рано, т.к. влияет на все остальные фичи (permission-aware UI)
3. **Фаза 3 + 4** — параллельно, улучшают разные части панели
4. **Фаза 5** — после стабилизации основы
5. **Фаза 6** — автоматизации требуют стабильного RBAC и аудит-лога
6. **Фаза 7** — визард и компоненты полезнее, когда основные фичи уже работают

---

## Технические решения

### shadcn/ui + Vite

shadcn/ui официально поддерживает Vite. Настройка:
```bash
npx shadcn-ui@latest init
# Framework: Vite
# Style: Default
# Base color: Slate (для тёмной темы)
# CSS variables: Yes
```

Замена иконок: `react-icons/hi` → `lucide-react` (shadcn использует Lucide).

### RBAC: проверка прав

```python
# Backend: декоратор
@router.post("/users")
async def create_user(
    data: CreateUserRequest,
    admin: AdminUser = Depends(get_current_admin),
    _: None = Depends(require_permission("users", "create")),
    __: None = Depends(check_quota("max_users")),
):
    ...
```

```tsx
// Frontend: компонент
<PermissionGate resource="users" action="create">
  <Button onClick={openCreateDialog}>Создать пользователя</Button>
</PermissionGate>
```

### Временные ряды для графиков

Новая таблица для хранения метрик (или агрегация из существующих данных):
```sql
CREATE TABLE metrics_snapshots (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100),     -- "traffic_bytes", "users_online", "connections"
    metric_value DOUBLE PRECISION,
    node_uuid UUID,               -- NULL для глобальных метрик
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_metrics_name_time ON metrics_snapshots(metric_name, recorded_at);
```

---

## Что НЕ планируется (и почему)

| Идея | Причина отказа |
|------|---------------|
| Полноценная система плагинов | Сторонний код, маркетплейс, sandbox — overkill. Вместо этого Фаза 6 (встроенные автоматизации) |
| Мультиязычность веб-панели | Русский достаточен, бот уже поддерживает en/ru |
| Мониторинг CPU/RAM серверов | Требует системного агента на каждом сервере, лучше использовать Prometheus/Grafana |

---

*Последнее обновление: Февраль 2026*

# Web Panel — Roadmap v2

План развития веб-панели Remnawave Admin.

---

## Текущее состояние

Веб-панель представляет собой полнофункциональную систему управления VPN-инфраструктурой. Ниже — сводка всего, что реализовано на данный момент.

**Стек:** React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui (Radix UI), React Query, Zustand, Recharts, Leaflet, Axios, Sonner, cmdk, react-i18next

### Инфраструктура UI

- Дизайн-система на shadcn/ui: 22+ UI-примитивов + 45+ компонентов (Button, Card, Dialog, Table, Select, Badge, Tabs, Tooltip, DropdownMenu, Sheet, Switch, Checkbox, Popover, ScrollArea, Skeleton, Separator, Breadcrumb, Command и др.)
- Тёмная тема с CSS-переменными (teal/cyan акценты), единая цветовая схема
- Иконки: lucide-react
- Адаптивный дизайн: desktop-таблицы + мобильные карточки на всех страницах
- Skeleton-загрузки, toast-уведомления (sonner), ConfirmDialog
- Command Palette (Cmd/Ctrl+K): навигация, быстрые действия, live-поиск пользователей
- Breadcrumbs с динамическим разрешением имён
- Сохранённые фильтры (Zustand + localStorage)
- Мультиязычность (react-i18next): RU/EN, переключатель в Header, localStorage + navigator detection
- Code splitting: React.lazy + Suspense для каждой страницы, manual chunks для vendor-библиотек
- Виртуализация таблиц: @tanstack/react-virtual для Users

### Страницы и функции

| Страница | Функциональность |
|----------|-----------------|
| **Dashboard** | Карточки статистики с дельта-индикаторами, графики трафика (stacked area chart по нодам, переключатель 24ч/7д/30д), парк серверов (компактные карточки с быстрыми действиями), системный статус (API, PostgreSQL, ноды, WebSocket), проверка обновлений (GitHub Releases API) |
| **Users** | CRUD с пагинацией/фильтрацией/сортировкой, массовые операции (чекбоксы, enable/disable/delete/reset-traffic, до 100 за раз), экспорт CSV/JSON, виртуализация таблиц |
| **User Detail** | Трафик, стратегия сброса трафика (NO_RESET/DAY/WEEK/MONTH), HWID устройства (полный CRUD: список, удаление, лимит, платформа, модель, версия), подписка (URL, copy-to-clipboard, QR-код), нарушения, история действий админов (timeline) |
| **Nodes** | CRUD, статус, перезапуск Xray, агент-токены (генерация/отзыв/статус), enable/disable |
| **Fleet** | Полноценный центр управления: мониторинг (CPU, RAM, диск, скорость, uptime, Xray-версия), веб-терминал (xterm.js через PTY), каталог скриптов (~20 встроенных + CRUD + импорт из GitHub + скрипт обновления агента), история команд, провижининг нод. Node Agent v2 (WebSocket + HMAC подпись команд) |
| **Hosts** | CRUD, inbound конфигурация, security layer (TLS, Reality, XTLS), SNI/host/path, порты, позиционирование |
| **Violations** | Просмотр нарушений с IP Lookup и скор-разбивкой (temporal, geo, ASN, profile, device), фильтры по IP/стране/дате, resolve-действия (ignore/warn/block), аннулирование (обнуление скора), **whitelist** (CRUD, таб, кнопки в карточках, expiration), экспорт CSV/JSON |
| **Billing** | История платежей за инфраструктуру, управление провайдерами (CRUD), привязка нод к провайдерам, overdue-индикаторы |
| **Resources** | CRUD шаблонов VPN-конфигов (templates), сниппетов, конфигурационных профилей. API-токены Remnawave (управление через Settings) |
| **Reports** | Генерация отчётов (daily/weekly/monthly), сводка по нарушениям, трафику, пользователям |
| **Automations** | Конструктор правил (4-шаговый визард), 3 типа триггеров (событие/расписание/порог), 7 типов действий, 6 готовых шаблонов, лог срабатываний, dry-run тестирование, CRON-билдер |
| **Analytics** | Географическая карта подключений (Leaflet, lazy-load), топ пользователей по трафику, анализ тенденций (area chart) |
| **Admins** | CRUD админов, конструктор ролей (матрица прав 9 ресурсов × 5 действий), прогресс-бары лимитов, журнал аудита |
| **Audit Log** | Автоматическое логирование всех мутаций (middleware), фильтры по админу/ресурсу/периоду, экспорт, real-time через WebSocket |
| **System Logs** | Real-time стриминг логов через WebSocket, 4 источника (web/bot × INFO/WARNING), фильтр по уровню и тексту, live/paused режим |
| **Notifications** | Центр уведомлений: 4 вкладки (уведомления, правила алертов, логи алертов, каналы). Bell-иконка в Header с бейджем непрочитанных и dropdown. CRUD правил алертов с кастомными шаблонами. 4 канала доставки (in-app, Telegram, Webhook, Email). Per-admin настройка каналов |
| **Mail Server** | Управление почтовым сервером: домены (DKIM, SPF, DMARC, PTR верификация), очередь отправки (retry/cancel), входящие письма, отправка тестовых, SMTP-креденшлы для внешних клиентов |
| **Settings** | Динамические настройки (3-tier: DB > .env > defaults), категории, маскировка секретов, IP whitelist, статус синхронизации |
| **Login** | Telegram Login Widget + логин/пароль, JWT (access + refresh), определение первого запуска (форма регистрации первого админа) |

### Системные возможности

- **RBAC**: 4 системные роли (superadmin, manager, operator, viewer), PermissionGate на всех страницах, квоты для админов
- **WebSocket**: real-time обновления (ноды, пользователи, нарушения, аудит, уведомления), автоматическая инвалидация React Query кеша, toast-уведомления о действиях других админов, exponential backoff reconnection
- **Движок автоматизаций**: обработка событий, CRON/interval планировщик (60с цикл), мониторинг порогов (5-мин цикл), lock на повторное срабатывание (30с), интеграция с WebSocket
- **Система уведомлений**: 4 канала (in-app, Telegram, Webhook, Email), правила алертов с кастомными шаблонами, дедупликация (5-мин окно), per-admin настройка каналов, severity levels
- **Почтовый сервер**: встроенный SMTP inbound/outbound, DKIM-подпись, DNS-верификация доменов (MX, SPF, DKIM, DMARC, PTR), очередь отправки, SMTP-креденшлы
- **Fleet Management**: Node Agent v2 через WebSocket (HMAC-подпись команд), веб-терминал (PTY + xterm.js), каталог скриптов (~20 встроенных), провижининг нод, история выполнений
- **Аудит**: AuditMiddleware перехватывает все POST/PUT/PATCH/DELETE, broadcast через WebSocket
- **Проверка обновлений**: GitHub Releases API с 30-мин кешем, семантическое сравнение версий
- **i18n**: react-i18next, 2 локали (RU/EN), useFormatters() хук для Intl API, переключатель языка в Header
- **Кэширование фронтенда**: Hashed chunks с immutable cache (1y), index.html с no-cache/no-store, nginx Cache-Control headers
- **Redis-кеширование**: CacheService с fallback на in-memory. `@cached` декоратор для analytics (30-300с TTL). Настройка через `REDIS_URL`
- **Rate limiting**: Гранулярные лимиты по эндпоинтам (auth 5-10/мин, analytics 30/мин, bulk 10/мин, глобальный 200/мин). Redis-бэкенд для distributed rate limiting
- **Cursor-based пагинация**: audit_log, automation_log — эффективная пагинация для больших таблиц
- **Модульная архитектура (shared/)**: Общие сервисы (database, api_client, config_service, sync, geoip, cache, logger, agent_tokens, maxmind_updater, asn_parser, data_access) вынесены в `shared/` модуль. Бот (`src/`) и веб-бэкенд (`web/backend/`) импортируют из `shared/` напрямую. Независимые Dockerfiles для каждого компонента

### База данных (32 миграции Alembic)

Основные таблицы: `users`, `nodes`, `hosts`, `violations`, `violation_whitelist`, `ip_metadata`, `hwid_devices`, `bot_config`, `admin_roles`, `admin_permissions`, `admin_accounts`, `admin_audit_log`, `automation_rules`, `automation_log`, `node_agent_tokens`, `notifications`, `notification_channels`, `smtp_config`, `alert_rules`, `alert_rule_log`, `domain_config`, `email_queue`, `email_inbox`, `smtp_credentials`, `node_command_log`, `node_scripts`, `node_provision_sessions`

### Backend API (29 модулей маршрутов)

`auth`, `users`, `nodes`, `hosts`, `violations`, `analytics`, `advanced_analytics`, `automations`, `settings`, `admins`, `roles`, `audit`, `logs`, `notifications`, `mailserver`, `fleet`, `scripts`, `terminal`, `agent_ws`, `websocket`, `collector`, `billing`, `reports`, `templates`, `snippets`, `config_profiles`, `tokens`, `resources`, `deps`

---

## Выполненные фазы (архив)

| Фаза | Название | Описание |
|------|----------|----------|
| 1 | Миграция на shadcn/ui | Все страницы + Layout мигрированы. Единая дизайн-система, CSS-переменные, lucide-react |
| 2 | RBAC | 4 роли, матрица прав, CRUD админов и ролей, квоты, Permission-aware UI, совместимость с legacy auth |
| 3 | Улучшение Dashboard | Графики трафика, дельта-индикаторы, карточки нод с быстрыми действиями, системный статус |
| 4 | Улучшение функций | Массовые операции, экспорт CSV/JSON, Command Palette, сохранённые фильтры, toast/ConfirmDialog/breadcrumbs |
| 5 | Новые функции | Аудит-лог с middleware, системные логи, проверка обновлений, расширенная аналитика (гео + тренды), реалтайм-уведомления |
| 6 | Автоматизации | Конструктор правил, 3 типа триггеров, 7 действий, 6 шаблонов, движок с CRON/threshold/event, dry-run |
| 10 | Уведомления и алерты | Центр уведомлений (bell + dropdown + страница), 4 канала (in-app, Telegram, Webhook, Email), правила алертов с шаблонами, дедупликация, per-admin каналы |
| 10+ | Почтовый сервер | Встроенный SMTP (inbound/outbound), домены с DKIM/SPF/DMARC/PTR, очередь отправки, SMTP-креденшлы для внешних клиентов |
| 7 | Fleet Management | Node Agent v2 (WebSocket + HMAC), веб-терминал (xterm.js + PTY), каталог скриптов (~20 встроенных), провижининг нод, история команд |
| 11 | Тестирование | Frontend: Vitest (204 теста, 17 файлов), Backend: pytest (459 тестов, 29 файлов), E2E: Playwright (3 сценария), CI: GitHub Actions |
| 12 | Мультиязычность (frontend) | react-i18next, RU/EN локали, переключатель языка, useFormatters() хук |
| 13 (frontend) | Оптимизация frontend | Code splitting (16 чанков), виртуализация таблиц, React.memo, lazy Leaflet, Service Worker/PWA |
| 13 (backend) | Оптимизация backend | Redis-кеширование (CacheService + @cached), cursor-based пагинация (audit/automation logs), 7 составных индексов, WebSocket permessage-deflate, гранулярный rate limiting |
| Arch | Рефакторинг shared/ | Выделение shared/ модуля (9 сервисов), миграция импортов бота и веб-бэкенда, обновление Dockerfiles, независимый деплой компонентов |

---

## Фаза 7 — Управление нодами (Fleet Management Center) ✅

**Статус: полностью реализовано** (миграция 0025). Node Agent v2 с WebSocket-соединением, HMAC-подпись команд, веб-терминал, каталог скриптов, провижининг нод.

### 7.1 Архитектура: расширение Node Agent v2 ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 7.1.1 | Модель данных | ✅ | Alembic 0025: таблицы `node_command_log`, `node_scripts`, `node_provision_sessions` |
| 7.1.2 | RBAC permissions | ✅ | `fleet.terminal` (superadmin), `fleet.scripts` (superadmin+manager), `fleet.provision` (superadmin) |
| 7.1.3 | Протокол команд | ✅ | JSON через WebSocket: exec_script, shell_session, pty_input/output, ping/pong |
| 7.1.4 | HMAC-подпись | ✅ | Backend подписывает команды SHA-256 от agent token, агент проверяет перед выполнением |
| 7.1.5 | Agent: WebSocket-клиент | ✅ | `ws_client.py` — постоянное соединение к `wss://admin/api/v1/agent/ws` с переподключением |
| 7.1.6 | Agent: Command Runner | ✅ | `command_runner.py` — маршрутизатор: скрипты, PTY, service_status. Whitelist + FORBIDDEN_PATTERNS |
| 7.1.7 | Agent: обновление config/main | ✅ | Новые настройки + `asyncio.gather` для WS параллельно с метриками |
| 7.1.8 | Backend: WS-эндпоинт для агентов | ✅ | `agent_ws.py` + Agent Connection Manager (реестр подключённых нод) |
| 7.1.9 | Backend: API статуса агентов | ✅ | `fleet.py` — список нод с agent v2 connected/disconnected |

### 7.2 Веб-терминал (SSH из браузера) ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 7.2.1 | Agent: PTY-провайдер | ✅ | `pty_provider.py` — `os.openpty()` + `/bin/bash`, стриминг через WS |
| 7.2.2 | Backend: WS-прокси для PTY | ✅ | `terminal.py` — мост xterm.js ↔ agent PTY |
| 7.2.3 | Backend: управление сессиями | ✅ | `terminal_sessions.py` — создание/закрытие, таймаут 30 мин, лимит на ноду/админа |
| 7.2.4 | Backend: запись сессий | ✅ | Запись в `node_command_log` |
| 7.2.5 | Frontend: WebTerminal | ✅ | `WebTerminal.tsx` — xterm.js + addon-fit, тёмная тема Remnawave |
| 7.2.6 | Frontend: UI терминала | ✅ | `TerminalDialog.tsx` — кнопка «Терминал» в карточке ноды, полноэкранный режим |

### 7.3 Каталог скриптов ✅

~20 встроенных скриптов + возможность создавать свои. Каждый скрипт — параметризованный bash с валидацией, таймаутом и live-стримингом вывода.

**Безопасность и защита:**

| Slug | Название | Описание |
|------|----------|----------|
| `fail2ban-install` | Установка fail2ban | Защита SSH и сервисов от brute-force. Параметры: maxretry, bantime |
| `ufw-setup` | Настройка UFW | Файрвол: SSH-порт + VPN-порты + custom. Параметры: порты, default policy |
| `ssh-hardening` | Усиление SSH | Отключение root, key-only auth, кастомный порт. Параметры: disable_root, port |
| `crowdsec-install` | CrowdSec | Community-driven threat intelligence + iptables bouncer |
| `ddos-protection` | DDoS-защита | iptables: SYN flood protection, rate limiting, drop invalid. Параметры: rate_limit |
| `auto-updates` | Авто-обновления | unattended-upgrades для security-патчей. Параметры: reboot_time, auto_reboot |

**Сеть и VPN:**

| Slug | Название | Описание |
|------|----------|----------|
| `bbr-enable` | TCP BBR | Включение BBR congestion control — критично для VPN-производительности |
| `xray-update` | Обновление Xray | Обновление до указанной или последней версии. Параметры: version |
| `wireguard-setup` | WireGuard | Установка, генерация ключей, настройка интерфейса. Параметры: port, server_ip |
| `dns-change` | Смена DNS | systemd-resolved или /etc/resolv.conf. Параметры: primary, secondary |
| `mtu-optimize` | Оптимизация MTU | Автоопределение оптимального MTU через PMTUD |

**Система:**

| Slug | Название | Описание |
|------|----------|----------|
| `docker-install` | Docker | Docker CE + Compose из официального репозитория |
| `swap-setup` | Swap | Создание swap-файла, настройка swappiness. Параметры: size_gb, swappiness |
| `disk-cleanup` | Очистка диска | apt cache, Docker prune, systemd journal, tmp |
| `kernel-tuning` | Тюнинг ядра | sysctl: net.core.*, net.ipv4.*, conntrack, somaxconn для VPN |
| `ntp-setup` | NTP/Timezone | systemd-timesyncd или chrony. Параметры: timezone |
| `certbot-install` | Let's Encrypt | Certbot + сертификат + auto-renewal. Параметры: domain, email |

**Мониторинг и автоматизация:**

| Slug | Название | Описание |
|------|----------|----------|
| `vnstat-install` | vnstat | Учёт трафика по интерфейсам |
| `network-diag` | Диагностика сети | mtr + speedtest-cli + ping → отчёт. Параметры: target |
| `logrotate-setup` | Ротация логов | Xray, nginx, системные логи. Параметры: max_size, keep_days |
| `backup-setup` | Настройка бэкапов | Конфиги Xray + БД, cron автозапуск. Параметры: path, cron |
| `system-update` | Обновление системы | apt update && apt upgrade. Параметры: reboot |

#### 7.3 Задачи

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 7.3.1 | Backend: seed скриптов | ✅ | Миграция 0025: ~20 встроенных скриптов с параметрами, категориями |
| 7.3.2 | Backend: CRUD API | ✅ | `scripts.py` — CRUD с RBAC |
| 7.3.3 | Backend: запуск скрипта | ✅ | Запуск с параметрами через agent WebSocket |
| 7.3.4 | Backend: стриминг вывода | ✅ | Live-вывод через WebSocket |
| 7.3.5 | Agent: script_executor | ✅ | `command_runner.py` — bash, стриминг stdout/stderr, таймаут |
| 7.3.6 | Frontend: каталог | ✅ | `ScriptCatalog.tsx` — карточки с категориями |
| 7.3.7 | Frontend: диалог запуска | ✅ | `RunScriptDialog.tsx` — параметры, подтверждение, live-вывод |
| 7.3.8 | Frontend: редактор скриптов | ✅ | ScriptFormDialog (CRUD), ImportScriptDialog (импорт из GitHub), скрипт обновления агента (миграция 0030) |
| 7.3.9 | Frontend: история выполнений | ✅ | `CommandHistory.tsx` — список запусков с фильтрами |

### 7.4 Провижининг нод ✅

One-click настройка свежего VPS как VPN-ноды.

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 7.4.1 | Backend: API провижининга | ✅ | `fleet.py` — API провижининга, статус, шаги, лог |
| 7.4.2 | Backend: движок | ✅ | Пошаговое выполнение, стриминг статуса. Таблица `node_provision_sessions` |
| 7.4.3 | Agent: install-скрипт | ✅ | Установка и настройка Node Agent |
| 7.4.4 | Frontend: визард | ✅ | Fleet.tsx (746 строк) — UI провижининга с прогрессом |

### 7.5 Интеграция в Fleet UI ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 7.5.1 | Вкладки Fleet | ✅ | Мониторинг / Терминал / Скрипты / История / Провижининг |
| 7.5.2 | NodeDetailPanel | ✅ | `NodeCard.tsx` — кнопки «Терминал», «Скрипты», быстрые действия |
| 7.5.3 | Статус Agent v2 | ✅ | Индикатор WebSocket-соединения в карточке ноды (`agent_v2_connected`) |
| 7.5.4 | Массовое выполнение | ✅ | Запуск скрипта на нескольких нодах |

---

## Фаза 8 — Миграция функционала бота в панель ✅

**Зачем:** Telegram-бот содержит функционал, которого нет в веб-панели: шаблоны VPN-конфигов, сниппеты, API-токены, биллинг инфраструктуры, провайдеры, отчёты, ASN-синхронизация. Цель — перенести всё в панель и свести бот к роли уведомлений и быстрого доступа.

**Статус: практически полностью реализовано (~90%).** Все основные функции перенесены. Осталось: UI настроек бота (bot_config) + расписание отчётов через автоматизации.

**Сводка миграции:**

| Функционал | Бот | Вебка | Статус |
|-----------|-----|-------|--------|
| Шаблоны VPN-конфигов (templates) | CRUD | CRUD (Resources.tsx + templates.py) | ✅ Готово |
| Сниппеты конфигов (snippets) | CRUD | CRUD (Resources.tsx + snippets.py) | ✅ Готово |
| API-токены Remnawave | CRUD | CRUD (Settings + tokens.py) | ✅ Готово |
| Config profiles | CRUD | CRUD (Resources.tsx + config_profiles.py) | ✅ Готово |
| Биллинг инфраструктуры | Просмотр | Полная страница (Billing.tsx + billing.py) | ✅ Готово |
| Провайдеры (AWS, DO и т.д.) | CRUD | CRUD (в Billing + billing.py) | ✅ Готово |
| Подписки (URL, revoke) | Управление | URL + copy + QR-код (qrcode.react) | ✅ Готово |
| Отчёты (daily/weekly/monthly) | Scheduled | Страница Reports (Reports.tsx + reports.py) | ✅ Готово |
| HWID устройства (CRUD) | Полный | Полный | ✅ Готово |
| Настройки бота (bot_config) | Управление | -- | ⏳ Нет UI |
| Синхронизация ASN | Запуск | Кнопка в Settings (SYNCABLE_ENTITIES) | ✅ Готово |
| Traffic reset strategy | На пользователе | ✅ | ✅ Готово |

### 8.1 Ресурсы и конфигурация ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 8.1.1 | Страница «Шаблоны» | ✅ | CRUD VPN-конфигов — Resources.tsx + templates.py |
| 8.1.2 | Страница «Сниппеты» | ✅ | CRUD сниппетов — Resources.tsx + snippets.py |
| 8.1.3 | Управление «API-токенами» | ✅ | Генерация, список, отзыв — Settings + tokens.py |
| 8.1.4 | Страница «Config Profiles» | ✅ | CRUD конфигурационных профилей — Resources.tsx + config_profiles.py |

### 8.2 Биллинг и провайдеры ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 8.2.1 | Страница «Биллинг» | ✅ | Billing.tsx — история платежей, суммы, сроки, overdue |
| 8.2.2 | Управление провайдерами | ✅ | CRUD в Billing: название, favicon, URL, привязанные ноды |
| 8.2.3 | Биллинг нод | ✅ | Стоимость нод, дата следующего платежа, overdue-индикаторы |
| 8.2.4 | Dashboard: виджет биллинга | ⏳ | Ближайшие платежи, суммарные расходы за месяц — не реализован |

### 8.3 Подписки и HWID ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 8.3.1 | Управление подписками | ✅ | URL + copy-to-clipboard + QR-код (qrcode.react в UserDetail.tsx) |
| 8.3.2 | HWID устройства | ✅ | Полный CRUD: список устройств (платформа, модель, OS, app version, user agent), удаление, лимит, пагинация, синхронизация |
| 8.3.3 | Traffic reset strategy | ✅ | В форме пользователя: NO_RESET / DAY / WEEK / MONTH + last_traffic_reset_at |

### 8.4 Отчёты и аналитика ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 8.4.1 | Генератор отчётов | ✅ | Reports.tsx + reports.py — за день/неделю/месяц |
| 8.4.2 | Расписание отчётов | ⏳ | Интеграция с автоматизациями: cron-триггер → отчёт → Telegram/email |
| 8.4.3 | ASN синхронизация | ✅ | Кнопка в Settings (SYNCABLE_ENTITIES) |

### 8.5 Настройки бота

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 8.5.1 | Bot Config в Settings | ⏳ | Секция настроек бота: язык, topic ID'ы, интервалы (таблица bot_config существует, нет UI) |
| 8.5.2 | Управление уведомлениями | ✅ | Реализовано через Notifications: правила алертов, каналы доставки (Telegram topics, webhook, email) |

---

## Фаза 9 — Telegram Mini App

**Зачем:** После миграции основного функционала из бота в панель (Фаза 8), нужен лёгкий способ взаимодействия с панелью прямо из Telegram. Mini App — не замена полной панели, а быстрый доступ к ключевым функциям с телефона.

### 9.1 Инфраструктура

| # | Задача | Описание |
|---|--------|----------|
| 9.1.1 | Регистрация Mini App | Создать Web App через BotFather, настроить URL |
| 9.1.2 | Авторизация через initData | Валидация Telegram initData (HMAC), маппинг на admin_accounts |
| 9.1.3 | Отдельный build target | Vite config: отдельная entry point для Mini App (лёгкий бандл без тяжёлых зависимостей) |

### 9.2 Функционал

| # | Задача | Описание |
|---|--------|----------|
| 9.2.1 | Dashboard (компактный) | Ключевые метрики: онлайн, ноды, нарушения, трафик. Числа и дельты без графиков |
| 9.2.2 | Быстрый поиск пользователя | Поиск → карточка → enable/disable/reset traffic |
| 9.2.3 | Статус нод | Список: статус, users online. Tap → restart/enable/disable |
| 9.2.4 | Последние нарушения | Лента нарушений с быстрыми действиями (resolve) |
| 9.2.5 | Push-уведомления | При событиях (нода offline, нарушение) — Mini App уведомление |

### 9.3 UI/UX

| # | Задача | Описание |
|---|--------|----------|
| 9.3.1 | Telegram UI Kit | @telegram-apps/sdk, нативные цвета Telegram (theme_params) |
| 9.3.2 | Haptic feedback | Вибрация при действиях (Telegram WebApp API) |
| 9.3.3 | Bottom navigation | Tab bar: Dashboard / Users / Nodes / Alerts |
| 9.3.4 | Offline cache | Service Worker + IndexedDB для базовых данных |

---

## Фаза 10 — Уведомления и алерты ✅

**Зачем:** Сейчас уведомления — это toast'ы в панели и Telegram через автоматизации. Нужна полноценная подсистема уведомлений: центр уведомлений в UI, гибкая настройка каналов, эскалация.

**Статус: полностью реализовано** (миграции 0017-0022). Дополнительно реализован встроенный почтовый сервер, который не планировался в исходном роадмапе.

### 10.1 Центр уведомлений (in-app) ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 10.1.1 | Модель данных | ✅ | Таблицы `notifications`, `notification_channels`, `alert_rules`, `alert_rule_log`, `smtp_config` |
| 10.1.2 | Backend: API | ✅ | CRUD, mark read/unread, mark all read, delete old (30+ дней) |
| 10.1.3 | Frontend: иконка в Header | ✅ | Bell с бейджем непрочитанных (99+), dropdown с 8 последними уведомлениями, severity-цвета, mark all read |
| 10.1.4 | Frontend: страница уведомлений | ✅ | 4 вкладки: уведомления, правила алертов, логи алертов, каналы. Фильтры по read/severity |
| 10.1.5 | WebSocket интеграция | ✅ | Топик `notification` → push через WS → обновление бейджа + toast. Auto-fetch каждые 30с |

### 10.2 Каналы доставки ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 10.2.1 | Telegram | ✅ | Telegram Bot API с поддержкой topic/thread для разных типов алертов (nodes, service, users, errors, violations). Fallback на NOTIFICATIONS_CHAT_ID |
| 10.2.2 | Webhook | ✅ | POST на указанный URL с JSON payload. Совместимые форматы для Discord и Slack |
| 10.2.3 | Email | ✅ | **Встроенный почтовый сервер** (inbound/outbound SMTP, DKIM, DNS-верификация) + fallback на внешний SMTP relay. HTML-шаблоны |
| 10.2.4 | Настройка каналов на уровне админа | ✅ | Каждый админ выбирает каналы (in_app, telegram, webhook, email). Per-alert-rule настройка каналов |

### 10.3 Правила алертов ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 10.3.1 | Пороговые алерты | ✅ | Конфигурируемые правила с severity, кастомными шаблонами (title_template, body_template) |
| 10.3.2 | Группировка и дедупликация | ✅ | 5-минутное окно дедупликации по group_key |
| 10.3.3 | Эскалация | ⏳ | Если алерт не подтверждён за N минут → уведомить вышестоящего админа (не реализовано) |

### 10.4 Почтовый сервер (бонус, не планировался) ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 10.4.1 | Страница Mail Server | ✅ | 5 вкладок: домены, очередь, входящие, отправка, креденшлы |
| 10.4.2 | Управление доменами | ✅ | CRUD доменов, DNS-верификация (MX, SPF, DKIM, DMARC, PTR), per-domain sender name |
| 10.4.3 | SMTP inbound/outbound | ✅ | Приём и отправка писем, DKIM-подпись, очередь с retry/cancel |
| 10.4.4 | SMTP-креденшлы | ✅ | Аутентификация PLAIN/LOGIN на порту 587, rate limiting, ограничение доменов |
| 10.4.5 | Входящие письма | ✅ | Просмотр с HTML-рендерингом, mark read, удаление |

---

## Фаза 11 — Тестирование и стабильность ✅

**Зачем:** Проект вырос до 16+ страниц, 23+ API-модулей, 25+ миграций. Тесты — необходимость для стабильности.

**Итого: 1005+ тестов** (801 backend + 204 frontend), 55 тест-файлов (38 BE + 17 FE), 0 failures.

### 11.1 Frontend-тесты ✅ (204 теста, 17 файлов)

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 11.1.1 | Настройка Vitest | ✅ | vitest.config.ts, jsdom, setup файл с моками (React Query, Zustand, Axios, i18n, matchMedia, ResizeObserver) |
| 11.1.2 | Тесты утилит | ✅ | export.ts, helpers.ts (автоматизации), useFormatters (formatBytes, formatSpeed, formatDate, formatTimeAgo, formatNumber) |
| 11.1.3 | Тесты хуков и сторов | ✅ | authStore (login/logout/register/validateSession/isTokenExpired), permissionStore, filtersStore, useAppearanceStore, useWebSocket, authBridge |
| 11.1.4 | Тесты API-клиентов | ✅ | api/client (interceptors, getApiBaseUrl, Bearer token, 401 refresh mutex), api/auth (все методы authApi, getErrorMessage) |
| 11.1.5 | Компонентные тесты | ✅ | PermissionGate, ConfirmDialog, ExportDropdown, CommandPalette, ErrorBoundary (fallback UI, componentDidCatch, reload) |
| 11.1.6 | Тесты страниц (smoke) | ✅ | 16 страниц рендерятся без ошибок (Dashboard, Users, UserDetail, Nodes, Fleet, Hosts, Violations, Settings, Admins, AuditLog, SystemLogs, Analytics, Automations, Notifications, MailServer, Login) |

### 11.2 Backend-тесты ✅ (801 тест, 38 файлов)

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 11.2.1 | Настройка pytest | ✅ | conftest.py, фикстуры (FastAPI TestClient, AdminUser с 4 ролями, mock_db, mock_db_acquire, dependency overrides), pytest-cov |
| 11.2.2 | Тесты API | ✅ | Auth, Admins, Health, Users, Nodes, Violations, Hosts, Automations, Settings, Analytics — happy path + ошибки + RBAC |
| 11.2.3 | Тесты RBAC | ✅ | Матрица: 4 роли (superadmin/manager/operator/viewer) × 14 ресурсов × 5 действий — параметризованные тесты |
| 11.2.4 | Тесты автоматизаций | ✅ | CRON-парсер, условия (8 операторов), target inference, engine lifecycle (start/stop) |
| 11.2.5 | Тесты миграций | ✅ | Валидация структуры файлов, линейность цепочки revision → down_revision |
| 11.2.6 | Тесты безопасности | ✅ | JWT, Telegram auth (HMAC, expiry, signature), bcrypt, LoginGuard, TokenBlacklist, IP whitelist, agent_hmac (sign/verify, replay protection) |
| 11.2.7 | Тесты конфигурации | ✅ | WebSettings: CORS, ADMINS, JWT, defaults |
| 11.2.8 | Тесты core-модулей | ✅ | audit_middleware (_match_route, _build_details, _extract_token), rate_limit (SlowAPI + Redis), agent_manager (WebSocket tracking), cache (InMemoryCache, CacheService, @cached), notifier (Telegram), notification_service (HTML email, config), update_checker (GitHub API + cache) |

### 11.3 E2E-тесты ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 11.3.1 | Настройка Playwright | ✅ | playwright.config.ts (Chromium + Firefox), webServer, CI reporter |
| 11.3.2 | Критические сценарии | ✅ | Login flow, auth guard (10 protected routes → redirect), navigation smoke (10 страниц с API mocking) |
| 11.3.3 | CI интеграция | ✅ | GitHub Actions: frontend unit tests + backend pytest + E2E Playwright на каждый PR |

---

## Фаза 12 — Мультиязычность (i18n)

**Зачем:** Панель используется не только русскоязычными админами. i18n позволит расширить аудиторию без дублирования кода.

### 12.1 Инфраструктура ✅

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 12.1.1 | Настройка react-i18next | ✅ | i18n.ts, языковые файлы в `locales/`, определение языка из настроек админа (localStorage + navigator detection) |
| 12.1.2 | Извлечение строк | ✅ | Все hardcoded строки → `t('key')`. 16 страниц + компоненты. Namespace-разделение |
| 12.1.3 | Русский (ru) | ✅ | Базовый язык — перенос текущих строк в `src/locales/ru/translation.json` |
| 12.1.4 | Английский (en) | ✅ | Полный перевод в `src/locales/en/translation.json` |

### 12.2 Интеграция

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| 12.2.1 | Переключатель языка | ✅ | Кнопка с Globe иконкой в Header, переключение RU/EN, сохранение в localStorage |
| 12.2.2 | Форматирование | ✅ | `useFormatters()` хук: даты, числа, байты, скорость — через Intl API с учётом локали |
| 12.2.3 | Backend: i18n ошибок | ⏳ | Сейчас бэкенд возвращает текстовые сообщения в `detail` поле HTTPException. Нужно: коды ошибок + перевод на фронте |
| 12.2.4 | Автоматизации: шаблоны уведомлений | ⏳ | Шаблоны автоматизаций используют простую подстановку плейсхолдеров ({rule_name}, {metric} и т.д.) без i18n. Нужно: поддержка языка в шаблонах |

---

## Фаза 13 — Оптимизация производительности

**Зачем:** С ростом числа пользователей и нод таблицы становятся тяжёлыми, дашборд загружает много данных параллельно, бандл фронтенда растёт.

### 13.1 Frontend ✅

| # | Задача | Описание | Статус |
|---|--------|----------|--------|
| 13.1.1 | Code splitting | React.lazy + Suspense для каждой страницы (16 чанков). Manual chunks: vendor-react, vendor-data, vendor-i18n, vendor-radix, vendor-charts, vendor-maps, vendor-icons | ✅ |
| 13.1.2 | Виртуализация таблиц | @tanstack/react-virtual для Users (30+ строк): sticky header, виртуальные spacers | ✅ |
| 13.1.3 | Оптимизация re-renders | React.memo для StatusBadge, TrafficBar, OnlineIndicator, MobileUserCard, ViolationCard, ScoreBar, StatCard и др. useMemo/useCallback для хэндлеров | ✅ |
| 13.1.4 | Оптимизация Leaflet | Lazy-load через React.lazy (LazyGeoMap) — карта + leaflet CSS загружаются только на вкладке Geography | ✅ |
| 13.1.5 | Кэширование | Hashed chunks с immutable cache (1y), index.html с no-cache/no-store, nginx headers. PWA/Service Worker удалён (вызывал stale content после деплоев) | ✅ |

### 13.2 Backend ✅

| # | Задача | Описание | Статус |
|---|--------|----------|--------|
| 13.2.1 | Кеширование Redis | CacheService с Redis-бэкендом (fallback на in-memory). `@cached` декоратор для analytics эндпоинтов (overview 30с, traffic/deltas 60с, geo/trends/top-users 300с). Настройка через `REDIS_URL` | ✅ |
| 13.2.2 | Пагинация cursor-based | Cursor-based пагинация для audit_log и automation_log (параметр `cursor` = последний id, `next_cursor` в ответе). Обратная совместимость с offset-пагинацией | ✅ |
| 13.2.3 | Индексы БД | Alembic миграция 0023: 7 составных индексов (audit admin+created, audit cursor, violations detected+score, ip_metadata created, users status+created, automation_log cursor, notifications admin+read+created) | ✅ |
| 13.2.4 | Сжатие WebSocket | permessage-deflate включён в uvicorn (Dockerfile + main.py). `--ws websockets --ws-per-message-deflate` | ✅ |
| 13.2.5 | Rate limiting | Гранулярные лимиты: auth 5-10/мин, analytics 30/мин, bulk 10/мин, глобальный 200/мин. Redis-бэкенд для distributed rate limiting. Пресеты: RATE_AUTH, RATE_ANALYTICS, RATE_BULK и др. | ✅ |

---

## Архитектурный рефакторинг — shared/ модуль ✅

**Зачем:** Бот и веб-панель дублировали ~9000+ строк сервисного кода. Рефакторинг устраняет дублирование и позволяет деплоить компоненты независимо.

**Статус: полностью выполнено.**

### Что сделано

| # | Задача | Статус | Описание |
|---|--------|--------|----------|
| A.1 | Создание shared/ модуля | ✅ | 11 сервисов вынесены: database, api_client, config_service, sync, geoip, cache, logger, agent_tokens, maxmind_updater, asn_parser, data_access |
| A.2 | Миграция веб-бэкенда | ✅ | Все импорты `web/backend/` переведены на `from shared.` |
| A.3 | Миграция бота | ✅ | Все handlers, services, utils переведены на `from shared.` для shared-модулей. Бот-специфичный код остался в `src/` |
| A.4 | Обновление Dockerfiles | ✅ | Bot Dockerfile копирует `shared/` + `src/`. Web backend Dockerfile копирует `shared/` + `web/backend/` (без `src/`) |
| A.5 | Re-export обёртки | ✅ | `src/services/*.py` содержат re-export из `shared/` для обратной совместимости (не используются внутри проекта) |
| A.6 | Тестирование | ✅ | 1005+ тестов (801 backend + 204 frontend) — все проходят |

### Архитектура

```
remnawave-admin/
├── shared/              ← Общие сервисы (database, api_client, logger, ...)
├── src/                 ← Telegram-бот (handlers, keyboards, бот-специфичные services)
│   ├── handlers/        ← import from shared.* + src.*
│   ├── services/        ← бот-специфичные + re-export обёртки
│   └── utils/           ← бот-утилиты (formatters, notifications, ...)
├── web/
│   ├── backend/         ← FastAPI (import from shared.* + web.backend.*)
│   └── frontend/        ← React (TypeScript, Vite)
```

---

## Фаза 14 — Бэкап, импорт и миграция

**Зачем:** Возможность экспортировать всю конфигурацию, перенести на другой сервер, восстановить после сбоя.

### 14.1 Задачи

| # | Задача | Описание |
|---|--------|----------|
| 14.1.1 | Экспорт конфигурации | JSON-файл со всеми настройками, ролями, правилами автоматизации, правилами алертов |
| 14.1.2 | Импорт конфигурации | Загрузка JSON + валидация + применение (с диалогом конфликтов) |
| 14.1.3 | Бэкап БД из панели | Кнопка → pg_dump → скачивание архива. Расписание через автоматизации |
| 14.1.4 | Восстановление из бэкапа | Загрузка архива → pg_restore с подтверждением |
| 14.1.5 | Миграция пользователей | Импорт пользователей из CSV/JSON (массовое создание с валидацией) |
| 14.1.6 | Лог миграций | История импортов/экспортов с результатами (N успешно, M ошибок) |

---

## Фаза 15 — API для внешних интеграций

**Зачем:** Позволить внешним системам (биллинг, CRM, боты продаж, мониторинг) взаимодействовать с панелью по API без доступа к внутренним эндпоинтам.

### 15.1 Задачи

| # | Задача | Описание |
|---|--------|----------|
| 15.1.1 | API-ключи | Генерация API-ключей для внешних систем с привязкой к роли/правам |
| 15.1.2 | Public API (v3) | Отдельный набор эндпоинтов: создание/управление пользователями, проверка статуса, получение подписки |
| 15.1.3 | Webhook-подписки | Подписка внешних систем на события (user.created, user.expired, node.offline). Учесть уже реализованный webhook-канал из Фазы 10 |
| 15.1.4 | Документация API | OpenAPI/Swagger UI с примерами, доступный из панели |
| 15.1.5 | Rate limiting для API-ключей | Индивидуальные лимиты на каждый ключ |
| 15.1.6 | SDK / примеры | Python и JavaScript клиенты, примеры интеграции с WHMCS, Telegram-ботами продаж |

---

## Приоритетность фаз

```
Выполнено:
  Фаза 1  (shadcn/ui)          ██████████  Дизайн-система                      ✅
  Фаза 2  (RBAC)               ██████████  Роли и права                        ✅
  Фаза 3  (Dashboard)          ██████████  Графики и мониторинг                ✅
  Фаза 4  (Improvements)       ██████████  Массовые операции, поиск, UX        ✅
  Фаза 5  (New features)       ██████████  Аудит, логи, аналитика              ✅
  Фаза 6  (Automations)        ██████████  Конструктор правил                  ✅
  Фаза 7  (Fleet Management)   ██████████  Терминал, скрипты, CRUD, импорт     ✅
  Фаза 8  (Bot Migration)      █████████░  Ресурсы, биллинг, отчёты, подписки  ✅ (~90%)
  Фаза 10 (Notifications)      ██████████  Уведомления, алерты, почта          ✅
  Фаза 11 (Testing)            ██████████  1005+ тестов (801 BE + 204 FE) + E2E ✅
  Фаза 12 (i18n)               ██████████  Мультиязычность (фронтенд)          ✅
  Фаза 13 (Performance FE)     ██████████  Оптимизация фронтенда               ✅
  Фаза 13 (Performance BE)     ██████████  Redis, cursor-based, индексы, WS     ✅
  Arch    (shared/ модуль)      ██████████  11 сервисов в shared/, независимый деплой ✅

Частично выполнено:
  Фаза 8  (Bot Config UI)      █░░░░░░░░░  Нет UI для bot_config в Settings    ⚠️
  Фаза 12 (i18n backend)       ██░░░░░░░░  Нет кодов ошибок, нет i18n шаблонов ⚠️ (~80%)

Планируется:
  Фаза 9  (Mini App)           ░░░░░░░░░░  Telegram Mini App
  Фаза 14 (Backup)             ░░░░░░░░░░  Бэкап, импорт, миграция
  Фаза 15 (External API)       ░░░░░░░░░░  API-ключи, SDK, документация
```

### Порядок реализации (оставшиеся задачи)

1. **Фаза 8 (остаток)** — UI настроек бота (bot_config в Settings), виджет биллинга на Dashboard, расписание отчётов
2. **Фаза 12.2** — i18n бэкенда: коды ошибок, i18n шаблонов автоматизаций/уведомлений
3. **Фаза 9** — Mini App: лёгкий доступ к панели из Telegram
4. **Фаза 14** — бэкап: экспорт/импорт конфигурации, pg_dump/pg_restore из панели
5. **Фаза 15** — внешний API: API-ключи, webhook-подписки, SDK, документация

Фазы 12.2, 14, 15 могут выполняться параллельно, т.к. затрагивают разные слои.

---

## Что НЕ планируется (и почему)

| Идея | Причина отказа |
|------|---------------|
| Визард первого запуска | Настройка через `.env` достаточна для целевой аудитории. Текущая форма создания первого админа покрывает базовый сценарий |
| Страница компонентов системы | Dashboard уже содержит SystemStatusCard с мониторингом всех компонентов (API, PostgreSQL, ноды, WebSocket). Выделенная страница — дублирование |
| Управление тарифными планами | Панель предназначена для администраторов, не для клиентов. Управление пользователями (лимиты, сроки, HWID) уже реализовано |
| Система плагинов | Сторонний код, sandbox, маркетплейс — overkill. Автоматизации (Фаза 6) + внешний API (Фаза 15) закрывают эту потребность |
| Глубокий мониторинг серверов | Fleet + Node Agent v2 покрывают базовые метрики. Для глубокого мониторинга лучше Prometheus + Grafana |

---

*Последнее обновление: 23 февраля 2026*

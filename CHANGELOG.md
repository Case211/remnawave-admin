# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-02-15

### Обзор

Крупное обновление: поддержка ARM64 архитектуры, система уведомлений и алертов, полная интернационализация веб-панели, интерактивная гео-карта с детализацией по пользователям, оптимизация производительности фронтенда, встроенный почтовый сервер с DKIM, SMTP relay, тестовая инфраструктура (Playwright E2E + CI), поддержка Remnawave v2.6.0 API. Исправлено более 30 багов.

---

### Новый функционал

#### Поддержка ARM64 (aarch64)
- Docker-образы теперь собираются для двух платформ: `linux/amd64` и `linux/arm64`
- Все четыре образа проекта (bot, web-backend, web-frontend, node-agent) поддерживают ARM

#### Система уведомлений и алертов (Phase 10)
- Полноценная система алертов с настраиваемыми каналами (Telegram, email, внешние webhook)
- Маршрутизация алертов по типам в отдельные топики Telegram
- Настраиваемые шаблоны сообщений с live-превью
- Выбор канала уведомлений для каждого типа алерта

#### Интернационализация веб-панели (Phase 12)
- Полная поддержка русского и английского языков в веб-панели (i18n)
- Переведены все страницы: настройки, автоматизации, аналитика, логи
- Переведены метки и описания параметров конфигурации
- GeoIP fallback-провайдер для локализации

#### Интерактивная гео-карта
- При нажатии на точку на карте отображается список пользователей с возможностью перехода в профиль
- Статус-бейджи и детальная информация по каждому пользователю
- Таблица распределения пользователей по городам с группировкой и поиском
- Сворачиваемые группы по городам с фильтром

#### Оптимизация фронтенда (Phase 13)
- Code splitting и tree shaking для уменьшения размера бандла
- Ленивая загрузка гео-карты (LazyGeoMap)
- Оффлайн-индикатор для отслеживания состояния соединения
- Исправление циклических зависимостей между чанками

#### Встроенный почтовый сервер
- Встроенный SMTP-сервер с DKIM-подписью (RSA-2048) и inbox
- Настройки почтового сервера вынесены на страницу Settings в веб-панели
- SMTP Submission сервер с AUTH для внешнего relay
- UI-вкладка для управления SMTP-учётными данными
- Проверка PTR (reverse DNS) записей при верификации DNS
- Настраиваемое имя отправителя (from_name) для каждого домена
- Документация по настройке reverse proxy (nginx, Caddy, Traefik) для почтового сервера

#### Тестовая инфраструктура (Phase 11)
- Бэкенд-тесты и E2E тесты на Playwright
- GitHub Actions CI workflows для фронтенд-тестов
- Моки API для тестов авторизации и навигации

#### Динамическое логирование
- Динамическая смена уровня логирования (DEBUG/INFO/WARNING/ERROR) без перезапуска
- Настройка ротации и максимального размера лог-файлов
- Убраны тайлы nginx, добавлены логи обработки нарушений
- При ошибке токена агента в логах отображается информация о конкретной ноде

#### Обновления интерфейса
- Кастомное имя панели в сайдбаре
- Ссылки в сайдбаре и секция донатов на странице логина
- Убран текст бренда 'Remnawave' из сайдбара, оставлен только логотип
- Переработан интерфейс авторизации с flow регистрации
- Улучшен диалог создания пользователей
- Target-селекторы в конструкторе правил автоматизации

#### Интеграции
- Поддержка Remnawave panel v2.6.0 API (новые поля в UI)
- Интеграция с [MaxMind GitHub mirror](https://github.com/ltsdev/maxmind) как альтернативный источник скачивания баз GeoLite2
- Dev branch Docker workflow и dev compose файл

---

### Улучшения
- Аналитика переработана в табличный layout с вкладками
- Консолидация аутентификации: единая таблица admin_accounts, удалена legacy admin_credentials
- Безопасность: hardening фронтенд-утилит и бэкенд SQL-запросов
- Оптимизация запроса гео-пользователей: единый JOIN с нормализацией IP-адресов

---

### Исправления

#### Критические
- Белый экран при загрузке — исправлен прямой импорт Login/Dashboard, добавлен chunk retry и validation timeout
- Краш при старте — удалены индексы tag-колонок из SCHEMA_SQL
- Сброс пароля не сохранялся — исправлен debug request logging и change_password
- Правила автоматизации не работали — исправлено выполнение действий, добавлена детекция событий

#### Почтовый сервер
- Исправлена верификация TLS-сертификатов при исходящей отправке
- SMTP-доставка: использование SMTP-класса вместо send() shortcut
- SMTP AUTH: синхронный аутентификатор для совместимости с aiosmtpd
- Использование local_hostname вместо source_hostname
- Исправлены MIME-кодированные заголовки во входящих письмах
- Исправлена ошибка asyncpg-подключения в inbound SMTP-сервере
- Исправлены проблемы доставляемости, обнаруженные mail-tester.com
- Инициализация config_service до запуска mail service

#### Гео-карта и аналитика
- Исправлено несоответствие типов INET/VARCHAR при отображении пользователей на карте
- Приведение INET к text перед TRIM в запросе гео-пользователей
- Использование host() для снятия /32 CIDR маски с INET IP-адресов
- Исправлено перекрытие тултипов на карте
- Стилизация Leaflet popup для тёмной/светлой тем

#### Уведомления и алерты
- Исправлена доставка уведомлений в Telegram и внешние каналы
- Исправлены имена колонок alert engine, FK violation для legacy-админов
- Адаптивная мобильная вёрстка страницы уведомлений
- Автоматическое разрешение legacy admin-аккаунтов для создания каналов

#### Интернационализация
- Синхронизация EN/RU файлов переводов
- Исправление cronToHuman для дней через запятую и сокращений дней в describeAction
- Добавлены пропущенные ключи переводов, DB-first паттерн для хостов

#### Прочие исправления
- Удалена зависимость react-leaflet-cluster из-за конфликта с react-leaflet 4.x
- Ошибочный await на синхронном config_service.get() для имени панели
- Исправлен URL загрузки MaxMind GitHub: использование ветки master вместо main
- Кнопка очистки логов
- Ошибка 422 при автоматизации, логирование ошибок токена
- Healthcheck бэкенда: python вместо curl
- Разрешение fleet resource permission для node-fleet endpoint
- Удалены авто-сгенерированные credentials при первом запуске, исправлено отображение squad names
- Исправлены все TypeScript strict-mode ошибки
- Циклическая зависимость между чанками vendor-i18n и vendor-data

---

## [2.0.0] - 2026-02-10

### Обзор

Масштабное обновление: полностью переработанная веб-панель администратора, система ролей и прав доступа, движок автоматизаций, расширенная аналитика, система тем оформления и множество улучшений UX. Исправлено более 25 багов и недочётов.

---

### Новый функционал

#### Система ролей и прав доступа (RBAC)
- Полноценная система ролей администраторов с гранулярными правами доступа
- Матрица разрешений по ресурсам: пользователи, ноды, хосты, флот, логи и др.
- Квоты на создание ресурсов с контролем лимитов
- Ограничение UI-элементов по ролям (скрытие кнопок для viewer)

#### Расширенный Dashboard (Phase 3)
- Интерактивные графики трафика и статистики (Recharts)
- Мониторинг флота нод в реальном времени
- Индикаторы состояния системы
- Информационные тултипы с описаниями на всех виджетах и графиках

#### Страница Fleet Monitoring
- Мониторинг флота нод с детальной панелью
- Поиск, фильтрация, адаптивная мобильная версия
- Системные метрики через Node Agent (CPU, RAM, диск)

#### Node Agent — сбор метрик
- Сбор системных метрик с серверов
- Docker-сборка и CI/CD pipeline
- Оптимизация: авто-рестарт, снижение нагрузки логирования

#### UX-улучшения (Phase 4)
- Массовые операции с пользователями и нарушениями
- Расширенный поиск нарушений с экспортом и сохранёнными фильтрами
- Command Palette с горячими клавишами
- Хлебные крошки (breadcrumbs) и диалоги подтверждения
- Toast-уведомления и компоненты shadcn/ui

#### Аудит и аналитика (Phase 5)
- Подробный журнал аудита с human-readable описаниями
- Просмотр системных логов в реальном времени
- Проверка обновлений панели
- Расширенная аналитика
- Редизайн страницы входа с улучшенной безопасностью сессий

#### Движок автоматизаций (Phase 6)
- Полноценный Automation Engine с настраиваемыми правилами
- CRON-расписания с human-readable отображением
- Валидация правил и UX-улучшения интерфейса автоматизаций

#### Система тем оформления
- 6 тёмных тем + 1 светлая тема
- Настройка плотности интерфейса, радиуса скругления, размера шрифта
- Управление анимациями и сворачивание сайдбара

#### MaxMind GeoLite2
- Поддержка MaxMind GeoLite2 как основного GeoIP-провайдера
- Автоматическая загрузка баз данных при старте

#### CLI-инструменты администратора
- Сброс пароля администратора через CLI
- Создание суперадмина из командной строки

#### Прочее
- Реструктуризация меню: сворачиваемая группа «Администрирование»
- Адаптивная матрица прав доступа с динамическим размером
- Флот как отдельный RBAC-ресурс с правами view/edit

---

### Улучшения
- Оптимизация Node Agent: авто-рестарт, снижение логирования, отключение gzip
- Перенос метрик флота нод с Dashboard на страницу Nodes
- Повышение надёжности и производительности node-agent
- Динамическое получение версии из GitHub Releases

---

### Исправления

Исправлено более 25 багов и недочётов, включая:
- Корректное отображение трафика (форматы дат, API-эндпоинты, статистика по периодам)
- Исправления HWID-устройств (пропущенные колонки, счётчики)
- Корректная работа тем: читаемость текста и графиков в светлой/тёмной теме
- Безопасность авторизации: сброс сессии при истечении токена
- Идемпотентные миграции БД, исправление старта PostgreSQL-контейнера
- Переработка системы логирования: логи бота, инфраструктурные сервисы, регистронезависимый поиск
- Исправления UI: тултипы, респонсивность, z-index, позиционирование
- Исправление CRON-расписания дней недели в автоматизациях
- Совместимость react-leaflet с React 18

---

## [1.7.0] - 2026-02-08

### Added

#### Web Admin Panel
- **Full-featured web admin panel** built with React 18 + TypeScript + Tailwind CSS
- **Telegram Login Widget authentication** with JWT (access + refresh tokens)
- **Dark theme** with teal/cyan accent colors, fully responsive design
- **Smooth animations** system: fade-in, fade-in-up, scale-in, slide, shimmer, glow-pulse
- **Stagger animations** for dynamic lists (`.stagger-1` through `.stagger-8`)
- Pages: Dashboard, Users, User Detail, Nodes, Hosts, Violations, Settings, Login

#### Dashboard
- Real-time system overview: users (active/expired/disabled), nodes (online/offline), hosts
- **Bandwidth Stats API integration** — accurate traffic data (today, week, month, total) from `/api/system/stats/bandwidth`
- Per-node realtime traffic from `/api/bandwidth-stats/nodes/realtime`
- Violation statistics with severity bar charts (Recharts) and action breakdown
- System health indicators (API, nodes, database) with live status dots
- Quick action navigation cards

#### Violations Page (Full Rewrite)
- Detailed violation viewer with tabs: Overview, Devices, Geography
- Advanced filtering: severity level, action, country, date range
- Search by username and IP address
- **IP Lookup feature** — resolve provider name, city, connection type (ISP/mobile/hosting/VPN) via GeoIP
- Pagination, sorting, severity badges with color coding
- UUID-to-string fix for violation list rendering

#### Settings System v2
- **Priority changed**: DB > .env > default values (was: .env > DB > default)
- **Auto-save**: instant for boolean/select toggles, 800ms debounce for text/number inputs
- **20+ new fine-tuning settings**:
  - Violation weights (temporal, geo, ASN, profile, device)
  - Cooldown between analyses, retention period, notification throttling
  - Quiet hours for notifications
  - Sync retry count, GeoIP cache TTL
  - Dashboard refresh interval, timezone, table rows per page
- Source badges (DB / env / Default) with visual indicators
- Reset to fallback value (X button on hover)
- Full-text search across all settings
- Subcategory grouping within categories

#### Dynamic Bot Language
- Language changed via web panel now applies **instantly without restart**
- i18n middleware reads language from `config_service` (DB) on every request
- Removed `.env` locking in Telegram bot config handler

#### Security
- **Security audit** of web panel with P0–P2 fixes documented in `web/SECURITY_AUDIT.md`
- JWT validation hardening, XSS protection, API access restrictions
- Input sanitization for settings values

### Changed
- Config priority inverted: database values now take precedence over `.env` for runtime flexibility
- Overview and traffic endpoints use Remnawave Bandwidth Stats API instead of broken DB fallback
- Node list enriched with realtime bandwidth data for per-node today traffic
- User status comparison made case-insensitive (handles `ACTIVE`, `Active`, `active`)
- Traffic extraction handles nested `userTraffic.usedTrafficBytes` from raw API data
- Project structure updated in README to reflect web panel directories

### Fixed
- Dashboard showing 0 for active/expired users (case-sensitive status comparison)
- Dashboard showing 0 for all traffic stats (nested `userTraffic` object not extracted)
- Week/month traffic showing same as total (broken fallback: `week = total, month = total`)
- Node "today" traffic always 0 (`trafficTodayBytes` field doesn't exist in Remnawave API)
- Violation list empty due to UUID-to-string conversion error
- Bot language not changing after update via web panel (static `settings.default_locale`)

---

## [1.6.0] - 2026-01-31

### Added

#### Dynamic Settings (Динамические настройки)
- **Runtime Configuration System**: Change bot settings without restart via Telegram interface
- **Configuration Categories**:
  - General: language, log level
  - Notifications: enable/disable notifications
  - Sync: data synchronization interval
  - Violations: abuse detection settings
  - Collector API: Node Agent integration settings
  - Limits: search results, pagination, bulk operations
  - Appearance: UI customization
- **Priority System**: environment variables > database values > default values
- **Type Validation**: supports string, int, float, bool, JSON types
- **Secret Protection**: sensitive values are masked in UI
- **Read-only Settings**: .env variables cannot be overwritten via UI
- New command `/config` for managing settings
- New database table `bot_config` for storing configuration

#### Anti-Abuse System (Violation Detector)
- **Multi-factor Analysis** for detecting account sharing and abuse:

  **Temporal Analyzer**:
  - Detects simultaneous connections from different IPs
  - Device count-aware thresholds (stricter for single-device accounts)
  - Configurable network switch buffer for WiFi/Mobile transitions

  **Geographic Analyzer**:
  - Recognition of 60+ Russian metropolitan areas (agglomerations)
  - "Impossible travel" detection using Haversine distance calculation
  - Travel speed validation:
    - Same city: 50 km/h threshold
    - Domestic travel: 200 km/h
    - International travel: 800 km/h
  - Simultaneous multi-country detection (highest risk)

  **ASN/Provider Analyzer**:
  - Provider type classification with suspicion modifiers:
    - Mobile carriers: ×0.3 (low risk)
    - Mobile ISP: ×0.5
    - Fixed broadband: ×0.8
    - Hosting/Datacenter: ×1.5 (high risk)
    - VPN providers: ×1.8 (very high risk)

  **User Profile Analyzer**:
  - Builds 30-day behavioral baseline from connection history
  - Tracks typical countries, cities, IPs, connection hours
  - Detects anomalies: 2× normal usage = 45 points, >2.5× = critical

  **Device Fingerprint Analyzer**:
  - OS detection from User-Agent (Android, iOS, Windows, macOS, Linux)
  - VPN client detection (V2RayNG, Shadowrocket, Clash, Surge, etc.)
  - Multiple device fingerprint scoring

- **Weighted Scoring System**:
  - Temporal: 25%
  - Geography: 25%
  - ASN: 15%
  - Profile: 20%
  - Device: 15%

- **Action Thresholds**:
  - < 30: No action (normal behavior)
  - 30-50: Monitor
  - 50-65: Warn user
  - 65-80: Soft block (rate limit)
  - 80-90: Temporary block
  - 90+: Hard block + manual review

#### Node Agent Integration
- **Collector API**: `POST /api/v1/connections/batch` endpoint for receiving connection data
- **Agent Token System**:
  - Secure 32-byte hex token generation for node authentication
  - Token management: generate, lookup, set, revoke
  - Unique index for fast token lookups
- **Batch Processing**: efficient handling of connection data batches
- **Automatic Violation Checking**: triggers analysis on each data batch

#### Notifications
- New topic `NOTIFICATIONS_TOPIC_VIOLATIONS` for violation alerts
- Detailed violation reports including:
  - Specific devices and OS detected
  - Countries and cities involved
  - Device fingerprints
  - Recommended action
  - Confidence score

### Changed
- Reduced verbose logging in violation detector (moved to DEBUG level)
- Improved notification formatting for violation events

### Database Migrations
- `20260128_0003_add_node_agent_token.py`: Added `agent_token` column to `nodes` table
- `20260129_0006_add_bot_config_table.py`: Created `bot_config` table for runtime configuration

---

## [1.5.1] - Previous Release

### Fixed
- Minor bug fixes and stability improvements

---

## [1.5.0] - Previous Release

### Added

#### PostgreSQL Integration
- Local data caching to reduce API panel load
- Automatic data synchronization with configurable interval (`SYNC_INTERVAL_SECONDS`)
- Real-time updates through webhook events

#### Data Reading Optimization
- Read operations now use local database:
  - Subscriptions
  - User searches
  - Host lists
  - Node information
  - Panel statistics
  - Configuration profiles
- Node status continues pulling real-time data from the API

#### Diff Notifications
- When data changes through the panel, the bot displays exactly what was modified
- Shows before-and-after values for affected fields

#### Notification Topic Routing
- Route different notification types to different Telegram topics
- Separate topics for: users, nodes, service, HWID, billing, errors
- Fallback to general topic if specific one is not set

#### Graceful Degradation
- System continues functioning through the API if database becomes unavailable
- Full backward compatibility — PostgreSQL is optional

---

## [1.4.0] - Previous Release

### Added
- HWID device management
- Bulk operations for users
- Extended user statistics

---

## [1.3.0] - Previous Release

### Added
- Billing module
- Host management
- API token management

---

## [1.2.0] - Previous Release

### Added
- Node management and monitoring
- Traffic statistics
- Configuration profiles

---

## [1.1.0] - Previous Release

### Added
- User management features
- Search functionality
- Basic statistics

---

## [1.0.0] - Initial Release

### Added
- Basic bot functionality
- Telegram authentication
- API integration with Remnawave panel
- Russian and English localization

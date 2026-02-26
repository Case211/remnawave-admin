# Полировка проекта — План

Цель: стабилизация, исправление ошибок, улучшение надёжности и UX. Без новых фич — только доводка существующего.

---

## 1. Обработка ошибок на фронтенде

**Проблема:** 11 страниц не обрабатывают `isError` из React Query — при сбое API пользователь видит пустую страницу или бесконечный skeleton.

| Страница | Файл |
|----------|------|
| Billing | `src/pages/Billing.tsx` |
| Reports | `src/pages/Reports.tsx` |
| Automations | `src/pages/Automations.tsx` |
| Analytics | `src/pages/Analytics.tsx` |
| AdvancedAnalytics | `src/pages/AdvancedAnalytics.tsx` |
| Resources | `src/pages/Resources.tsx` |
| SystemLogs | `src/pages/SystemLogs.tsx` |
| Notifications | `src/pages/Notifications.tsx` |
| MailServer | `src/pages/MailServer.tsx` |
| AuditLog | `src/pages/AuditLog.tsx` |
| Fleet | `src/pages/Fleet.tsx` |

**Что делать:** Добавить `isError` / `error` состояние с отображением компонента ошибки (Alert или inline-сообщение с кнопкой retry). Пример есть на страницах Users, Nodes, Hosts.

---

## 2. Тихие except-блоки в бэкенде

**Проблема:** ~26 мест с `except: pass` или `except Exception: pass` — ошибки проглатываются, баги невидимы.

**Что делать:** Пройти по всем `except` блокам и добавить `logger.warning(...)` или `logger.exception(...)`. Где возможно — сузить тип исключения.

**Файлы:**
- `web/backend/api/v2/collector.py` — несколько мест
- `web/backend/api/v2/analytics.py`
- `web/backend/api/v2/violations.py`
- `web/backend/core/notification_service.py`
- `shared/violation_detector.py`
- `shared/database.py`
- `shared/geoip.py`

---

## 3. Битая ссылка на API-документацию

**Проблема:** На странице Dashboard ссылка «API Docs» ведёт на `/api/v3/docs`, но API работает на `/api/v2/`. Ссылка 404.

**Файл:** `web/frontend/src/pages/Dashboard.tsx`

**Что делать:** Исправить на `/api/v2/docs`.

---

## 4. Мобильная адаптивность

**Проблема:** Страницы ApiKeys и Backup не имеют мобильной адаптации — таблицы выходят за экран.

**Что делать:** Добавить `overflow-x-auto` обёртки, responsive breakpoints для мелких элементов, mobile card view для таблиц на маленьких экранах.

---

## 5. TypeScript ошибки

**Проблема:** 3 TS6133 (unused variable) ошибки в кодовой базе.

**Что делать:** Найти и удалить неиспользуемые переменные. Запустить `npm run typecheck` и убедиться что 0 ошибок.

---

## 6. Docker-улучшения

### 6.1 Healthcheck для бота
Бот-контейнер не имеет `HEALTHCHECK` — Docker/Compose не знает, жив ли он.

**Что делать:** Добавить simple healthcheck (проверка PID процесса или HTTP endpoint если есть).

### 6.2 Init-процесс
Контейнеры не используют `init: true` (tini) — zombie-процессы могут накапливаться.

**Что делать:** Добавить `init: true` в `docker-compose.yml` для сервисов.

### 6.3 start_period для healthcheck
Web-backend healthcheck не имеет `start_period` — может фейлиться при долгом старте (миграции, etc.).

**Что делать:** Добавить `start_period: 30s` к healthcheck.

---

## 7. Неиспользуемые зависимости (фронтенд)

**Проблема:** 7 пакетов в `package.json` которые потенциально не используются.

**Что делать:** Проверить через поиск по коду, удалить неиспользуемые из `package.json`.

---

## 8. ESLint конфигурация

**Проблема:** Конфигурация ESLint отсутствует или неполная — нет автоматической проверки качества кода.

**Что делать:** Настроить ESLint с базовыми правилами для React + TypeScript. Без фанатизма — только то что ловит реальные баги.

---

## 9. Логирование и observability

### 9.1 Уровни логов
Некоторые важные события всё ещё на DEBUG уровне и не видны в production-логах.

**Что делать:** Аудит уровней логирования — убедиться что ключевые операции (auth, CRUD, sync, ошибки) логируются на INFO+.

### 9.2 Структурированные ошибки
Некоторые `except` блоки логируют только `str(e)` без traceback.

**Что делать:** Использовать `logger.exception(...)` вместо `logger.error(str(e))` для неожиданных ошибок.

---

## 10. Хардкодированные строки

**Проблема:** Часть UI-текстов зашита напрямую в компоненты вместо использования i18n.

**Что делать:** Вынести в i18n файлы строки из компонентов Fleet, Violations, Billing, Resources.

---

## Приоритеты

| Приоритет | Пункты | Причина |
|-----------|--------|---------|
| **P0 — Критично** | 1, 2, 3 | Пользователи видят пустые страницы, ошибки невидимы |
| **P1 — Важно** | 5, 6, 9 | Стабильность, Docker-здоровье, observability |
| **P2 — Улучшение** | 4, 7, 8, 10 | UX, чистота кода, поддерживаемость |

---

## Порядок выполнения

1. Исправить битую ссылку API docs (1 мин)
2. Добавить isError обработку на 11 страниц
3. Пройти except-блоки в бэкенде
4. Исправить TS ошибки
5. Docker healthcheck/init
6. Логирование
7. Мобильная адаптивность
8. Неиспользуемые зависимости
9. ESLint
10. i18n строки

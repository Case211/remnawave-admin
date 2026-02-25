# Аудит системы нарушений (Violations) — План улучшений

## Результаты аудита

Проведён детальный аудит всех компонентов: `shared/violation_detector.py` (6 анализаторов + скоринг), `web/backend/api/v2/collector.py`, `web/backend/api/v2/violations.py`, `shared/database.py`, `web/backend/core/violation_notifier.py`, `web/frontend/src/pages/Violations.tsx`.

---

## Группа 1: Баги в логике детектора (shared/violation_detector.py)

### 1.1 [MEDIUM] DeviceAnalyzer не учитывает лимит устройств пользователя

**Файл:** `shared/violation_detector.py`, строки 1534-1548

**Проблема:** DeviceFingerprintAnalyzer считает уникальные комбинации OS+Client и выставляет скоры (60/40/25/10), но НЕ сравнивает с `user_device_count`. Пользователь с 3 разрешёнными устройствами, использующий Android + iOS + Windows, получает score=40 ("Разные ОС одновременно"), хотя это легитимное использование.

**Исправление:** Сравнивать `unique_fingerprints_count` с `user_device_count` и начислять score только при превышении лимита. Если fingerprints <= device_count, score=0.

### 1.2 [LOW] DeviceAnalyzer считает 'Unknown' ОС как отдельную ОС

**Файл:** `shared/violation_detector.py`, строка 1527

**Проблема:** `different_os_count = len(os_families)` включает 'Unknown'. Если 2 реальных ОС + 1 Unknown = 3 ОС → score=40, хотя по сути только 2 ОС.

**Исправление:** Использовать `len(os_families_known)` вместо `len(os_families)` для подсчёта.

### 1.3 [LOW] ProfileAnalyzer — неиспользуемые данные baseline

**Файл:** `shared/violation_detector.py`, строки 1180-1184

**Проблема:** В baseline собираются `typical_hours` и `avg_session_duration`, но никогда не используются в анализе. Аномальные подключения в нехарактерное время (напр. в 3 ночи для дневного пользователя) не детектируются.

**Исправление:** Добавить проверку часов подключения — если текущий час не входит в типичные, добавлять +10 к score.

### 1.4 [LOW] ASNAnalyzer — тихий возврат 0 при сбое GeoIP

**Файл:** `shared/violation_detector.py`, строки 1030-1040

**Проблема:** Если `lookup_batch()` возвращает пустой результат (сбой сети, таймаут), ASN score = 0.0 без логирования. Злоупотребление может пройти незамеченным.

**Исправление:** Логировать warning при пустом результате. Не менять score на 0, а пропускать ASN-множитель (не применять ×0.3 для mobile и т.д.), чтобы итоговый score не занижался.

### 1.5 [LOW] Timezone handling в TemporalAnalyzer

**Файл:** `shared/violation_detector.py`, строки 166-167

**Проблема:** `conn_time.replace(tzinfo=None)` убирает timezone без конвертации в UTC. Если timestamp хранится в UTC+3, а `now = datetime.utcnow()` — разница 3 часа, что ломает все временные проверки.

**Исправление:** Использовать `conn_time.astimezone(timezone.utc).replace(tzinfo=None)` вместо простого `replace(tzinfo=None)`.

---

## Группа 2: Улучшения скоринговой модели

### 2.1 [MEDIUM] Уязвимость новых аккаунтов в ProfileAnalyzer

**Файл:** `shared/violation_detector.py`, строки 1315-1321

**Проблема:** Пользователи с < 7 дней данных получают score=0 от ProfileAnalyzer. Это создаёт окно уязвимости: новые/пробные аккаунты — самая высокая группа риска для шаринга, но профильный анализатор полностью их игнорирует.

**Исправление:** Для новых аккаунтов (< 7 дней) применить "подозрительные по умолчанию" правила — использовать средние показатели всех пользователей как baseline и давать score с множителем 0.7 (менее уверенный).

### 2.2 [LOW] HWID анализатор — бинарный скоринг

**Файл:** `shared/violation_detector.py`, строки 1560-1621

**Проблема:** HWID score всегда 0 или 100 — без градации. 1 чужой аккаунт = 100, и 10 чужих = 100.

**Исправление:** Градуированный скоринг: 1 аккаунт = 75, 2-3 = 85, 4+ = 100.

### 2.3 [LOW] Network switch pattern слишком агрессивно снижает score

**Файл:** `shared/violation_detector.py`, строки 1802-1810

**Проблема:** Если обнаружен паттерн mobile + home ISP, score умножается на 0.5. Но если пользователь реально шарит аккаунт и при этом один из шареров использует мобильный интернет — score незаслуженно занижается.

**Исправление:** Применять ×0.5 только если одновременных IP ≤ device_count + 2 (т.е. переключение сети правдоподобно). При превышении лимита переключение сети менее вероятно, не снижать score.

---

## Группа 3: Проблемы производительности бэкенда

### 3.1 [HIGH] Client-side фильтрация в violations API

**Файл:** `web/backend/api/v2/violations.py`

**Проблема:** Эндпоинт `GET /violations` загружает ВСЕ нарушения за период (до 1000), а потом фильтрует по min_score, user_uuid, severity В PYTHON. При большом количестве нарушений — значительная нагрузка на память и CPU.

**Исправление:** Перенести фильтрацию в SQL-запрос: добавить WHERE clauses для score >= $X, user_uuid = $Y и severity в функцию `get_violations_for_period()` в database.py.

### 3.2 [HIGH] Линейный поиск violation по ID

**Файл:** `web/backend/api/v2/violations.py`

**Проблема:** `GET /violations/{id}` загружает до 1000 нарушений за 90 дней, потом ищет нужное линейным поиском O(n).

**Исправление:** Добавить функцию `get_violation_by_id(violation_id)` в database.py с `WHERE id = $1`.

### 3.3 [MEDIUM] Дублирование GeoIP-запросов

**Файл:** `shared/violation_detector.py`

**Проблема:** GeoAnalyzer и ASNAnalyzer оба делают `lookup_batch()` для тех же IP. В collector.py после detection ещё один batch lookup для ip_metadata. Тройное обращение к GeoIP.

**Исправление:** Выполнять один batch lookup в начале check_user() и передавать результат всем анализаторам.

### 3.4 [LOW] SQL-запросы используют string formatting вместо параметров

**Файл:** `shared/database.py`, строки 1186, 1208, 1237, 1303, 2628, 2664

**Проблема:** Используется `.replace('%s', str(value))` для INTERVAL значений. Хотя значения внутренние (не пользовательский ввод) и риск SQL-инъекции минимален, это плохая практика.

**Исправление:** Использовать `f"INTERVAL '{int(value)} minutes'"` с явным int() кастом или передавать интервал как параметр PostgreSQL.

---

## Группа 4: Проблемы API и уведомлений

### 4.1 [MEDIUM] Аудит-лог записывается ДО подтверждения операции

**Файл:** `web/backend/api/v2/violations.py`

**Проблема:** resolve endpoint пишет audit log до того, как DB update выполнится успешно. Если update упадёт — лог содержит ложную запись.

**Исправление:** Переместить запись audit log после успешного DB update.

### 4.2 [MEDIUM] Нет проверки существования violation перед resolve/annul

**Файл:** `web/backend/api/v2/violations.py`

**Проблема:** `resolve_violation()` и `annul_violation()` не проверяют, существует ли violation. При несуществующем ID — тихо ничего не обновляется, но возвращается 200.

**Исправление:** Добавить проверку и возвращать 404 если violation не найден.

### 4.3 [LOW] In-memory кэш уведомлений теряется при рестарте

**Файл:** `web/backend/core/violation_notifier.py`

**Проблема:** `_violation_notification_cache` хранится в памяти. При рестарте сервера кэш обнуляется → дублирование уведомлений.

**Исправление:** Использовать `notified_at` поле в базе данных (уже есть в схеме, но `mark_violation_notified()` не вызывается).

### 4.4 [LOW] Хардкоженные cooldown значения

**Файл:** `web/backend/api/v2/collector.py`, строка 32

**Проблема:** `VIOLATION_CHECK_COOLDOWN_MINUTES = 5` и cooldown уведомлений (30 мин) захардкожены.

**Исправление:** Вынести в `config_service` для настройки через Settings UI без рестарта.

---

## Группа 5: Проблемы фронтенда

### 5.1 [HIGH] Отсутствие Array.isArray() проверок

**Файл:** `web/frontend/src/pages/Violations.tsx`

**Проблема:** `.map()` вызывается на `detail.reasons`, `detail.countries`, `detail.asn_types`, `detail.ips` без проверки `Array.isArray()`. Если API вернёт null — краш с "`.map()` is not a function".

**Исправление:** Добавить `Array.isArray()` перед каждым `.map()` / `.reduce()` на данных из API.

### 5.2 [HIGH] Монолитный файл 2100+ строк

**Файл:** `web/frontend/src/pages/Violations.tsx`

**Проблема:** 11 компонентов, все типы, все API вызовы — в одном файле. Ухудшает maintainability, усложняет code review.

**Исправление:** Разбить на:
- `types/violations.ts` — общие TypeScript типы
- `api/violations.ts` — API функции
- `components/violations/` — ViolationCard, ViolationDetail, WhitelistTab и т.д.
- `pages/Violations.tsx` — только роутинг и композиция

### 5.3 [MEDIUM] Фильтры по IP, стране, дате — состояние есть, UI нет

**Файл:** `web/frontend/src/pages/Violations.tsx`

**Проблема:** State переменные `ipFilter`, `countryFilter`, `dateFrom`, `dateTo` объявлены и передаются в API, но НЕТ соответствующих input полей в UI. Пользователи не могут использовать эти фильтры.

**Исправление:** Добавить UI-компоненты для расширенных фильтров (с collapse/expand).

### 5.4 [MEDIUM] Экспорт только текущей страницы

**Проблема:** CSV экспорт выгружает только 15 записей текущей страницы. Нет индикации лимита и нет опции "экспортировать все".

**Исправление:** Добавить серверный эндпоинт для full export или загружать все страницы перед экспортом.

### 5.5 [LOW] Дублирование типов между страницами

**Проблема:** `Violation` интерфейс определён отдельно в `Violations.tsx`, `UserDetail.tsx` и `Dashboard.tsx`. Типы могут разойтись.

**Исправление:** Создать общий `types/violations.ts` (входит в 5.2).

### 5.6 [LOW] CSV экспорт — отсутствие экранирования

**Проблема:** Reasons/countries соединяются через `;`/`,` без экранирования спецсимволов. Может создать невалидный CSV.

**Исправление:** Использовать proper CSV escaping (кавычки вокруг полей с разделителями).

### 5.7 [LOW] Нет bulk actions для нарушений

**Проблема:** Нельзя выбрать несколько нарушений для массового resolve/dismiss/annul.

**Исправление:** Добавить чекбоксы и панель массовых действий.

---

## Группа 6: Отсутствующая функциональность

### 6.1 [LOW] Нет автоматической ротации/очистки старых violations

**Проблема:** Аннулированные нарушения остаются в БД с score=0. Нет автоочистки → неограниченный рост таблицы.

**Исправление:** Добавить retention policy — автоудаление resolved/annulled violations старше N дней (настраиваемо через config_service).

### 6.2 [LOW] Нет real-time обновлений на фронте

**Проблема:** Violations page не имеет WebSocket/auto-refresh. Новые нарушения видны только после ручного обновления.

**Исправление:** Добавить polling каждые 30 сек для вкладки Pending или SSE/WebSocket для push-уведомлений.

---

## Приоритизация

| Приоритет | ID | Что | Сложность |
|-----------|-----|-----|-----------|
| HIGH | 3.1 | SQL-фильтрация violations вместо Python | Средняя |
| HIGH | 3.2 | Прямой запрос violation по ID | Низкая |
| HIGH | 5.1 | Array.isArray() guards | Низкая |
| MEDIUM | 1.1 | DeviceAnalyzer + device_count | Низкая |
| MEDIUM | 2.1 | Новые аккаунты в ProfileAnalyzer | Средняя |
| MEDIUM | 2.3 | Network switch — условное снижение | Низкая |
| MEDIUM | 3.3 | Единый GeoIP batch lookup | Средняя |
| MEDIUM | 4.1 | Audit log после успешного update | Низкая |
| MEDIUM | 4.2 | 404 для несуществующих violations | Низкая |
| MEDIUM | 5.3 | UI расширенных фильтров | Средняя |
| MEDIUM | 5.4 | Full export | Средняя |
| LOW | 1.2 | Unknown OS в подсчёте | Низкая |
| LOW | 1.3 | Typical hours в ProfileAnalyzer | Низкая |
| LOW | 1.4 | Логирование при сбое GeoIP | Низкая |
| LOW | 1.5 | Timezone normalization | Низкая |
| LOW | 2.2 | Градуированный HWID скоринг | Низкая |
| LOW | 3.4 | Параметризованные SQL INTERVAL | Низкая |
| LOW | 4.3 | Persistent notification cache | Низкая |
| LOW | 4.4 | Configurable cooldowns | Низкая |
| LOW | 5.2 | Рефакторинг Violations.tsx | Высокая |
| LOW | 5.5-5.7 | Типы, CSV, bulk actions | Средняя |
| LOW | 6.1-6.2 | Retention policy, real-time | Средняя |

---

## Рекомендуемый порядок реализации

**Фаза 1 — Критические фиксы** (баги и производительность):
- 3.1, 3.2: SQL-оптимизация violations API
- 5.1: Array.isArray() guards на фронте
- 4.1, 4.2: Правильный порядок audit log + 404

**Фаза 2 — Логика детектора**:
- 1.1: DeviceAnalyzer + device_count
- 2.1: Защита новых аккаунтов
- 2.3: Условный network switch modifier
- 1.2, 1.4, 1.5: Мелкие фиксы анализаторов

**Фаза 3 — Оптимизация**:
- 3.3: Единый GeoIP lookup
- 3.4: SQL параметризация
- 4.3, 4.4: Persistent cache, configurable cooldowns

**Фаза 4 — UX фронтенда**:
- 5.3: Advanced filters UI
- 5.4: Full export
- 5.5-5.7: Типы, CSV, bulk actions

**Фаза 5 — Новая функциональность** (опционально):
- 5.2: Рефакторинг Violations.tsx
- 6.1, 6.2: Retention policy, real-time
- 1.3, 2.2: Typical hours, градуированный HWID

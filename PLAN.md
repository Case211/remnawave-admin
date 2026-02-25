# Аудит системы нарушений (Violations) — Детальный план реализации

## Результаты аудита

Проведён детальный аудит всех компонентов: `shared/violation_detector.py` (6 анализаторов + скоринг), `web/backend/api/v2/collector.py`, `web/backend/api/v2/violations.py`, `shared/database.py`, `web/backend/core/violation_notifier.py`, `web/frontend/src/pages/Violations.tsx`.

**Найдено 22 проблемы** в 6 группах. Ниже — подробный план исправлений с указанием файлов, строк и конкретных изменений.

---

# Фаза 1 — Критические фиксы (баги и производительность)

## 1. SQL-оптимизация: фильтрация в БД вместо Python [3.1]

### Проблема
`web/backend/api/v2/violations.py:100-165` — эндпоинт `GET /violations` вызывает `db.get_violations_for_period()` с единственными фильтрами `start_date`, `end_date`, `min_score` (строки 101-105). Потом в Python фильтрует по `user_uuid`, `severity`, `resolved`, `ip`, `country`, `date_from`, `date_to` (строки 108-165). При 1000 записях — ненужная нагрузка.

### Что делаю

**Файл `shared/database.py` — расширяю `get_violations_for_period()`:**

Текущая сигнатура (строка 2332):
```python
async def get_violations_for_period(self, start_date, end_date, min_score=0.0, limit=1000)
```

Новая сигнатура:
```python
async def get_violations_for_period(
    self, start_date, end_date, min_score=0.0, limit=1000,
    user_uuid=None, severity=None, resolved=None,
    ip=None, country=None, offset=0
)
```

SQL-запрос (строки 2356-2365) меняю с:
```sql
SELECT * FROM violations
WHERE detected_at >= $1 AND detected_at < $2 AND score >= $3
ORDER BY detected_at DESC LIMIT $4
```

На динамический SQL с дополнительными WHERE-условиями:
```sql
SELECT * FROM violations
WHERE detected_at >= $1 AND detected_at < $2 AND score >= $3
  AND ($4::text IS NULL OR user_uuid::text = $4)
  AND ($5::text IS NULL OR action_taken IS NOT NULL = $5)  -- resolved filter
  AND ($6::text IS NULL OR $6 = ANY(ip_addresses))          -- ip filter
  AND ($7::text IS NULL OR UPPER($7) = ANY(
       SELECT UPPER(x) FROM UNNEST(countries) AS x))        -- country filter
  AND (CASE WHEN $8 = 'low' THEN score >= 0 AND score < 40
            WHEN $8 = 'medium' THEN score >= 40 AND score < 60
            WHEN $8 = 'high' THEN score >= 60 AND score < 80
            WHEN $8 = 'critical' THEN score >= 80
            ELSE TRUE END)                                   -- severity filter
ORDER BY detected_at DESC
LIMIT $9 OFFSET $10
```

Также добавляю метод для подсчёта total (для пагинации):
```python
async def count_violations_for_period(self, start_date, end_date, min_score=0.0,
                                       user_uuid=None, severity=None, resolved=None,
                                       ip=None, country=None) -> int:
```

**Файл `web/backend/api/v2/violations.py` — упрощаю эндпоинт:**

Строки 100-174 — убираю всю Python-фильтрацию. Заменяю на:
```python
# Получаем count для пагинации
total = await db.count_violations_for_period(
    start_date=start_date, end_date=end_date, min_score=min_score,
    user_uuid=user_uuid, severity=severity, resolved=resolved,
    ip=ip, country=country,
)
# Получаем страницу данных
violations = await db.get_violations_for_period(
    start_date=start_date, end_date=end_date, min_score=min_score,
    user_uuid=user_uuid, severity=severity, resolved=resolved,
    ip=ip, country=country,
    limit=per_page, offset=(page - 1) * per_page,
)
```

---

## 2. Прямой SQL-запрос violation по ID [3.2]

### Проблема
`web/backend/api/v2/violations.py:540-554` — `GET /violations/{id}` загружает до 1000 записей за 90 дней, затем линейный поиск O(n).

### Что делаю

**Файл `shared/database.py` — добавляю новый метод:**

Вставляю после `get_violations_for_period()` (после строки 2371):
```python
async def get_violation_by_id(self, violation_id: int) -> Optional[Dict[str, Any]]:
    """Получить нарушение по ID."""
    if not self.is_connected:
        return None
    try:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM violations WHERE id = $1", violation_id
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Error getting violation by id %s: %s", violation_id, e, exc_info=True)
        return None
```

**Файл `web/backend/api/v2/violations.py` — переписываю эндпоинт:**

Строки 540-554 заменяю на:
```python
violation = await db.get_violation_by_id(violation_id)
if not violation:
    raise api_error(404, E.VIOLATION_NOT_FOUND)
```

---

## 3. Array.isArray() guards на фронте [5.1]

### Проблема
`web/frontend/src/pages/Violations.tsx` — строки 749, 771, 788, 805: `.map()` на `detail.reasons`, `detail.countries`, `detail.asn_types`, `detail.ips` без проверки. Если API вернёт null → краш.

### Что делаю

**Файл `web/frontend/src/pages/Violations.tsx` — 4 точки исправления:**

Строка 749 — меняю:
```tsx
{detail.reasons.map((reason, i) => (
```
На:
```tsx
{(Array.isArray(detail.reasons) ? detail.reasons : []).map((reason, i) => (
```

Строка 771 — меняю:
```tsx
{detail.countries.map((country, i) => (
```
На:
```tsx
{(Array.isArray(detail.countries) ? detail.countries : []).map((country, i) => (
```

Строка 788 — меняю:
```tsx
{detail.asn_types.map((asn, i) => (
```
На:
```tsx
{(Array.isArray(detail.asn_types) ? detail.asn_types : []).map((asn, i) => (
```

Строка 805 — меняю:
```tsx
{detail.ips.map((ip, i) => {
```
На:
```tsx
{(Array.isArray(detail.ips) ? detail.ips : []).map((ip, i) => {
```

Также проверю строки 854 (`hwidDevices.map`), 1055 (`v.actions.map`), 1369 (`item.excluded_analyzers.map`) — аналогичные guards.

---

## 4. Audit log после успешного update + 404 [4.1, 4.2]

### Проблема
`web/backend/api/v2/violations.py:603-622` — resolve endpoint: audit log пишется на строке 612, но `update_violation_action()` на строке 603 может вернуть `success=False`, при этом audit log уже записан (на самом деле — нет, т.к. есть проверка `if not success` на строке 609, но если `update_violation_action` бросит exception — audit log не запишется, что корректно).

Перечитав код: **resolve и annul** проверяют `success` (строки 609, 639) и бросают 404 при неуспехе. Audit log пишется ПОСЛЕ проверки. Это **корректно**.

Однако: `update_violation_action()` возвращает `True` даже если `WHERE id = $1` не нашёл строку (UPDATE 0 rows). Нужно проверять `affected_rows > 0`.

### Что делаю

**Файл `shared/database.py` — нахожу `update_violation_action()`:**

Проверяю, возвращает ли `execute()` / `fetchrow()` результат. Если используется `conn.execute()` — парсим строку `"UPDATE N"`. Меняю на:
```python
result = await conn.execute(...)
return result == "UPDATE 1"  # Вернёт False если строка не найдена
```

Это гарантирует, что resolve/annul для несуществующего ID вернёт 404.

---

# Фаза 2 — Логика детектора

## 5. DeviceAnalyzer: учёт лимита устройств [1.1]

### Проблема
`shared/violation_detector.py:1462-1557` — `DeviceFingerprintAnalyzer.analyze()` не принимает `user_device_count`. Считает `unique_fingerprints_count` и выдаёт фиксированные скоры (60/40/25/10) без сравнения с лимитом.

### Что делаю

**Файл `shared/violation_detector.py`:**

1) Меняю сигнатуру `analyze()` (строка 1462):
```python
def analyze(self, connections, connection_history) -> DeviceScore:
```
→
```python
def analyze(self, connections, connection_history, user_device_count: int = 1) -> DeviceScore:
```

2) Добавляю проверку перед скорингом (перед строкой 1534):
```python
# Если количество fingerprints не превышает лимит устройств — это нормально
if unique_fingerprints_count <= user_device_count:
    return DeviceScore(
        score=0.0,
        reasons=[],
        unique_fingerprints_count=unique_fingerprints_count,
        different_os_count=different_os_count,
        os_list=os_families_known if os_families_known else None,
        client_list=client_types_known if client_types_known else None
    )
```

3) Корректирую скоринг для превышающих лимит (строки 1535-1548):
```python
excess = unique_fingerprints_count - user_device_count
if excess >= 3 or unique_fingerprints_count > 3:
    score = 60.0
    reasons.append(f"Много устройств ({unique_fingerprints_count}) при лимите {user_device_count}")
elif different_os_count > user_device_count and different_os_count >= 3:
    score = 40.0
    reasons.append(f"Разные ОС ({different_os_count}) при лимите {user_device_count}: {', '.join(os_families_known)}")
elif different_clients_count > user_device_count:
    score = 25.0
    reasons.append(f"Разные клиенты ({different_clients_count}) при лимите {user_device_count}: {', '.join(client_types_known)}")
elif excess >= 1:
    score = 10.0
    reasons.append(f"Превышение на {excess}: {unique_fingerprints_count} fingerprints, лимит {user_device_count}")
```

4) В `IntelligentViolationDetector.check_user()` (строка 1739) передаю `user_device_count`:
```python
device_score = self.device_analyzer.analyze(active_connections, connection_history, user_device_count)
```

---

## 6. Unknown OS не считать как отдельную ОС [1.2]

### Проблема
`shared/violation_detector.py:1527` — `different_os_count = len(os_families)` включает 'Unknown'.

### Что делаю

Строка 1527 меняю:
```python
different_os_count = len(os_families)
```
→
```python
different_os_count = len(os_families_known) if os_families_known else len(os_families)
```

---

## 7. Логирование при сбое GeoIP в ASNAnalyzer [1.4]

### Проблема
`shared/violation_detector.py:1030-1040` — при пустом `ip_metadata` возвращается score=0 молча.

### Что делаю

После строки 1032 (`if not ip_metadata:`) добавляю:
```python
if all_ips:
    logger.warning(
        "GeoIP lookup returned empty result for %d IPs, ASN analysis skipped",
        len(all_ips)
    )
```

---

## 8. Timezone normalization в TemporalAnalyzer [1.5]

### Проблема
`shared/violation_detector.py:166-167` — `conn_time.replace(tzinfo=None)` удаляет timezone без конвертации.

### Что делаю

Строки 166-167 меняю:
```python
if conn_time.tzinfo:
    conn_time = conn_time.replace(tzinfo=None)
```
→
```python
if conn_time.tzinfo:
    from datetime import timezone
    conn_time = conn_time.astimezone(timezone.utc).replace(tzinfo=None)
```

---

## 9. Network switch modifier — условное применение [2.3]

### Проблема
`shared/violation_detector.py:1802-1810` — ×0.5 при network switch паттерне безусловен. При шаринге через мобильный → ложное занижение.

### Что делаю

Строки 1802-1806 меняю:
```python
is_network_switch = self._detect_network_switch_pattern(asn_score.asn_types)
if is_network_switch:
    score_before_switch = raw_score
    raw_score *= 0.5
```
→
```python
is_network_switch = self._detect_network_switch_pattern(asn_score.asn_types)
if is_network_switch:
    # Применяем снижение только если количество IP правдоподобно для переключения сети
    # (лимит устройств + буфер 2 на переключение)
    if temporal_score.simultaneous_connections_count <= user_device_count + 2:
        score_before_switch = raw_score
        raw_score *= 0.5
        logger.debug(
            "Network switch pattern detected, IPs (%d) within device limit + buffer (%d+2), reducing: %.2f -> %.2f",
            temporal_score.simultaneous_connections_count, user_device_count,
            score_before_switch, raw_score
        )
    else:
        logger.debug(
            "Network switch pattern detected but IPs (%d) exceed device limit + buffer (%d+2), NOT reducing score",
            temporal_score.simultaneous_connections_count, user_device_count,
        )
```

---

## 10. Защита новых аккаунтов в ProfileAnalyzer [2.1]

### Проблема
`shared/violation_detector.py:1315-1321` — аккаунты < 7 дней = score 0. Окно уязвимости.

### Что делаю

Строки 1315-1321 меняю:
```python
if baseline['data_points'] < 7:
    return ProfileScore(score=0.0, reasons=[], deviation_from_baseline=0.0)
```
→
```python
if baseline['data_points'] < 7:
    # Для новых аккаунтов: оцениваем по абсолютным показателям
    # Если > 3 уникальных IP и аккаунт совсем новый — подозрительно
    if len(current_ips) > 3 and baseline['data_points'] < 3:
        return ProfileScore(
            score=20.0,
            reasons=[f"Новый аккаунт ({baseline['data_points']} дн. данных) с {len(current_ips)} уникальными IP"],
            deviation_from_baseline=0.0
        )
    return ProfileScore(score=0.0, reasons=[], deviation_from_baseline=0.0)
```

---

# Фаза 3 — Оптимизация

## 11. Единый GeoIP batch lookup [3.3]

### Проблема
GeoAnalyzer (строка 1719) и ASNAnalyzer (строка 1731) оба вызывают `lookup_batch()` для тех же IP. Потом collector.py (строка 350) делает третий lookup.

### Что делаю

**Файл `shared/violation_detector.py` — `IntelligentViolationDetector.check_user()`:**

1) Перед вызовами анализаторов (строка ~1718), добавляю единый lookup:
```python
# Единый GeoIP lookup для всех анализаторов
all_ips = list({str(conn.ip_address) for conn in active_connections})
for conn in connection_history:
    ip = str(conn.get("ip_address", ""))
    if ip:
        all_ips.append(ip)
all_ips = list(set(all_ips))

ip_metadata_cache = {}
if all_ips:
    try:
        from shared.geoip import get_geoip_service
        geoip = get_geoip_service()
        ip_metadata_cache = await geoip.lookup_batch(all_ips)
    except Exception as e:
        logger.warning("Failed pre-fetching GeoIP data: %s", e)
```

2) Меняю сигнатуры `GeoAnalyzer.analyze()` и `ASNAnalyzer.analyze()` — добавляю `ip_metadata_cache: dict = None`:
```python
async def analyze(self, connections, connection_history, ip_metadata_cache=None):
    # Если кэш передан, используем его вместо нового lookup
    if ip_metadata_cache is not None:
        ip_metadata = ip_metadata_cache
    else:
        ip_metadata = await self.geoip.lookup_batch(...)
```

3) Передаю кэш при вызове:
```python
geo_score = await self.geo_analyzer.analyze(active_connections, connection_history, ip_metadata_cache)
asn_score = await self.asn_analyzer.analyze(active_connections, connection_history, ip_metadata_cache)
```

4) Добавляю `ip_metadata_cache` в `ViolationScore` чтобы collector.py не делал третий lookup:
```python
return ViolationScore(
    ...,
    ip_metadata=ip_metadata_cache,  # Новое поле
)
```

**Файл `web/backend/api/v2/collector.py` строки 344-352:**

Заменяю:
```python
ip_metadata = {}
if active_conns:
    try:
        from shared.geoip import get_geoip_service
        ...
```
На:
```python
ip_metadata = getattr(violation_score, 'ip_metadata', {}) or {}
```

---

## 12. SQL INTERVAL параметризация [3.4]

### Проблема
`shared/database.py` — 6 мест с `.replace('%s', str(value))` для INTERVAL.

### Что делаю

Во всех 6 местах меняю паттерн. Пример для строки 2628:

Было:
```python
AND detected_at > NOW() - INTERVAL '%s hours'
""".replace('%s', str(hours)),
user_uuid
```
Стало:
```python
AND detected_at > NOW() - make_interval(hours => $2)
""",
user_uuid, int(hours)
```

Аналогично для строк 1186 (minutes), 1208 (hours), 1237 (minutes), 1303 (days), 2664 (days).

---

## 13. Persistent notification cache [4.3]

### Проблема
`web/backend/core/violation_notifier.py:13` — `_violation_notification_cache` in-memory dict.

### Что делаю

**Файл `web/backend/core/violation_notifier.py`:**

Строки 67-72 — вместо in-memory cache, проверяю `notified_at` в БД:
```python
# Throttling: check DB notified_at instead of in-memory cache
if not force:
    from shared.database import db_service
    last_notified = await db_service.get_user_last_violation_notification(user_uuid)
    if last_notified and now - last_notified < timedelta(minutes=VIOLATION_NOTIFICATION_COOLDOWN_MINUTES):
        logger.debug("Violation notification throttled for user %s (last: %s)", user_uuid, last_notified)
        return
```

В конце функции (после отправки), вызываю:
```python
await db_service.mark_violation_notified(user_uuid)
```

**Файл `shared/database.py` — добавляю метод:**
```python
async def get_user_last_violation_notification(self, user_uuid: str) -> Optional[datetime]:
    """Получить время последнего уведомления о нарушении."""
    async with self.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT MAX(notified_at) as last FROM violations WHERE user_uuid = $1 AND notified_at IS NOT NULL",
            user_uuid
        )
        return row['last'] if row else None

async def mark_violation_notified(self, user_uuid: str) -> None:
    """Отметить последнее нарушение как нотифицированное."""
    async with self.acquire() as conn:
        await conn.execute(
            """UPDATE violations SET notified_at = NOW()
               WHERE user_uuid = $1 AND notified_at IS NULL
               ORDER BY detected_at DESC LIMIT 1""",
            user_uuid
        )
```

Удаляю in-memory `_violation_notification_cache` и `_cleanup_cache()`.

---

## 14. Configurable cooldowns [4.4]

### Проблема
`web/backend/api/v2/collector.py:32` — `VIOLATION_CHECK_COOLDOWN_MINUTES = 5` захардкожено. `violation_notifier.py:14` — `VIOLATION_NOTIFICATION_COOLDOWN_MINUTES = 30` захардкожено.

### Что делаю

**Файл `web/backend/api/v2/collector.py` строка 311:**

Меняю:
```python
if last_check and (now_check - last_check).total_seconds() < VIOLATION_CHECK_COOLDOWN_MINUTES * 60:
```
→
```python
cooldown_minutes = config_service.get("violation_check_cooldown_minutes", 5)
if last_check and (now_check - last_check).total_seconds() < cooldown_minutes * 60:
```

**Файл `web/backend/core/violation_notifier.py` строка 70:**

Меняю:
```python
timedelta(minutes=VIOLATION_NOTIFICATION_COOLDOWN_MINUTES)
```
→
```python
from shared.config_service import config_service
cooldown = config_service.get("violation_notification_cooldown_minutes", 30)
timedelta(minutes=cooldown)
```

---

# Фаза 4 — UX фронтенда

## 15. Advanced filters UI [5.3]

### Проблема
`web/frontend/src/pages/Violations.tsx` — state `ipFilter`, `countryFilter`, `dateFrom`, `dateTo` существует, но UI для них нет.

### Что делаю

В секции фильтров (после блока с `severity`/`scoreFilter` слайдерами) добавляю collapsible "Расширенные фильтры":

```tsx
<Collapsible>
  <CollapsibleTrigger className="flex items-center gap-1 text-sm text-muted-foreground">
    <ChevronRight className="h-4 w-4" />
    {t('violations.advancedFilters')}
  </CollapsibleTrigger>
  <CollapsibleContent className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
    <Input
      placeholder={t('violations.filterByIp')}
      value={ipFilter}
      onChange={(e) => setIpFilter(e.target.value)}
    />
    <Input
      placeholder={t('violations.filterByCountry')}
      value={countryFilter}
      onChange={(e) => setCountryFilter(e.target.value)}
    />
    <Input
      type="date"
      value={dateFrom}
      onChange={(e) => setDateFrom(e.target.value)}
    />
    <Input
      type="date"
      value={dateTo}
      onChange={(e) => setDateTo(e.target.value)}
    />
  </CollapsibleContent>
</Collapsible>
```

Добавляю debounce (300ms) на все filter inputs чтобы не дёргать API на каждый символ.

---

## 16. Full CSV export [5.4]

### Проблема
Экспорт выгружает только 15 записей текущей страницы.

### Что делаю

**Файл `web/backend/api/v2/violations.py` — новый эндпоинт:**

```python
@router.get("/export/csv")
async def export_violations_csv(
    days: int = Query(7, ge=1, le=365),
    min_score: float = Query(0, ge=0, le=100),
    severity: Optional[str] = None,
    user_uuid: Optional[str] = None,
    admin: AdminUser = Depends(require_permission("violations", "view")),
    db: DatabaseService = Depends(get_db),
):
    """Экспорт нарушений в CSV."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    violations = await db.get_violations_for_period(
        start_date=start_date, end_date=end_date,
        min_score=min_score, severity=severity,
        user_uuid=user_uuid, limit=10000,
    )

    # Формируем CSV с proper escaping
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(["Date", "User", "Email", "Score", "Action", "IPs", "Countries", "Reasons"])
    for v in violations:
        writer.writerow([...])

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=violations_{days}d.csv"}
    )
```

**Файл `web/frontend/src/pages/Violations.tsx` — меняю кнопку Export:**

Заменяю client-side генерацию CSV на вызов серверного эндпоинта:
```tsx
const handleExport = () => {
    const params = new URLSearchParams({ days: String(days), min_score: String(scoreFilter) })
    window.open(`/api/v2/violations/export/csv?${params}`, '_blank')
}
```

---

## 17. CSV escaping fix [5.6]

### Проблема
Текущий export на фронте (строка ~1649) соединяет reasons через `;` без экранирования.

### Что делаю

Решается через серверный CSV export (пункт 16 выше) с использованием Python `csv.writer(quoting=csv.QUOTE_ALL)` — автоматическое экранирование.

---

## 18. Дублирование типов [5.5]

### Что делаю

**Создаю `web/frontend/src/types/violations.ts`:**

Выношу интерфейсы `Violation`, `ViolationDetail`, `ViolationStats`, `TopViolator`, `WhitelistItem` из `Violations.tsx`.

**Меняю `Violations.tsx`, `UserDetail.tsx`, `Dashboard.tsx`:**

```tsx
import type { Violation, ViolationStats } from '@/types/violations'
```

Удаляю локальные определения типов из каждого файла.

---

# Фаза 5 — Новая функциональность (опционально)

## 19. Градуированный HWID скоринг [2.2]

### Что делаю

**Файл `shared/violation_detector.py` строка 1602:**

Меняю:
```python
score = 100.0
```
→
```python
if other_count >= 4:
    score = 100.0
elif other_count >= 2:
    score = 85.0
else:
    score = 75.0
```

---

## 20. Typical hours в ProfileAnalyzer [1.3]

### Что делаю

**Файл `shared/violation_detector.py` — в `analyze()` (после строки ~1370):**

```python
# Проверка подключения в нетипичное время
typical_hours = set(baseline.get('typical_hours', []))
if typical_hours and current_ips:
    current_hour = datetime.utcnow().hour
    if current_hour not in typical_hours:
        score += 10.0
        reasons.append(f"Подключение в нетипичное время ({current_hour}:00 UTC, обычно: {sorted(typical_hours)})")
```

---

## 21. Retention policy [6.1]

### Что делаю

**Файл `shared/database.py` — новый метод:**
```python
async def cleanup_old_violations(self, retention_days: int = 90) -> int:
    """Удалить resolved/annulled violations старше N дней."""
    async with self.acquire() as conn:
        result = await conn.execute(
            """DELETE FROM violations
               WHERE action_taken IS NOT NULL
               AND detected_at < NOW() - make_interval(days => $1)""",
            retention_days
        )
        return int(result.split()[-1])  # "DELETE N"
```

**Файл `web/backend/api/v2/collector.py` — в post-processing:**

Раз в час (через простой timestamp check) вызываем cleanup:
```python
_last_cleanup = datetime.min
...
if (datetime.utcnow() - _last_cleanup).total_seconds() > 3600:
    retention_days = config_service.get("violation_retention_days", 90)
    cleaned = await db.cleanup_old_violations(retention_days)
    if cleaned:
        logger.info("Cleaned up %d old violations (retention: %d days)", cleaned, retention_days)
    _last_cleanup = datetime.utcnow()
```

---

## 22. Auto-refresh на Pending вкладке [6.2]

### Что делаю

**Файл `web/frontend/src/pages/Violations.tsx`:**

Добавляю `refetchInterval` в React Query для pending вкладки:
```tsx
const { data: violations, isLoading } = useQuery({
    queryKey: ['violations', ...filters],
    queryFn: () => fetchViolations(filters),
    refetchInterval: tab === 'pending' ? 30000 : false,  // 30 сек на Pending
})
```

---

# Итого по файлам

| Файл | Изменения |
|------|-----------|
| `shared/database.py` | Расширить `get_violations_for_period()`, добавить `get_violation_by_id()`, `count_violations_for_period()`, `get_user_last_violation_notification()`, `mark_violation_notified()`, `cleanup_old_violations()`. SQL INTERVAL параметризация (6 мест). |
| `shared/violation_detector.py` | DeviceAnalyzer: +device_count (сигнатура + скоринг). Unknown OS fix. Timezone fix. Network switch условие. ProfileAnalyzer: новые аккаунты, typical hours. HWID градуированный. GeoIP warning. Единый lookup + кэш. |
| `web/backend/api/v2/violations.py` | SQL-фильтрация вместо Python. Прямой запрос по ID. CSV export эндпоинт. |
| `web/backend/api/v2/collector.py` | Configurable cooldown. GeoIP из кэша. Retention cleanup. |
| `web/backend/core/violation_notifier.py` | Persistent throttle (DB вместо memory). Configurable cooldown. |
| `web/frontend/src/pages/Violations.tsx` | Array.isArray() guards (7 мест). Advanced filters UI. Server-side export. Auto-refresh. |
| `web/frontend/src/types/violations.ts` | Новый файл — общие TypeScript типы. |

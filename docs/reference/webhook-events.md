# Каталог событий webhook

Каждое событие приходит в одинаковой оболочке:

```json
{
  "event": "<имя события>",
  "data": { }
}
```

Ниже описано содержимое `data`. Со временем поля добавляются — принимающая сторона должна **игнорировать незнакомые**, тогда обновления ничего не сломают.

## Пользователи

### `user.created`

Создан пользователь — из интерфейса или через API.

```json
{
  "uuid": "e4f...",
  "username": "alice",
  "email": "alice@example.com",
  "telegram_id": 123456789,
  "expire_at": "2026-06-01T00:00:00+00:00",
  "created_by": "admin"
}
```

### `user.updated`

Изменены поля пользователя.

```json
{
  "uuid": "e4f...",
  "username": "alice",
  "changed_fields": ["expire_at", "traffic_limit_bytes"],
  "updated_by": "admin"
}
```

В `changed_fields` перечислено, что именно тронули. Новые значения при необходимости запрашиваются через API.

### `user.deleted`

Приходит и на одиночное, и на массовое удаление — по событию на пользователя, у массового стоит `"bulk": true`.

```json
{
  "uuid": "e4f...",
  "deleted_by": "admin",
  "bulk": false
}
```

### `user.blocked`

Пользователь отключён анти-абузом или вручную по нарушению. Обычная правка статуса сюда не попадает — это `user.updated`.

```json
{
  "uuid": "e4f...",
  "username": "alice",
  "reason": "violation",
  "details": "hard_block recommended (score=87.5)",
  "violation_id": 9123,
  "blocked_by": "auto"
}
```

| Поле | Значения |
|------|----------|
| `reason` | `violation`, `torrent`, `blacklist`, `traffic_rate`, `automation`, `manual` |
| `violation_id` | есть, когда блокировка связана с записью нарушения |
| `blocked_by` | `auto`, `automation` или имя администратора |

### `user.expired`

У пользователя закончилась подписка. Приходит один раз — на проверке, которая первой увидела срок в прошлом; после рестарта панели давно истёкшие не присылаются.

```json
{
  "user_uuid": "e4f...",
  "uuid": "e4f...",
  "username": "alice",
  "expire_at": "2026-09-24T00:00:00+00:00",
  "tag": "PREMIUM",
  "squads": "Default, Europe"
}
```

`squads` — имена внутренних сквадов через запятую.

### `user.traffic_exceeded`

Пользователь израсходовал лимит трафика. Приходит один раз при переходе через 100 %; повторно — только если трафик сбросят или лимит поднимут, а потом его снова исчерпают.

```json
{
  "user_uuid": "e4f...",
  "uuid": "e4f...",
  "username": "alice",
  "traffic_limit_bytes": 107374182400,
  "used_traffic_bytes": 107911053312,
  "percent": 100.5,
  "traffic_gb": 100.5,
  "days_left": 12.4,
  "tag": "PREMIUM",
  "squads": "Default,Europe"
}
```

`days_left` — дней до конца подписки, `null` у бессрочной.

## Ноды

### `node.online`

Нода вернулась на связь. Смена состояния замечается опросом, гранулярность около двух минут.

```json
{
  "uuid": "...",
  "name": "eu-west-1",
  "downtime_minutes": 7.5
}
```

### `node.offline`

Нода пропала со связи.

```json
{
  "uuid": "...",
  "name": "eu-west-1"
}
```

Событие приходит один раз на переход, а не на каждый опрос, пока нода лежит.

### `node.shaper_penalty`

[Шейпер ноды](/guide/anti-abuse#шеипер-ноды) оштрафовал адрес клиента: за окно тот прокачал больше порога и до `until` получает штрафную скорость.

```json
{
  "node_uuid": "a1b...",
  "node_name": "eu-west-1",
  "ip": "203.0.113.10",
  "started_at": "2026-09-24 12:00:00+00:00",
  "until": "2026-09-24 12:10:00+00:00",
  "bytes": 1073741824,
  "users": [{"uuid": "e4f...", "username": "alice"}]
}
```

`bytes` — сколько адрес прокачал за окно штрафа. `users` — юзеры, подключавшиеся с этого адреса к ноде в это время; бывает пустым.

## Нарушения

### `violation.created`

Записано новое нарушение.

```json
{
  "violation_id": 9123,
  "user_uuid": "...",
  "username": "alice",
  "score": 87.5,
  "confidence": 0.9,
  "recommended_action": "hard_block",
  "reasons": ["4 одновременных подключения из 3 стран"],
  "ip_addresses": ["1.2.3.4", "5.6.7.8"],
  "source": "detector"
}
```

`source` бывает `detector` (общий конвейер анализаторов), `torrent` или `traffic_rate`. Полная раскладка по анализаторам доступна через [`GET /api/v3/violations/{id}`](/reference/api-endpoints#нарушения).

## Автоматизации

### `automation.triggered`

Правило сработало и выполнило действие.

```json
{
  "rule_id": 17,
  "rule_name": "Блокировать за торренты",
  "event": "torrent.detected",
  "action": "block_user",
  "target_type": "user",
  "target_id": "e4f...",
  "result": "success",
  "details": {"action": "block_user", "user_uuid": "e4f..."}
}
```

## Бэкапы

### `backup.created`

Бэкап успешно создан — по расписанию или вручную.

```json
{
  "filename": "db_backup_20260607_115500.sql.gz",
  "size_bytes": 4837293,
  "backup_type": "database"
}
```

`backup_type` — `database` (дамп) или `config` (выгрузка настроек).

### `backup.failed`

Бэкап не удался — по расписанию или вручную.

```json
{
  "backup_type": "database",
  "error": "pg_dump: error: connection to server failed"
}
```

`error` обрезается до 500 символов.

## Отчёты

### `report.generated`

Сформирован и сохранён отчёт о нарушениях — по расписанию или из интерфейса.

```json
{
  "report_id": 57,
  "report_type": "daily",
  "period_start": "2026-09-23 00:00:00+03:00",
  "period_end": "2026-09-24 00:00:00+03:00",
  "total_violations": 42,
  "critical_count": 3,
  "unique_users": 17,
  "trend_percent": -12.5
}
```

`report_type` — `daily`, `weekly` или `monthly`.

## Проверка

### `webhook.test`

Уходит только по кнопке **Отправить тест**. В историю доставок не пишется и в очередь повторов не попадает.

```json
{
  "message": "This is a test payload from Remnawave Admin.",
  "webhook_id": 42
}
```

Годится, чтобы проверить связность, заголовки и разбор подписи.

## Что стоит знать

**Никакой пакетной отправки.** Одно логическое событие — один HTTP-запрос на каждую подходящую подписку, отправляемый прямо из того места кода, которое меняет состояние.

**Порядок не гарантирован.** Если он важен, опирайтесь на временные метки самих объектов, а не на очерёдность доставок.

**Уникального идентификатора события пока нет.** Приёмникам, которым нужна защита от дублей, стоит строить ключ из идентификатора объекта и полей содержимого.

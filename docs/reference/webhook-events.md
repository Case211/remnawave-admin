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

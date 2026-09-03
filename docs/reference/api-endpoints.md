# Эндпоинты API v3

Все пути начинаются с `/api/v3`, каждый запрос требует заголовок `X-API-Key` и область доступа, указанную рядом с маршрутом. Основы авторизации — в разделе [Внешний API](/reference/api).

## Пользователи

### `GET /users` — список

Область: `users:read`.

| Параметр | Тип | По умолчанию | Что делает |
|----------|-----|--------------|------------|
| `limit` | int, 1..500 | `100` | размер страницы |
| `offset` | int | `0` | смещение |
| `status` | string | — | фильтр по статусу: `active`, `disabled` и т. д. |
| `search` | string | — | поиск по части username, email или uuid |

```json
[
  {
    "uuid": "a2e...",
    "username": "alice",
    "status": "active",
    "traffic_limit_bytes": 107374182400,
    "used_traffic_bytes": 52013875200,
    "expire_at": "2026-06-01T00:00:00Z",
    "online": true
  }
]
```

### `GET /users/{uuid}` — карточка

Область: `users:read`. Вернёт объект пользователя или `404`.

### `POST /users` — создать

Область: `users:write`.

```json
{
  "username": "alice",
  "expire_at": "2026-06-01T00:00:00Z",
  "traffic_limit_bytes": 107374182400,
  "traffic_limit_strategy": "MONTH",
  "hwid_device_limit": 3,
  "description": "Создан из CI",
  "telegram_id": 123456789,
  "email": "alice@example.com",
  "tag": "vip",
  "status": "active"
}
```

Ответ — `201` и `{"success": true, "uuid": "..."}`.

### Остальные действия

| Эндпоинт | Метод | Область | Что делает |
|----------|-------|---------|------------|
| `/users/{uuid}/enable` | POST | `users:write` | включить |
| `/users/{uuid}/disable` | POST | `users:write` | отключить, можно передать `{"reason": "..."}` |
| `/users/{uuid}/reset-traffic` | POST | `users:write` | обнулить счётчики трафика |
| `/users/{uuid}` | DELETE | `users:delete` | удалить |

## Массовые операции

Все принимают `{"uuids": ["...", "..."]}`, до 500 записей за раз.

```json
{
  "success": 498,
  "failed": 2,
  "errors": [
    {"uuid": "...", "error": "not found"}
  ]
}
```

| Эндпоинт | Область |
|----------|---------|
| `POST /users/bulk/enable` | `bulk:write` |
| `POST /users/bulk/disable` | `bulk:write` |
| `POST /users/bulk/delete` | `bulk:write` |
| `POST /users/bulk/reset-traffic` | `bulk:write` |

У массовых операций свой лимит запросов — `API_V3_RATE_BULK_PER_MIN`, по умолчанию 10 в минуту.

## Ноды

| Эндпоинт | Метод | Область | Что делает |
|----------|-------|---------|------------|
| `/nodes` | GET | `nodes:read` | список |
| `/nodes/{uuid}` | GET | `nodes:read` | карточка |
| `/nodes/{uuid}/enable` | POST | `nodes:write` | включить |
| `/nodes/{uuid}/disable` | POST | `nodes:write` | отключить |
| `/nodes/{uuid}/restart` | POST | `nodes:write` | перезапустить |
| `/nodes/sync` | POST | `nodes:write` | синхронизировать список нод с панелью |
| `/nodes/{uuid}/agent-token/generate` | POST | `nodes:token` | сгенерировать (перевыпустить) токен агента |
| `/nodes/{uuid}/agent-token/revoke` | POST | `nodes:token` | отозвать токен агента |

```json
{
  "uuid": "...",
  "name": "eu-west-1",
  "address": "1.2.3.4",
  "port": 62050,
  "is_disabled": false,
  "is_connected": true,
  "users_online": 42
}
```

## Хосты

| Эндпоинт | Метод | Область |
|----------|-------|---------|
| `/hosts` | GET | `hosts:read` |
| `/hosts/{uuid}` | GET | `hosts:read` |

Поля повторяют объекты хостов панели Remnawave: uuid, remark, address, port, sni, host, is_disabled, alpn, fingerprint.

## Нарушения

### `GET /violations` — список

Область: `violations:read`. Свежие сверху.

| Параметр | Тип | По умолчанию | Что делает |
|----------|-----|--------------|------------|
| `limit` | int, 1..500 | `100` | размер страницы |
| `offset` | int | `0` | смещение |
| `user_uuid` | string | — | по конкретному пользователю |
| `min_score` | float | — | нижняя граница скоринга |
| `recommended_action` | string | — | `hard_block`, `temp_block`, `monitor` |
| `resolved` | bool | — | `true` — решение принято, `false` — открытые |
| `date_from`, `date_to` | ISO datetime | — | границы по времени обнаружения |

```json
[
  {
    "id": 9123,
    "user_uuid": "...",
    "username": "alice",
    "score": 87.5,
    "confidence": 0.9,
    "recommended_action": "hard_block",
    "action_taken": null,
    "reasons": ["4 одновременных подключения из 3 стран"],
    "ip_addresses": ["1.2.3.4"],
    "countries": ["RU", "NL"],
    "detected_at": "2026-06-07T11:50:00+00:00"
  }
]
```

### `GET /violations/{id}` — карточка

Область: `violations:read`. Отдаёт полную раскладку по анализаторам (`temporal_score`, `geo_score`, `asn_score`, `profile_score`, `device_score`, `hwid_score`, `user_agent_score`), собранные свидетельства (`cities`, `asn_types`, `os_list`, `client_list`), флаги (`impossible_travel`, `is_mobile`, `is_datacenter`, `is_vpn`) и разбор (`action_taken`, `action_taken_at`, `admin_comment`).

## Статистика

`GET /stats`, область `stats:read`:

```json
{
  "users_total": 3450,
  "users_active": 2980,
  "users_disabled": 370,
  "users_online": 512,
  "nodes_total": 12,
  "nodes_online": 11,
  "traffic_total_bytes": 48934567890123
}
```

## Общие правила

- Время всегда в ISO 8601 и в UTC
- Трафик — в байтах, без пересчёта в мегабайты
- `uuid` — идентификаторы панели Remnawave, не путайте с внутренними id
- Неизвестные поля на входе игнорируются, на выходе не появляются: модели строгие

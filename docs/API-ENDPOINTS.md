# API v3 Endpoint Reference

All endpoints are under the base path `/api/v3` and require `X-API-Key` header plus the scope
shown next to each route. See [API.md](./API.md) for authentication basics.

---

## Users

### `GET /users` - list users

Required scope: `users:read`.

Query parameters:

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int (1..500) | 100 | Page size |
| `offset` | int | 0 | Page offset |
| `status` | string | - | Filter by status (`active`, `disabled`, ...) |
| `search` | string | - | Partial match on username / email / uuid |

Response: `List[UserPublic]`.

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

### `GET /users/{uuid}` - user detail

Required scope: `users:read`.
Returns `UserPublic` or `404`.

### `POST /users` - create a user

Required scope: `users:write`.

Body:

```json
{
  "username": "alice",
  "expire_at": "2026-06-01T00:00:00Z",
  "traffic_limit_bytes": 107374182400,
  "traffic_limit_strategy": "MONTH",
  "hwid_device_limit": 3,
  "description": "Created via CI",
  "telegram_id": 123456789,
  "email": "alice@example.com",
  "tag": "vip",
  "status": "active"
}
```

Returns `201` with `{"success": true, "uuid": "..."}`.

### `POST /users/{uuid}/enable` - enable

Required scope: `users:write`.

### `POST /users/{uuid}/disable` - disable

Required scope: `users:write`. Accepts optional `{"reason": "..."}` body.

### `POST /users/{uuid}/reset-traffic` - reset traffic counters

Required scope: `users:write`.

### `DELETE /users/{uuid}` - delete user

Required scope: `users:delete`.

---

## Bulk operations on users

All bulk endpoints accept `{"uuids": ["...", "..."]}` with up to 500 entries. Response:

```json
{
  "success": 498,
  "failed": 2,
  "errors": [
    {"uuid": "...", "error": "not found"}
  ]
}
```

| Endpoint | Required scope |
|---|---|
| `POST /users/bulk/enable` | `bulk:write` |
| `POST /users/bulk/disable` | `bulk:write` |
| `POST /users/bulk/delete` | `bulk:write` |
| `POST /users/bulk/reset-traffic` | `bulk:write` |

Bulk endpoints use the dedicated bulk rate limit bucket (`API_V3_RATE_BULK_PER_MIN`, default 10/min).

---

## Nodes

| Endpoint | Method | Scope | Description |
|---|---|---|---|
| `/nodes` | GET | `nodes:read` | List nodes |
| `/nodes/{uuid}` | GET | `nodes:read` | Node detail |
| `/nodes/{uuid}/enable` | POST | `nodes:write` | Enable node |
| `/nodes/{uuid}/disable` | POST | `nodes:write` | Disable node |
| `/nodes/{uuid}/restart` | POST | `nodes:write` | Restart node |

`NodePublic` schema:

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

---

## Hosts

| Endpoint | Method | Scope |
|---|---|---|
| `/hosts` | GET | `hosts:read` |
| `/hosts/{uuid}` | GET | `hosts:read` |

`HostPublic` mirrors `Remnawave Panel` host objects (uuid, remark, address, port, sni, host,
is_disabled, alpn, fingerprint).

---

## Violations

### `GET /violations` - list anti-abuse violations

Required scope: `violations:read`. Newest first.

Query parameters:

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int (1..500) | 100 | Page size |
| `offset` | int | 0 | Page offset |
| `user_uuid` | string | - | Filter by user UUID |
| `min_score` | float | - | Minimum violation score |
| `recommended_action` | string | - | e.g. `hard_block`, `temp_block`, `monitor` |
| `resolved` | bool | - | `true` = action taken, `false` = open |
| `date_from` / `date_to` | ISO datetime | - | `detected_at` bounds |

Response: `List[ViolationPublic]`.

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
    "reasons": ["4 simultaneous connections from 3 countries"],
    "ip_addresses": ["1.2.3.4"],
    "countries": ["RU", "NL"],
    "detected_at": "2026-06-07T11:50:00+00:00"
  }
]
```

### `GET /violations/{id}` - violation detail

Required scope: `violations:read`.
Returns the full analyzer breakdown (`temporal_score`, `geo_score`, `asn_score`,
`profile_score`, `device_score`, `hwid_score`, `user_agent_score`), evidence lists
(`cities`, `asn_types`, `os_list`, `client_list`), flags (`impossible_travel`,
`is_mobile`, `is_datacenter`, `is_vpn`) and resolution fields (`action_taken`,
`action_taken_at`, `admin_comment`). `404` if not found.

---

## Stats

`GET /stats` - global counters. Scope: `stats:read`.

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

---

## Notes

- All timestamps are ISO 8601 UTC.
- Traffic sizes are raw bytes (not MB/GB).
- `uuid` fields are Remnawave Panel UUIDs; do not confuse with admin-internal IDs.
- Unknown fields are ignored on input but not returned on output (strict models).

# API v3 Endpoint Reference

All endpoints are under the base path `/api/v3` and require `X-API-Key` header plus the scope
shown next to each route. See [Public API](/en/reference/api) for authentication basics.

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
    "online": true,
    "short_uuid": "AbCdEf123",
    "subscription_url": "https://sub.example.com/AbCdEf123"
  }
]
```

### `GET /users/{uuid}` - user detail

Required scope: `users:read`.
Returns `UserPublic` or `404`.

`short_uuid` and `subscription_url` are the panel's subscription id and link. The link comes from the last sync with the panel and is `null` until the user has been synced. It grants access to the configs — don't publish it.

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
  "status": "active",
  "external_squad_uuid": "3f2c...",
  "active_internal_squads": ["a1b2...", "c3d4..."]
}
```

`external_squad_uuid` and `active_internal_squads` are optional; take squad UUIDs from
`GET /squads/external` and `GET /squads/internal` (below).

Returns `201`:

```json
{
  "success": true,
  "message": "User alice created",
  "uuid": "a2e...",
  "short_uuid": "AbCdEf123",
  "subscription_url": "https://sub.example.com/AbCdEf123"
}
```

The user is written to the admin database right away, so `GET /users/{uuid}` works without waiting for a sync. If the local database is unavailable, `uuid` may be `null` — the user shows up after the next sync.

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
| `/nodes/sync` | POST | `nodes:write` | Sync the node list from the panel |
| `/nodes/{uuid}/agent-token/generate` | POST | `nodes:token` | Generate (rotate) the node's agent token |
| `/nodes/{uuid}/agent-token/revoke` | POST | `nodes:token` | Revoke the node's agent token |

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

## Squads

Required scope: `users:read`. Lists come live from the Remnawave panel — use them to pick UUIDs
for `external_squad_uuid` and `active_internal_squads` when creating a user.

| Endpoint | Method | Returns |
|----------|--------|---------|
| `/squads/internal` | GET | internal squads: `uuid`, `name`, `members_count`, `inbounds` (`uuid`, `tag`) |
| `/squads/external` | GET | external squads: `uuid`, `name`, `members_count` |

```json
[
  {
    "uuid": "3f2c...",
    "name": "Standard",
    "members_count": 128,
    "inbounds": [{"uuid": "a1b2...", "tag": "VLESS-Reality"}]
  }
]
```

Panel unavailable — `503`.

## Violations

### `GET /violations` - list anti-abuse violations

Required scope: `violations:read`. Newest first.

Query parameters:

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | int (1..500) | 100 | Page size |
| `offset` | int | 0 | Page offset |
| `user_uuid` | string | - | Filter by user UUID |
| `telegram_id` | int | - | Filter by the customer's Telegram ID |
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
    "detected_at": "2026-06-07T11:50:00+00:00",
    "notified_at": null
  }
]
```

`notified_at` is when the customer was sent a [warning](/en/guide/anti-abuse#client-warnings)
about this violation; `null` if no warning was sent.

### `GET /violations/summary` - customer verdict

Required scope: `violations:read`. Answers a single question: can this person be trusted. Meant
for integrations that make a decision — whether to grant a trial, a promo code, a renewal — and
have no reason to parse the violation list.

| Param | Type | Default | Description |
|---|---|---|---|
| `telegram_id` | int | - | Customer by Telegram ID |
| `user_uuid` | string | - | Customer by panel UUID |
| `window_days` | int (1..365) | 30 | How far back to count |

Either `telegram_id` **or** `user_uuid` is required, otherwise `422`.

```json
{
  "user_uuid": "...",
  "telegram_id": 366945364,
  "window_days": 30,
  "level": "warned",
  "violations": 2,
  "max_score": 74.0,
  "last_detected_at": "2026-09-20T10:00:00+00:00",
  "last_action": null,
  "whitelisted": false,
  "notice": {
    "violation_id": 9123,
    "kind": "device",
    "subject": "Your subscription is used on several devices",
    "body": "We noticed…",
    "sent_at": "2026-09-20T10:05:00+00:00"
  }
}
```

`level` has three values: `clean` (no violations in the window, or the person is whitelisted),
`warned` (there are violations, but no action was taken), `limited` (a block or a speed limit
was applied for the latest violation).

Annulled violations are not counted — the detector was wrong, and the person has nothing to do
with it. The whitelist overrides everything: it is set by hand, already knowing about the
violations, and an integration should not punish someone the operator cleared.

`notice` is the latest warning the customer actually received: subject and text exactly as they
were sent, even if the template was edited later; `null` if no warning was sent. `kind` is the
violation type whose template was used: `default`, `temporal`, `geo`, `asn`, `profile`,
`device`, `hwid`, `user_agent`, `torrent`, `traffic_rate`.

### `GET /violations/{id}` - violation detail

Required scope: `violations:read`.
Returns the full analyzer breakdown (`temporal_score`, `geo_score`, `asn_score`,
`profile_score`, `device_score`, `hwid_score`, `user_agent_score`), evidence lists
(`cities`, `asn_types`, `os_list`, `client_list`), flags (`impossible_travel`,
`is_mobile`, `is_datacenter`, `is_vpn`) and resolution fields (`action_taken`,
`action_taken_at`, `admin_comment`). `404` if not found.

## External support contact

### `POST /support-events`

Required scope: `enforcement:support`. A bot or helpdesk reports that the customer contacted support. If a delayed violation step is waiting with the support check enabled, the step is skipped with the `support_contacted` reason when it becomes due.

The `Idempotency-Key` header is required and must identify the event within the API key. Retrying the same value safely returns `202` with `duplicate: true`.

```json
{
  "source": "telegram-support",
  "kind": "customer_message",
  "occurred_at": "2026-09-26T10:30:00Z",
  "user": { "telegram_id": 123456789 },
  "ticket_id": "ticket-42",
  "metadata": { "queue": "billing" }
}
```

`user` must contain at least one of `user_uuid`, `telegram_id`, `email`, or `username`. When several are supplied, all of them must identify the same user. Responses: `404` when no user matches, `409` when the identity is ambiguous, and `422` for invalid input or an event time more than five minutes in the future.

For a standalone Telegram bot, `telegram_id` is normally sufficient. The event is stored by Admin; the integration needs no access to the database or Bedolaga tickets.

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

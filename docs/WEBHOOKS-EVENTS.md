# Webhook Event Catalog

All events share the envelope:

```json
{
  "event": "<event name>",
  "data": { ... }
}
```

This document describes the `data` payload for each event. Payloads may grow over time;
receivers should **ignore unknown fields** (backward-compatible evolution).

---

## `user.created`

Fires when a new user is created via the admin UI or API.

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

## `user.updated`

Fires when user fields are changed via the admin UI or API.

```json
{
  "uuid": "e4f...",
  "username": "alice",
  "changed_fields": ["expire_at", "traffic_limit_bytes"],
  "updated_by": "admin"
}
```

`changed_fields` lists which fields were touched (sorted). Fetch the user via API
if you need the new values.

## `user.deleted`

Fires for single and bulk deletions (one event per user; bulk deletions carry
`"bulk": true`).

```json
{
  "uuid": "e4f...",
  "deleted_by": "admin",
  "bulk": false
}
```

## `user.blocked`

Fires whenever a user is disabled by the anti-abuse machinery or manually from a
violation. **Not** fired for plain status edits (those are `user.updated`).

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

| Field | Meaning |
|---|---|
| `reason` | `violation` (detector hard_block), `torrent`, `blacklist`, `traffic_rate`, `automation`, `manual` |
| `violation_id` | Present when the block is tied to a stored violation |
| `blocked_by` | `auto`, `automation`, or the admin username for manual blocks |

---

## `node.online`

A node transitioned offline → online (detected by the panel's polling loop,
~120s granularity).

```json
{
  "uuid": "...",
  "name": "eu-west-1",
  "downtime_minutes": 7.5
}
```

## `node.offline`

A node transitioned online → offline.

```json
{
  "uuid": "...",
  "name": "eu-west-1"
}
```

The event fires once per transition, not on every poll while the node stays down.

---

## `violation.created`

A new anti-abuse violation has been stored.

```json
{
  "violation_id": 9123,
  "user_uuid": "...",
  "username": "alice",
  "score": 87.5,
  "confidence": 0.9,
  "recommended_action": "hard_block",
  "reasons": ["4 simultaneous connections from 3 countries"],
  "ip_addresses": ["1.2.3.4", "5.6.7.8"],
  "source": "detector"
}
```

`source` is `detector` (multi-factor pipeline), `torrent`, or `traffic_rate`.
Full analyzer breakdown is available via `GET /api/v3/violations/{id}`
(scope `violations:read`, see [API-ENDPOINTS.md](./API-ENDPOINTS.md)).

---

## `automation.triggered`

An automation rule fired and executed its action.

```json
{
  "rule_id": 17,
  "rule_name": "Block on torrent",
  "event": "torrent.detected",
  "action": "block_user",
  "target_type": "user",
  "target_id": "e4f...",
  "result": "success",
  "details": {"action": "block_user", "user_uuid": "e4f...", "reason": "Blocked by automation"}
}
```

---

## `backup.created`

A scheduled or manual backup completed successfully.

```json
{
  "filename": "db_backup_20260607_115500.sql.gz",
  "size_bytes": 4837293,
  "backup_type": "database"
}
```

`backup_type` is `database` (pg_dump) or `config` (settings export).

---

## `webhook.test`

Sent only when an admin clicks **Send test delivery** in the UI. This event is **not**
persisted to `webhook_deliveries` (tests are ephemeral) and never participates in the
retry queue.

```json
{
  "message": "This is a test payload from Remnawave Admin.",
  "webhook_id": 42
}
```

Use it in dev to verify connectivity, headers, and signature verification.

---

## Scheduled vs real-time

All events above are fired in-band from the code path that mutates the underlying state.
There is no batching - one logical event = one HTTP POST per matching subscription.

## Ordering

Deliveries are not strictly ordered. If order matters for your integration, use the
timestamps recorded on the underlying resources rather than delivery order.

## Idempotency

Events currently do not carry a globally unique `event_id`. Receivers that need dedup should
key off (resource id + payload fields). An `event_id` field is planned for a future release.

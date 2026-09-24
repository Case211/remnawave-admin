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

## `user.expired`

A user's subscription ended. Fires once, on the check that first sees the expiry in the past;
after a panel restart, long-expired users are not sent.

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

`squads` holds internal squad names separated by commas.

---

## `user.traffic_exceeded`

A user used up the traffic limit. Fires once when crossing 100%; again only if the traffic is
reset or the limit raised and then used up once more.

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

`days_left` is the number of days until the subscription ends, `null` for an unlimited one.

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

## `node.shaper_penalty`

The [node shaper](/en/guide/anti-abuse#node-shaper) penalized a client address: it pulled more
than the threshold within the window and gets the penalty speed until `until`.

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

`bytes` is how much the address pulled within the penalty window. `users` are the users who
connected to the node from this address at that time; the list can be empty.

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
(scope `violations:read`, see [Endpoints](/en/reference/api-endpoints)).

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

## `backup.failed`

A scheduled or manual backup failed.

```json
{
  "backup_type": "database",
  "error": "pg_dump: error: connection to server failed"
}
```

`error` is truncated to 500 characters.

---

## `report.generated`

A violations report was built and saved — on schedule or from the UI.

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

`report_type` is `daily`, `weekly` or `monthly`.

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

# Webhooks

Remnawave Admin can push events to any HTTP(S) endpoint. Each webhook subscription picks a set
of events; matching events are delivered as signed JSON POSTs.

- **Event catalog:** [Event catalogue](/en/reference/webhook-events)
- **Signature verification (v1 and v2):** [Signature verification](/en/reference/webhook-signatures)

---

## Concepts

- **Subscription** = URL + event list + signing config. One admin can have many subscriptions.
- **Event** = `user.created`, `node.offline`, etc. See the full list in WEBHOOKS-EVENTS.md.
- **Delivery** = a single HTTP attempt. Persisted in the **Delivery history** panel.
- **Retry queue** = failed deliveries automatically re-tried 2 more times with exponential
  backoff. After that, a manual re-dispatch is required.

---

## Creating a subscription

1. **API & Webhooks -> Webhooks** -> **Create webhook**.
2. Fill in:
   - **Name** - label (e.g. `slack-ops-channel`).
   - **URL** - must start with `http://` or `https://`. Private / loopback addresses are
     rejected by default (see SSRF protection below).
   - **Secret** (optional but strongly recommended) - any string; used as HMAC key.
   - **Signature version** - `v2` by default (timestamped, replay-protected). `v1` is legacy.
   - **Events** - pick one or more.
   - **Description** (optional).

The subscription is active immediately. Send a synthetic POST with the **Send test delivery**
button to verify the endpoint is reachable.

---

## Delivery format

`POST <your URL>` with:

```
Content-Type: application/json
X-Webhook-Event: <event name>
X-Webhook-Signature: sha256=<hex digest>
X-Webhook-Timestamp: <unix seconds>         # v2 only
X-Webhook-Signature-Version: v2              # v2 only
```

Body:

```json
{
  "event": "user.created",
  "data": {
    "uuid": "...",
    "username": "alice",
    "...": "..."
  }
}
```

See per-event `data` shapes in [Event catalogue](/en/reference/webhook-events).

---

## Signature verification

Webhooks sign the request body with your secret using HMAC-SHA256. There are two versions:

- **v1 (legacy):** `HMAC(secret, body)`.
- **v2 (recommended):** `HMAC(secret, f"{timestamp}.{body}")`. The timestamp is sent as
  `X-Webhook-Timestamp`. Receivers should reject requests whose timestamp differs from local
  clock by more than 5 minutes to prevent replay attacks.

Full examples for Python, Node, Go and PHP are in
[Signature verification](/en/reference/webhook-signatures).

---

## Retry policy

- First attempt is synchronous with the originating request (10s timeout).
- On failure (network error, 4xx/5xx) the delivery is queued for retry.
- Retries: up to 2 more attempts with 1-minute, 5-minute, 25-minute backoff.
- All attempts are logged to the **Delivery history** panel.

If all retries fail, the webhook's `consecutive_failures` counter increments.

### Auto-disable

Once `consecutive_failures` reaches 50 (configurable via `WEBHOOK_AUTO_DISABLE_AFTER`),
the webhook is automatically disabled. The UI shows an **Auto-disabled** badge with the reason.
Toggling the switch back to Active clears the counter and re-enables it.

### Manual re-dispatch

The UI currently does not expose a "resend" button per delivery; it is planned for a later
release. Re-enabling the webhook + triggering the original event again is the current workaround.

---

## SSRF protection

Webhook URLs are validated for safety at create / update / test / dispatch time:

- Must use `http` or `https` scheme.
- Hostname is resolved and checked against RFC-1918 private ranges, `127.0.0.0/8`,
  `169.254.0.0/16`, `::1`, `fc00::/7`, `fe80::/10`.
- A URL that resolves to any of the above is rejected with `400`.

Override for development only (NOT recommended in production):

```bash
export WEBHOOK_ALLOW_PRIVATE_URL=1
```

---

## Delivery history

Open the clock icon next to a webhook to see the last 200 deliveries (oldest trimmed
automatically). For each attempt you get:

- HTTP status code (or `ERR` for transport errors)
- Event name
- Timestamp
- Duration (ms)
- Response body (up to 5000 chars)
- Error message (if any, up to 500 chars)

The **Send test delivery** button does **not** appear here - test deliveries are ephemeral.

---

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `WEBHOOK_TIMEOUT_SEC` | `10` | Per-attempt HTTP timeout |
| `WEBHOOK_MAX_ATTEMPTS` | `3` | Attempts including the first |
| `WEBHOOK_AUTO_DISABLE_AFTER` | `50` | Consecutive failures -> auto-disable |
| `WEBHOOK_RETRY_WORKER_INTERVAL` | `10` | Background worker tick, seconds |
| `WEBHOOK_ALLOW_PRIVATE_URL` | `0` | Set `1` to skip SSRF check |

Changes require a backend restart.

---

## Troubleshooting

- **"Auto-disabled" badge appeared.** The receiver returned errors 50 times in a row. Fix
  the endpoint, then toggle the switch back to active - the counter resets.
- **No delivery history.** The webhook has never received a matching event, or the receiver
  is unreachable at DNS/TCP layer before the request is recorded.
- **Signature does not match on my side.** See WEBHOOKS-SIGNATURES.md; the most common
  issues are (a) using a rotated secret, (b) re-serializing the body before hashing, (c)
  checking v1 signature on a v2 subscription.
- **Test delivery succeeds, real events do not.** Confirm the event is actually selected in
  the subscription and the firing code path runs (check admin_audit_log).

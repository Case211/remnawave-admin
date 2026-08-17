# Panel webhook

The Remnawave panel can report what happens inside it: a subscription renewed, a device added, a node dropped. Remnawave Admin receives those events and turns them into Telegram notifications.

Not to be confused with [outgoing webhooks](/en/reference/webhooks), where Remnawave Admin pushes its own events to external systems.

## Setup

### On the Remnawave Admin side

```ini
WEBHOOK_PORT=8080
# openssl rand -hex 64
WEBHOOK_SECRET=long_random_key
```

### On the Remnawave panel side

```ini
WEBHOOK_ENABLED=true
WEBHOOK_URL=http://bot:8080/webhook
WEBHOOK_SECRET_HEADER=the_same_key
```

`WEBHOOK_SECRET_HEADER` on the panel and `WEBHOOK_SECRET` on the bot must match: the panel signs the request body with HMAC-SHA256 and sends the signature in `X-Remnawave-Signature`, and the bot verifies it.

The hostname in `WEBHOOK_URL` is the service name from your `docker-compose.yml`. If the bot and the panel live in different networks or on different servers, put a reverse proxy in front of the bot and point the panel at it.

::: danger The classic mistake: HTTPS to an internal address
The bot webhook server speaks **HTTP**. An address like `https://bot:8080/webhook` produces `write EPROTO ... tlsv1 alert internal error` in the panel logs.

Inside a Docker network always use `http://`. If you need HTTPS from outside, terminate it on the reverse proxy and go to the bot over HTTP.
:::

## Checking

```bash
curl http://localhost:8080/webhook/health
# {"status":"ok","service":"webhook"}
```

At startup the bot logs `Webhook server will be started on port 8080`. Then change something on a test user in the panel and see whether a notification arrives.

## Which events arrive

::: details Users (`user.*`)
`created`, `modified`, `deleted`, `revoked`, `disabled`, `enabled`, `limited`, `expired`, `traffic_reset`, `first_connected`, `not_connected`, `bandwidth_usage_threshold_reached`, plus expiry warnings: `expires_in_72_hours`, `expires_in_48_hours`, `expires_in_24_hours`, `expired_24_hours_ago`.

The notification shows what changed: traffic limit, expiry date, device limit — old value and new one, subscription link, squad.
:::

::: details Devices (`user_hwid_devices.*`)
`added`, `deleted` — user, device HWID, date.
:::

::: details Nodes (`node.*`)
`created`, `modified`, `deleted`, `disabled`, `enabled`, `connection_lost`, `connection_restored`, `traffic_notify` — name, UUID, address, country, status, traffic limit.
:::

::: details Service and errors (`service.*`, `errors.*`)
`panel_started`, `login_attempt_failed`, `login_attempt_success` — with address and User-Agent. Plus `errors.bandwidth_usage_threshold_reached_max_notifications`.
:::

::: details Infrastructure billing (`crm.*`)
Node payment reminders: 7 days, 48 and 24 hours ahead, on the due date, and overdue by 24 hours, 48 hours and 7 days — node, provider, amount, next payment date.
:::

Where each notification lands is decided by [topics](/en/guide/bot#routing-by-topic).

## If nothing arrives

1. Is `WEBHOOK_ENABLED=true` on the panel?
2. Does the address in `WEBHOOK_URL` resolve from that side? Try `docker exec <panel> wget -qO- http://bot:8080/webhook/health`
3. Is port 8080 reachable between the containers — are they on the same network?
4. Do the secrets match? A mismatch is rejected by signature, and the bot logs it
5. Is the scheme `http://` rather than `https://` when going straight to the container?

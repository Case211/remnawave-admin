# Delayed enforcement

This feature adds a durable warning → grace period → recheck → action workflow. It is disabled by default and starts only after an explicit switch under **Settings → Enforcement**.

## Safe rollout

1. Keep `dry_run` mode and add test UUIDs to the pilot allowlist.
2. Use **Simulate** to inspect the matching violation and policy snapshot.
3. Switch to `deliver_only`: existing violation notice templates are delivered, while the final action is only recorded.
4. Select `enforce`, violation scope, minimum score, action, and grace period for automatic enforcement. Throttle speed and duration are configured separately. An empty pilot list means all matching users.

Each case stores a policy snapshot, so later settings changes do not alter an active deadline. The violation, user and whitelist are rechecked immediately before an action. Deadlines and state live in PostgreSQL and survive restarts.

## Support integrations

When support pausing is enabled, a customer contact moves an active case to `paused_for_support`. For any external bot or helpdesk, enable the Public API (`EXTERNAL_API_ENABLED=true`), create an API key with only `enforcement:support`, and send an idempotent event:

```http
POST /api/v3/enforcement/support-events
X-API-Key: rwa_...
Idempotency-Key: message-123
Content-Type: application/json

{
  "event": "customer_contacted",
  "user": {"uuid": "00000000-0000-0000-0000-000000000000"},
  "ticket": {
    "provider": "generic-helpdesk",
    "external_id": "ticket-123",
    "url": "https://support.example.com/tickets/123"
  }
}
```

`telegram_id`, `email`, and `username` are also accepted. A case is paused only when the identity resolves to exactly one user; message contents are not required. Reusing the same provider and idempotency key has no additional side effects.

## Operator actions

The queue exposes status, deadline, mode, and resolution. Run now, manual review, and cancel require the violation-resolution permission and are written to the audit log.

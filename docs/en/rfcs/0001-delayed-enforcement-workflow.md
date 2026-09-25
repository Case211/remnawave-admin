# RFC: warning with delayed enforcement

Status: proposal for discussion.

## Motivation

An operator can currently warn a customer, block them immediately, throttle
them, or leave the decision for manual review. High-risk detections also need a
durable workflow that can warn, wait for a configurable grace period, recheck
the case, and then apply a selected action.

An in-process delay is not sufficient: the workflow must survive backend
restarts, duplicate events, and temporary integration outages.

## Proposed state model

Store one policy-bound case per violation in
`violation_enforcement_cases`:

```text
pending_notice -> grace_period -> due -> enforced
                      |           |       |
                      |           |       +-> failed / manual_review
                      |           +-> cancelled / resolved
                      +-> paused_for_support
```

The row stores `violation_id`, `user_uuid`, state, a policy snapshot,
`deadline_at`, attempt counters, delivery result, pause/cancellation reason,
and timestamps. A unique violation/policy key makes enqueueing idempotent.

Workers claim due rows with `FOR UPDATE SKIP LOCKED`. Before enforcement they
must recheck that the violation still exists and was not annulled, the user is
not whitelisted, the action was not already applied, support has not paused the
case, and the panel user is still resolvable.

Payment history is intentionally outside this RFC. Future billing-specific
checks can be implemented as optional resolvers without coupling the workflow
core to one billing system.

## Policy settings

Settings should be declared in `shared/config_service.py` so they appear in the
existing UI:

- workflow enabled;
- eligible violation kinds and minimum score;
- grace period, default 12 hours;
- deadline action: `manual_review`, `disable`, `throttle`, or `none`;
- throttle rate and duration;
- behavior after warning delivery failure;
- retry count and interval;
- whether a support contact pauses the deadline;
- pilot mode and selected test UUIDs.

Safe defaults for existing installations are disabled workflow and
`manual_review` as the final action.

## Support contact pause

This behavior is optional. A `customer_contacted` event moves an active case to
`paused_for_support`. No automatic action runs until an operator resumes,
cancels, or resolves it manually.

Supported sources are the built-in Remnawave Admin helpdesk, Bedolaga tickets
when configured, and a generic endpoint for any support bot or helpdesk:

```http
POST /api/v3/enforcement/support-events
Authorization: Bearer <scoped-api-key>
Idempotency-Key: <provider-event-id>
Content-Type: application/json

{
  "event": "customer_contacted",
  "user": {
    "uuid": "00000000-0000-0000-0000-000000000000"
  },
  "ticket": {
    "provider": "generic-helpdesk",
    "external_id": "ticket-123",
    "url": "https://support.example.com/tickets/123"
  },
  "occurred_at": "2026-01-01T12:00:00Z"
}
```

The identity may use `uuid`, `telegram_id`, or `email`, but must resolve to one
unambiguous user. The endpoint needs a dedicated API-key scope, rate limiting,
idempotency, and audit logging. Ticket content is not required; the event and a
link are enough.

## Pilot mode

Pilot mode makes production-shaped testing possible without creating many
accounts or risking a bulk block:

- `dry_run` creates cases, deadlines, and decisions without messages or user
  changes;
- `deliver_only` sends the warning but only logs the final action;
- `selected_users` runs only for explicitly listed UUIDs;
- “Simulate” previews template, deadline, cancellation conditions, and final
  action;
- “Run step now” requires violation-resolution permission and is audited.

Pilot mode must not bypass whitelist, RBAC, or admin visibility scope.

## UI

Add a dedicated “Enforcement” tab under Violations instead of mixing these
settings into detector tuning. It contains an explicit master switch, policy
editor, durable queue, state filters, pause/resume/cancel/apply-now actions,
and the pilot/simulation tools.

## Implementation slices

1. Migration, case repository, scheduler, and state-transition unit tests.
2. Policy settings, API, and queue UI.
3. Built-in ticket adapter and generic support endpoint.
4. Pilot/simulation and restart-recovery integration tests.

Each slice should remain independently reviewable. Full compatibility with the
external Bedolaga Ban System is not required; that is useful only when
Remnawave Admin must back its entire UI, statistics, punishments, and settings.
This workflow only needs the public notification and support-event contracts.

## Acceptance criteria

- deadlines survive restart;
- duplicate events cannot apply an action twice;
- every action is preceded by a recheck;
- support contact atomically stops automatic enforcement;
- delivery failures and enforcement failures are recorded separately;
- `manual_review` never changes a Remnawave user;
- pilot mode cannot affect a user outside its allowlist;
- races between contact/deadline and manual/scheduled resolution are tested.

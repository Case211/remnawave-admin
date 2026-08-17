# What it is

Remnawave Admin sits on top of the [Remnawave](https://remna.st) panel: a web interface and a Telegram bot that take care of everything the panel does not. Own database, own data collection from nodes, own rules and notifications.

The Remnawave panel stays the source of truth for users and configuration — Remnawave Admin talks to it over the API, while everything it gathers itself (connections, violations, metrics, mail, audit trail) lives in its own PostgreSQL.

## What it is made of

| Part | What it does | Where it runs |
|------|--------------|---------------|
| **Telegram bot** | Manage users, nodes and hosts from a chat; notifications with action buttons | `bot` container |
| **Web panel** | Admin interface: analytics, violations, terminal, mail, plugins | `web-backend` and `web-frontend` |
| **Collector** | Background processing of node data, violation detection, sync with the panel | same image, collector mode |
| **Node Agent** | Reads Xray logs and host metrics on every node, executes commands | separate container on the node |

Everything except the agent comes up with a single `docker compose up -d`.

## What it can do

### Management

- Users: search, create, edit, HWID devices, bulk operations
- Nodes: enable and restart, traffic, host metrics, remote terminal and a script catalogue
- Hosts, subscription templates, snippets, panel API tokens
- Audit log: the full history of admin actions

### Anti-abuse

Seven analyzers look for subscription sharing: temporal, geographic, ASN, behaviour profile, devices, HWID and User-Agent. Thresholds are configurable, actions are automatic — from a warning to a hard block. See [Anti-abuse](/en/guide/anti-abuse).

[Torrent detection](/en/guide/torrents) is separate: the Xray routing tag plus traffic inspection through nDPI.

### Observability

- Dashboard with online, violation and collector-queue trends
- Geo map of connections, down to the city
- Analytics: top users, traffic per node, minute-level granularity for the last day
- [Prometheus metrics](/en/guide/monitoring) and five ready-made Grafana dashboards

### Communication

- Telegram notifications routed by topic, push to the mobile app, email and webhooks
- [Built-in mail server](/en/guide/mail): direct MX delivery, DKIM, inbound mail
- Android app with a home-screen widget and push

### Extensions

- [Plugin store](/en/guide/plugins) inside the panel
- [Public API](/en/reference/api) with keys and scopes
- [Outgoing webhooks](/en/reference/webhooks) with HMAC signatures

## What you need to start

A Remnawave panel with API access, a server with Docker and a Telegram bot. Everything else is optional: the node agent is only required for anti-abuse, mail and monitoring are opt-in.

Next: [server requirements](/en/guide/requirements) and [installation](/en/guide/installation).

## Licence

AGPL-3.0 with a plugin exception (§7). Versions up to and including 2.15.x remain under MIT. A commercial licence is available on request.

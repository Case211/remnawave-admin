# Access and roles

## Ways in

Both are toggled in the panel settings.

**Telegram Login Widget** — only IDs listed in `ADMINS` can get in. Requires the [domain registered in BotFather](/en/guide/web-panel#domain-in-botfather) and HTTPS.

**Login and password** — accounts from the database (the Administrators section) or the fallback pair `WEB_ADMIN_LOGIN` / `WEB_ADMIN_PASSWORD` from `.env`. TOTP two-factor and biometric login (WebAuthn) can be added on top.

The first administrator is created by the registration form on first open. If the panel is already running and nobody can get in, use the CLI:

```bash
docker exec -it <container> python3 scripts/admin_cli.py create-superadmin --username admin
```

## Roles and permissions

RBAC is granular: a permission is a pair of resource and action, such as `users.edit` or `nodes.restart`. A role is a set of permissions, an administrator gets a role.

The superadmin receives every permission automatically, including those declared by [plugins](/en/guide/plugins) — installing a plugin grants its permissions to the superadmin right away, other roles get them by hand.

## Sessions

Browsers get JWTs in **HttpOnly cookies** (`rw_access`, `rw_refresh`): JavaScript cannot read them and they never touch `localStorage`. Mutating requests additionally require the `X-CSRF-Token` header carrying the value of the `rw_csrf` cookie — double-submit protection.

API clients and the mobile app use plain `Authorization: Bearer <token>`; tokens are returned in the bodies of `/auth/login`, `/auth/telegram` and `/auth/refresh`. Bearer requests need no CSRF header.

WebSockets authenticate through a subprotocol (`Sec-WebSocket-Protocol: access-token, <jwt>`) or the same cookie. Passing a token in the query string (`?token=`) is deprecated and kept only for older clients.

Token lifetimes are set by `WEB_JWT_EXPIRE_MINUTES` (30 minutes by default) and `WEB_JWT_REFRESH_HOURS` (6 hours).

## Network restrictions

```ini
# Who may open the panel at all
WEB_ALLOWED_IPS=1.2.3.4,10.0.0.0/24

# Whose X-Forwarded-For headers to trust
WEB_TRUSTED_PROXIES=172.18.0.0/16
```

::: warning About trusted proxies
If the panel sits behind Cloudflare or another balancer and `WEB_TRUSTED_PROXIES` is empty, every request appears to come from the proxy. That breaks the allowlist, the brute-force protection and violation analysis all at once — everything sees a single address.
:::

## External keys

Integrations get their own keys with a limited set of scopes; they are not tied to admin accounts and give no access to the interface. See [Public API](/en/reference/api).

## Audit

Every admin action lands in the audit log: who, what, when, from which address. Automatic actions — an anti-abuse block, for instance — are recorded too, marked as having no human behind them.

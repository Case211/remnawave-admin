# Access and roles

## Ways in

Both are toggled in the panel settings.

**Telegram Login Widget** — only IDs listed in `ADMINS` can get in. Requires the [domain registered in BotFather](/en/guide/web-panel#domain-in-botfather) and HTTPS.

**Telegram Mini App** — when the panel is opened inside Telegram (the bot's "Open panel" button, the `/panel` command, or the BotFather Menu Button), sign-in happens automatically from the signed `initData` — no login form is shown. The same `ADMINS` list, per-account login-method policy and 2FA rules apply as for the widget. Turn it off with `auth_telegram_webapp_enabled`; if auto-login fails, the panel quietly falls back to the regular login screen.

The bot button appears once a public https address of the panel is set — the "General → Public panel URL" setting (`web_panel_public_url`) or the `APP_PUBLIC_URL` variable.

Signed `initData` is only read from the URL fragment and only inside a Telegram client, so a link with `#tgWebAppData=...` sent in a chat cannot poison an admin's tab; the parameter is stripped from the address immediately after it is read. In fullscreen mode the Telegram client draws its buttons on top of the page, so the header and sidebar inset by their height (`--tg-content-safe-area-inset-*` from the vendored `telegram-web-app.js`).

**Login and password** — accounts from the database (the Administrators section) or the fallback pair `WEB_ADMIN_LOGIN` / `WEB_ADMIN_PASSWORD` from `.env`. TOTP two-factor and biometric login (WebAuthn) can be added on top.

The first administrator is created by the registration form on first open. If the panel is already running and nobody can get in, use the CLI:

```bash
docker exec -it <container> python3 scripts/admin_cli.py create-superadmin --username admin
```

## Roles and permissions

RBAC is granular: a permission is a pair of resource and action, such as `users.edit` or `nodes.restart`. A role is a set of permissions, an administrator gets a role.

The superadmin receives every permission automatically, including those declared by [plugins](/en/guide/plugins) — installing a plugin grants its permissions to the superadmin right away, other roles get them by hand.

## Access Scopes

Access policies can be attached to a role or directly to an administrator. Role and personal rules form one union. A rule selects a node, host, squad or user by UUID or tag. User tags are resolved through the dedicated `users.tag` column; node and host tags continue to use their panel `raw_data` JSON.

The **Can view all users** checkbox (`unrestricted_user_access`) sets the base set of visible users. A policy with `resource_type="user"` only narrows that set, it never expands it:

| unrestricted_user_access | User policy present | Expected visibility |
| --- | --- | --- |
| true | no | All users, represented by None |
| true | yes | Exactly the user-policy scope |
| false | no | Only users with created_by_admin_id equal to the admin |
| false | yes | Owned users intersected with the user-policy scope |

An empty resolved scope means no visible users. Database and scope-resolution failures also produce no visible users. Superadmins and supported legacy/environment administrators retain unrestricted access.

**Intentional behavior change:** node, host and squad policies no longer determine user visibility. They scope only their own resource types. In particular, they cannot add users who connected through an allowed node or belonged to an allowed squad. Owned users remain visible immediately after creation, before their first connection.

User policies are view-only. They do not grant or restrict user edit/delete actions; the separate `users.edit` and `users.delete` permissions work as before. The API rejects user rules containing actions other than `view`.

Downgrading migration `0128` to `0127` removes user-scoped rules before restoring the old database constraint. Policies, their non-user rules and role/admin attachments remain.

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

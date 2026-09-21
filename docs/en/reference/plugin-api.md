# Plugin API

A reference of the extension points. For building and installing the package, see [writing a plugin](/en/reference/plugin-development).

A plugin may import two panel modules:

- `web.backend.core.plugin_api` — the facade: context, notifications, access to the Panel API and GeoIP;
- `web.backend.core.plugins` — the manifest dataclasses: `PluginManifest`, `PluginParts`, `NavEntry`, `ScheduledTask`, `PluginUI`.

Everything else is panel internals: they change between releases without notice. The facade grows on request rather than in advance; if something is missing, asking is easier than working around it.

The current API version is **1**. A manifest with a different `api_version` is skipped, with `plugins.api_version_mismatch` in the log.

## PluginManifest

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | `str` | The plugin identifier. It names the route prefix and, by convention, the RBAC resource. No colons. |
| `name` | `str` | Human-readable name for the **Plugins** page. |
| `version` | `str` | The version. Take it from package metadata. |
| `api_version` | `int` | `1` only. |
| `billing` | `"free" \| "subscription"` | `subscription` turns on the license gate (below). For a third-party plugin: `free`. |
| `build` | `(ctx) -> PluginParts` | Factory for the router and background tasks. Without it the plugin registers empty. |
| `rbac_resources` | `dict[str, list[str]]` | Resources and actions the plugin adds to the role system. |
| `navigation` | `list[NavEntry]` | Sidebar entries. |
| `ui` | `PluginUI \| None` | How to render the plugin's page. |

The manifest is declarative: the panel reads it before running anything of yours. So don't compute anything heavy in `manifest()` and don't touch the database there — the work belongs in `build(ctx)`.

## PluginParts and background tasks

```python
from web.backend.core.plugins import PluginParts, ScheduledTask

def _build(ctx):
    return PluginParts(
        router=build_router(ctx),
        scheduled_tasks=[
            ScheduledTask(
                name="collector",
                interval_seconds=300,
                coro=functools.partial(tick, ctx),
            ),
        ],
    )
```

`ScheduledTask.coro` is a coroutine taking no arguments; `functools.partial` is the convenient way to close over the context. The panel runs it in a forever loop: an exception on a tick is logged and the loop carries on, and the interval is at least one second. Tasks start after every plugin is registered and stop together with the panel.

Don't sleep inside a tick — the interval already does that. Take database connections through `ctx.db` so they go back to the shared pool.

## PluginContext

The panel builds the context itself and hands it to `build(ctx)`.

| Field | What it is |
| --- | --- |
| `plugin_id` | The identifier from the manifest. |
| `logger` | A `logging.Logger` named `plugin.<id>`, feeding the panel's own log. |
| `db` | The entry point into the panel's PostgreSQL. |
| `settings` | JSON storage for the plugin's settings. |
| `license` | Subscription state (only for `billing="subscription"`). |
| `cloud` | Calls to the first-party licensing server. |
| `events` | Emitting events into outgoing webhooks. |
| `telemetry` | Anonymous product counters. |

### ctx.db

```python
rows = await ctx.db.fetch("SELECT uuid FROM users WHERE status = $1", "ACTIVE")
row  = await ctx.db.fetchrow("SELECT * FROM plugin_hello_items WHERE id = $1", item_id)
n    = await ctx.db.fetchval("SELECT count(*) FROM plugin_hello_items")
await ctx.db.execute("DELETE FROM plugin_hello_items WHERE id = $1", item_id)

async with ctx.db.acquire() as conn:      # your own transaction
    async with conn.transaction():
        ...
```

This is asyncpg, with `$1, $2, …` placeholders. Raw SQL is not restricted in any way — the plugin is already inside the panel, there is nothing left to restrict. The panel's own helpers (`get_user_by_uuid`, `get_user_by_telegram_id`, `get_user_by_short_uuid`, `get_user_uuid_by_email` and the rest of `db_service`) are available directly on `ctx.db`.

::: warning Other people's tables are read-only
Read the panel's tables all you like, but write only to your own. The panel schema changes between releases, and writes from a plugin are the first thing to break.
:::

### ctx.settings

A shared `plugin_settings (plugin_id, key, value jsonb)` table, namespaced per plugin.

```python
await ctx.settings.set("threshold", {"warn": 10, "crit": 25})
cfg = await ctx.settings.get("threshold", default={})
await ctx.settings.delete("threshold")
```

The value is anything that survives `json.dumps`. This is the place for the plugin's configuration, not for its data: data belongs in your own tables, created by a migration.

### ctx.events

```python
ctx.events.emit("item_created", {"id": item_id})
```

The event goes into the shared outgoing-webhook dispatch under the name `plugin.<id>.item_created`. The operator subscribes to it like any other [panel event](/en/reference/webhook-events). The call is synchronous and waits for nothing.

### ctx.license and ctx.cloud

Both serve paid plugins from the first-party store: `license` is a snapshot of the subscription state, `cloud` makes calls to the licensing server. A third-party plugin needs neither, and neither will work for it: `cloud` talks to a server that has never heard of your plugin.

For a free plugin `ctx.license.state` returns `missing` and `usable` returns `False`. That is not a symptom of anything: the panel only consults them when `billing="subscription"`, and reports `not_required` to the frontend for `free`. Don't build logic on `ctx.license`.

The difference between `billing="free"` and `billing="subscription"`: in the second case the panel attaches a dependency to every plugin route that answers `402` while the subscription is inactive, and skips background task ticks. For a third-party plugin that means "nothing works" — so, `billing="free"`.

### ctx.telemetry

```python
ctx.telemetry.count("report_built")
```

Counters accumulate in memory and leave with the next heartbeat to the licensing server. They only mean anything for store plugins; in a third-party plugin the call is harmless but pointless.

## Routes and permissions

The router is mounted under `/api/v2/plugins/<id>`, with OpenAPI tags `plugin:<id>`.

The panel hands out the auth dependencies through the facade, so there is no need to import `web.backend.api.deps`:

```python
from web.backend.core.plugin_api import auth_deps

AdminUser, require_permission = auth_deps()

@router.put("/settings")
async def put_settings(
    payload: SettingsIn,
    _admin: AdminUser = Depends(require_permission("hello", "edit")),
):
    ...
```

The resource/action pairs declared in `rbac_resources` land in the shared role registry and show up on the [Access and roles](/en/guide/access) page like any other panel permission. The superadmin is granted them automatically at startup; other roles get them from the operator by hand.

If the panel already has a resource under that name, your actions are added to its list rather than replacing it. To avoid arguing with the panel over a name, name the resource after the plugin.

::: warning Authentication is not implied
The panel does not guard plugin routes on its own (the license gate on paid plugins aside). A route without `require_permission` is open to anyone who can reach the API. Guard every one of them.
:::

## Navigation

```python
NavEntry(
    path="/plugins/hello",
    label_i18n="Hello",
    icon="Sparkles",
    permission=("hello", "view"),
    section_i18n="nav.sections.plugins",
)
```

- `path` — the frontend route. For an external page it must be `/plugins/<id>`, with the plugin identifier's underscores replaced by dashes.
- `label_i18n` — a key in the panel's dictionary. A third-party plugin has no such key, so the string itself reaches the screen; put ready text there. It will be the same in the English and Russian locale.
- `permission` — a resource/action pair. The entry is hidden from anyone without that permission.
- `section_i18n` — the group heading in the sidebar. `nav.sections.plugins` is translated by the panel ("Extensions") and is what you get if you leave the field out.
- `icon` — a name from the list below. An unknown name gives `Sparkles`; that is not treated as an error.

Available icons (the [Lucide](https://lucide.dev) set):

`Activity`, `AlertTriangle`, `BarChart3`, `Bot`, `Bug`, `Globe`, `HardDrive`, `Heart`, `Key`, `LayoutDashboard`, `Mail`, `Search`, `Server`, `Settings`, `Shield`, `ShieldAlert`, `ShieldBan`, `ShieldCheck`, `Sparkles`, `Stethoscope`, `Terminal`, `Users`, `UsersRound`, `Wrench`, `Zap`.

The list is deliberately short: otherwise the frontend would have to bundle the whole library for the sake of one plugin.

## A page in the UI

The plugin declares in its manifest that it has a page of its own:

```python
from web.backend.core.plugins import PluginUI

PluginManifest(
    ...,
    ui=PluginUI(kind="module", path="/app"),
)
```

The frontend loads `api_prefix + path` (that is, `/api/v2/plugins/hello/app`) as a plain `<script>` and expects the script to register itself:

```js
window.rwaPluginUI['hello'] = {
  mount(el) { /* draw yourself into el */ },
  unmount() { /* clean up when leaving the page */ },
}
```

Serving that script is your own router's job:

```python
from fastapi import Response

BUNDLE = (Path(__file__).parent / "static" / "app.js").read_text(encoding="utf-8")

@router.get("/app")
async def app_bundle(
    _admin: AdminUser = Depends(require_permission("hello", "view")),
) -> Response:
    return Response(BUNDLE, media_type="application/javascript")
```

Worth knowing:

- The script is served from the same origin as the panel and passes its CSP (`script-src 'self'`). Pulling code from another domain is blocked.
- Guarding the route with a permission works fine: the web frontend keeps its session in an HttpOnly cookie, and the browser attaches it to the script load by itself.
- `kind` is `module` only, for now. An iframe kind is deliberately not offered: the panel stamps `X-Frame-Options: DENY` on every response, plugin routes included, so a framed page could never open anyway.
- The page is mounted on the generic `/plugins/:pluginId` route. Built-in pages (for plugins shipped inside the repository) take precedence over it.
- If the script fails to load or never registers itself, the operator sees a clear error rather than a blank screen.
- Available from panel version **4.5.4**.

Bundle it with whatever you like — what matters is a single self-contained file with no external fetches. Ship styles in it too; the panel's theme is readable from the document's CSS variables.

## Migrations

A plugin carries its tables on a separate Alembic branch. A second entry point points at the revisions directory:

```toml
[project.entry-points."rwa.plugin.migrations"]
hello = "rwa_plugin_hello.migrations:versions_path"

[tool.setuptools.package-data]
"rwa_plugin_hello" = ["migrations/versions/*.py"]
```

```python
# rwa_plugin_hello/migrations/__init__.py
import os

def versions_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "versions")
```

The first revision has to open a branch of its own:

```python
revision = "hello_001"
down_revision = None
branch_labels = ("plugin_hello",)
depends_on = None

def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS plugin_hello_items (
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plugin_hello_items")
```

The rules are short:

- `down_revision = None` and `branch_labels = ("plugin_<id>",)` on the first revision — otherwise your revisions collide with the panel's in one graph.
- Revision ids are globally unique: prefix them with the plugin, don't call one `0001`.
- Name tables `plugin_<id>_*` so the operator can see in the database whose they are.
- Don't forget `package-data`: without it the revision files never reach the wheel and the panel finds an empty directory.
- `CREATE TABLE IF NOT EXISTS` and `DROP TABLE IF EXISTS` are a good habit: migrations can be replayed right after a wheel is installed.

Revisions are applied together with the panel's at startup; nothing has to be invoked by hand.

## Notifications

```python
from web.backend.core.plugin_api import panel_notify

await panel_notify(
    title="Threshold exceeded",
    body="Node <b>de-1</b> has been at 120% of the norm for an hour",
    severity="warning",              # info | warning | critical
    plugin_id=ctx.plugin_id,
    link="/plugins/hello",
    group_key="hello:de-1",
)
```

The notification goes out at once to the panel UI, to Telegram (the shared chat and admins' personal channels) and to push. It returns a `bool` — delivery never raises, so it cannot take the calling code down with it.

Details: the panel adds the severity emoji itself, so keep it out of `title`; `body` is Telegram HTML, and lines indented by three spaces become a list; `group_key` mutes repeats: a notification with the same key arriving within the next few minutes never reaches anyone.

The `actions` argument builds buttons under the Telegram message from `{text, action, ref}` triples. The panel will render the markup, but the press is handled by the bot, whose handlers are listed in the panel's own code — that part is out of reach for a third-party plugin, and the press answers "unknown plugin".

## The rest of the facade

| Function | What for |
| --- | --- |
| `panel_api()` | The Remnawave Panel API client: user mutations, traffic resets, subscription revocation. |
| `panel_user_from_api(uuid)` | A user straight from the Panel API, when the local cache is not enough. |
| `normalize_user(raw)` | A Panel API response in the panel's own shape (camelCase → snake_case). |
| `geoip_service()` | The panel's GeoIP: `lookup_batch` and the `ip_metadata` cache. |
| `panel_db` | The same database entry point as `ctx.db`, for modules that were not handed the context. |

## What the panel reports about plugins

`GET /api/v2/plugins` lists the registered plugins for any authenticated admin: `id`, `name`, `version`, `license_state`, `api_prefix`, navigation and the page descriptor. That is where the frontend learns what to render.

Operations on the code itself (`/api/v2/admin/plugins/...`: wheel upload, install, remove, restart) are superadmin-only.

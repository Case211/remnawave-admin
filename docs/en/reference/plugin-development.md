# Writing a plugin

A plugin is an ordinary Python package that the panel `pip install`-s into itself and runs inside its own process. It brings its own HTTP routes, its own permissions in the shared role system, a sidebar entry, a page in the UI, database tables and background tasks.

You do not need access to the panel repository for any of this: it all rests on two entry points and one facade module — the [Plugin API](/en/reference/plugin-api).

::: danger A plugin is code inside the panel
The wheel is installed into the same process as the backend and gets live access to the database, to the Panel API and to the settings. There is no sandbox. Installing someone else's plugin is the same kind of decision as upgrading the panel itself — only from a source you trust.
:::

## A minimal plugin

```
rwa-plugin-hello/
├── pyproject.toml
└── rwa_plugin_hello/
    └── __init__.py
```

### pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "rwa-plugin-hello"
version = "0.1.0"
description = "Hello — a remnawave-admin plugin example"
requires-python = ">=3.11"
# For your own builds and tests: on the panel the wheel is installed with --no-deps
dependencies = ["fastapi>=0.110", "pydantic>=2.5"]

[project.entry-points."rwa.plugin"]
hello = "rwa_plugin_hello:manifest"

[tool.setuptools.packages.find]
where = ["."]
include = ["rwa_plugin_hello*"]
```

The entry point in the `rwa.plugin` group is the only way the panel learns about your plugin. The name of the entry point does not matter; what matters is what it points at — a callable returning a `PluginManifest`.

::: warning Distribution name
Name the package `rwa-plugin-<id>`, or start it with `rwa-plugin-<id>-`. The panel looks up a plugin's files by that prefix when uninstalling it. A package named differently installs and works fine, but the **Remove** button will not find its wheel and the operator will have to clean the directory by hand.
:::

### \_\_init\_\_.py

```python
"""Hello — a remnawave-admin plugin example (Plugin API v1)."""
from __future__ import annotations


def _own_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("rwa-plugin-hello")
    except PackageNotFoundError:   # running from source, not from a wheel
        return "0.0.0"


def _build(ctx):
    from fastapi import APIRouter, Depends

    from web.backend.core.plugin_api import auth_deps
    from web.backend.core.plugins import PluginParts

    AdminUser, require_permission = auth_deps()
    router = APIRouter()

    @router.get("/greeting")
    async def greeting(
        _admin: AdminUser = Depends(require_permission("hello", "view")),
    ) -> dict:
        who = await ctx.settings.get("who", "world")
        ctx.logger.info("hello.greeting", extra={"who": who})
        return {"hello": who}

    return PluginParts(router=router)


def manifest():
    from web.backend.core.plugins import NavEntry, PluginManifest

    return PluginManifest(
        id="hello",
        name="Hello",
        version=_own_version(),
        api_version=1,
        billing="free",
        build=_build,
        rbac_resources={"hello": ["view", "edit"]},
        navigation=[
            NavEntry(
                path="/plugins/hello",
                label_i18n="Hello",
                icon="Sparkles",
                permission=("hello", "view"),
                section_i18n="nav.sections.plugins",
            ),
        ],
    )
```

The router lands on `/api/v2/plugins/hello`, and the endpoint above on `/api/v2/plugins/hello/greeting`.

::: tip Keep panel imports inside functions
The `web.backend.*` package only exists where the panel runs. Keep those imports in function bodies: your package then builds, imports and tests on a machine without the panel — CI included.
:::

::: tip Take the version from package metadata
A version constant next to `pyproject.toml` drifts away from it sooner or later, and the operator ends up seeing a version that isn't the one running. The only source of truth is the wheel itself, via `importlib.metadata.version()`.
:::

## Building

```bash
python -m build --wheel
# or, without the extra dependency:
pip wheel . --no-deps -w dist/
```

You get `dist/rwa_plugin_hello-0.1.0-py3-none-any.whl`.

The panel accepts a file whose name parses as `<name>-<version>[-...].whl`, where the name contains only letters, digits and underscores — which is exactly how setuptools names wheels. Uploads through the UI are additionally capped at 50 MB.

::: warning Your dependencies will not come along
The wheel is installed with `--no-deps`: nothing but your own package reaches the panel. The `dependencies` section of `pyproject.toml` only works on your side — local installs and tests.

You can rely on what the panel already ships: `fastapi`, `pydantic`, `asyncpg`, `sqlalchemy`, `alembic`, `aiohttp`, `httpx`, `structlog`, `redis`, `prometheus-client`, `cryptography`, `geoip2`. For the exact list, read `requirements.txt` and `web/backend/requirements.txt` of the panel release you target.
:::

## Installing

Two paths, both ending in the same plugins directory.

**Through the UI.** **Plugins** → **Upload wheel** → pick the file. The panel stores it, installs it with pip right away and drops older versions of the same package from the directory. Superadmin only.

**As a file.** Drop the `.whl` into the `plugins` directory next to `docker-compose.yml` — inside the container that is `/app/plugins`, overridable with `RWA_PLUGINS_DIR`. The panel installs it on the next start.

::: warning A restart is required
Python does not re-read entry points on the fly, so the contract is "install, then restart". The panel says so in its response, and the restart button is on the same page.
:::

What the panel does at startup:

1. Scans the plugins directory, takes one wheel per package — the newest one — and installs those whose distribution is missing from the current environment or sits at a different version.
2. If anything was installed, replays migrations, this time seeing the new plugin's branch.
3. Reads the manifests, mounts the routers, adds the plugin's permissions to the role registry and grants them to the superadmin, starts the background tasks.

Asking `pip` instead of trusting an install marker is deliberate: the plugins directory survives container recreation, its `site-packages` does not. After a `docker compose pull` the wheel is still there and the panel installs it again, with no manual work.

The loader fails soft: a factory that raised, a mismatched `api_version` or two plugins claiming the same `id` get a log line and a skip. A broken plugin does not take the panel down.

## Developing without building

To avoid rebuilding a wheel on every change, the panel can load a plugin straight from source:

```bash
RWA_DEV_PLUGINS=rwa_plugin_hello:manifest
RWA_DEV_PLUGIN_MIGRATIONS=/src/rwa_plugin_hello/migrations/versions
```

`RWA_DEV_PLUGINS` is a comma-separated list of `module:factory`; the module has to be importable from the panel process (the easy way is mounting your sources into the container and adding the path to `PYTHONPATH`). `RWA_DEV_PLUGIN_MIGRATIONS` lists Alembic revision directories, separated by the platform path separator.

A live skeleton for checking that the loader works at all ships with the panel — `scripts/plugin_noop.py`:

```bash
RWA_DEV_PLUGINS=scripts.plugin_noop:manifest
# GET /api/v2/plugins        → the list contains id=noop
# GET /api/v2/plugins/noop/ping → {"pong": true}
```

## Removing

The **Remove** button on the plugin card: the panel removes its wheel from the directory and runs `pip uninstall`; after a restart the routes and menu entries are gone.

The plugin's tables stay. That is on purpose: removing code should not take the operator's data with it in case the plugin comes back. If your plugin wants a "forget everything about me" action, ship it as an explicit endpoint of your own.

## Checklist before publishing

- [ ] The distribution is named `rwa-plugin-<id>` and the manifest `id` matches it
- [ ] `api_version=1`
- [ ] The version comes from `importlib.metadata`, not from a constant
- [ ] `web.backend.*` imports live inside functions; the package imports without the panel
- [ ] No dependencies beyond what the panel already has
- [ ] Every route is guarded by `require_permission`, and the resource is declared in `rbac_resources`
- [ ] Tables are prefixed `plugin_<id>_`, and the first revision carries `branch_labels`
- [ ] Background tasks survive an exception and leak no connections
- [ ] State a minimum panel version if you use anything recent (plugin pages: 4.5.4 and up)

## What a plugin cannot do

- **Bring its own dependencies.** `--no-deps`, and there is no way around it.
- **Load without a restart.** Installing and uninstalling both need the backend restarted.
- **Add translations to the panel UI.** The locale dictionaries live in the frontend; a third-party plugin never gets into them. Put ready text into `label_i18n` — it shows as-is, but identically in both locales. Inside your own page, translate however you like.
- **Add its own button under a Telegram notification.** The panel will build the markup (see `panel_notify`), but the press is handled by the bot, whose handlers are listed in the panel's own code — `src/handlers/plugin_actions.py`. For an unknown `plugin_id` the press answers "unknown plugin".
- **Render inside an iframe.** The panel stamps `X-Frame-Options: DENY` on every response, plugin routes included. Pages are attached as a script instead — see the [Plugin API](/en/reference/plugin-api#a-page-in-the-ui).

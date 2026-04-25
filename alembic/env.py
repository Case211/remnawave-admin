"""
Alembic environment configuration for Remnawave Admin Bot.
"""
import logging
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text
from alembic import context

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# existing_loggers=False prevents fileConfig from disabling loggers
# created by the application (e.g. the bot logger) — otherwise migration
# errors would be silently swallowed.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

_log = logging.getLogger("alembic.env")

# Get database URL from environment
database_url = os.getenv("DATABASE_URL")
if database_url:
    # Convert asyncpg URL to psycopg2 for alembic (sync driver)
    if database_url.startswith("postgresql://"):
        sync_url = database_url
    elif database_url.startswith("postgresql+asyncpg://"):
        sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    else:
        sync_url = database_url
    config.set_main_option("sqlalchemy.url", sync_url)


# We don't use SQLAlchemy models, so target_metadata is None
# The schema is managed directly via SQL in database.py
target_metadata = None


# ── plugin migrations discovery ────────────────────────────────────
# Plugins ship their own alembic revisions in a separate folder. To make
# ``alembic upgrade head`` cover them, each plugin declares an entry point
# in group ``rwa.plugin.migrations`` pointing to a callable that returns
# the absolute path to its ``versions`` directory:
#
#   [project.entry-points."rwa.plugin.migrations"]
#   debugger = "rwa_plugin_debugger.migrations:versions_path"
#
# The plugin's first revision MUST set ``branch_labels='plugin_<id>'`` and
# ``down_revision=None`` so it forms its own branch in the revision graph
# and never collides with panel revision ids.

def _collect_plugin_version_locations() -> list[str]:
    out: list[str] = []
    try:
        from importlib.metadata import entry_points
    except Exception:
        return out

    try:
        try:
            eps = list(entry_points(group="rwa.plugin.migrations"))  # type: ignore[arg-type]
        except TypeError:
            eps = list(entry_points().get("rwa.plugin.migrations", []))  # type: ignore[union-attr]
    except Exception:
        _log.warning("alembic.plugin_entry_points_lookup_failed", exc_info=True)
        return out

    for ep in eps:
        name = getattr(ep, "name", "<unknown>")
        try:
            target = ep.load()
            path = target() if callable(target) else target
        except Exception:
            _log.warning("alembic.plugin_migrations_load_failed name=%s", name, exc_info=True)
            continue
        if not path:
            continue
        path_str = str(path)
        if not os.path.isdir(path_str):
            _log.warning("alembic.plugin_migrations_path_missing name=%s path=%s", name, path_str)
            continue
        out.append(path_str)
        _log.info("alembic.plugin_migrations_discovered name=%s path=%s", name, path_str)
    return out


_panel_versions = os.path.join(os.path.dirname(os.path.abspath(__file__)), "versions")
_plugin_versions = _collect_plugin_version_locations()

# Dev override: a colon-separated list of absolute paths, used in CI and
# local smoke tests to exercise multi-folder alembic without pip-installing
# a plugin package. Mirrors RWA_DEV_PLUGINS for the runtime plugin loader.
_dev_paths = os.environ.get("RWA_DEV_PLUGIN_MIGRATIONS", "").strip()
if _dev_paths:
    for raw in _dev_paths.split(os.pathsep):
        p = raw.strip()
        if p and os.path.isdir(p):
            _plugin_versions.append(p)

if _plugin_versions:
    config.set_main_option(
        "version_locations",
        os.pathsep.join([_panel_versions, *_plugin_versions]),
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    If the caller passed a connection via config.attributes['connection'],
    reuse it (single-connection mode used by main.py).  Otherwise create
    our own engine — this path is used by `alembic upgrade head` from CLI.
    """
    connection = config.attributes.get("connection")

    if connection is not None:
        # Reuse the connection provided by main.py — no extra engine needed.
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        # CLI / standalone: create our own engine.
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as conn:
            context.configure(
                connection=conn, target_metadata=target_metadata
            )
            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

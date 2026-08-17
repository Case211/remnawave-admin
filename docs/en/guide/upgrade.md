# Upgrading

```bash
cd /path/to/remnawave-admin
docker compose pull
docker compose up -d
```

The database schema takes care of itself: migrations run at startup. The panel, the collector and the bot all start at once, but only one of them migrates — the others wait and get a ready schema.

## Which image you get

| Branch | Image tag | For whom |
|--------|-----------|----------|
| `main` | `latest` | everyone |
| `dev` | `dev` | those willing to catch rough edges |

Compose pulls `latest` by default. Switching to `dev` means editing the image tag in `docker-compose.yml` — that is where changes live before anyone has run them in production.

## Node agents

Agents update separately and at their own pace; the panel works with older ones. New node-side features, such as [torrent detection via nDPI](/en/guide/torrents), only appear with a fresh agent.

On each node:

```bash
cd /opt/remnawave-node-agent
docker compose pull
docker compose up -d
```

The agent version is shown on the node card in the panel. If it is too old for a feature, the panel says so.

## Before a big upgrade

- Read the [release notes](https://github.com/Case211/remnawave-admin/releases) — the "Important" section is exactly the list of things you have to do by hand
- Take a [database backup](/en/guide/backups); the panel can do it from the interface
- Keep the previous image tag handy: rolling back is a tag change plus `docker compose up -d`

::: warning Rolling back after migrations
Migrations move the schema forward. An older image may refuse to start against an already-migrated database — which is why the backup matters more than it seems.
:::

## After upgrading

```bash
docker compose ps
docker compose logs --tail 100 web-backend
```

The current version and whether a newer one exists are shown on the dashboard.

# Node Agent

The agent runs on every node and does three things: reads the Xray `access.log` and ships connections to the panel, collects host and network metrics, and keeps a command channel open (terminal, scripts, block lists).

Without it there is no [anti-abuse](/en/guide/anti-abuse) — the panel simply has no way to know who connects from where.

## One-line install

The panel builds the command for you, token included:

1. **Nodes** → the node → **Agent token** → **Install agent**
2. Copy the resulting line and run it on the node:

```bash
curl -fsSL --retry 3 --retry-delay 2 \
  https://raw.githubusercontent.com/Case211/remnawave-admin/main/node-agent/install.sh \
  -o /tmp/rwa-node-agent-install.sh \
  && bash /tmp/rwa-node-agent-install.sh --uuid UUID --url URL --token TOKEN
```

The script creates `/opt/remnawave-node-agent/`, downloads `docker-compose.yml`, writes `.env` and starts the container.

| Flag | Purpose | Default |
|------|---------|---------|
| `--uuid` | node UUID | required |
| `--url` | panel address | required |
| `--token` | agent token | required |
| `--interval` | how often to send data, seconds | `30` |
| `--ws-secret` | command signing key, the `WEB_SECRET_KEY` of the panel | — |
| `--no-command` | skip the command channel | — |
| `--no-host-mode` | do not run commands on the host | — |
| `--dir` | install directory | `/opt/remnawave-node-agent` |

## Manual install

Generate the token in the panel (**Nodes → node → Agent token**) or in the bot. It is shown once.

```bash
mkdir -p /opt/remnawave-node-agent && cd /opt/remnawave-node-agent
curl -fsSLO --retry 3 --retry-delay 2 https://raw.githubusercontent.com/Case211/remnawave-admin/main/node-agent/docker-compose.yml
nano .env
docker compose up -d
```

```ini
AGENT_NODE_UUID=fd3a2983-4f68-45eb-8652-7557d7e15f7a
AGENT_COLLECTOR_URL=https://admin.example.com
AGENT_AUTH_TOKEN=token_from_the_panel
AGENT_INTERVAL_SECONDS=30
AGENT_XRAY_LOG_PATH=/var/log/remnanode/access.log
```

The image comes ready-made: `ghcr.io/case211/remnawave-admin-node-agent:latest`.

### Agent variables

| Variable | What it sets | Default |
|----------|--------------|---------|
| `AGENT_NODE_UUID` | node UUID from the Remnawave panel | required |
| `AGENT_COLLECTOR_URL` | Remnawave Admin address | required |
| `AGENT_AUTH_TOKEN` | token of this node | required |
| `AGENT_INTERVAL_SECONDS` | batch interval | `30` |
| `AGENT_LOG_PARSING_MODE` | `realtime` or `polling` | `realtime` |
| `AGENT_XRAY_LOG_PATH` | path to `access.log` | `/var/log/remnanode/access.log` |
| `AGENT_MAX_BUFFER_SIZE` | connection buffer ceiling | `50000` |
| `AGENT_SEND_MAX_RETRIES` | batch send attempts | `3` |
| `AGENT_SEND_RETRY_DELAY_SECONDS` | pause between attempts | `5.0` |
| `AGENT_LOG_LEVEL` | log level | `INFO` |
| `AGENT_COMMAND_ENABLED` | command channel from the panel | `false` |
| `AGENT_WS_URL` | WebSocket address if it differs | = `AGENT_COLLECTOR_URL` |
| `AGENT_WS_SECRET_KEY` | command signature key | — |

The `AGENT_NDPI_*` variables are covered in [Torrent detection](/en/guide/torrents).

## Checking

```bash
docker compose logs -f
```

A healthy start looks like this:

```
INFO: Collector API OK: https://admin.example.com/api/v2/collector/health
INFO: Log file found: /var/log/remnanode/access.log (size: X bytes)
INFO: Node Agent started: node_uuid=..., mode=realtime, interval=30s
INFO: Real-time parsing: new_lines=X accepted_lines=X connections=X
```

On shutdown the agent flushes what it has instead of dropping it:

```
INFO: Shutdown: sending remaining X accumulated connections...
INFO: Node Agent stopped
```

## Proxy in front of the collector

The agent talks to `/api/v2/collector/*` and holds a WebSocket on `/api/v2/agent/ws`. Both must pass through your reverse proxy — sample configs are in [Web panel and reverse proxy](/en/guide/web-panel).

## What the agent reads

A Remnawave log line looks like this:

```
2026/01/28 11:23:18.306521 from 188.170.87.33:20129 accepted tcp:accounts.google.com:443 [Sweden1 >> DIRECT] email: 154
```

`email: 154` is a user identifier, not an address: the collector resolves it by `short_uuid`, email or ID. IPv4 and IPv6 are both supported. If your log format differs, the parser lives in `node-agent/src/collectors/xray_log.py`.

## Upgrading

```bash
cd /opt/remnawave-node-agent
docker compose pull
docker compose up -d
```

If the agent was once installed as a local build (`build: .` in compose), move to the published image: stop the container, keep your `.env`, take the current `docker-compose.yml` from the repository and start again. Newer versions add a healthcheck, resource limits, graceful shutdown and a connectivity check at startup.

## If no data arrives

- **The agent cannot see the log.** Make sure the path in `AGENT_XRAY_LOG_PATH` exists inside the container and is mounted in `docker-compose.yml`
- **The collector does not answer.** The address in `AGENT_COLLECTOR_URL` must be reachable from the node: `curl https://admin.example.com/api/v2/collector/health`
- **`server rejected WebSocket connection: HTTP 404`.** The reverse proxy is not passing `/api/v2/agent/ws`, so the terminal and live node status will not work
- **Commands are rejected.** `AGENT_WS_SECRET_KEY` on the node must match the `WEB_SECRET_KEY` of the panel: commands are HMAC-signed

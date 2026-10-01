# Torrent detection

There are two sources, and they carry different weight.

**The Xray routing tag.** A rule with `"protocol": ["bittorrent"]` puts a `TORRENT` tag on the connection, the agent sees it in the log and sends an event. It works with no extras, but catches little: Xray recognises BitTorrent by the plaintext handshake at the start of a connection, while modern clients encrypt the stream by default (MSE/PE) and live in DHT and uTP over UDP. The handshake usually never happens, so mostly old clients with encryption disabled get caught.

**nDPI verdicts.** [nDPI](https://github.com/ntop/nDPI) has heuristics for encrypted BitTorrent, DHT packets and uTP. This is traffic inspection rather than reading log metadata, so it sees considerably more.

## Turning it on

The **Torrent detection via nDPI** toggle: **Settings → Violations**.

Nothing else is required — no packages to install on the node, no `.env` to edit. The `nDPId` daemon ships inside the agent image, so enabling it comes down to starting a pair of processes. The agent can listen on the interface because it already runs in host networking with `privileged` — without that, network metrics would not work either. The interface is picked from the default route rather than every interface at once: there is no point inspecting the traffic of the agent itself.

The toggle state is pushed to every connected agent immediately, and re-sent to an agent when it connects — a node restart does not lose the setting.

::: tip The agent must be 1.5.0 or newer
The daemon appeared in the agent image in version 1.5.0. An older agent answers honestly that it has no binaries, and the panel shows that — the toggle will not pretend everything is running.
:::

## How a verdict becomes a violation

nDPI sees traffic after NAT, on behalf of the node, and knows nothing about whose client it is. The destination address, however, is the same for it and for Xray — that is what the agent uses to tie a verdict to the log line that does have a user in it.

The event carries a `detected_by` field:

| Value | Meaning |
|-------|---------|
| `xray_routing` | the Xray routing tag fired |
| `ndpi` | traffic inspection verdict |

When somebody asks why they were blocked, this field says what exactly caught them. Events recorded before the second source existed are marked `xray_routing` — there was nothing else.

**Game launchers.** Some launchers ship updates over real BitTorrent, War Thunder's among them, so the verdict on them is correct. The peers are other players, so filtering by address owner only removes the publisher's servers. The whole swarm, however, sits on the launcher's port (27032 for War Thunder), while a regular torrent client's peers are spread across ports. When more than half of the distinct peers in the window are on that port, the detector treats the exchange as a game update and raises no violation. A mixed case (a game plus a torrent client) is still caught. To keep game traffic out of the VPN entirely, use a per-process or per-folder rule in the VPN client; game domains will not help.

**A reviewed exchange is not counted again.** The half-hour window starts from the moment an operator annulled or otherwise resolved the customer's previous torrent violation. Otherwise the window would pick up the same events right away and a new violation would arrive within minutes. The violation in the panel and the Telegram card are built from the same window: the same event and peer counts, the same list of addresses.

## Fine-tuning

Rarely needed, the toggle covers the normal case:

```ini
AGENT_NDPI_ENABLED=true          # start without waiting for the panel command
AGENT_NDPI_MANAGE_DAEMON=true    # false if the daemon is already running on the node
AGENT_NDPI_INTERFACE=eth0        # empty means the default-route interface
AGENT_NDPI_SOCKET_PATH=/tmp/ndpid-distributor.sock
AGENT_NDPI_WINDOW_SECONDS=120    # how long a verdict stays fresh
```

If the socket at that path already answers, the agent assumes the daemon was started externally and does not spawn its own.

## Worth thinking about first

::: warning This is traffic inspection
Reading the Xray log means metadata the node already writes down. nDPI inspects traffic on the interface. That is a noticeably bigger step, and it deserves a deliberate decision.
:::

The load is modest: the daemon works from heuristics over the first packets of a flow, and the agent tells it not to send packet events at all — they carry no verdict and only loaded the socket.

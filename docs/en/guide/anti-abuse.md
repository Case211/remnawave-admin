# Anti-abuse

Easy to state, unpleasant in practice: tell apart a person using a subscription from a phone and a laptop from five people sharing one. Remnawave Admin collects connections from nodes through [the agent](/en/guide/node-agent), runs them through seven analyzers and scores the result.

## Analyzers

| Analyzer | What it looks for |
|----------|-------------------|
| **Temporal** | simultaneous connections from different places, rapid switching |
| **Geographic** | impossible travel: two cities an hour apart, minutes apart |
| **ASN** | one subscription living at several providers at once |
| **Profile** | behaviour that does not look like one person: daily rhythm, session lengths |
| **Devices** | more devices than the subscription allows |
| **HWID** | one device serving several accounts |
| **User-Agent** | different client applications where one is expected |

Each can be turned on or off separately, and the results add up into a score. A notification is sent once the score passes the **minimum score** threshold, 50 by default.

## How sources are counted

Addresses from the same network within a narrow prefix (/24 for IPv4, /64 for IPv6) count as **one source**. Otherwise mobile CGNAT, which hands every connection its own address, would look like a crowd of four — an ordinary situation for mobile carriers.

Where collapsing is not allowed: hosting, datacentres and VPNs. There, neighbouring addresses are different machines, and sharing lives exactly there.

Both numbers stay in the violation text — 3 sources (7 addresses) — otherwise the incident cannot be reviewed.

Whether a network is mobile is decided by the organisation name from the ASN database, not by a one-off flag on the address record.

## Thresholds

All of them live in **Settings → Violations → Thresholds**.

| Setting | Meaning | Default |
|---------|---------|---------|
| Minimum notification score | below this a violation stays quiet | `50` |
| Max simultaneous IPs | above the device limit; `0` means derive it | `0` |
| Mobile CGNAT buffer | how many extra addresses to forgive a mobile connection | `3` |
| Max distance between cities | below this, movement is not suspicious | `50` km |
| Max accounts per HWID | how many different people may share a device | `2` |
| Max subscriptions per account on a HWID | guards against multi-plan abuse | `10` |
| Max active trials per HWID | how many live trial subscriptions on one device | `1` |

::: tip An account is a person, not a subscription
Subscriptions of one person are grouped by `telegram_id`, or by email when the registration had no Telegram. Two plans of the same user do not look like two accounts.
:::

## Trial farming

The live-trials rule catches exactly what new accounts are created for: one device carrying several active trials. The upgrade path — trial expired, paid plan bought — does not trigger it, and neither do two paying people sharing a tablet.

The whole cluster gets blocked, not just the account under review: otherwise, once it is banned, the rest see a single live trial on the device, fall below the threshold, and the farming costs the abuser exactly one account out of N. Paid and expired subscriptions are never included.

Which subscriptions count as trials is defined by a list of tags and internal squad UUIDs, in the same thresholds section.

## What happens on a violation

The score picks a **recommendation**, not a verdict: watch, warn, review manually, block temporarily, block. The panel itself touches nobody — with one exception: at the hard-block threshold with auto-blocking on (`violation_auto_hard_block`, enabled by default) the user is disabled right away. The notification then says "Done: user blocked" instead of a recommendation, so there is nothing to guess about.

Hard-block thresholds are configured separately — by number of addresses, simultaneous connections, devices, HWID matches and accounts per device.

## Soft block

Between "warn" and "cut off entirely" there is a middle measure: **throttle the speed**. The person stays online — sites and messengers work, video and torrents don't — notices the internet has gone weird, and comes to sort it out. A full block gets you nothing of the sort: they simply disappear.

The limit is attached to the user's **address**, via `tc` rules on the node. It touches neither the Xray config nor squad membership, so it applies and lifts instantly and affects nobody else. Requires agent 1.7.0 or newer.

**Settings → Violations → Speed throttling:**

| Setting | Meaning | Default |
|---------|---------|---------|
| Speed throttling | enables the mechanism | on |
| Default speed | what the violator is left with, kbit/s | `1024` |
| Reserve squad for violators | where to move them as well; empty — leave squads alone | empty |
| Node bandwidth | link width, `tc` needs it as the ceiling for everyone else | `10` Gbit/s |

There are three ways to apply it: the **"🐌 Throttle"** button under a violation notification, manually via the API, and automatically — when the traffic usage monitor has "throttle" as its auto-action.

With a reserve squad configured, the violator is moved there as well, and their previous squads are remembered and restored when the limit is lifted.

::: warning Addresses change
People change addresses several times a day, so rules are not set once and forgotten — they are rebuilt from live connections, and a new address is covered within a minute. An address with even one non-throttled user behind it is skipped: a single mobile-carrier address serves a whole district, and throttling it wholesale would punish the innocent.
:::

The notification arrives in Telegram with buttons: block, drop connections, whitelist — either entirely or only for the analyzer that raised the alarm (see [buttons under notifications](/en/guide/bot#buttons-under-notifications)). Automatic actions are marked in the record as taken by the system — there is no administrator behind them and nothing to review.

Repeat notifications about the same user are held back by a cooldown, so a single incident does not turn into a stream of messages.

## Reviewing an incident

The violation card shows which analyzers fired and with what weight, the addresses and sources, cities and providers, devices. Actions and the review note are made from there.

Nearby tools: **IP Lookup** for a single address, the connection geo map, and the shared-HWID tab with its live-trial counter.

## Torrents

A separate story: [torrent detection](/en/guide/torrents), the Xray routing tag plus traffic inspection via nDPI.

## If it catches too much

1. Look at which analyzer contributed the weight — it is named on the violation card
2. For mobile carriers: check the CGNAT buffer and that the network is recognised as mobile
3. Raise the minimum score — fewer notifications, but weak signals disappear too
4. Turn off an analyzer that does not suit your audience
5. The whitelist settles the question for a specific user or address for good

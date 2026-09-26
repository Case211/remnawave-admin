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
| Throttle automatically | apply straight away on the "review manually" verdict | off |

There are four ways to apply it: the **"🐌 Throttle"** button under a violation notification, by hand on the **Blocking → Throttling** tab, automatically by traffic usage ("throttle" as the monitor's auto-action), and automatically by score — with "Throttle automatically" on, the detector applies it itself on the "review manually" verdict.

The node's link width does not need to be configured: ordinary traffic bypasses the shaper entirely, only the violators' addresses go through it.

With agent 1.9.0 the node shaper does the cutting (see below): the limit applies in both directions, on any port and to IPv6 as well. If the node-wide cap is enabled too, the client gets the lower of the two. 0 or empty speed means no limit: in the throttle dialog it lifts the personal limit, in settings it turns the bot button and automatic actions off.

With a reserve squad configured, the violator is moved there as well, and their previous squads are remembered and restored when the limit is lifted.

::: warning Addresses change
People change addresses several times a day, so rules are not set once and forgotten — they are rebuilt from live connections, and a new address is covered within a minute. An address with even one non-throttled user behind it is skipped: a single mobile-carrier address serves a whole district, and throttling it wholesale would punish the innocent.
:::

The notification arrives in Telegram with buttons: block, drop connections, whitelist — either entirely or only for the analyzer that raised the alarm (see [buttons under notifications](/en/guide/bot#buttons-under-notifications)). Automatic actions are marked in the record as taken by the system — there is no administrator behind them and nothing to review.

Repeat notifications about the same user are held back by a cooldown, so a single incident does not turn into a stream of messages.

## Node shaper

A speed cap for every client address on the node — keeps heavy downloaders in check without hurting everyone else. Configured per node: **Servers → Panel nodes → node menu → Client shaper**. Off by default.

| Field | Meaning |
|-------|---------|
| Inbound ports | clients connect to these ports; prefilled from the node profile |
| Download, upload | cap per address, Mbit/s; 0 — no cap |
| Penalty mode | whoever moves more than the threshold within the window (both directions) gets the penalty speed for a while |

How it works: the agent (1.9.0+) attaches an eBPF program to the interface ingress and egress. Download packets are held until their scheduled departure time, upload is cut by dropping what exceeds the rate. The departure time is enforced by `fq`, so the agent installs it at the interface root when the kernel default sits there, and removes it when the shaper is turned off. If you set your own discipline, the agent leaves it alone: download is then cut more roughly, by dropping, and the dialog warns about it.

**Is it working?** While the shaper is on, the node card — in the compact view and the table too — shows a “Shaper” badge: green — the caps are in place, amber — download is capped roughly (someone else's discipline sits at the interface root), red — not applied, the reason is in the shaper dialog, theme-colored — waiting for the agent.

**Penalty notifications.** In penalty mode the agent reports who it penalized once a minute. The panel finds the user by address and connection time and sends a notification to Telegram and the bell, in the violations topic: who, on which node, how much they moved and until when they are slowed down. At most once per 6 hours per user; an address with no matching user produces no notification. Recent penalties are listed in the shaper dialog, the history is kept for 30 days.

::: warning Where it doesn't fit
Several clients can sit behind one mobile carrier address — they share the cap. Behind a CDN every client arrives from CDN addresses, so don't enable the shaper there: everyone would share one cap.
:::

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

## Client warnings

A violation is not yet a reason to cut access. People often do not know they are breaking the rules: they shared a key with a relative, left a torrent client running, or moved and log in from two countries within an hour. Access cut without explanation comes back to you as a “my VPN is broken” ticket, and sorting it out takes longer than the violation itself.

That is why you can write to the customer: from the violation card, from the Telegram notification with the **“⚠️ Warn”** button, or automatically together with the applied action.

### Texts

**Violations → Warnings tab.** One template per violation type: someone who shares a subscription and someone who downloads torrents need different words. Every template has a switch, a score threshold and channels — **Telegram** and **Email**: the warning goes strictly through the checked ones, and at least one always stays on.

The channels have separate texts; the **Telegram / Email** switch in the template changes the editor:

- **Telegram** — HTML in Telegram's reduced markup: `<b>`, `<i>`, `<u>`, `<s>`, `<a href>`, `<code>`, `<pre>`, `<blockquote>`, `<tg-spoiler>`; a line break is just Enter. Telegram rejects the whole message because of one extra tag or a bare `&`, so the editor highlights such places as you type, and a template with errors will not save. Next to it is a preview styled as a message. The customer sees the same text in the cabinet, without the tags.
- **Email** — the subject and ordinary email HTML with a preview. Empty — the email is built from the Telegram text: line breaks, bold, links. The “Start from the Telegram text” button puts that layout into the editor so you can edit it.

The type is determined by the analyzer that contributed the most — the same one the whitelist buttons are based on. If there is no template for it or it is off, the general one is used; if that one is off too, nothing is sent.

::: warning Do not tell the customer what the detector saw
No countries, device counts or scores. A list of triggered signals in the hands of the violator is a ready-made bypass guide: they will simply spread connections across networks and devices. Give the customer the fact and the consequence; the details stay in the panel.
:::

The **score threshold** in a template applies only to automatic sending together with an action. Pressing “Warn” sends the message at any score: the operator sees the whole violation, and refusing them because of a weak score means arguing with them.

Sending requires the `violations:resolve` permission — the same as blocking: the message goes to a person on behalf of the service and cannot be taken back. Sending again for the same violation happens only on explicit request, so an accidental double click does not write to the customer.

### Delivery

Telegram goes through the Bedolaga bot — the same bot the customer already talks to. Email goes through it too, and if the bot did not deliver it (not connected, did not find the customer, the customer has no email in the bot), it is sent by the panel's **built-in mail server**, provided a sending domain is set up. Any customer with an email gets the letter, whether they have Telegram or not.

Channels report separately: a customer who blocked the bot still gets the email. If the customer has no contacts for the enabled channels, the warning is not sent, and the operator sees why.

Telegram requires a bot with the `POST /users/{id}/notify` endpoint in its external API and `BEDOLAGA_API_URL` with `BEDOLAGA_API_TOKEN` filled in — the same ones tickets and customer cards work with.

### Warn first, act later

A soft scenario for violation types where the detector is wrong more often: the customer is warned right away, and the action is applied only if nothing has changed within the allotted time. It is built as a rule in **Automations**: the “Violation detected” (or “Torrent detected”) event, the “Warn user” action, then a “Limit speed” or “Block user” step with the **“Run after N h after the trigger”** field.

A delayed step waits in the database and survives a restart. Before running, it re-checks the case and is skipped if:

- the violation was annulled or already resolved by an operator;
- the customer is whitelisted;
- the action is already in place — otherwise a delayed one-day block would unblock someone blocked forever, and a limit would override a manual one;
- the customer contacted support in the meantime (Bedolaga tickets or [external support events](/en/reference/api-endpoints#external-support-contact)) — then the operator decides; the check can be turned off for the step;
- the rule was turned off — this cancels all waiting steps.

If the warning in the chain did not reach the customer, the delayed action is not applied at all: punishing without explanation is exactly what the chain protects against. A repeated trigger for the same customer does not add a second action while the first one is waiting. What is waiting, what ran and why a step was skipped is in the automations log.

The detector's built-in auto-block (hard_block, e.g. for trial abuse) fires immediately. To route it through a warning too, turn off `violation_auto_hard_block` and create a rule: “Violation detected” with the condition `recommended_action = hard_block` → “Warn user” → after N hours “Block user” with the **“Also trial-abuse accomplices on the same HWID”** checkbox. Like the built-in auto-block, the action reaches other subscriptions with a live trial on the same device — otherwise the bundle keeps working; it does not touch customers who are already blocked, limited or whitelisted.

## Violations in the Bedolaga cabinet

The cabinet can show the customer a warning, and the operator the verdict and the violation history. The panel stays the source of data; the cabinet only displays it.

### How it fits together

```
cabinet (customer's browser) ──► bot (Web API) ──► panel (API v3)
                                   the key lives here
```

The cabinet **does not talk to the panel directly**: its frontend runs in the user's browser, and any key that ends up there is available to the customer. Only the bot's server knows the key.

### Setup

**1. Enable the panel's external API.** A web backend variable:

```
EXTERNAL_API_ENABLED=true
```

Without it `/api/v3/*` does not respond. The state is shown in **Settings → API**.

**2. Create a key.** **API & Webhooks → API keys → Create**, scope — **only `violations:read`**. The bot only reads the verdict and the history and needs no write permissions. The key is shown once and looks like `rwa_…`.

**3. Set four variables for the bot:**

| Variable | Example | What it does |
|----------|---------|--------------|
| `ABUSE_API_ENABLED` | `true` | the main switch of the integration |
| `ABUSE_API_URL` | `https://panel.example.com/api/v3` | the panel's external API address |
| `ABUSE_API_KEY` | `rwa_…` | the key from the previous step |
| `ABUSE_API_TIMEOUT` | `5` | how many seconds to wait for a response |

If the panel and the bot share a docker network, the address can be internal: `http://remnawave-web-backend:8081/api/v3`. On different servers use public https.

### What appears

**The customer** sees a banner on the home page with the very warning that was sent to them and a button to contact support. Only the latest one and only while it is relevant: the customer sees neither history nor scores nor violation types — this data is not in the response their browser gets.

**The operator** sees a level chip next to the name on the customer card (“Flagged”, “Limited”) and a “Violations” tab with the history: date, reason, score, the action taken, whether a warning was sent. The tab is read-only; warning, blocking or annulling is done in the panel and its notifications.

### If it is not connected

Nothing breaks. The tab honestly says the service is not connected, there is no banner, and the other screens work as before. An unavailable panel or a slow response is treated the same way: **no questions to the customer**. A mistake in this direction costs nothing, while one in the other direction refuses an honest person and shows them a warning about a violation that never happened.

### Levels

| Level | When | What it means |
|-------|------|---------------|
| `clean` | no violations in the window, or the customer is whitelisted | no questions |
| `warned` | there are violations, but no action was taken | worth keeping an eye on |
| `limited` | a block or a speed limit was applied for the latest violation | access is already limited |

Annulled violations are not counted: the detector was wrong, and the person has nothing to do with it. The whitelist overrides everything — it is set by hand, already knowing about the violations.

The verdict is served by `GET /api/v3/violations/summary?telegram_id=…`; any integration of your own can use it too — for example, to deny trials to limited customers.

# Warnings via Bedolaga

If customers buy access through the [Bedolaga](https://github.com/BEDOLAGA-DEV/remnawave-bedolaga-telegram-bot) bot, the panel can explain violations to them through it. The warning arrives in Telegram from the same bot the customer already talks to, and by email. In the Bedolaga cabinet the customer sees a banner with that warning, and the operator sees the trust level and the violation history.

The panel stays the source of data: it decides whom to warn and about what, and keeps the texts and the history. The bot only delivers and displays.

## What you need

| Component | Version | Why |
|-----------|---------|-----|
| Remnawave Admin | 5.1.0 or newer | templates with Telegram and Email channels, soft measures in automations |
| Bedolaga bot | 4.16.0 or newer | the `POST /users/{id}/notify` sending endpoint and the cabinet endpoints for the banner |
| Bedolaga cabinet | with violations support | the customer banner and the operator tab — the changes are in [PR #613](https://github.com/BEDOLAGA-DEV/bedolaga-cabinet/pull/613), awaiting review |

## Step 1. Connect the panel and the bot

The connection goes both ways: the panel sends warnings through the bot, and the bot asks the panel for the verdict and the history to show them in the cabinet.

### Panel → bot

The panel talks to the bot's external API (Web API). The same connection is used by the Tickets section and the Bedolaga customer cards — if they already work for you, this half is done.

**Bot** `.env`:

```bash
WEB_API_ENABLED=true
WEB_API_DEFAULT_TOKEN=a-long-random-string
```

The Web API answers from the root of the bot's web server — the same address payment webhooks come to.

**Panel** `.env`:

```bash
BEDOLAGA_API_URL=https://bot.example.com
BEDOLAGA_API_TOKEN=a-long-random-string   # the same token
```

If the bot and the panel share a docker network, the address can be internal: `http://remnawave_bot:8080`.

### Bot → panel

1. **Enable the panel's external API** — in its `.env`:

   ```bash
   EXTERNAL_API_ENABLED=true
   ```

2. **Create a key.** **API & Webhooks → API keys → Create**, scope — **only `violations:read`**: the bot only reads the verdict and the history. Leave the allowed addresses empty or enter the bot server's address.
3. **Configure the bot** `.env`:

   ```bash
   ABUSE_API_ENABLED=true
   ABUSE_API_URL=https://panel.example.com/api/v3
   ABUSE_API_KEY=rwa_…
   ABUSE_API_TIMEOUT=5
   ```

This half is used by the cabinet: without it warnings still go out, but the banner and the operator tab have nothing to show. The cabinet itself never calls the panel — its frontend runs in the customer's browser, and a key that ended up there would be the customer's. The key lives only on the bot's server.

### Apply

`docker compose up -d bot` for the bot, `docker compose up -d` for the panel.

::: tip up -d, not restart
Variables from `.env` get into a container only when it is created. `restart` starts the old container with the old values, `up -d` recreates it with the new ones.
:::

## Step 2. Texts

**Violations → Warnings tab.** A shared template and one per violation type: someone who shares a subscription and someone who downloads torrents need different words. A template has a switch, a score threshold for automatic sending and channels — **Telegram** and **Email**, with separate texts per channel.

State the fact and the consequence, without detection details: no countries, no device counts, no scores — otherwise the warning becomes a guide to evading the detector. End with where to write if the warning is wrong, for example to support via the cabinet: the ticket lands in the Tickets section.

Telegram markup, the email and previews are covered in [Client warnings](/en/guide/anti-abuse#client-warnings).

## Step 3. How to send

- **Manually** — the “Warn” button in the violation card or “⚠️ Warn” in the Telegram violation notification. Requires the `violations:resolve` permission. The score threshold does not apply here: a person has already decided.
- **Together with a measure** — the “Violations: warn the customer on action” setting, on by default. An automatic block or throttle, as well as a measure applied with a button in the Telegram notification, reaches the customer with an explanation. The template's score threshold applies here.
- **Warn first, act later** — in automations: the “Warn user” action, with the measure as a delayed step N hours later. If the customer writes to support in the meantime, the measure is not applied and the operator decides. Details are in [Warn first, act later](/en/guide/anti-abuse#warn-first-act-later).

## Delivery

- **Telegram** — from the Bedolaga bot.
- **Email** — also through the bot. If the bot did not deliver the email (unavailable, did not find the customer, the customer has no email in the bot), the panel's built-in [mail server](/en/guide/mail) sends it, provided a sending domain is set up.
- **Unconfirmed emails are not written to.** Anyone could have entered such an address, and the violation letter would reach a stranger. The bot does not send to it, and the panel does not send it either.
- Channels are independent: a customer who blocked the bot still gets the email.
- The “customer was warned” mark is set only if at least one channel delivered. Sending again for the same violation happens only explicitly.

## Banner and tab in the cabinet

They appear once the cabinet is updated to a version with violations support, provided the “bot → panel” connection is set up.

**The customer** gets a banner on the home screen with exactly the warning they were sent and a button to contact support. The customer sees no history, no scores and no violation types: that data is not in the response their browser receives.

**The operator** gets a “Flagged” or “Limited” chip next to the name in the customer card and an “Abuse” tab with the history; the `users:read` permission is enough.

**When there is no banner:**

- no warning has been sent yet — a violation alone is not enough;
- more than 14 days have passed since sending;
- the violation was annulled — the operator decided the detection was wrong;
- the customer has no Telegram ID: the cabinet looks violations up by it, so someone who signs in only by email will not see the banner. The operator tab has nothing to show for such a customer either.

## Checking

**Panel → bot.** The Tickets section shows customer tickets — the connection works.

**Bot → panel.** A single request from the bot's server:

```bash
curl -s -H "X-API-Key: rwa_…" "https://panel.example.com/api/v3/violations/summary?telegram_id=1"
```

| Response | Meaning |
|----------|---------|
| `200` and `"level":"clean"` | everything works |
| `404 Not Found` | `EXTERNAL_API_ENABLED` is not enabled in the panel |
| `401` | the key was rejected: a typo, the key is disabled or expired, the bot server's address is not in the key's list, the key owner is disabled |
| `403` | the key lacks the `violations:read` scope |
| timeout or reset | the bot cannot reach the panel: a firewall or a closed network |

If a warning did not go out, the panel names the reason:

| Reason | What to do |
|--------|------------|
| “The Bedolaga bot rejected the warning” | the bot is older than 4.16.0 or unavailable — update it and check the “panel → bot” connection |
| “The customer is not found in the Bedolaga bot” | the customer was created in the panel bypassing the bot, and there is no email: no address or Email is off in the template — add an email to the customer in the panel |
| “The customer's email is not confirmed and Telegram is unavailable” | ask the customer to confirm the email in the cabinet |
| “Nothing to deliver with” | the customer has no contacts for the channels checked in the template — enable the second channel in the template |
| “No enabled warning template” | enable the shared template or the template for this type |

## FAQ

**The customer says they never downloaded torrents.** Check game launchers: some download updates over BitTorrent — War Thunder, for example. The detector sees real P2P, the customer just does not know about it. A “bypass VPN” rule by the game's domains will not help: torrent peers are bare addresses without a domain, and they go through the node. A rule by process or by the game folder in the VPN client will. Annul the violation itself — the customer will not see a banner.

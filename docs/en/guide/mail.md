# Mail server

The panel can send mail on its own: direct delivery to the recipient MX, DKIM signing, inbound mail. No external SMTP provider is needed — but the reputation of your domain becomes your responsibility.

## Turning it on

**Settings → Mail server → Mail server enabled**, then restart the container. Or via `.env`:

```ini
MAIL_SERVER_ENABLED=true
MAIL_INBOUND_PORT=2525
MAIL_SERVER_HOSTNAME=0.0.0.0
```

These variables are a fallback: everything here is configurable from the interface.

## Domain

1. **Mail Server → Domains → Add Domain**
2. Enter the domain, e.g. `example.com`
3. DKIM keys (RSA-2048) are generated automatically

The **DNS Records** button then shows what to add at your DNS provider:

| Type | Host | Purpose |
|------|------|---------|
| A | `mail.example.com` | address of the mail server |
| MX | `example.com` | where inbound mail goes |
| TXT | `example.com` | SPF — who may send on behalf of the domain |
| TXT | `rw._domainkey.example.com` | DKIM — the public signing key |
| TXT | `_dmarc.example.com` | DMARC — what to do with unsigned mail |
| PTR | server IP | reverse zone, configured at your host |

After adding them, press **Check DNS**.

::: warning Somebody else MX records swallow your mail silently
The check verifies **where** the MX record points, not just that one exists. If the domain moved from a previous host, its MX records often stay in the zone and keep receiving all inbound mail: senders get a rejection such as `550 Disabled`, and the panel knows nothing about it. Remove foreign MX records before adding yours.
:::

## Ports

```
25   — outbound: direct delivery to recipient MX servers
2525 — inbound: receiving mail
587  — SMTP submission
```

In `docker-compose.yml` the inbound port is published as the usual port 25:

```yaml
ports:
  - "25:2525"
```

::: warning Port 25 at cloud providers
AWS, GCP and Azure block outbound port 25. For mail, use a provider that does not — Hetzner, OVH, DigitalOcean.
:::

Only the HTTP API (`/api/v2/mailserver/*`) goes through the reverse proxy. SMTP cannot be tunnelled through an HTTP proxy — it is a different layer: either publish the port past the proxy, or configure `stream {}` in nginx or caddy-l4.

## Encryption

STARTTLS is offered on both mail ports:

```ini
MAIL_TLS_CERT_PATH=/app/certs/fullchain.pem
MAIL_TLS_KEY_PATH=/app/certs/privkey.pem
```

Without a configured path a self-signed certificate is issued into the `mail_certs` volume. For receiving mail that is enough: other servers encrypt the connection without validating the certificate. On port 587 clients will complain, so put a real certificate there — for example, mount the one from your reverse proxy.

::: danger Passwords before the certificate exists
Until a certificate is present, the "require TLS on port 587" setting has no effect, and logins travel in the clear. `AUTH PLAIN` is base64, not encryption. There is a warning about this in the logs at startup.
:::

## Inbound mail

Every message goes through SPF, DKIM and DMARC; the result is visible in the list and on the message card. Messages above the threshold are marked suspicious and kept out of the main list, behind their own filter.

The "reject suspicious messages" setting refuses them at reception instead — then at least a genuine sender gets a bounce rather than silence.

## Suppression list

Addresses that no longer receive mail. It fills itself:

- a hard bounce (`5.x.x`) closes the address permanently
- a soft one (`4.x.x`, mailbox full) for a week
- a message to `unsubscribe@<domain>` uses the address from the `List-Unsubscribe` header the panel adds to every message

This is not only good manners: persistently mailing non-existent boxes damages the reputation of the whole domain, and then mail to real recipients starts disappearing too. Entries can be removed by hand on the **Suppression** tab.

## DMARC reports

Mail systems send a daily summary to the address in the `_dmarc` record: who sent mail on behalf of the domain and whether it passed. The panel unpacks the attachment (`.gz`, `.zip`), parses the XML and shows the result on the **DMARC** tab. The unsigned-senders section reveals both foreign spoofing and your own service that forgot about DKIM.

## Retention

Inbound mail is kept indefinitely by default, the sending history for 90 days; messages still queued are never removed. Both are configurable, `0` means no limit.

## Verifying

1. Activate the domain → **Compose → Send Test** → check the queue, the status should become `sent`
2. Once an active domain exists, the notification system starts using the built-in server by itself, falling back to an external SMTP relay

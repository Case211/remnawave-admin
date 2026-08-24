# Telegram bot

The bot is a second interface to the same data as the web panel, plus a notification channel. It is handy when all you have is a phone: look up a user, restart a node, answer a violation with a button under the notification.

## Who can use it

Numeric Telegram IDs in `ADMINS`:

```ini
ADMINS=123456789,987654321
```

[@userinfobot](https://t.me/userinfobot) tells you your ID. The bot ignores everyone else.

## Commands

| Command | What it does |
|---------|--------------|
| `/start` | main menu |
| `/help` | help |
| `/health` | system status |
| `/stats` | panel statistics |
| `/bandwidth` | traffic statistics |
| `/config` | settings without a restart |
| `/user <username\|id>` | user card |
| `/node <uuid>` | node card |
| `/host <uuid>` | host card |

Everything else lives behind menu buttons: users, nodes, hosts, subscription templates, snippets, API tokens, billing.

## Notifications

Panel events and Remnawave Admin's own events go to the configured chat:

```ini
NOTIFICATIONS_CHAT_ID=-1001234567890
```

For events from the Remnawave panel itself (renewals, user changes) you also need the [panel webhook](/en/guide/webhook-setup).

### Routing by topic

If the chat is a forum group, notifications are split by topic:

```ini
NOTIFICATIONS_TOPIC_USERS=456       # users
NOTIFICATIONS_TOPIC_NODES=789       # nodes
NOTIFICATIONS_TOPIC_SERVICE=101     # service
NOTIFICATIONS_TOPIC_HWID=102        # devices
NOTIFICATIONS_TOPIC_CRM=103         # billing
NOTIFICATIONS_TOPIC_FINANCE=106     # finance
NOTIFICATIONS_TOPIC_ERRORS=104      # errors
NOTIFICATIONS_TOPIC_VIOLATIONS=105  # violations
```

Anything without its own topic goes to `NOTIFICATIONS_TOPIC_ID`.

### Buttons under notifications

A violation notification carries actions: block, drop connections, whitelist. The tap is checked against the permissions of whoever tapped it — a button never grants more than the role does.

There are two whitelists, and they are not the same thing. **"Whitelist"** lifts every check off that user at once. **"Skip: HWID"** (or geo, ASN — whichever fired) excludes only the angle this notification came from, while the other analyzers keep working. The second button shows up once it is clear which analyzer contributed most; existing partial exclusions are kept — a new one is added to them rather than replacing them.

[Plugins](/en/guide/plugins) add their own buttons: a plugin describes an action as text, action and object, and knows nothing about Telegram — the panel assembles the button itself.

## Bot on a restricted server

If the server sits on an address Telegram cannot be reached from:

```ini
BOT_PROXY_URL=socks5://user:pass@proxy.example.com:1080
```

`socks5://`, `socks4://` and `http://` are supported, with credentials. `socks5h://` and `https://` are not.

## Language

```ini
DEFAULT_LOCALE=ru   # or en
```

Both the bot and the web panel are fully translated, notification texts included.

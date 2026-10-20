<div align="center">

<img src="remnawave-admin.webp" alt="Remnawave Admin" width="100%" />

# Remnawave Admin

**A control panel and Telegram bot on top of your Remnawave panel**

Users, nodes, anti-abuse, mail and monitoring in one place

[![Stars](https://img.shields.io/github/stars/Case211/remnawave-admin?style=flat-square&logo=github&logoColor=white&labelColor=1f2430&color=f5c518)](https://github.com/Case211/remnawave-admin/stargazers) [![Release](https://img.shields.io/github/v/release/Case211/remnawave-admin?style=flat-square&logo=github&logoColor=white&labelColor=1f2430&color=3fb950)](https://github.com/Case211/remnawave-admin/releases/latest) [![License](https://img.shields.io/badge/License-AGPL_v3-blue?style=flat-square&logo=gnu&logoColor=white)](LICENSE)

### [🌐 Website](https://nexuslink.ru) · [💬 Chat](https://t.me/remnawave_admin) · [🛟 Support](https://t.me/rwa_moder_bot?start=support)

English · [Русский](README.md)

</div>

---

> [!IMPORTANT]
> **Remnawave Admin is now a paid product.** The current version is developed separately and runs on a subscription: the first 3 weeks are free with every feature included, then it is billed monthly and the price depends on the size of your service. Pricing, terms and sign-up are on **[nexuslink.ru](https://nexuslink.ru)**.
>
> This repository keeps the last free version, **5.2.0**. It works, but it no longer gets updates.

The Remnawave panel owns users and configuration. Remnawave Admin takes care of everything else: it collects connections from your nodes, hunts for subscription sharing and torrents, takes measures, sends notifications, keeps the history and shows you what is going on.

It works on top of your panel over the API and keeps its data in its own database.

## Features

🛡 **Anti-abuse.** Connection analyzers look for subscription sharing and trial farming: simultaneous connections, impossible travel, networks, devices, HWID, User-Agent. Measures, from a warning to the client to speed limits and disabling, can run automatically, and every violation can be reviewed on its card.

🧲 **Torrents.** An Xray routing tag plus traffic inspection on the node: encrypted BitTorrent shows up too, and game launchers or file sync can be marked as “not a torrent”.

🛰 **Node agent.** Xray logs, host metrics, a remote terminal and a script catalogue, speed limits on the node, channel quality towards clients. Installed with one line from the panel.

🚨 **Attacks and outages.** A DDoS detector for nodes, alerts when nodes go down or the channel degrades.

📧 **Mail server.** Your own MX, DKIM, inbound mail, SPF/DKIM/DMARC checks, with no external SMTP provider.

📈 **Monitoring and analytics.** Prometheus metrics and Grafana dashboards, a connection geo map, a hoster rating, analytics for users and nodes.

🤖 **Telegram bot.** Control from the chat, notifications with action buttons, routing to forum topics.

🔌 **API and integrations.** Its own API with keys and permissions, signed webhooks, violations in the Bedolaga cabinet.

Also: an automation builder, scheduled backups, an action log, roles and permissions, 2FA, themes, Russian and English.

## Getting started

1. Go to [nexuslink.ru](https://nexuslink.ru) and sign in to the cabinet with Telegram.
2. Issue an installation token; the instructions and documentation open right there.
3. Install the admin panel on your own server with Docker, preferably separate from the panel. The first 3 weeks are free.

Questions go to the [chat](https://t.me/remnawave_admin) or to support at [@rwa_moder_bot](https://t.me/rwa_moder_bot?start=support).

## The free version 5.2.0

The code in this repository is the last free version. Its [documentation](https://case211.github.io/remnawave-admin/en/) and [release](https://github.com/Case211/remnawave-admin/releases/tag/5.2.0) stay where they are, but it will not get updates, fixes or support any more, and pull requests are not accepted.

## Licence

The code in this repository is GNU AGPL v3.0 with a plugin exception (§7) — see [LICENSE](LICENSE); versions up to and including 2.15.x remain under MIT. The paid version is a separate product; its terms are in the [user agreement](https://nexuslink.ru/terms.html).

## Support the project

TON `UQDDe-jyFTbQsPHqyojdFeO1_m7uPF-q1w0g_MfbSOd3l1sC`
USDT TRC20 `TGyHJj2PsYSUwkBbWdc7BFfsAxsE6SGGJP`
BTC `1J6Zz7XcrpFkchwFmuU5WTFYTxziBdSwRz`

<div align="center">

<a href="https://github.com/Case211/remnawave-admin/stargazers">
  <img src="docs/star-history.svg" alt="Star history" width="640" />
</a>

Built for the Remnawave community

</div>

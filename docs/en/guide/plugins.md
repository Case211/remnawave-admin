# Plugins

A plugin is a separate package the panel installs into itself: it brings its own pages, its own permissions, its own database tables and background tasks. Installed and updated from the **Plugins** section.

## Installing

**Plugins** → the card you want → **Install**. The panel downloads the package, verifies its checksum, installs it and picks it up without a restart.

Permissions declared by the plugin appear for the superadmin immediately. Other roles get them by hand, like any other permission — see [Access and roles](/en/guide/access).

::: tip Panel version requirement
Every plugin release states the minimum panel version. If yours is older, the panel refuses to install and says which version is needed, rather than installing a package that would not work.
:::

## Free and paid

A free plugin installs right away, with no purchase: no prices, no quotas, no paid-until date. A paid one requires a subscription with an expiry date, and the card shows its state.

There is also a separate state for a plugin withdrawn from sale: the card stays, the purchase buttons are gone, and everyone who already paid keeps working.

## Release channels

Plugins have two channels, **stable** and **dev**. Everyone is on stable by default. Switching happens on the store side, per panel rather than for everybody at once. The dev channel carries versions that are still being run in.

## What plugins can do

- Their own pages in the panel and entries in the sidebar
- Their own permissions inside the shared role system
- Their own tables and migrations, applied together with the panel migrations
- Scheduled background tasks
- Buttons under Telegram notifications: the plugin describes an action as text, action and object, and knows nothing about Telegram — the panel assembles the button and checks the permissions of whoever taps it

## Existing plugins

**Block Radar** watches where and when the online count drops and correlates that across panels: it shows that a block is not yours alone but affects a hoster or a route. The block / false-alarm buttons in the notification feed back into the detector.

**Smart Support** diagnoses a user problem in one click: a report of the last day of connections, a hypothesis engine (subscription expired, node overloaded, client outdated), an outage check at the client ISP, and AI analysis on your own key — Gemini, Groq, OpenRouter or Claude. Plus a shared reference of client applications that panels maintain together.

## Removing

The **Remove** button on the card. The panel uninstalls the package and drops its pages from the interface; plugin data stays in the database in case you come back.

# Backups

The panel dumps its own database — from the interface or on a schedule. The **Backups** section.

This is the Remnawave Admin database: connections, violations, settings, mail, audit trail. The Remnawave panel keeps its own database and backs it up by its own means.

## By hand

The button creates a dump and it appears in the list, ready to download or restore.

## On a schedule

**Settings → Backups**:

| Setting | Meaning | Default |
|---------|---------|---------|
| Scheduled backup | enables everything below | off |
| Backup time | daily time in UTC | `03:00` |
| Interval, hours | `0` means once a day; `N` means every N hours starting at that time | `0` |
| Send to Telegram | the dump goes to the notification chat | off |
| Keep backups, count | how many recent ones to keep | `10` |
| Keep backups, days | maximum age | `30` |
| Back up the config | store panel settings separately | off |
| Alert if no backup for N hours | warn when a successful backup has not happened in a while; `0` disables | `0` |

::: tip About the dead-man switch
That last setting is the most useful and the most overlooked. A silent backup looks exactly like a working one: files simply stop appearing, and you notice months later — precisely when you need the backup. Set it slightly above your interval.
:::

## Restoring

Restore is started from the backup list. Before applying a dump the panel takes a snapshot of the current state, so a restore into the wrong place is not a one-way trip.

::: warning Test restores, not the presence of files
A backup that has never been restored is not a backup, it is a hope. Every so often restore a dump into a test database and check the data is there.
:::

## Sending to Telegram

The dump goes to the same chat as notifications. Convenient as a second copy, but remember: a file with your database sits in a chat, and access to that chat equals access to the data.

## What the dump contains

Everything in the database, which is nearly everything: connections and violations, settings, mail with attachments, DKIM keys, the audit log.

Outside it are only service files in Docker volumes: downloaded GeoIP databases, which restore themselves, and the mail server TLS certificates if you put your own there.

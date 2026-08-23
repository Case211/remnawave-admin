# Panel settings

Almost everything is configured from the interface, with no file editing and no restart: the **Settings** page. Changes apply immediately.

A value is resolved through the chain **database → `.env` → built-in default**. Until a setting is touched in the interface, whatever is in `.env` or in the code applies; after the first change it lives in the database and `.env` no longer affects it.

The list marks each setting: `DB` — overridden and stored in the database, `.env` — taken from the environment, `Default` — from the code. A few values are read-only: they are managed from their own pages and listed here for completeness.

::: tip This page is generated from the code
Names, descriptions and defaults come straight from the panel settings catalogue, so they cannot drift from what you see in the interface. Regenerate with `python scripts/gen_settings_docs.py`.
:::


## ⚙️ General

The basics: language, logs, access to the Remnawave panel, third-party service keys. Some values here are secrets managed on their own pages and shown in the list for reference only.

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🌐 Bot language** | `bot_language` | `ru` | Bot interface language (`DEFAULT_LOCALE`) |
| **📝 Log level** | `log_level` | `INFO` | Log detail level (requires restart) (`LOG_LEVEL`) |
| **📦 Max log file size (MB)** | `log_max_size_mb` | `10` | Maximum size of a single log file before rotation |
| **🗂️ Log backup count** | `log_backup_count` | `5` | Number of compressed backup files kept after rotation |
| **🌍 MaxMind GeoIP source** | `maxmind_source` | `auto` | auto — GitHub (ltsdev/maxmind) then MaxMind; github — GitHub only (no key); maxmind — official only (key required) (`MAXMIND_SOURCE`) |
| **🏷️ Panel name** | `panel_name` | empty | Project name displayed in the sidebar (next to the logo) |
| **Access token lifetime (minutes)** | `web_session_access_minutes` | `30` | Lifetime of the web panel access token. Applies to new logins and refreshes. Recommended: 30-120 min (`WEB_JWT_EXPIRE_MINUTES`) |
| **Session lifetime (hours)** | `web_session_refresh_hours` | `6` | Total session lifetime (refresh token). While it is valid the user stays signed in; after that a new login with 2FA is required. Recommended: 12-24h (`WEB_JWT_REFRESH_HOURS`) |
| **DNS: Cloudflare (encrypted)** | `dns_creds_cloudflare` | empty | Managed on the DNS page, not here (read-only) |
| **DNS: Timeweb Cloud (encrypted)** | `dns_creds_timeweb` | empty | Managed on the DNS page, not here (read-only) |
| **DNS: reg.ru (encrypted)** | `dns_creds_regru` | empty | Managed on the DNS page, not here (read-only) |
| **DNS: Selectel (encrypted)** | `dns_creds_selectel` | empty | Managed on the DNS page, not here (read-only) |
| **DNS: Aeza (encrypted)** | `dns_creds_aeza` | empty | Managed on the DNS page, not here (read-only) |
| **BS-Check: bschekbot token (encrypted)** | `bscheck_token` | empty | The bsk_live_ token (bsbord) used to test nodes through mobile carriers. Edited on the nodes page (read-only) |
| **Reputation: ipinfo.io token (encrypted)** | `reputation_ipinfo_token` | empty | Managed on the BS-Check page (read-only) |
| **Reputation: IPQualityScore token (encrypted)** | `reputation_ipqs_token` | empty | Managed on the BS-Check page (read-only) |
| **Reputation: AbuseIPDB token (encrypted)** | `reputation_abuseipdb_token` | empty | Managed on the BS-Check page (read-only) |
| **OAuth: Google client_id** | `oauth_google_client_id` | empty | Managed in the OAuth settings (read-only) |
| **OAuth: Google secret (encrypted)** | `oauth_google_client_secret` | empty | Managed in the OAuth settings (read-only) |
| **OAuth: GitHub client_id** | `oauth_github_client_id` | empty | Managed in the OAuth settings (read-only) |
| **OAuth: GitHub secret (encrypted)** | `oauth_github_client_secret` | empty | Managed in the OAuth settings (read-only) |
| **OAuth: OIDC client_id** | `oauth_oidc_client_id` | empty | Managed in the OAuth settings (read-only) |
| **OAuth: OIDC secret (encrypted)** | `oauth_oidc_client_secret` | empty | Managed in the OAuth settings (read-only) |
| **OAuth: OIDC issuer URL** | `oauth_oidc_issuer` | empty | Managed in the OAuth settings (read-only) |
| **OAuth: OIDC button label** | `oauth_oidc_name` | empty | Managed in the OAuth settings (read-only) |


## 🔔 Notifications

Where and what to write in Telegram. Topics spread events across forum threads, notification types switch individual events on and off.


### Main

| Setting | Key | Default | What it does |
|---|---|---|---|
| **💬 Notifications chat ID** | `notifications_chat_id` | empty | Telegram chat/group ID for notifications (`NOTIFICATIONS_CHAT_ID`) |
| **✨ Rich notification styling** | `notifications_rich_enabled` | `true` | Send Telegram notifications as Bot API 10.1 rich messages: real headings, field lists, collapsible sections. Falls back to plain HTML automatically if Telegram rejects it |


### 🔔 Telegram notification types

| Setting | Key | Default | What it does |
|---|---|---|---|
| **👤 Users** | `notifications_users_enabled` | `true` | Send Telegram notifications about users |
| **🖥️ Nodes** | `notifications_nodes_enabled` | `true` | Send Telegram notifications about nodes |
| **🔧 Service** | `notifications_service_enabled` | `true` | Send service Telegram notifications |
| **🔑 HWID** | `notifications_hwid_enabled` | `true` | Send Telegram notifications about HWID devices |
| **💼 CRM** | `notifications_crm_enabled` | `true` | Send Telegram notifications about CRM and infrastructure billing |
| **❗ Errors** | `notifications_errors_enabled` | `true` | Send Telegram notifications about errors |
| **🛡️ Violations** | `notifications_violations_enabled` | `true` | Send Telegram notifications about violations |
| **💰 Finance** | `notifications_finance_enabled` | `true` | Send financial Telegram notifications and reminders |


### 💬 Notification topics

| Setting | Key | Default | What it does |
|---|---|---|---|
| **💬 Topic: Default (fallback)** | `notifications_topic_id` | empty | Default topic ID, used when a specific topic is not set (`NOTIFICATIONS_TOPIC_ID`) |
| **👤 Topic: Users** | `notifications_topic_users` | empty | Topic ID for user notifications (`NOTIFICATIONS_TOPIC_USERS`) |
| **🖥️ Topic: Nodes** | `notifications_topic_nodes` | empty | Topic ID for node notifications (`NOTIFICATIONS_TOPIC_NODES`) |
| **🔧 Topic: Service** | `notifications_topic_service` | empty | Topic ID for service notifications (`NOTIFICATIONS_TOPIC_SERVICE`) |
| **🔑 Topic: HWID** | `notifications_topic_hwid` | empty | Topic ID for HWID notifications (`NOTIFICATIONS_TOPIC_HWID`) |
| **💼 Topic: CRM** | `notifications_topic_crm` | empty | Topic ID for CRM and infrastructure billing (`NOTIFICATIONS_TOPIC_CRM`) |
| **🛡️ Topic: Violations** | `notifications_topic_violations` | empty | Topic ID for violation notifications (`NOTIFICATIONS_TOPIC_VIOLATIONS`) |
| **❗ Topic: Errors** | `notifications_topic_errors` | empty | Topic ID for error notifications (`NOTIFICATIONS_TOPIC_ERRORS`) |
| **💰 Topic: Finance** | `notifications_topic_finance` | empty | Topic ID for financial notifications and reminders (`NOTIFICATIONS_TOPIC_FINANCE`) |


## 🛡️ Violation Detection

The largest section: analyzers, thresholds, automatic actions and retention. What the analyzers mean and how to review incidents is in [Anti-abuse](/en/guide/anti-abuse).


### Main

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🛡️ Violation detection** | `violations_enabled` | `true` | Global on/off switch for the violation detector |
| **📐 Min notification score** | `violations_min_score` | `50.0` | Minimum violation score to trigger a notification (default 50) |
| **⏱️ Temporal analyzer** | `violations_analyzer_temporal` | `true` | Analyses simultaneous connections and rapid-switch patterns |
| **🌍 Geo analyzer** | `violations_analyzer_geo` | `true` | Detects impossible travel and suspicious geolocation |
| **🏢 ASN analyzer** | `violations_analyzer_asn` | `true` | Provider classification (VPN, datacenter, mobile carrier) |
| **👤 Profile analyzer** | `violations_analyzer_profile` | `true` | Detects deviations from the user's usual behaviour |
| **📱 Device analyzer** | `violations_analyzer_device` | `true` | Detects unique device fingerprints (OS, client) |
| **🔑 HWID cross-account analyzer** | `violations_analyzer_hwid` | `true` | Detects the same HWID used across multiple accounts (trial abuse) |
| **🔤 User-Agent analyzer** | `violations_analyzer_user_agent` | `true` | Detects double tunnels (vless:// in UA), bots (curl, Go-http-client), and unknown clients |


### 📐 Detection thresholds

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🌐 Max simultaneous IPs** | `violations_max_simultaneous_ips` | `0` | Max simultaneous IPs above the device limit to trigger a violation (0 = auto from device count) |
| **📏 Max inter-city distance (km)** | `violations_geo_max_city_distance_km` | `50` | Distance between cities below which movement is not considered suspicious |
| **👥 Max accounts per HWID** | `violations_hwid_max_accounts` | `2` | How many distinct accounts may share one HWID WITHOUT triggering — a violation starts at the next account (value 2 → fires on the third). Subscriptions of the same person count as one account: grouped by telegram_id, or by email when the user signed up without Telegram |
| **Max subscriptions per account on one HWID** | `violations_hwid_max_per_account` | `10` | How many panel UUIDs (subscriptions) of a single telegram_id are allowed on one HWID. Guards against multi-plan abuse. 0 = unlimited |
| **📱 Mobile CGNAT buffer (IPs)** | `violations_mobile_cgnat_buffer` | `3` | Extra simultaneous IPs allowed for mobile connections beyond the device limit (CGNAT gives 3-5 IPs from one device) |
| **🎁 Max active trials per HWID** | `violations_hwid_max_active_trials` | `1` | How many distinct accounts with a LIVE trial subscription may share one device without triggering. Catches trial farming via fresh accounts while ignoring both the normal «trial expired → paid plan purchased» upgrade and two paying people sharing a device. Trial status is determined by the tag and internal squad settings below. 0 = disabled |
| **♻️ Max trial subscriptions per account per HWID** | `violations_hwid_max_trial_subs` | `1` | How many times one person may take a trial from the same device — counting expired and disabled ones. Closes the workaround where a second trial is taken on a fresh subscription with the same telegram_id linked to it: to every other check that is one account with one live trial. Ignores both the «trial → paid» upgrade and two different people sharing a tablet. 0 = disabled |
| **Check cooldown (min)** | `violation_check_cooldown_minutes` | `15` | Minimum interval between repeated detector checks of the same user (load throttling). Not the same as the notification cooldown |
| **Violation retention (days)** | `violation_retention_days` | `90` | How many days violation records are kept before automatic cleanup |
| **Connection retention (days)** | `connections_retention_days` | `30` | How many days the user connection history is kept before automatic cleanup |
| **HWID scan interval (min)** | `violations_hwid_scan_interval_minutes` | `30` | How often offline users sharing a HWID are checked for cross-account abuse (the batch detector only sees users who are online) |
| **Torrent event retention (days)** | `torrent_retention_days` | `90` | How many days recorded torrent events are kept before automatic cleanup |
| **📅 Max SRH record age (days)** | `violation_ua_max_age_days` | `0` | Ignore subscription requests older than N days. 0 = analyse all records |
| **Torrent detection via nDPI** | `ndpi_detection_enabled` | `false` | Xray only recognises BitTorrent by the plaintext handshake, so encrypted streams, DHT and uTP slip past. nDPI sees those too. Requires the nDPId daemon on the node: the setting is pushed to agents as a command, no .env editing needed |
| **🔗 Min score for link in UA** | `violation_ua_link_floor` | `70` | Minimum violation score when a subscription link (vless://) is detected in User-Agent. 70 = warn, 80 = soft_block |
| **🤖 Min score for bot UA** | `violation_ua_bot_floor` | `55` | Minimum violation score for curl/Go-http-client/python-requests User-Agents |
| **🗑️ SRH retention (days)** | `srh_retention_days` | `90` | Delete synced Subscription Request History records older than N days. 0 = keep forever |


### 🔤 User-Agent patterns

| Setting | Key | Default | What it does |
|---|---|---|---|
| **✅ Extra whitelist UA (regex)** | `violation_ua_whitelist_extra` | `[]` | JSON array of regex patterns for new VPN clients. Example: ["^NewClash/", "^MyClient/"] |
| **🚫 Extra blacklist UA (regex)** | `violation_ua_blacklist_extra` | `[]` | JSON array of regex patterns for suspicious UAs. Example: ["^SuspiciousBot/"] |


### 🚫 Hard block

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🚫 Hard block: max IPs** | `violations_hard_block_ips` | `50` | Number of unique IPs to trigger an automatic hard block |
| **🚫 Hard block: max simultaneous** | `violations_hard_block_simultaneous` | `20` | Number of simultaneous connections to trigger a hard block |
| **🚫 Hard block: max devices** | `violations_hard_block_devices` | `80` | Number of unique device fingerprints to trigger a hard block |
| **🚫 Hard block: max HWID matches** | `violations_hard_block_hwid_matches` | `10` | Number of matching HWIDs (same model) to trigger a hard block |
| **🚫 Hard block: accounts on one HWID** | `violations_hard_block_hwid_accounts` | `5` | How many distinct accounts on a single device (HWID) counts as mass trial abuse and triggers a hard block. Subscriptions of the same telegram_id count as one account. 0 = disabled |


### 🆓 Trial user detection

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🏷️ Trial user tags** | `violations_trial_tags` | `trial` | Comma-separated tags that mark a user as trial (e.g. trial,test,free) |
| **👥 Trial internal squads** | `violations_trial_squad_uuids` | `[]` | Select internal squads whose users are considered trial |


### 🧲 Torrent blocker

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🧲 Torrent detection** | `torrent_detection_enabled` | `true` | Enable/disable torrent traffic detection via Xray routing |
| **⚡ Auto-action on torrent** | `torrent_auto_action` | `notify` | Action on torrent traffic: notify (alert only), block_user (block) |
| **🔕 Torrent notification cooldown (min)** | `torrent_notification_cooldown_minutes` | `30` | Minimum interval between torrent notifications for the same user |


### 📈 Traffic usage

| Setting | Key | Default | What it does |
|---|---|---|---|
| **📈 Traffic usage monitor** | `traffic_rate_enabled` | `false` | Tracks abnormally high traffic consumption over a period |
| **📊 Threshold (GB per window)** | `traffic_rate_threshold_gb` | `10.0` | Notify when a user consumes more than this amount in the window |
| **⏱️ Check window (min)** | `traffic_rate_window_minutes` | `60` | Time window for traffic accounting (default 60 = 1 hour) |
| **🔁 Check interval (min)** | `traffic_rate_check_interval_minutes` | `5` | How often to check traffic consumption |
| **🔕 Notification cooldown (min)** | `traffic_rate_cooldown_minutes` | `60` | Minimum interval between repeated notifications for the same user |
| **⚡ Auto-action on breach** | `traffic_rate_auto_action` | `notify` | Action on excessive traffic: notify only or auto-block |
| **🚫 Auto-block threshold (GB)** | `traffic_rate_auto_block_gb` | `50.0` | Auto-block when traffic in the window exceeds this value. Only takes effect when auto-action = block_user |


### 🔍 Violation detection pipeline

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🔕 Notification cooldown (min)** | `violation_notification_cooldown_minutes` | `30` | Minimum interval between repeated notifications for the same user. Spam protection. |
| **Record deduplication window (hours)** | `violation_dedup_window_hours` | `24` | While a user has an unresolved violation newer than this window, repeated detections do not create a new record unless the score is higher. 0 disables deduplication |
| **Auto-block on hard_block** | `violation_auto_hard_block` | `true` | Disable the user through the Panel API when the detector recommends a hard block. When off, only a notification and a record are produced |


## 🔒 Security

Protection of the panel itself plus node attack detection: login methods, brute-force limits, user blacklist.


### 🔑 Auth methods

| Setting | Key | Default | What it does |
|---|---|---|---|
| **✈️ Telegram Authentication** | `auth_telegram_enabled` | `true` | Allow login via Telegram Login Widget |
| **🔒 Password Authentication** | `auth_password_enabled` | `true` | Allow login with username and password |
| **🔐 Mandatory 2FA (TOTP)** | `auth_totp_required` | `false` | Require TOTP setup for all accounts |


### 🛡️ Brute-force protection

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🚫 Max attempts before lockout** | `auth_max_attempts` | `5` | Number of failed login attempts before IP is blocked |
| **⏳ Lockout duration (min)** | `auth_lockout_minutes` | `15` | How long an IP is blocked after exceeding the attempt limit |
| **📋 Fail2ban logging** | `auth_fail2ban_logging` | `true` | Log failed login attempts to auth_failures.log |
| **🔔 Notify on IP block** | `auth_notify_on_block` | `true` | Send Telegram notification when an IP is blocked |
| **⚠️ Notify on failed login** | `auth_notify_on_failure` | `true` | Send Telegram notification on every failed login attempt |


### 🚫 User blacklist

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🚫 User blacklist** | `user_blacklist_enabled` | `false` | Enable Telegram ID blacklist lookup. Matching users are auto-blocked. |
| **🔗 Blacklist URLs (one per line)** | `user_blacklist_urls` | empty | External blacklist file URLs. Format: Telegram ID at the start of each line. |
| **🔄 Sync interval (hours)** | `user_blacklist_sync_hours` | `6` | How often to refresh blacklists from external URLs. |
| **⚡ Auto-block** | `user_blacklist_auto_block` | `false` | Automatically block blacklisted users via Panel API. When disabled — notification only. |
| **🛡️ HWID blacklist guard** | `hwid_blacklist_guard_enabled` | `true` | Periodically check whether a subscription came back to life for anyone seen on a blacklisted device, and disable it again. Blacklist blocking happens once, while a subscription can be revived afterwards — linking a telegram_id to an email-created one already did it. Entries set to «alert» are only reported, never disabled |
| **🛡️ HWID guard interval (min)** | `hwid_blacklist_guard_interval_minutes` | `5` | How often the guard walks the HWID blacklist. A shorter interval means a shorter window for a revived subscription to stay usable |
| **🌐 IP guard: repeated trials** | `violations_ip_trial_guard_enabled` | `true` | Spot addresses used for several trial subscriptions by different accounts. HWID is announced by the client itself and forged with a header, while an address comes from the provider and is harder to change. Service and carrier ranges are excluded |
| **🌐 Trial subscriptions per address** | `violations_ip_trial_accounts` | `2` | How many distinct trial subscriptions may share one address without an alert. Only trials count: a home provider address covers a whole flat |
| **📱 Same for mobile addresses** | `violations_ip_trial_accounts_mobile` | `4` | A separate threshold for mobile carrier addresses. CGNAT puts a whole district behind one address, so several people with trials there is ordinary |
| **🌐 Address lookup window (days)** | `violations_ip_trial_window_days` | `30` | How far back connections are counted. Too wide a window picks up dynamic addresses that changed hands between subscribers |
| **🌐 Silence per address (hours)** | `violations_ip_trial_repeat_hours` | `24` | How long to stay quiet about an address after reporting it |
| **🌐 Address guard interval (min)** | `violations_ip_trial_interval_minutes` | `60` | How often addresses are re-checked. Heavier than the HWID guard: it groups connection history over the whole window |


### node_attacks

| Setting | Key | Default | What it does |
|---|---|---|---|
| **Node attack detection** | `attack_detect_enabled` | `true` | Watch node network metrics and warn when a node is under attack. Requires agent 1.3.0 or newer |
| **Packet threshold (x normal)** | `attack_pps_ratio` | `4` | How many times the inbound packet rate must exceed the usual level for this node. Below 3 you will get false alarms on evening peaks |
| **Traffic threshold (x normal)** | `attack_bps_ratio` | `4` | The same for inbound traffic volume — catches attacks made of large packets |
| **Minimum packets/s to alert** | `attack_min_pps` | `5000` | Below this a spike is ignored: on an idle night-time node a tenfold rise is just noise |
| **Minimum bytes/s to alert** | `attack_min_bps` | `12500000` | The same for volume. The default 12,500,000 is 100 Mbit/s |
| **Samples for the baseline** | `attack_min_samples` | `20` | How many samples to collect before trusting the usual level of a node. Until then the detector stays quiet |
| **Small packet, bytes** | `attack_small_packet_bytes` | `300` | An average packet size below this is treated as a sign of flooding: useful traffic is made of bigger packets |


## 📧 Mail Server

The built-in mail server: TLS, inbound mail, spam scoring, retention. Setup is described in [Mail server](/en/guide/mail).

| Setting | Key | Default | What it does |
|---|---|---|---|
| **📧 Mail server enabled** | `mailserver_enabled` | `false` | Enable the built-in mail server (inbound/outbound) (`MAIL_SERVER_ENABLED`) |
| **🖥️ SMTP hostname** | `mailserver_hostname` | `0.0.0.0` | IP address for the inbound SMTP server (0.0.0.0 = all interfaces) (`MAIL_SERVER_HOSTNAME`) |
| **📥 Inbound SMTP port** | `mailserver_inbound_port` | `2525` | Port for inbound mail (default 2525, 25 in production) (`MAIL_INBOUND_PORT`) |
| **🚦 Send limit per hour** | `mailserver_max_send_per_hour` | `100` | Global per-domain hourly send limit. Applies to domains without their own limit (domain value 0). 0 = unlimited |
| **⏱️ Queue poll interval** | `mailserver_queue_poll_interval` | `10` | How often to poll the outbound queue (seconds) |
| **🔁 Max delivery retries** | `mailserver_max_retries` | `5` | Maximum number of delivery attempts per message |
| **📤 SMTP Submission enabled** | `mailserver_submission_enabled` | `false` | Enable SMTP Submission (port 587) for sending mail via login/password (`MAIL_SUBMISSION_ENABLED`) |
| **🔌 SMTP Submission port** | `mailserver_submission_port` | `587` | Port for the SMTP Submission server (standard — 587) (`MAIL_SUBMISSION_PORT`) |
| **TLS certificate path** | `mailserver_tls_cert_path` | empty | Certificate for STARTTLS on the mail ports. Empty means a self-signed one is issued: enough for receiving mail, but mail clients on port 587 will complain (`MAIL_TLS_CERT_PATH`) |
| **TLS key path** | `mailserver_tls_key_path` | empty | Private key for the certificate above (`MAIL_TLS_KEY_PATH`) |
| **Mail server hostname** | `mailserver_tls_hostname` | empty | How the server introduces itself over SMTP and what the certificate is issued for. Should match the PTR record of the IP. Empty means mail.&lt;first domain&gt; |
| **Require TLS on port 587** | `mailserver_submission_require_tls` | `true` | Refuse logins over an unencrypted connection. Clients from private networks (10.x, 192.168.x, 100.64.x such as Netbird) are exempt: that traffic is already inside a tunnel. Only effective once a certificate exists |
| **Spam threshold** | `mailserver_spam_threshold` | `5` | Score at which a message is marked suspicious. 5 points means the domain published a DMARC policy and the message failed it |
| **Reject suspicious messages** | `mailserver_reject_spam` | `false` | Refuse messages that reach the threshold at reception. When off, the message is accepted but flagged in the list |
| **Keep inbound mail, days** | `mailserver_inbox_retention_days` | `0` | After how many days received messages are deleted. 0 = keep forever |
| **Keep sending history, days** | `mailserver_queue_retention_days` | `90` | After how many days sent and rejected messages leave the queue. Messages still waiting to be sent are untouched. 0 = keep forever |
| **Notify about new mail** | `mailserver_notify_new_mail` | `false` | Send a notification when a message arrives, excluding service mail: bounces, unsubscribes and DMARC reports |


## 💾 Backups

Schedule, retention and the dead-man switch that warns when backups have stopped happening. See [Backups](/en/guide/backups).

| Setting | Key | Default | What it does |
|---|---|---|---|
| **Scheduled backup** | `backup_auto_enabled` | `false` | Create a database backup automatically on a schedule |
| **Backup time** | `backup_auto_time` | `03:00` | Time of the daily backup (HH:MM UTC) |
| **Send to Telegram** | `backup_auto_telegram` | `false` | Send the created backup to Telegram (chat_id from the notification settings) |
| **Keep backups (count)** | `backup_auto_keep_count` | `10` | How many recent automatic backups to keep |
| **Keep backups (days)** | `backup_auto_keep_days` | `30` | Maximum age of automatic backups in days |
| **Backup interval (hours)** | `backup_auto_interval_hours` | `0` | 0 — once a day at the configured time; N&gt;0 — every N hours starting from that time |
| **Back up the config** | `backup_auto_config` | `false` | Store panel settings alongside the database backup |
| **Alert if no backup for N hours** | `backup_deadman_hours` | `0` | Send an alert when there has been no successful backup for longer than N hours (0 = off) |


## 📊 Reports

Periodic summaries: what to send, when and to whom.

| Setting | Key | Default | What it does |
|---|---|---|---|
| **📊 Reports enabled** | `reports_enabled` | `true` | Global toggle for automatic reports |
| **📅 Daily reports** | `reports_daily_enabled` | `true` | Enable daily violation reports |
| **🕐 Daily report time** | `reports_daily_time` | `09:00` | Daily report send time (HH:MM UTC) |
| **📆 Weekly reports** | `reports_weekly_enabled` | `true` | Enable weekly violation reports |
| **📅 Weekly report day** | `reports_weekly_day` | `0` | Day of week for weekly report (0=Mon, 6=Sun) |
| **🕐 Weekly report time** | `reports_weekly_time` | `10:00` | Weekly report send time (HH:MM UTC) |
| **🗓️ Monthly reports** | `reports_monthly_enabled` | `true` | Enable monthly violation reports |
| **📅 Monthly report day** | `reports_monthly_day` | `1` | Day of month for monthly report (1-28) |
| **🕐 Monthly report time** | `reports_monthly_time` | `10:00` | Monthly report send time (HH:MM UTC) |
| **📐 Minimum score** | `reports_min_score` | `30.0` | Minimum violation score to include in report |
| **🏆 Top violators** | `reports_top_violators_count` | `10` | Number of users in top violators list |
| **📭 Send empty reports** | `reports_send_empty` | `false` | Send report when there are no violations for the period |
| **💬 Reports topic** | `reports_topic_id` | empty | Topic ID for sending reports (0 = main chat) (`NOTIFICATIONS_TOPIC_REPORTS`) |


## 💰 Finance

Infrastructure spending and income: reporting currency, exchange rates, payment reminders, sync with provider APIs.

| Setting | Key | Default | What it does |
|---|---|---|---|
| **Reporting currency** | `finance_base_currency` | `RUB` | Currency that aggregates are converted into (RUB, USD, EUR...) |
| **Auto-update exchange rates** | `finance_rates_auto_update` | `true` | Refresh rates once a day (CBR, falling back to open.er-api.com). Manually edited rates are left alone |
| **Payment reminders** | `finance_reminders_enabled` | `true` | Send notifications about upcoming and overdue payments to Telegram and the panel |
| **Remind this many days ahead** | `finance_reminder_days` | `7,3,1` | Comma-separated list of days before the charge (for example 7,3,1). Overdue payments are always reminded about |
| **Auto-sync hosting provider APIs** | `finance_autosync_enabled` | `true` | Periodically pull balance and services from connected hosting provider APIs |
| **Auto-sync interval (hours)** | `finance_autosync_interval_hours` | `6` | How often to poll provider APIs for balance, services and charge dates |
| **Pull charge dates** | `finance_autosync_update_due_dates` | `true` | Update next_due_at from provider data, matching services by name within a provider |
| **Record Bedolaga top-ups** | `finance_bedolaga_deposits_enabled` | `true` | Add balance top-ups from Bedolaga to income daily (P&L chart, monthly revenue). Do not combine with manual subscription revenue import — it would be counted twice |


## ⚡ Performance

Connection pools, cache and background task intervals. Worth touching when you hit a ceiling, not before.


### 🗄️ Database

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🗄️ DB Pool: min connections** | `db_pool_min_size` | `5` | Minimum number of connections in the PostgreSQL pool. Requires restart. (`DB_POOL_MIN_SIZE`) |
| **🗄️ DB Pool: max connections** | `db_pool_max_size` | `50` | Maximum number of connections in the PostgreSQL pool. Increase under heavy load. Requires restart. (`DB_POOL_MAX_SIZE`) |
| **⏱️ DB: statement timeout (sec)** | `db_statement_timeout` | `60` | Maximum SQL statement execution time in seconds. 0 = unlimited. Requires restart. |
| **💤 DB: idle connection lifetime (sec)** | `db_idle_connection_lifetime` | `300` | How long idle connections stay in the pool before being closed. Requires restart. |


### ⏱️ Intervals

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🔔 Alert check interval (sec)** | `alert_check_interval` | `60` | How often to evaluate alert rules. Lower = faster reaction, higher DB load. |
| **🔄 Config auto-reload (sec)** | `config_auto_reload_interval` | `30` | How often to reload configuration from the DB. Affects how quickly setting changes take effect. |


### 🚦 Rate limits

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🚦 API: requests/min (global)** | `api_rate_limit_per_minute` | `120` | Maximum API requests per minute per IP. 0 = unlimited. |
| **📡 Collector: rate limit** | `collector_rate_limit` | `1/second` | Rate limit for the node-agent metrics endpoint (format: '1/second'). |


### 💾 Cache

| Setting | Key | Default | What it does |
|---|---|---|---|
| **💾 Cache: max entries** | `cache_max_entries` | `5000` | Maximum entries in the in-memory cache. LRU eviction kicks in when exceeded. |
| **⏱️ Cache: default TTL (sec)** | `cache_default_ttl` | `300` | Default entry TTL. Lower = fresher data, more DB queries. |


### 🔍 Violation detection pipeline

| Setting | Key | Default | What it does |
|---|---|---|---|
| **⏱️ Violation queue: drain interval (sec)** | `violation_drain_interval` | `3.0` | How often the worker pulls a chunk of users from the queue. Lower = faster reaction, higher load. |
| **📦 Violation queue: chunk size** | `violation_chunk_size` | `200` | Users processed per cycle. Higher = queue drains faster, but peak load rises. |
| **🔀 Max background tasks** | `violation_max_background_tasks` | `20` | Maximum concurrent background tasks (torrents, etc.). New tasks are dropped when exceeded. |


## 🔄 Sync

Synchronisation with the Remnawave panel.

| Setting | Key | Default | What it does |
|---|---|---|---|
| **🔄 Sync interval** | `sync_interval_seconds` | `300` | Data sync interval with API (seconds, requires restart) (`SYNC_INTERVAL_SECONDS`) |


## Agent settings

Agent variables are set on the node itself and are not part of this list — see [Node Agent](/en/guide/node-agent#agent-variables).

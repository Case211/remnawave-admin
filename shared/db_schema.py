"""Shared database table/column constants.

Single source of truth for:
- Table names
- Column definitions (INSERT/UPDATE/SELECT)
- Counter column mappings

All code (bot, web backend) that touches admin tables should
reference these constants instead of hardcoding table/column names.
"""

from typing import List

# ── Table names ──────────────────────────────────────────────────

ADMIN_TABLE = "admin_accounts"
ADMIN_ROLES_TABLE = "admin_roles"
ADMIN_PERMISSIONS_TABLE = "admin_permissions"
AUDIT_TABLE = "admin_audit_log"
ADMIN_DEVICES_TABLE = "admin_devices"
ADMIN_ACCESS_POLICIES_TABLE = "admin_access_policies"

USERS_TABLE = "users"
NODES_TABLE = "nodes"
HOSTS_TABLE = "hosts"
USER_CONNECTIONS_TABLE = "user_connections"
IP_METADATA_TABLE = "ip_metadata"
VIOLATIONS_TABLE = "violations"
USER_BASELINES_TABLE = "user_baselines"
USER_HWID_DEVICES_TABLE = "user_hwid_devices"
VIOLATION_REPORTS_TABLE = "violation_reports"
VIOLATION_WHITELIST_TABLE = "violation_whitelist"
NODE_METRICS_SNAPSHOTS_TABLE = "node_metrics_snapshots"
NODE_ATTACK_EVENTS_TABLE = "node_attack_events"
USER_NODE_TRAFFIC_TABLE = "user_node_traffic"
NODE_SCRIPTS_TABLE = "node_scripts"
SETTINGS_TABLE = "settings"
SUBSCRIPTION_REQUEST_HISTORY_TABLE = "subscription_request_history"
BLOCKED_IPS_TABLE = "blocked_ips"
HWID_BLACKLIST_TABLE = "hwid_blacklist"
USER_BLACKLIST_TABLE = "user_blacklist"
FINANCE_CATEGORIES_TABLE = "finance_categories"
FINANCE_PROVIDERS_TABLE = "finance_providers"
FINANCE_ITEMS_TABLE = "finance_items"
FINANCE_PAYMENTS_TABLE = "finance_payments"
FINANCE_RATES_TABLE = "finance_rates"
FINANCE_ACCOUNTS_TABLE = "finance_provider_accounts"
FINANCE_SNAPSHOTS_TABLE = "finance_balance_snapshots"
ACCESS_POLICIES_TABLE = "access_policies"
ACCESS_POLICY_RULES_TABLE = "access_policy_rules"
ROLE_ACCESS_POLICIES_TABLE = "role_access_policies"
CONFIG_PROFILES_TABLE = "config_profiles"
SYNC_METADATA_TABLE = "sync_metadata"
API_TOKENS_TABLE = "api_tokens"
TEMPLATES_TABLE = "templates"
SNIPPETS_TABLE = "snippets"
SQUADS_TABLE = "squads"
INTERNAL_SQUADS_TABLE = "internal_squads"
EXTERNAL_SQUADS_TABLE = "external_squads"
AUTOMATION_RULES_TABLE = "automation_rules"
AUTOMATION_LOG_TABLE = "automation_log"
ALERT_RULES_TABLE = "alert_rules"
ALERT_RULE_LOG_TABLE = "alert_rule_log"
NODE_COMMAND_LOG_TABLE = "node_command_log"
WEBHOOK_SUBSCRIPTIONS_TABLE = "webhook_subscriptions"
WEBHOOK_DELIVERIES_TABLE = "webhook_deliveries"
WEBHOOK_RETRY_QUEUE_TABLE = "webhook_retry_queue"
DOMAIN_CONFIG_TABLE = "domain_config"
EMAIL_QUEUE_TABLE = "email_queue"
EMAIL_INBOX_TABLE = "email_inbox"
SMTP_CREDENTIALS_TABLE = "smtp_credentials"
SCHEDULED_TASKS_TABLE = "scheduled_tasks"
NODE_TRAFFIC_SNAPSHOTS_TABLE = "node_traffic_snapshots"
CONFIG_VERSIONS_TABLE = "config_versions"
USER_PRESETS_TABLE = "user_presets"
NODE_BSCHECK_TABLE = "node_bscheck"
BSCHECK_JOBS_TABLE = "bscheck_jobs"
WEBAUTHN_CREDENTIALS_TABLE = "webauthn_credentials"
OAUTH_LINKS_TABLE = "oauth_links"
ADMIN_SESSIONS_TABLE = "admin_sessions"
ONLINE_USERS_SNAPSHOTS_TABLE = "online_users_snapshots"
USER_NODE_TRAFFIC_HISTORY_TABLE = "user_node_traffic_history"
ASN_RUSSIA_TABLE = "asn_russia"
BOT_CONFIG_TABLE = "bot_config"
API_KEYS_TABLE = "api_keys"
SMTP_CONFIG_TABLE = "smtp_config"
NOTIFICATIONS_TABLE = "notifications"
NOTIFICATION_CHANNELS_TABLE = "notification_channels"
NOTIFICATION_CHANNEL_CONFIGS_TABLE = "notification_channel_configs"
ROLES_TABLE = "roles"

# ── All columns (in table order) ─────────────────────────────────

ADMIN_COLUMNS: List[str] = [
    "id",
    "username",
    "password_hash",
    "telegram_id",
    "role_id",
    "max_users",
    "max_traffic_gb",
    "max_nodes",
    "max_hosts",
    "is_active",
    "is_generated_password",
    "totp_secret",
    "totp_enabled",
    "backup_codes",
    "email",
    "unlimited_traffic_policy",
    "unrestricted_user_access",
    "has_bot_access",
    "users_created",
    "traffic_used_bytes",
    "nodes_created",
    "hosts_created",
    "created_by",
    "created_at",
    "updated_at",
]

ADMIN_COLUMNS_SET = frozenset(ADMIN_COLUMNS)

# ── Columns that can be set on INSERT (excluding auto-generated) ─

ADMIN_INSERT_COLUMNS: List[str] = [
    "username",
    "password_hash",
    "telegram_id",
    "role_id",
    "max_users",
    "max_traffic_gb",
    "max_nodes",
    "max_hosts",
    "unlimited_traffic_policy",
    "unrestricted_user_access",
    "has_bot_access",
    "is_generated_password",
    "created_by",
    "email",
]

# ── Columns that can be set on UPDATE ────────────────────────────

ADMIN_UPDATE_COLUMNS: List[str] = [
    "username",
    "password_hash",
    "telegram_id",
    "role_id",
    "max_users",
    "max_traffic_gb",
    "max_nodes",
    "max_hosts",
    "is_active",
    "is_generated_password",
    "totp_secret",
    "totp_enabled",
    "backup_codes",
    "email",
    "unlimited_traffic_policy",
    "unrestricted_user_access",
    "has_bot_access",
    "allowed_auth_methods",
]

ADMIN_UPDATE_COLUMNS_SET = frozenset(ADMIN_UPDATE_COLUMNS)

# ── Counter columns and their limits ─────────────────────────────

ADMIN_COUNTER_COLUMNS = {
    "users_created": "max_users",
    "nodes_created": "max_nodes",
    "hosts_created": "max_hosts",
}

# Not included as a counter: traffic_used_bytes (handled differently)

"""Structured error codes for API responses.

Usage:
    from web.backend.core.errors import api_error, E

    raise api_error(404, E.ADMIN_NOT_FOUND)
    raise api_error(400, E.INVALID_PASSWORD, "Current password is incorrect")
"""
from enum import Enum
from fastapi import HTTPException


class ErrorCode(str, Enum):
    """All API error codes. Frontend maps these to i18n translations."""

    # ── Auth ──────────────────────────────────────────────────
    INVALID_AUTH_HEADER = "INVALID_AUTH_HEADER"
    TOKEN_REQUIRED = "TOKEN_REQUIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_ALREADY_USED = "TOKEN_ALREADY_USED"
    INVALID_REFRESH_TOKEN = "INVALID_REFRESH_TOKEN"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED"
    ADMIN_NOT_FOUND = "ADMIN_NOT_FOUND"
    NOT_AN_ADMIN = "NOT_AN_ADMIN"
    INVALID_PASSWORD = "INVALID_PASSWORD"
    PASSWORD_UPDATE_FAILED = "PASSWORD_UPDATE_FAILED"
    INVALID_USERNAME = "INVALID_USERNAME"
    FORBIDDEN = "FORBIDDEN"
    EMAIL_NOT_CONFIGURED = "EMAIL_NOT_CONFIGURED"
    RESET_TOKEN_INVALID = "RESET_TOKEN_INVALID"

    # ── Admins ────────────────────────────────────────────────
    USERNAME_EXISTS = "USERNAME_EXISTS"
    CANNOT_MODIFY_SELF = "CANNOT_MODIFY_SELF"
    ADMIN_CREATE_FAILED = "ADMIN_CREATE_FAILED"
    ADMIN_UPDATE_FAILED = "ADMIN_UPDATE_FAILED"
    ADMIN_DELETE_FAILED = "ADMIN_DELETE_FAILED"

    # ── Roles ─────────────────────────────────────────────────
    ROLE_NOT_FOUND = "ROLE_NOT_FOUND"
    ROLE_NAME_EXISTS = "ROLE_NAME_EXISTS"
    ROLE_CREATE_FAILED = "ROLE_CREATE_FAILED"
    ROLE_UPDATE_FAILED = "ROLE_UPDATE_FAILED"
    ROLE_DELETE_FAILED = "ROLE_DELETE_FAILED"
    SYSTEM_ROLE_PROTECTED = "SYSTEM_ROLE_PROTECTED"
    UNKNOWN_RESOURCE = "UNKNOWN_RESOURCE"
    INVALID_ACTION = "INVALID_ACTION"

    # ── Users ─────────────────────────────────────────────────
    USER_NOT_FOUND = "USER_NOT_FOUND"
    SYNC_FAILED = "SYNC_FAILED"
    TRAFFIC_LIMIT_BELOW_USAGE = "TRAFFIC_LIMIT_BELOW_USAGE"

    # User creation / update — quota errors
    USERS_QUOTA_EXCEEDED = "USERS_QUOTA_EXCEEDED"
    TRAFFIC_QUOTA_EXCEEDED = "TRAFFIC_QUOTA_EXCEEDED"
    NODES_QUOTA_EXCEEDED = "NODES_QUOTA_EXCEEDED"
    HOSTS_QUOTA_EXCEEDED = "HOSTS_QUOTA_EXCEEDED"

    # User creation / update — validation errors
    USERNAME_REQUIRED = "USERNAME_REQUIRED"
    USERNAME_TOO_LONG = "USERNAME_TOO_LONG"
    USERNAME_INVALID_FORMAT = "USERNAME_INVALID_FORMAT"
    USERNAME_ALREADY_EXISTS = "USERNAME_ALREADY_EXISTS"
    TRAFFIC_LIMIT_REQUIRED = "TRAFFIC_LIMIT_REQUIRED"
    TRAFFIC_LIMIT_NEGATIVE = "TRAFFIC_LIMIT_NEGATIVE"
    TRAFFIC_LIMIT_TOO_SMALL = "TRAFFIC_LIMIT_TOO_SMALL"
    INVALID_EMAIL_FORMAT = "INVALID_EMAIL_FORMAT"
    INVALID_TELEGRAM_ID = "INVALID_TELEGRAM_ID"
    INVALID_HWID_DEVICE_LIMIT = "INVALID_HWID_DEVICE_LIMIT"
    INVALID_EXPIRE_DATE = "INVALID_EXPIRE_DATE"
    TAG_TOO_LONG = "TAG_TOO_LONG"
    DESCRIPTION_TOO_LONG = "DESCRIPTION_TOO_LONG"

    # User creation — Panel API side
    PANEL_REJECTED_USERNAME = "PANEL_REJECTED_USERNAME"
    PANEL_REJECTED_TRAFFIC_STRATEGY = "PANEL_REJECTED_TRAFFIC_STRATEGY"
    PANEL_REJECTED_STATUS = "PANEL_REJECTED_STATUS"
    PANEL_REJECTED_SQUAD = "PANEL_REJECTED_SQUAD"
    PANEL_REJECTED_TAG = "PANEL_REJECTED_TAG"
    PANEL_REJECTED_GENERIC = "PANEL_REJECTED_GENERIC"
    PANEL_USER_ALREADY_EXISTS = "PANEL_USER_ALREADY_EXISTS"

    # ── Nodes ─────────────────────────────────────────────────
    NODE_NOT_FOUND = "NODE_NOT_FOUND"
    TOKEN_GENERATE_FAILED = "TOKEN_GENERATE_FAILED"
    TOKEN_REVOKE_FAILED = "TOKEN_REVOKE_FAILED"

    # ── Hosts ─────────────────────────────────────────────────
    HOST_NOT_FOUND = "HOST_NOT_FOUND"
    HOST_CREATE_FAILED = "HOST_CREATE_FAILED"
    HOST_UPDATE_FAILED = "HOST_UPDATE_FAILED"
    HOST_DELETE_FAILED = "HOST_DELETE_FAILED"
    HOST_ENABLE_FAILED = "HOST_ENABLE_FAILED"
    HOST_DISABLE_FAILED = "HOST_DISABLE_FAILED"

    # ── Violations ────────────────────────────────────────────
    VIOLATION_NOT_FOUND = "VIOLATION_NOT_FOUND"
    VIOLATION_UPDATE_FAILED = "VIOLATION_UPDATE_FAILED"
    WHITELIST_ADD_FAILED = "WHITELIST_ADD_FAILED"
    WHITELIST_USER_NOT_FOUND = "WHITELIST_USER_NOT_FOUND"

    # ── Automations ───────────────────────────────────────────
    AUTOMATION_NOT_FOUND = "AUTOMATION_NOT_FOUND"
    AUTOMATION_CREATE_FAILED = "AUTOMATION_CREATE_FAILED"
    AUTOMATION_UPDATE_FAILED = "AUTOMATION_UPDATE_FAILED"
    AUTOMATION_TOGGLE_FAILED = "AUTOMATION_TOGGLE_FAILED"
    AUTOMATION_DELETE_FAILED = "AUTOMATION_DELETE_FAILED"
    AUTOMATION_ACTIVATE_FAILED = "AUTOMATION_ACTIVATE_FAILED"
    TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"

    # ── Settings ──────────────────────────────────────────────
    SETTING_NOT_FOUND = "SETTING_NOT_FOUND"
    SETTING_READONLY = "SETTING_READONLY"

    # ── Scripts ───────────────────────────────────────────────
    SCRIPT_NOT_FOUND = "SCRIPT_NOT_FOUND"
    BUILTIN_SCRIPT_PROTECTED = "BUILTIN_SCRIPT_PROTECTED"
    AGENT_NOT_CONNECTED = "AGENT_NOT_CONNECTED"
    AGENT_TOKEN_NOT_FOUND = "AGENT_TOKEN_NOT_FOUND"
    AGENT_COMMAND_FAILED = "AGENT_COMMAND_FAILED"
    EXECUTION_NOT_FOUND = "EXECUTION_NOT_FOUND"
    INVALID_GITHUB_URL = "INVALID_GITHUB_URL"
    CONTENT_TOO_LARGE = "CONTENT_TOO_LARGE"
    REPO_NOT_FOUND = "REPO_NOT_FOUND"

    # ── Notifications ─────────────────────────────────────────
    NOTIFICATION_NOT_FOUND = "NOTIFICATION_NOT_FOUND"
    CHANNEL_NOT_FOUND = "CHANNEL_NOT_FOUND"
    ALERT_RULE_NOT_FOUND = "ALERT_RULE_NOT_FOUND"
    SMTP_NOT_CONFIGURED = "SMTP_NOT_CONFIGURED"
    SMTP_UPDATE_FAILED = "SMTP_UPDATE_FAILED"
    SMTP_CREDENTIAL_NOT_FOUND = "SMTP_CREDENTIAL_NOT_FOUND"

    # ── Mail ──────────────────────────────────────────────────
    DOMAIN_NOT_FOUND = "DOMAIN_NOT_FOUND"
    NO_OUTBOUND_DOMAIN = "NO_OUTBOUND_DOMAIN"
    QUEUE_ITEM_NOT_FOUND = "QUEUE_ITEM_NOT_FOUND"
    MESSAGE_NOT_FOUND = "MESSAGE_NOT_FOUND"
    ATTACHMENT_NOT_FOUND = "ATTACHMENT_NOT_FOUND"
    SUPPRESSION_NOT_FOUND = "SUPPRESSION_NOT_FOUND"

    # ── Reports / ASN ─────────────────────────────────────────
    REPORT_NOT_FOUND = "REPORT_NOT_FOUND"
    ASN_NOT_FOUND = "ASN_NOT_FOUND"

    # ── Backups ─────────────────────────────────────────────────
    BACKUP_NOT_FOUND = "BACKUP_NOT_FOUND"
    BACKUP_CREATE_FAILED = "BACKUP_CREATE_FAILED"
    BACKUP_RESTORE_FAILED = "BACKUP_RESTORE_FAILED"
    BACKUP_DELETE_FAILED = "BACKUP_DELETE_FAILED"
    IMPORT_FAILED = "IMPORT_FAILED"
    INVALID_FILENAME = "INVALID_FILENAME"

    # ── Blocked IPs ──────────────────────────────────────────
    BLOCKED_IP_NOT_FOUND = "BLOCKED_IP_NOT_FOUND"
    BLOCKED_IP_DUPLICATE = "BLOCKED_IP_DUPLICATE"
    BLOCKED_IP_INVALID_CIDR = "BLOCKED_IP_INVALID_CIDR"
    BLOCKED_IP_ADD_FAILED = "BLOCKED_IP_ADD_FAILED"

    # ── Generic ───────────────────────────────────────────────
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    NO_FIELDS_TO_UPDATE = "NO_FIELDS_TO_UPDATE"
    API_SERVICE_UNAVAILABLE = "API_SERVICE_UNAVAILABLE"
    DB_UNAVAILABLE = "DB_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    VALIDATION = "VALIDATION"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    NOT_FOUND = "NOT_FOUND"


# Shorthand alias
E = ErrorCode

# Default human-readable messages per code (English fallback)
_DEFAULT_MESSAGES: dict[str, str] = {
    E.ADMIN_NOT_FOUND: "Admin not found",
    E.USERNAME_EXISTS: "Username already exists",
    E.ROLE_NOT_FOUND: "Role not found",
    E.CANNOT_MODIFY_SELF: "Cannot modify your own account",
    E.USER_NOT_FOUND: "User not found",
    E.TRAFFIC_LIMIT_BELOW_USAGE: "Cannot set traffic limit below current usage.",
    E.USERS_QUOTA_EXCEEDED: "You have reached the maximum number of users allowed for your account.",
    E.TRAFFIC_QUOTA_EXCEEDED: "Traffic limit exceeds your quota.",
    E.NODES_QUOTA_EXCEEDED: "You have reached the maximum number of nodes allowed for your account.",
    E.HOSTS_QUOTA_EXCEEDED: "You have reached the maximum number of hosts allowed for your account.",
    E.USERNAME_REQUIRED: "Username is required.",
    E.USERNAME_TOO_LONG: "Username is too long.",
    E.USERNAME_INVALID_FORMAT: "Username contains invalid characters. Use 1-100 letters, digits, underscores, or hyphens.",
    E.USERNAME_ALREADY_EXISTS: "A user with this username already exists.",
    E.TRAFFIC_LIMIT_REQUIRED: "Traffic limit is required. Unlimited traffic is disabled for your role.",
    E.TRAFFIC_LIMIT_NEGATIVE: "Traffic limit cannot be negative.",
    E.TRAFFIC_LIMIT_TOO_SMALL: "Traffic limit is too small. Minimum is 1 MB.",
    E.INVALID_EMAIL_FORMAT: "Email address is not valid.",
    E.INVALID_TELEGRAM_ID: "Telegram ID is not valid.",
    E.INVALID_HWID_DEVICE_LIMIT: "HWID device limit must be 0 (unlimited) or a positive integer.",
    E.INVALID_EXPIRE_DATE: "Expiration date must be in the future.",
    E.TAG_TOO_LONG: "Tag is too long.",
    E.DESCRIPTION_TOO_LONG: "Description is too long.",
    E.PANEL_REJECTED_USERNAME: "Panel rejected the username.",
    E.PANEL_REJECTED_TRAFFIC_STRATEGY: "Panel rejected the traffic limit strategy.",
    E.PANEL_REJECTED_STATUS: "Panel rejected the status value.",
    E.PANEL_REJECTED_SQUAD: "Panel rejected the squad reference.",
    E.PANEL_REJECTED_TAG: "Panel rejected the tag value.",
    E.PANEL_REJECTED_GENERIC: "Panel rejected the request.",
    E.PANEL_USER_ALREADY_EXISTS: "A user with this username already exists in the panel.",
    E.NODE_NOT_FOUND: "Node not found",
    E.HOST_NOT_FOUND: "Host not found",
    E.VIOLATION_NOT_FOUND: "Violation not found",
    E.AUTOMATION_NOT_FOUND: "Automation rule not found",
    E.SETTING_NOT_FOUND: "Setting not found",
    E.SETTING_READONLY: "Setting is read-only",
    E.SCRIPT_NOT_FOUND: "Script not found",
    E.NOTIFICATION_NOT_FOUND: "Notification not found",
    E.CHANNEL_NOT_FOUND: "Channel not found",
    E.ALERT_RULE_NOT_FOUND: "Alert rule not found",
    E.DOMAIN_NOT_FOUND: "Domain not found",
    E.ATTACHMENT_NOT_FOUND: "Attachment not found",
    E.SUPPRESSION_NOT_FOUND: "Suppressed address not found",
    E.REPORT_NOT_FOUND: "Report not found",
    E.ASN_NOT_FOUND: "ASN not found",
    E.BLOCKED_IP_NOT_FOUND: "Blocked IP not found",
    E.BLOCKED_IP_DUPLICATE: "IP already blocked",
    E.BLOCKED_IP_INVALID_CIDR: "Invalid IP or CIDR notation",
    E.BLOCKED_IP_ADD_FAILED: "Failed to add blocked IP",
    E.BACKUP_NOT_FOUND: "Backup file not found",
    E.BACKUP_CREATE_FAILED: "Failed to create backup",
    E.BACKUP_RESTORE_FAILED: "Failed to restore backup",
    E.BACKUP_DELETE_FAILED: "Failed to delete backup",
    E.IMPORT_FAILED: "Import failed",
    E.INVALID_FILENAME: "Invalid filename",
    E.QUOTA_EXCEEDED: "Resource quota exceeded",
    E.API_SERVICE_UNAVAILABLE: "API service not available",
    E.DB_UNAVAILABLE: "Database not available",
    E.INTERNAL_ERROR: "Internal error",
    E.NO_FIELDS_TO_UPDATE: "No fields to update",
    E.FORBIDDEN: "Access denied",
    E.INVALID_INPUT: "Invalid input",
    E.VALIDATION: "Validation error",
    E.ALREADY_EXISTS: "Resource already exists",
    E.NOT_FOUND: "Resource not found",
}


def api_error(
    status_code: int,
    code: ErrorCode | str,
    detail: str | None = None,
) -> HTTPException:
    """Create an HTTPException with a structured error code.

    Args:
        status_code: HTTP status code (400, 404, 500, etc.)
        code: ErrorCode enum value or a plain string code. Часть вызовов
            передаёт код строкой ("NO_CHAT_ID") — раньше это роняло сам
            api_error (AttributeError на .value) и превращало осмысленный
            400 в невнятный 500.
        detail: Human-readable message. If None, uses default for the code.

    Returns:
        HTTPException with JSON body {"detail": "...", "code": "ERROR_CODE"}
    """
    code_value = code.value if isinstance(code, ErrorCode) else str(code)
    message = detail or _DEFAULT_MESSAGES.get(code, code_value)
    return HTTPException(
        status_code=status_code,
        detail={"detail": message, "code": code_value},
    )

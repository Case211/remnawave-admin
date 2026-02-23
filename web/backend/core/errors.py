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

    # ── Reports / ASN ─────────────────────────────────────────
    REPORT_NOT_FOUND = "REPORT_NOT_FOUND"
    ASN_NOT_FOUND = "ASN_NOT_FOUND"

    # ── Generic ───────────────────────────────────────────────
    NO_FIELDS_TO_UPDATE = "NO_FIELDS_TO_UPDATE"
    API_SERVICE_UNAVAILABLE = "API_SERVICE_UNAVAILABLE"
    DB_UNAVAILABLE = "DB_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Shorthand alias
E = ErrorCode

# Default human-readable messages per code (English fallback)
_DEFAULT_MESSAGES: dict[str, str] = {
    E.ADMIN_NOT_FOUND: "Admin not found",
    E.USERNAME_EXISTS: "Username already exists",
    E.ROLE_NOT_FOUND: "Role not found",
    E.CANNOT_MODIFY_SELF: "Cannot modify your own account",
    E.USER_NOT_FOUND: "User not found",
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
    E.REPORT_NOT_FOUND: "Report not found",
    E.ASN_NOT_FOUND: "ASN not found",
    E.API_SERVICE_UNAVAILABLE: "API service not available",
    E.DB_UNAVAILABLE: "Database not available",
    E.INTERNAL_ERROR: "Internal error",
    E.NO_FIELDS_TO_UPDATE: "No fields to update",
    E.FORBIDDEN: "Access denied",
}


def api_error(
    status_code: int,
    code: ErrorCode,
    detail: str | None = None,
) -> HTTPException:
    """Create an HTTPException with a structured error code.

    Args:
        status_code: HTTP status code (400, 404, 500, etc.)
        code: ErrorCode enum value
        detail: Human-readable message. If None, uses default for the code.

    Returns:
        HTTPException with JSON body {"detail": "...", "code": "ERROR_CODE"}
    """
    message = detail or _DEFAULT_MESSAGES.get(code, code.value)
    return HTTPException(
        status_code=status_code,
        detail={"detail": message, "code": code.value},
    )

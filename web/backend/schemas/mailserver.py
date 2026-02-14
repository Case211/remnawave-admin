"""Pydantic schemas for the embedded mail server."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Domain Config ────────────────────────────────────────────────

class DomainCreate(BaseModel):
    domain: str
    from_name: Optional[str] = None
    inbound_enabled: bool = False
    outbound_enabled: bool = True
    max_send_per_hour: int = 100


class DomainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain: str
    is_active: bool = False
    dkim_selector: str = "rw"
    dkim_public_key: Optional[str] = None
    from_name: Optional[str] = None
    inbound_enabled: bool = False
    outbound_enabled: bool = True
    max_send_per_hour: int = 100
    dns_mx_ok: bool = False
    dns_spf_ok: bool = False
    dns_dkim_ok: bool = False
    dns_dmarc_ok: bool = False
    dns_ptr_ok: bool = False
    dns_checked_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DomainUpdate(BaseModel):
    is_active: Optional[bool] = None
    from_name: Optional[str] = None
    inbound_enabled: Optional[bool] = None
    outbound_enabled: Optional[bool] = None
    max_send_per_hour: Optional[int] = None
    dkim_selector: Optional[str] = None


# ── DNS Records ──────────────────────────────────────────────────

class DnsRecordItem(BaseModel):
    record_type: str
    host: str
    value: str
    purpose: str
    is_configured: bool = False
    current_value: Optional[str] = None


class DnsCheckResult(BaseModel):
    domain: str
    mx_ok: bool = False
    spf_ok: bool = False
    dkim_ok: bool = False
    dmarc_ok: bool = False
    ptr_ok: bool = False


# ── Email Queue ──────────────────────────────────────────────────

class EmailQueueItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_email: str
    to_email: str
    subject: str
    status: str = "pending"
    category: Optional[str] = None
    priority: int = 0
    attempts: int = 0
    max_attempts: int = 5
    last_error: Optional[str] = None
    message_id: Optional[str] = None
    created_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None


class EmailQueueDetail(EmailQueueItem):
    from_name: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    smtp_response: Optional[str] = None
    last_attempt_at: Optional[datetime] = None
    next_attempt_at: Optional[datetime] = None
    domain_id: Optional[int] = None


class QueueStats(BaseModel):
    pending: int = 0
    sending: int = 0
    sent: int = 0
    failed: int = 0
    total: int = 0


# ── Email Inbox ──────────────────────────────────────────────────

class InboxItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mail_from: Optional[str] = None
    rcpt_to: str
    from_header: Optional[str] = None
    subject: Optional[str] = None
    date_header: Optional[datetime] = None
    is_read: bool = False
    is_spam: bool = False
    has_attachments: bool = False
    attachment_count: int = 0
    created_at: Optional[datetime] = None


class InboxDetail(InboxItem):
    to_header: Optional[str] = None
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    remote_ip: Optional[str] = None
    remote_hostname: Optional[str] = None
    spam_score: float = 0


class InboxMarkRead(BaseModel):
    ids: List[int] = Field(default_factory=list)


# ── SMTP Credentials ─────────────────────────────────────────────

class SmtpCredentialCreate(BaseModel):
    username: str
    password: str
    description: Optional[str] = None
    allowed_from_domains: List[str] = Field(default_factory=list)
    max_send_per_hour: int = 100


class SmtpCredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    description: Optional[str] = None
    is_active: bool = True
    allowed_from_domains: List[str] = Field(default_factory=list)
    max_send_per_hour: int = 100
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SmtpCredentialUpdate(BaseModel):
    password: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    allowed_from_domains: Optional[List[str]] = None
    max_send_per_hour: Optional[int] = None


# ── Compose ──────────────────────────────────────────────────────

class ComposeEmail(BaseModel):
    to_email: str
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    domain_id: Optional[int] = None

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
    # 0 = inherit the global mailserver_max_send_per_hour; >0 = per-domain override
    max_send_per_hour: int = 0


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
    max_send_per_hour: int = 0  # 0 = inherit global mailserver_max_send_per_hour
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
    # Результаты проверки отправителя — по ним в списке видно подделку
    # раньше, чем письмо откроют.
    spf_result: Optional[str] = None
    dkim_result: Optional[str] = None
    dmarc_result: Optional[str] = None
    spam_score: float = 0


class InboxDetail(InboxItem):
    to_header: Optional[str] = None
    message_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    refs_header: Optional[str] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    remote_ip: Optional[str] = None
    remote_hostname: Optional[str] = None
    auth_details: Dict[str, Any] = Field(default_factory=dict)
    attachments: List["AttachmentItem"] = Field(default_factory=list)


class InboxMarkRead(BaseModel):
    ids: List[int] = Field(default_factory=list)


class UnreadCount(BaseModel):
    unread: int = 0


# ── Вложения ─────────────────────────────────────────────────────

class AttachmentItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str = "application/octet-stream"
    size_bytes: int = 0
    is_inline: bool = False


# ── Ответ на письмо ──────────────────────────────────────────────

class ReplyEmail(BaseModel):
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    subject: Optional[str] = None
    # Адрес, с которого отвечаем. Пусто — тот, на который письмо пришло:
    # человек ждёт ответа оттуда же, куда писал.
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    quote_original: bool = True


# ── Подавленные адреса ───────────────────────────────────────────

class SuppressionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    reason: str
    detail: Optional[str] = None
    smtp_code: Optional[str] = None
    hits: int = 1
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SuppressionCreate(BaseModel):
    email: str
    reason: str = "manual"
    detail: Optional[str] = None


# ── DMARC ────────────────────────────────────────────────────────

class DmarcReportItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: str
    org_name: Optional[str] = None
    domain: str
    date_begin: datetime
    date_end: datetime
    total_messages: int = 0
    passed_messages: int = 0
    failed_messages: int = 0
    created_at: Optional[datetime] = None


class DmarcReportDetail(DmarcReportItem):
    org_email: Optional[str] = None
    policy: Dict[str, Any] = Field(default_factory=dict)
    records: List[Dict[str, Any]] = Field(default_factory=list)


class DmarcSummary(BaseModel):
    reports: int = 0
    total_messages: int = 0
    passed_messages: int = 0
    failed_messages: int = 0
    # Отправители, чьи письма не прошли проверку — здесь виден и чужой
    # спуфинг, и собственный сервис, забывший про DKIM.
    top_failing_sources: List[Dict[str, Any]] = Field(default_factory=list)


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


# AttachmentItem объявлен после InboxDetail, который на него ссылается —
# без пересборки pydantic оставит ссылку неразрешённой.
InboxDetail.model_rebuild()

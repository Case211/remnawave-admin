"""Mail server API endpoints."""
import json
import logging
import re
from email.header import decode_header as _decode_mime_header
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from shared.db_schema import (
    DMARC_REPORTS_TABLE,
    DOMAIN_CONFIG_TABLE,
    EMAIL_ATTACHMENTS_TABLE,
    EMAIL_INBOX_TABLE,
    EMAIL_QUEUE_TABLE,
    EMAIL_SUPPRESSION_TABLE,
    SMTP_CREDENTIALS_TABLE,
)
from shared.db_query import select_sql, insert_sql, update_sql, delete_sql

from web.backend.core.errors import api_error, E


def _decode_subject(raw: str | None) -> str:
    """Decode MIME-encoded subject like =?utf-8?b?...?= to readable text."""
    if not raw or '=?' not in raw:
        return raw or ''
    try:
        parts = _decode_mime_header(raw)
        decoded = []
        for data, charset in parts:
            if isinstance(data, bytes):
                decoded.append(data.decode(charset or 'utf-8', errors='replace'))
            else:
                decoded.append(data)
        return ' '.join(decoded)
    except Exception:
        return raw
from web.backend.api.deps import AdminUser, get_client_ip, require_permission
from web.backend.core.audit import write_audit_log
from web.backend.schemas.mailserver import (
    AttachmentItem,
    ComposeEmail,
    DmarcReportDetail,
    DmarcReportItem,
    DmarcSummary,
    DnsCheckResult,
    DnsRecordItem,
    DomainCreate,
    DomainRead,
    DomainUpdate,
    EmailQueueDetail,
    EmailQueueItem,
    InboxDetail,
    InboxItem,
    InboxMarkRead,
    QueueStats,
    ReplyEmail,
    SmtpCredentialCreate,
    SmtpCredentialRead,
    SmtpCredentialUpdate,
    SuppressionCreate,
    SuppressionItem,
    UnreadCount,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mailserver", tags=["mailserver"])


# ── Domain endpoints ──────────────────────────────────────────────

@router.post("/domains", response_model=DomainRead)
async def create_domain(
    payload: DomainCreate,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "create")),
):
    """Create a new mail domain with auto-generated DKIM keys."""
    from web.backend.core.mail.mail_service import mail_service

    try:
        row = await mail_service.setup_domain(payload.domain)
        # Apply extra settings
        from shared.database import db_service
        async with db_service.acquire() as conn:
            await conn.execute(
                update_sql(DOMAIN_CONFIG_TABLE, "inbound_enabled = $1, outbound_enabled = $2, max_send_per_hour = $3, from_name = $4", "id = $5"),
                payload.inbound_enabled, payload.outbound_enabled,
                payload.max_send_per_hour, payload.from_name, row["id"],
            )
            updated = await conn.fetchrow(select_sql(DOMAIN_CONFIG_TABLE, "*", "WHERE id = $1"), row["id"])
        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="mailserver.create_domain", resource="mailserver",
            resource_id=str(row["id"]),
            details=json.dumps({"domain": payload.domain}),
            ip_address=get_client_ip(request),
        )
        return dict(updated)
    except Exception as e:
        logger.error("Domain creation failed: %s", e)
        raise HTTPException(status_code=400, detail="Internal server error")


@router.get("/domains", response_model=List[DomainRead])
async def list_domains(
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """List all configured mail domains."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        rows = await conn.fetch(select_sql(DOMAIN_CONFIG_TABLE, "*", "ORDER BY id"))
    return [dict(r) for r in rows]


@router.get("/domains/{domain_id}", response_model=DomainRead)
async def get_domain(
    domain_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Get domain details."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(select_sql(DOMAIN_CONFIG_TABLE, "*", "WHERE id = $1"), domain_id)
    if not row:
        raise api_error(404, E.DOMAIN_NOT_FOUND)
    return dict(row)


@router.put("/domains/{domain_id}", response_model=DomainRead)
async def update_domain(
    domain_id: int,
    payload: DomainUpdate,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "edit")),
):
    """Update domain settings."""
    from shared.database import db_service

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise api_error(400, E.NO_FIELDS_TO_UPDATE)

    set_clauses = []
    values = []
    idx = 1
    for key, val in updates.items():
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    set_clauses.append(f"updated_at = NOW()")
    values.append(domain_id)

    query = update_sql(DOMAIN_CONFIG_TABLE, ', '.join(set_clauses), f"id = ${idx}", returning="*")
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(query, *values)
    if not row:
        raise api_error(404, E.DOMAIN_NOT_FOUND)
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="mailserver.update_domain", resource="mailserver",
        resource_id=str(domain_id),
        details=json.dumps({"updated_fields": list(updates.keys())}),
        ip_address=get_client_ip(request),
    )
    return dict(row)


@router.delete("/domains/{domain_id}")
async def delete_domain(
    domain_id: int,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "delete")),
):
    """Delete a domain and its DKIM keys."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        deleted = await conn.execute(delete_sql(DOMAIN_CONFIG_TABLE, "id = $1"), domain_id)
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="mailserver.delete_domain", resource="mailserver",
        resource_id=str(domain_id),
        details=json.dumps({"domain_id": domain_id}),
        ip_address=get_client_ip(request),
    )
    return {"ok": True}


@router.post("/domains/{domain_id}/check-dns", response_model=DnsCheckResult)
async def check_domain_dns(
    domain_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Run DNS verification for a domain."""
    from web.backend.core.mail.mail_service import mail_service
    result = await mail_service.check_domain_dns(domain_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/domains/{domain_id}/dns-records", response_model=List[DnsRecordItem])
async def get_domain_dns_records(
    domain_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Get required DNS records for a domain."""
    from web.backend.core.mail.mail_service import mail_service
    records = await mail_service.get_domain_dns_records(domain_id)
    if not records:
        raise api_error(404, E.DOMAIN_NOT_FOUND)
    return records


# ── Queue endpoints ───────────────────────────────────────────────

@router.get("/queue", response_model=List[EmailQueueItem])
async def list_queue(
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """List outbound email queue."""
    from shared.database import db_service

    conditions = []
    params = []
    idx = 1

    if status_filter:
        conditions.append(f"status = ${idx}")
        params.append(status_filter)
        idx += 1
    if category:
        conditions.append(f"category = ${idx}")
        params.append(category)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    query = select_sql(EMAIL_QUEUE_TABLE,
        "id, from_email, to_email, subject, status, category, priority, attempts, max_attempts, last_error, message_id, created_at, sent_at",
        f"{where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}")

    async with db_service.acquire() as conn:
        rows = await conn.fetch(query, *params)
    result = []
    for r in rows:
        d = dict(r)
        d["subject"] = _decode_subject(d.get("subject"))
        result.append(d)
    return result


@router.get("/queue/stats", response_model=QueueStats)
async def get_queue_stats(
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Get queue statistics."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            select_sql(EMAIL_QUEUE_TABLE,
                "COUNT(*) FILTER (WHERE status = 'pending') AS pending, "
                "COUNT(*) FILTER (WHERE status = 'sending') AS sending, "
                "COUNT(*) FILTER (WHERE status = 'sent') AS sent, "
                "COUNT(*) FILTER (WHERE status = 'failed' AND attempts >= max_attempts) AS failed, "
                "COUNT(*) AS total")
        )
    return dict(row)


@router.get("/queue/{item_id}", response_model=EmailQueueDetail)
async def get_queue_item(
    item_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Get queue item details."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(select_sql(EMAIL_QUEUE_TABLE, "*", "WHERE id = $1"), item_id)
    if not row:
        raise api_error(404, E.QUEUE_ITEM_NOT_FOUND)
    d = dict(row)
    d["subject"] = _decode_subject(d.get("subject"))
    return d


@router.post("/queue/{item_id}/retry")
async def retry_queue_item(
    item_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "edit")),
):
    """Retry a failed queue item."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        result = await conn.execute(
            update_sql(EMAIL_QUEUE_TABLE, "status = 'pending', attempts = 0, next_attempt_at = NOW(), last_error = NULL", "id = $1 AND status = 'failed'"),
            item_id,
        )
    return {"ok": True}


@router.post("/queue/{item_id}/cancel")
async def cancel_queue_item(
    item_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "edit")),
):
    """Cancel a pending queue item."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        await conn.execute(
            update_sql(EMAIL_QUEUE_TABLE, "status = 'cancelled'", "id = $1 AND status IN ('pending', 'failed')"),
            item_id,
        )
    return {"ok": True}


@router.delete("/queue")
async def clear_old_queue(
    days: int = Query(30, ge=1, le=365),
    admin: AdminUser = Depends(require_permission("mailserver", "delete")),
):
    """Clear queue items older than N days."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        result = await conn.execute(
            delete_sql(EMAIL_QUEUE_TABLE, "created_at < NOW() - ($1 || ' days')::INTERVAL"),
            str(days),
        )
    return {"ok": True, "deleted": result}


# ── Inbox endpoints ───────────────────────────────────────────────

@router.get("/inbox", response_model=List[InboxItem])
async def list_inbox(
    is_read: Optional[bool] = None,
    is_spam: Optional[bool] = None,
    has_attachments: Optional[bool] = None,
    rcpt_to: Optional[str] = None,
    q: Optional[str] = Query(None, description="Поиск по теме, отправителю и тексту"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """List inbox messages."""
    from shared.database import db_service

    conditions = []
    params = []
    idx = 1

    if is_read is not None:
        conditions.append(f"is_read = ${idx}")
        params.append(is_read)
        idx += 1
    if is_spam is not None:
        conditions.append(f"is_spam = ${idx}")
        params.append(is_spam)
        idx += 1
    if has_attachments is not None:
        conditions.append(f"has_attachments = ${idx}")
        params.append(has_attachments)
        idx += 1
    if rcpt_to:
        conditions.append(f"lower(rcpt_to) = lower(${idx})")
        params.append(rcpt_to)
        idx += 1
    if q:
        # Тема в письме бывает закодирована (=?utf-8?B?...?=), поэтому поиск
        # по ней одной ненадёжен — ищем заодно по отправителю и телу.
        conditions.append(
            f"(subject ILIKE ${idx} OR from_header ILIKE ${idx} OR body_text ILIKE ${idx})"
        )
        params.append(f"%{q}%")
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])

    query = select_sql(EMAIL_INBOX_TABLE,
        "id, mail_from, rcpt_to, from_header, subject, date_header, is_read, is_spam, "
        "has_attachments, attachment_count, created_at, spf_result, dkim_result, "
        "dmarc_result, spam_score",
        f"{where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}")

    async with db_service.acquire() as conn:
        rows = await conn.fetch(query, *params)
    result = []
    for r in rows:
        d = dict(r)
        d["subject"] = _decode_subject(d.get("subject"))
        result.append(d)
    return result


@router.get("/inbox/unread-count", response_model=UnreadCount)
async def get_unread_count(
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Сколько писем не прочитано — для счётчика в меню."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        count = await conn.fetchval(
            select_sql(EMAIL_INBOX_TABLE, "COUNT(*)", "WHERE is_read = false AND is_spam = false")
        )
    return {"unread": count or 0}


@router.get("/inbox/{item_id}", response_model=InboxDetail)
async def get_inbox_item(
    item_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Get full inbox message."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(select_sql(EMAIL_INBOX_TABLE, "*", "WHERE id = $1"), item_id)
        if not row:
            raise api_error(404, E.MESSAGE_NOT_FOUND)
        attachments = await conn.fetch(
            select_sql(EMAIL_ATTACHMENTS_TABLE,
                "id, filename, content_type, size_bytes, is_inline",
                "WHERE inbox_id = $1 ORDER BY id"),
            item_id,
        )
    d = dict(row)
    d["subject"] = _decode_subject(d.get("subject"))
    # Само содержимое письма наружу не отдаём: в raw лежит base64 вложений,
    # и на письме с картинками ответ распухает до мегабайтов без всякой пользы.
    d.pop("raw_message", None)
    if isinstance(d.get("auth_details"), str):
        try:
            d["auth_details"] = json.loads(d["auth_details"])
        except ValueError:
            d["auth_details"] = {}
    d["attachments"] = [dict(a) for a in attachments]
    return d


@router.get("/inbox/{item_id}/attachments", response_model=List[AttachmentItem])
async def list_inbox_attachments(
    item_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Файлы, приложенные к письму."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            select_sql(EMAIL_ATTACHMENTS_TABLE,
                "id, filename, content_type, size_bytes, is_inline",
                "WHERE inbox_id = $1 ORDER BY id"),
            item_id,
        )
    return [dict(r) for r in rows]


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Скачать вложение."""
    from fastapi.responses import Response
    from shared.database import db_service

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            select_sql(EMAIL_ATTACHMENTS_TABLE, "filename, content_type, content",
                "WHERE id = $1"),
            attachment_id,
        )
    if not row:
        raise api_error(404, E.ATTACHMENT_NOT_FOUND)

    # Имя файла приходит из письма, то есть от постороннего. Кавычки и
    # переводы строк в нём позволяют дописать свои заголовки ответа, поэтому
    # в Content-Disposition уезжает только очищенное имя.
    safe_name = re.sub(r'[^\w\s.\-()\[\]]', "_", row["filename"] or "attachment")[:200]
    return Response(
        content=row["content"],
        media_type=row["content_type"] or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.post("/inbox/{item_id}/reply")
async def reply_to_message(
    item_id: int,
    payload: ReplyEmail,
    admin: AdminUser = Depends(require_permission("mailserver", "create")),
):
    """Ответить на письмо из ящика.

    Ответ уходит с теми же заголовками ветки, что и у исходного письма, —
    иначе у получателя он открывается отдельным сообщением, оторванным от
    переписки.
    """
    from email.utils import parseaddr
    from shared.database import db_service
    from web.backend.core.mail.mail_service import mail_service

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            select_sql(EMAIL_INBOX_TABLE,
                "from_header, mail_from, rcpt_to, subject, message_id, refs_header, "
                "body_text, date_header, created_at",
                "WHERE id = $1"),
            item_id,
        )
    if not row:
        raise api_error(404, E.MESSAGE_NOT_FOUND)

    to_email = parseaddr(row["from_header"] or "")[1] or row["mail_from"]
    if not to_email:
        raise api_error(400, E.NO_OUTBOUND_DOMAIN)

    original_subject = _decode_subject(row["subject"]) or ""
    subject = payload.subject or (
        original_subject if original_subject.lower().startswith("re:")
        else f"Re: {original_subject}"
    )

    body_text = payload.body_text or ""
    if payload.quote_original and row["body_text"]:
        when = row["date_header"] or row["created_at"]
        quoted = "\n".join(f"> {line}" for line in (row["body_text"] or "").splitlines()[:200])
        body_text = f"{body_text}\n\n{when:%d.%m.%Y %H:%M}, {row['from_header']}:\n{quoted}"

    # References копит всю цепочку, In-Reply-To указывает на прямого
    # предшественника — почтовые клиенты собирают ветку по обоим.
    references = " ".join(filter(None, [row["refs_header"], row["message_id"]]))[:2000]
    headers = {}
    if row["message_id"]:
        headers["In-Reply-To"] = row["message_id"]
    if references:
        headers["References"] = references

    queue_id = await mail_service.send_email(
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=payload.body_html,
        # По умолчанию отвечаем с адреса, на который написали: человек ждёт
        # ответа оттуда же, куда обращался.
        from_email=payload.from_email or row["rcpt_to"],
        from_name=payload.from_name,
        category="reply",
        priority=2,
        headers=headers,
        # Ответ конкретному человеку — осознанное действие администратора,
        # список подавленных адресов тут ни при чём.
        ignore_suppression=True,
    )
    if queue_id is None:
        raise api_error(400, E.NO_OUTBOUND_DOMAIN)

    async with db_service.acquire() as conn:
        await conn.execute(
            update_sql(EMAIL_INBOX_TABLE, "is_read = true", "id = $1"), item_id,
        )
    return {"ok": True, "queue_id": queue_id}


@router.post("/inbox/mark-read")
async def mark_inbox_read(
    payload: InboxMarkRead,
    admin: AdminUser = Depends(require_permission("mailserver", "edit")),
):
    """Mark inbox messages as read."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        if payload.ids:
            await conn.execute(
                update_sql(EMAIL_INBOX_TABLE, "is_read = true", "id = ANY($1::bigint[])"),
                payload.ids,
            )
        else:
            await conn.execute(update_sql(EMAIL_INBOX_TABLE, "is_read = true", "is_read = false"))
    return {"ok": True}


@router.delete("/inbox/{item_id}")
async def delete_inbox_item(
    item_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "delete")),
):
    """Delete an inbox message."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        await conn.execute(delete_sql(EMAIL_INBOX_TABLE, "id = $1"), item_id)
    return {"ok": True}


# ── Compose / Send ────────────────────────────────────────────────

@router.post("/send")
async def send_email(
    payload: ComposeEmail,
    admin: AdminUser = Depends(require_permission("mailserver", "create")),
):
    """Send an email via the built-in mail server."""
    from web.backend.core.mail.mail_service import mail_service

    queue_id = await mail_service.send_email(
        to_email=payload.to_email,
        subject=payload.subject,
        body_text=payload.body_text,
        body_html=payload.body_html,
        from_email=payload.from_email,
        from_name=payload.from_name,
        category="manual",
        priority=1,
    )
    if queue_id is None:
        raise api_error(400, E.NO_OUTBOUND_DOMAIN)
    return {"ok": True, "queue_id": queue_id}


@router.post("/send/test")
async def send_test_email(
    payload: ComposeEmail,
    admin: AdminUser = Depends(require_permission("mailserver", "create")),
):
    """Send a test email to verify mail server setup."""
    from web.backend.core.mail.mail_service import mail_service
    from web.backend.core.notification_service import _build_html_email

    subject = payload.subject or "Mail Server Test"
    body_text = payload.body_text or "This is a test email from your mail server. If you received this, your setup is working correctly!"
    body_html = payload.body_html or _build_html_email(
        title=subject,
        body=body_text,
        severity="success",
    )

    queue_id = await mail_service.send_email(
        to_email=payload.to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        from_email=payload.from_email,
        from_name=payload.from_name,
        category="test",
        priority=2,
    )
    if queue_id is None:
        raise api_error(400, E.NO_OUTBOUND_DOMAIN)
    return {"ok": True, "queue_id": queue_id}


# ── SMTP Credentials endpoints ────────────────────────────────────

@router.post("/smtp-credentials", response_model=SmtpCredentialRead)
async def create_smtp_credential(
    payload: SmtpCredentialCreate,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "create")),
):
    """Create SMTP credentials for external services to relay mail."""
    from web.backend.core.mail.submission_server import hash_password_for_storage
    from shared.database import db_service

    password_hash = hash_password_for_storage(payload.password)
    try:
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                insert_sql(SMTP_CREDENTIALS_TABLE,
                    ["username", "password_hash", "description", "allowed_from_domains", "max_send_per_hour"],
                    returning="*"),
                payload.username, password_hash, payload.description,
                payload.allowed_from_domains, payload.max_send_per_hour,
            )
        from web.backend.core.mail.mail_service import mail_service
        await mail_service.refresh_smtp_credentials()
        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="mailserver.create_smtp_credential", resource="mailserver",
            resource_id=str(row["id"]),
            details=json.dumps({"username": payload.username}),
            ip_address=get_client_ip(request),
        )
        return dict(row)
    except Exception as e:
        logger.error("SMTP credential creation failed: %s", e)
        raise HTTPException(status_code=400, detail="Internal server error")


@router.get("/smtp-credentials", response_model=List[SmtpCredentialRead])
async def list_smtp_credentials(
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """List all SMTP credentials."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            select_sql(SMTP_CREDENTIALS_TABLE,
                "id, username, description, is_active, allowed_from_domains, max_send_per_hour, last_login_at, last_login_ip, created_at, updated_at",
                "ORDER BY id")
        )
    return [dict(r) for r in rows]


@router.get("/smtp-credentials/{cred_id}", response_model=SmtpCredentialRead)
async def get_smtp_credential(
    cred_id: int,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Get SMTP credential details."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            select_sql(SMTP_CREDENTIALS_TABLE,
                "id, username, description, is_active, allowed_from_domains, max_send_per_hour, last_login_at, last_login_ip, created_at, updated_at",
                "WHERE id = $1"), cred_id,
        )
    if not row:
        raise api_error(404, E.SMTP_CREDENTIAL_NOT_FOUND)
    return dict(row)


@router.put("/smtp-credentials/{cred_id}", response_model=SmtpCredentialRead)
async def update_smtp_credential(
    cred_id: int,
    payload: SmtpCredentialUpdate,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "edit")),
):
    """Update SMTP credential settings."""
    from shared.database import db_service

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise api_error(400, E.NO_FIELDS_TO_UPDATE)

    # Hash password if provided
    if "password" in updates:
        from web.backend.core.mail.submission_server import hash_password_for_storage
        updates["password_hash"] = hash_password_for_storage(updates.pop("password"))

    set_clauses = []
    values = []
    idx = 1
    for key, val in updates.items():
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    set_clauses.append("updated_at = NOW()")
    values.append(cred_id)

    query = update_sql(SMTP_CREDENTIALS_TABLE, ', '.join(set_clauses), f"id = ${idx}", returning="id, username, description, is_active, allowed_from_domains, max_send_per_hour, last_login_at, last_login_ip, created_at, updated_at")
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(query, *values)
    if not row:
        raise api_error(404, E.SMTP_CREDENTIAL_NOT_FOUND)
    from web.backend.core.mail.mail_service import mail_service
    await mail_service.refresh_smtp_credentials()
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="mailserver.update_smtp_credential", resource="mailserver",
        resource_id=str(cred_id),
        details=json.dumps({"updated_fields": list(updates.keys())}),
        ip_address=get_client_ip(request),
    )
    return dict(row)


# ── Подавленные адреса ────────────────────────────────────────────

@router.get("/suppression", response_model=List[SuppressionItem])
async def list_suppression(
    q: Optional[str] = None,
    reason: Optional[str] = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Адреса, которым письма не уходят."""
    from shared.database import db_service

    conditions = []
    params = []
    idx = 1
    if q:
        conditions.append(f"email ILIKE ${idx}")
        params.append(f"%{q}%")
        idx += 1
    if reason:
        conditions.append(f"reason = ${idx}")
        params.append(reason)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.extend([limit, offset])
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            select_sql(EMAIL_SUPPRESSION_TABLE, "*",
                f"{where} ORDER BY updated_at DESC LIMIT ${idx} OFFSET ${idx + 1}"),
            *params,
        )
    return [dict(r) for r in rows]


@router.post("/suppression", response_model=SuppressionItem)
async def add_suppression(
    payload: SuppressionCreate,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "create")),
):
    """Добавить адрес вручную."""
    from shared.database import db_service
    from web.backend.core.mail.processor import suppress

    await suppress(payload.email, reason=payload.reason, detail=payload.detail or "")
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            select_sql(EMAIL_SUPPRESSION_TABLE, "*", "WHERE lower(email) = lower($1)"),
            payload.email,
        )
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="mailserver.suppress_address", resource="mailserver",
        resource_id=payload.email,
        details=json.dumps({"reason": payload.reason}),
        ip_address=get_client_ip(request),
    )
    return dict(row)


@router.delete("/suppression/{item_id}")
async def delete_suppression(
    item_id: int,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "delete")),
):
    """Снять запрет — писать по адресу снова можно."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        removed = await conn.fetchval(
            f"{delete_sql(EMAIL_SUPPRESSION_TABLE, 'id = $1')} RETURNING email", item_id,
        )
    if not removed:
        raise api_error(404, E.SUPPRESSION_NOT_FOUND)
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="mailserver.unsuppress_address", resource="mailserver",
        resource_id=str(removed),
        details=json.dumps({"email": removed}),
        ip_address=get_client_ip(request),
    )
    return {"ok": True}


# ── DMARC-отчёты ──────────────────────────────────────────────────

@router.get("/dmarc/reports", response_model=List[DmarcReportItem])
async def list_dmarc_reports(
    domain: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Отчёты почтовых систем о письмах от имени наших доменов."""
    from shared.database import db_service

    where = "WHERE domain = $1" if domain else ""
    params = ([domain] if domain else []) + [limit, offset]
    idx = 2 if domain else 1
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            select_sql(DMARC_REPORTS_TABLE,
                "id, report_id, org_name, domain, date_begin, date_end, total_messages, "
                "passed_messages, failed_messages, created_at",
                f"{where} ORDER BY date_begin DESC LIMIT ${idx} OFFSET ${idx + 1}"),
            *params,
        )
    return [dict(r) for r in rows]


@router.get("/dmarc/summary", response_model=DmarcSummary)
async def get_dmarc_summary(
    days: int = Query(30, ge=1, le=365),
    admin: AdminUser = Depends(require_permission("mailserver", "view")),
):
    """Сводка за период: сколько писем прошло проверку и кто заваливает её чаще всех."""
    from shared.database import db_service

    async with db_service.acquire() as conn:
        totals = await conn.fetchrow(
            f"""SELECT COUNT(*) AS reports,
                       COALESCE(SUM(total_messages), 0) AS total_messages,
                       COALESCE(SUM(passed_messages), 0) AS passed_messages,
                       COALESCE(SUM(failed_messages), 0) AS failed_messages
                FROM {DMARC_REPORTS_TABLE}
                WHERE date_begin > NOW() - ($1 || ' days')::INTERVAL""",
            str(days),
        )
        # Записи отчёта лежат массивом JSON — разворачиваем и складываем
        # непрошедшие по адресам источников.
        sources = await conn.fetch(
            f"""SELECT rec->>'source_ip' AS source_ip,
                       SUM((rec->>'count')::INT) AS messages,
                       MAX(rec->>'header_from') AS header_from
                FROM {DMARC_REPORTS_TABLE},
                     LATERAL jsonb_array_elements(records) AS rec
                WHERE date_begin > NOW() - ($1 || ' days')::INTERVAL
                  AND rec->>'dkim' IS DISTINCT FROM 'pass'
                  AND rec->>'spf' IS DISTINCT FROM 'pass'
                GROUP BY rec->>'source_ip'
                ORDER BY messages DESC
                LIMIT 10""",
            str(days),
        )

    return {
        **dict(totals),
        "top_failing_sources": [dict(s) for s in sources],
    }


@router.delete("/smtp-credentials/{cred_id}")
async def delete_smtp_credential(
    cred_id: int,
    request: Request,
    admin: AdminUser = Depends(require_permission("mailserver", "delete")),
):
    """Delete an SMTP credential."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        await conn.execute(delete_sql(SMTP_CREDENTIALS_TABLE, "id = $1"), cred_id)
    from web.backend.core.mail.mail_service import mail_service
    await mail_service.refresh_smtp_credentials()
    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="mailserver.delete_smtp_credential", resource="mailserver",
        resource_id=str(cred_id),
        details=json.dumps({"credential_id": cred_id}),
        ip_address=get_client_ip(request),
    )
    return {"ok": True}

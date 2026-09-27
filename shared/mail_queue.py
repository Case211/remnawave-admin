"""Постановка письма в исходящую очередь встроенного почтового сервера.

Отправляет письма почтовый сервер веб-бэкенда (DKIM, повторы, разбор
отказов), а поставить письмо в очередь может любой процесс с доступом к
базе. Так предупреждение клиенту уходит почтой и из бота, у которого в
образе нет пакета web.
"""
import json
import logging
from typing import Any, Dict, Optional

from shared.db_query import insert_sql, select_sql
from shared.db_schema import DOMAIN_CONFIG_TABLE, EMAIL_QUEUE_TABLE, EMAIL_SUPPRESSION_TABLE

logger = logging.getLogger(__name__)


# Письма, которые человек ждёт, а не получает рассылкой: коды и ссылки,
# ретранслированные через submission, ответы на его же обращения, проверка
# настроек, уведомления (в т.ч. сброс пароля). Отписка (List-Unsubscribe)
# относится к рассылкам и такие письма не блокирует; жёсткий отказ доставки
# (bounce) блокирует всё — туда писать бесполезно в любом случае.
TRANSACTIONAL_CATEGORIES = frozenset({"smtp_submission", "reply", "test", "notification"})


def suppression_applies(reason: Optional[str], category: Optional[str]) -> bool:
    """Мешает ли запись в подавленных письму этой категории."""
    if reason is None:
        return False
    if reason == "unsubscribe" and category in TRANSACTIONAL_CATEGORIES:
        return False
    return True


async def suppression_reason(email_addr: str) -> Optional[str]:
    """Причина, по которой адрес сейчас в подавленных, или None.

    Истёкшие мягкие отказы не считаются: строка остаётся ради истории, но
    писать по адресу снова можно.
    """
    from shared.database import db_service
    try:
        async with db_service.acquire() as conn:
            reason = await conn.fetchval(
                select_sql(EMAIL_SUPPRESSION_TABLE, "reason",
                    "WHERE lower(email) = lower($1) "
                    "AND (expires_at IS NULL OR expires_at > NOW())"),
                email_addr,
            )
    except Exception:
        # Недоступная база не повод молча проглотить письмо.
        return None
    if reason is None:
        return None
    return str(reason) or "unknown"


async def is_suppressed(email_addr: str) -> bool:
    """Стоит ли адрес в списке подавленных прямо сейчас (любая причина)."""
    return await suppression_reason(email_addr) is not None


def effective_hourly_limit(domain_limit: Optional[int]) -> int:
    """Resolve the effective hourly send cap for a domain.

    A positive per-domain ``max_send_per_hour`` is an explicit override.
    Otherwise (0 / NULL) the domain inherits the global default from
    settings (``mailserver_max_send_per_hour``). A result ``<= 0`` means
    unlimited. This is what makes the "Лимит отправки в час" setting in the
    UI actually take effect — historically it was read nowhere.
    """
    if domain_limit and domain_limit > 0:
        return int(domain_limit)
    try:
        from shared.config_service import config_service
        return int(config_service.get("mailserver_max_send_per_hour", 100) or 0)
    except Exception:
        return 100


async def within_rate_limit(conn, domain_id: int) -> bool:
    """Check if the domain is within its effective hourly send limit."""
    row = await conn.fetchrow(
        select_sql(DOMAIN_CONFIG_TABLE, "max_send_per_hour", "WHERE id = $1"), domain_id,
    )
    limit = effective_hourly_limit(row["max_send_per_hour"] if row else None)
    if limit <= 0:
        return True  # unlimited

    sent_count = await conn.fetchval(
        select_sql(EMAIL_QUEUE_TABLE, "COUNT(*)",
            "WHERE domain_id = $1 AND created_at > NOW() - INTERVAL '1 hour'"),
        domain_id,
    )
    return (sent_count or 0) < limit


async def enqueue(
    from_email: str,
    to_email: str,
    subject: str,
    body_text: Optional[str] = None,
    body_html: Optional[str] = None,
    from_name: Optional[str] = None,
    category: Optional[str] = None,
    priority: int = 0,
    domain_id: Optional[int] = None,
    ignore_suppression: bool = False,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[int]:
    """Add an email to the outbound queue. Returns the queue row id."""
    try:
        # Адрес, который уже ответил жёстким отказом или отписался, письма
        # не получит. Повторные попытки не просто бесполезны: почтовые
        # системы считают настойчивую отправку в мёртвые ящики признаком
        # спамера и портят репутацию домена целиком.
        if not ignore_suppression:
            reason = await suppression_reason(to_email)
            if suppression_applies(reason, category):
                logger.info("Skipped suppressed address: %s (%s)", to_email, reason)
                return None

        from shared.database import db_service
        async with db_service.acquire() as conn:
            # Auto-resolve domain_id from sender address
            if domain_id is None:
                sender_domain = from_email.split("@")[-1] if "@" in from_email else None
                if sender_domain:
                    domain_id = await conn.fetchval(
                        select_sql(DOMAIN_CONFIG_TABLE, "id",
                            "WHERE domain = $1 AND is_active = true"),
                        sender_domain,
                    )

            # Rate limit check
            if domain_id and not await within_rate_limit(conn, domain_id):
                logger.warning(
                    "Rate limit exceeded for domain_id=%d (effective hourly cap reached)",
                    domain_id,
                )
                return None

            row_id = await conn.fetchval(
                insert_sql(EMAIL_QUEUE_TABLE,
                    ["domain_id", "from_email", "from_name", "to_email", "subject",
                     "body_text", "body_html", "category", "priority", "headers",
                     "status", "next_attempt_at"],
                    values="$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'pending', NOW()",
                    returning="id"),
                domain_id, from_email, from_name, to_email, subject,
                body_text, body_html, category, priority,
                json.dumps(headers or {}),
            )
            logger.info("Enqueued email id=%s to=%s subj=%s", row_id, to_email, subject[:60])
            return row_id
    except Exception as e:
        logger.error("Failed to enqueue email: %s", e)
        return None


async def active_outbound_domain() -> Optional[Dict[str, Any]]:
    """Return the first active outbound domain config, or None."""
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(DOMAIN_CONFIG_TABLE, "*",
                    "WHERE is_active = true AND outbound_enabled = true ORDER BY id LIMIT 1")
            )
            return dict(row) if row else None
    except Exception:
        return None


async def send_email(
    to_email: str,
    subject: str,
    body_text: Optional[str] = None,
    body_html: Optional[str] = None,
    category: Optional[str] = None,
    priority: int = 0,
    reply_mailbox: Optional[str] = None,
) -> Optional[int]:
    """Письмо от noreply@ первого активного домена. None — домена нет или очередь отказала.

    ``reply_mailbox`` — ящик на том же домене, куда ждём ответы (например, ``support``).
    Ставится в Reply-To, только если домен принимает входящую почту: иначе ответ
    отскочит, и честнее оставить пометку «отвечать не нужно».
    """
    domain = await active_outbound_domain()
    if not domain:
        logger.warning("No active outbound domain configured")
        return None
    headers = None
    if reply_mailbox and domain.get("inbound_enabled"):
        headers = {"Reply-To": f"{reply_mailbox}@{domain['domain']}"}
    return await enqueue(
        from_email=f"noreply@{domain['domain']}",
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        from_name=domain.get("from_name"),
        category=category,
        priority=priority,
        headers=headers,
    )

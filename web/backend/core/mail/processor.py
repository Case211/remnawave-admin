"""Разбор служебной почты: отказы в доставке, отписки, DMARC-отчёты.

Всё это приходит на общих основаниях и до сих пор оседало в ящике мёртвым
грузом. Между тем каждое такое письмо — это ответ на вопрос, который иначе
никто не задаёт:

* отказ говорит, что адресата больше нет, и повторять рассылку туда бесполезно
  (а при большом объёме — вредно: почтовые системы считают долбёжку в
  несуществующие ящики признаком спамера и режут репутацию отправителя);
* отписка говорит, что человек больше не хочет писем;
* DMARC-отчёт говорит, кто отправлял письма от имени наших доменов.

Разбор идёт отдельным фоновым проходом, а не прямо в момент приёма: письмо
должно попасть в ящик даже если разбор упадёт, и наоборот — тяжёлая
распаковка отчёта не должна держать SMTP-сессию открытой.
"""
from __future__ import annotations

import asyncio
import email
import gzip
import io
import json
import logging
import re
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from shared.db_schema import (
    DMARC_REPORTS_TABLE,
    EMAIL_ATTACHMENTS_TABLE,
    EMAIL_INBOX_TABLE,
    EMAIL_QUEUE_TABLE,
    EMAIL_SUPPRESSION_TABLE,
)
from shared.db_query import insert_sql, select_sql, update_sql

logger = logging.getLogger(__name__)

_BATCH = 50
_POLL_SECONDS = 60
# Распакованный отчёт кладём в память целиком — потолок бережёт от архива,
# который в сжатом виде занимает килобайты, а разворачивается в гигабайты.
_MAX_UNPACKED_BYTES = 20 * 1024 * 1024
# Мягкий отказ — это «сейчас не получилось»: ящик переполнен, сервер занят.
# Через неделю адрес стоит попробовать снова.
_SOFT_BOUNCE_DAYS = 7


# ── Подавленные адреса ────────────────────────────────────────────

async def suppress(email_addr: str, reason: str, detail: str = "",
                   smtp_code: str = "", source_inbox_id: Optional[int] = None,
                   expires_at: Optional[datetime] = None) -> None:
    """Занести адрес в список тех, кому больше не пишем.

    Повторный отказ по тому же адресу не плодит строки, а увеличивает счётчик:
    так видно разницу между «один раз не доставилось» и «стучимся сюда сотый раз».
    """
    from shared.database import db_service
    try:
        async with db_service.acquire() as conn:
            await conn.execute(
                insert_sql(EMAIL_SUPPRESSION_TABLE,
                    ["email", "reason", "detail", "smtp_code", "source_inbox_id", "expires_at"],
                    suffix="ON CONFLICT (lower(email)) DO UPDATE SET "
                           "hits = email_suppression.hits + 1, "
                           "reason = EXCLUDED.reason, "
                           "detail = EXCLUDED.detail, "
                           "smtp_code = EXCLUDED.smtp_code, "
                           "expires_at = EXCLUDED.expires_at, "
                           "updated_at = NOW()"),
                email_addr.lower(), reason, detail[:1000] or None,
                smtp_code[:16] or None, source_inbox_id, expires_at,
            )
        logger.info("Address suppressed: %s (%s)", email_addr, reason)
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to suppress %s: %s", email_addr, e)


async def is_suppressed(email_addr: str) -> bool:
    """Стоит ли адрес в списке подавленных прямо сейчас.

    Истёкшие мягкие отказы не считаются: строка остаётся ради истории, но
    писать по адресу снова можно.
    """
    from shared.database import db_service
    try:
        async with db_service.acquire() as conn:
            return bool(await conn.fetchval(
                select_sql(EMAIL_SUPPRESSION_TABLE, "1",
                    "WHERE lower(email) = lower($1) "
                    "AND (expires_at IS NULL OR expires_at > NOW())"),
                email_addr,
            ))
    except Exception:
        # Недоступная база не повод молча проглотить письмо.
        return False


# ── Отказы в доставке ─────────────────────────────────────────────

_STATUS_RE = re.compile(r"^Status:\s*([245])\.(\d+)\.(\d+)", re.MULTILINE | re.IGNORECASE)
_FINAL_RCPT_RE = re.compile(r"^Final-Recipient:\s*[^;]*;\s*(.+)$", re.MULTILINE | re.IGNORECASE)
_ORIGINAL_RCPT_RE = re.compile(r"^Original-Recipient:\s*[^;]*;\s*(.+)$", re.MULTILINE | re.IGNORECASE)
_DIAG_RE = re.compile(r"^Diagnostic-Code:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
_ACTION_RE = re.compile(r"^Action:\s*(\w+)", re.MULTILINE | re.IGNORECASE)


def parse_bounce(msg) -> Optional[Dict[str, Any]]:
    """Вытащить из отчёта о недоставке адрес, код и жёсткость отказа.

    Опознаём по структуре из RFC 3464 (multipart/report с частью
    message/delivery-status). Формально отчёты обязаны приходить с пустым
    обратным адресом, но на практике встречаются и подписанные — поэтому
    смотрим на структуру, а не на конверт.
    """
    content_type = (msg.get_content_type() or "").lower()
    report_type = (msg.get_param("report-type") or "").lower()
    is_report = content_type == "multipart/report" and report_type == "delivery-status"

    delivery_status = ""
    original_message_id = ""

    for part in (msg.walk() if msg.is_multipart() else [msg]):
        part_type = (part.get_content_type() or "").lower()
        if part_type == "message/delivery-status":
            payload = part.get_payload()
            if isinstance(payload, list):
                delivery_status = "\n".join(str(p) for p in payload)
            else:
                delivery_status = str(payload)
        elif part_type in ("message/rfc822", "text/rfc822-headers"):
            # Внутри лежит наше исходное письмо — по его Message-ID и
            # находим строку в очереди отправки.
            inner = part.get_payload()
            inner_text = ""
            if isinstance(inner, list) and inner:
                inner_text = str(inner[0])
            elif isinstance(inner, str):
                inner_text = inner
            found = re.search(r"^Message-ID:\s*(<[^>]+>)", inner_text,
                              re.MULTILINE | re.IGNORECASE)
            if found:
                original_message_id = found.group(1)

    if not delivery_status and not is_report:
        return None

    status = _STATUS_RE.search(delivery_status)
    action = _ACTION_RE.search(delivery_status)
    if not status and (not action or action.group(1).lower() != "failed"):
        return None

    recipient_match = _FINAL_RCPT_RE.search(delivery_status) or _ORIGINAL_RCPT_RE.search(delivery_status)
    recipient = (recipient_match.group(1).strip().strip("<>") if recipient_match else "")
    if not recipient or "@" not in recipient:
        return None

    status_class = status.group(1) if status else "5"
    diagnostic = _DIAG_RE.search(delivery_status)

    return {
        "recipient": recipient,
        "bounce_type": "hard" if status_class == "5" else "soft",
        "smtp_code": (f"{status.group(1)}.{status.group(2)}.{status.group(3)}"
                      if status else ""),
        "diagnostic": (diagnostic.group(1).strip() if diagnostic else "")[:500],
        "original_message_id": original_message_id,
    }


async def _handle_bounce(inbox_id: int, bounce: Dict[str, Any]) -> None:
    """Пометить исходное письмо и, если отказ жёсткий, закрыть адрес."""
    from shared.database import db_service

    if bounce["original_message_id"]:
        try:
            async with db_service.acquire() as conn:
                await conn.execute(
                    update_sql(EMAIL_QUEUE_TABLE,
                        "status = 'bounced', bounced_at = NOW(), bounce_type = $1, "
                        "last_error = $2",
                        "message_id = $3"),
                    bounce["bounce_type"],
                    f"{bounce['smtp_code']} {bounce['diagnostic']}".strip()[:500],
                    bounce["original_message_id"],
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to mark bounced message: %s", e)

    expires = (None if bounce["bounce_type"] == "hard"
               else datetime.now(timezone.utc) + timedelta(days=_SOFT_BOUNCE_DAYS))
    await suppress(
        bounce["recipient"],
        reason=f"{bounce['bounce_type']}_bounce",
        detail=bounce["diagnostic"],
        smtp_code=bounce["smtp_code"],
        source_inbox_id=inbox_id,
        expires_at=expires,
    )


# ── DMARC-отчёты ──────────────────────────────────────────────────

def _unpack_report(filename: str, content_type: str, blob: bytes) -> Optional[bytes]:
    """Достать XML из вложения: .gz, .zip или голый файл."""
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    try:
        if name.endswith(".gz") or "gzip" in ctype:
            with gzip.GzipFile(fileobj=io.BytesIO(blob)) as fh:
                return fh.read(_MAX_UNPACKED_BYTES)
        if name.endswith(".zip") or "zip" in ctype:
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                for entry in archive.namelist():
                    if entry.lower().endswith(".xml"):
                        with archive.open(entry) as fh:
                            return fh.read(_MAX_UNPACKED_BYTES)
            return None
        if name.endswith(".xml") or "xml" in ctype:
            return blob[:_MAX_UNPACKED_BYTES]
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to unpack DMARC report %s: %s", filename, e)
    return None


def parse_dmarc_report(xml_bytes: bytes) -> Optional[Dict[str, Any]]:
    """Разобрать агрегированный отчёт DMARC (RFC 7489, приложение C)."""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_bytes)
    except Exception as e:  # noqa: BLE001
        logger.warning("Malformed DMARC report: %s", e)
        return None

    def text(node, path: str, default: str = "") -> str:
        found = node.find(path) if node is not None else None
        return (found.text or default).strip() if found is not None and found.text else default

    metadata = root.find("report_metadata")
    policy = root.find("policy_published")
    if metadata is None:
        return None

    def as_time(value: str) -> datetime:
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            return datetime.now(timezone.utc)

    date_range = metadata.find("date_range")
    records: List[Dict[str, Any]] = []
    passed = failed = 0

    for record in root.findall("record"):
        row = record.find("row")
        policy_eval = row.find("policy_evaluated") if row is not None else None
        identifiers = record.find("identifiers")

        count = int(text(row, "count", "0") or 0)
        dkim_result = text(policy_eval, "dkim", "none")
        spf_result = text(policy_eval, "spf", "none")
        # DMARC засчитывается, если сошёлся хотя бы один механизм —
        # именно так его считает и принимающая сторона.
        ok = dkim_result == "pass" or spf_result == "pass"
        passed += count if ok else 0
        failed += 0 if ok else count

        records.append({
            "source_ip": text(row, "source_ip"),
            "count": count,
            "disposition": text(policy_eval, "disposition", "none"),
            "dkim": dkim_result,
            "spf": spf_result,
            "header_from": text(identifiers, "header_from"),
            "envelope_from": text(identifiers, "envelope_from"),
        })

    return {
        "report_id": text(metadata, "report_id") or "unknown",
        "org_name": text(metadata, "org_name"),
        "org_email": text(metadata, "email"),
        "domain": text(policy, "domain"),
        "date_begin": as_time(text(date_range, "begin")),
        "date_end": as_time(text(date_range, "end")),
        "policy": {
            "p": text(policy, "p", "none"),
            "sp": text(policy, "sp"),
            "adkim": text(policy, "adkim", "r"),
            "aspf": text(policy, "aspf", "r"),
            "pct": text(policy, "pct", "100"),
        },
        "records": records,
        "total_messages": passed + failed,
        "passed_messages": passed,
        "failed_messages": failed,
    }


async def _handle_dmarc_reports(inbox_id: int) -> int:
    """Разобрать вложения письма как DMARC-отчёты. Возвращает число сохранённых."""
    from shared.database import db_service

    async with db_service.acquire() as conn:
        attachments = await conn.fetch(
            select_sql(EMAIL_ATTACHMENTS_TABLE, "filename, content_type, content",
                "WHERE inbox_id = $1"),
            inbox_id,
        )

    saved = 0
    for att in attachments:
        xml_bytes = _unpack_report(att["filename"], att["content_type"], att["content"])
        if not xml_bytes:
            continue
        report = parse_dmarc_report(xml_bytes)
        if not report or not report["domain"]:
            continue
        try:
            async with db_service.acquire() as conn:
                await conn.execute(
                    insert_sql(DMARC_REPORTS_TABLE,
                        ["report_id", "org_name", "org_email", "domain", "date_begin",
                         "date_end", "policy", "records", "total_messages",
                         "passed_messages", "failed_messages", "source_inbox_id"],
                        # Тот же отчёт мог приехать дважды (повтор доставки) —
                        # для нас это одна и та же строка.
                        suffix="ON CONFLICT (domain, report_id) DO NOTHING"),
                    report["report_id"], report["org_name"], report["org_email"],
                    report["domain"], report["date_begin"], report["date_end"],
                    json.dumps(report["policy"]), json.dumps(report["records"]),
                    report["total_messages"], report["passed_messages"],
                    report["failed_messages"], inbox_id,
                )
            saved += 1
            logger.info("DMARC report stored: %s from %s (%d messages, %d failed)",
                        report["domain"], report["org_name"],
                        report["total_messages"], report["failed_messages"])
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to store DMARC report: %s", e)

    return saved


# ── Отписки ───────────────────────────────────────────────────────

async def _handle_unsubscribe(inbox_id: int, mail_from: str) -> None:
    """Письмо на unsubscribe@ — просьба больше не писать.

    Адрес обещан в заголовке List-Unsubscribe каждого нашего письма, так что
    отписка обязана работать: иначе заголовок — пустое обещание, а почтовые
    системы за такое понижают репутацию отправителя.
    """
    if not mail_from or "@" not in mail_from:
        return
    await suppress(mail_from, reason="unsubscribe",
                   detail="Отписка письмом на unsubscribe@", source_inbox_id=inbox_id)


# ── Основной проход ───────────────────────────────────────────────

async def process_pending(limit: int = _BATCH) -> Dict[str, int]:
    """Разобрать накопившиеся письма. Возвращает счётчики по видам."""
    from shared.database import db_service

    stats = {"processed": 0, "bounces": 0, "dmarc": 0, "unsubscribes": 0}
    try:
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(EMAIL_INBOX_TABLE,
                    "id, rcpt_to, mail_from, raw_message, has_attachments, subject",
                    "WHERE is_processed = false ORDER BY id LIMIT $1"),
                limit,
            )
    except Exception as e:  # noqa: BLE001
        logger.error("Failed to fetch unprocessed mail: %s", e)
        return stats

    for row in rows:
        inbox_id = row["id"]
        try:
            if (row["rcpt_to"] or "").lower().startswith("unsubscribe@"):
                await _handle_unsubscribe(inbox_id, row["mail_from"] or "")
                stats["unsubscribes"] += 1
            else:
                msg = email.message_from_string(row["raw_message"] or "")
                bounce = parse_bounce(msg)
                if bounce:
                    await _handle_bounce(inbox_id, bounce)
                    stats["bounces"] += 1
                elif row["has_attachments"]:
                    stats["dmarc"] += await _handle_dmarc_reports(inbox_id)

            async with db_service.acquire() as conn:
                await conn.execute(
                    update_sql(EMAIL_INBOX_TABLE, "is_processed = true", "id = $1"),
                    inbox_id,
                )
            stats["processed"] += 1
        except Exception as e:  # noqa: BLE001
            # Помечаем обработанным даже при сбое: письмо, на котором разбор
            # спотыкается, иначе будет вечно возвращаться в каждую выборку и
            # закрывать собой всю очередь.
            logger.error("Failed to process inbox message %s: %s", inbox_id, e)
            try:
                async with db_service.acquire() as conn:
                    await conn.execute(
                        update_sql(EMAIL_INBOX_TABLE, "is_processed = true", "id = $1"),
                        inbox_id,
                    )
            except Exception:
                pass

    return stats


async def cleanup_old(inbox_days: int, queue_days: int) -> Tuple[int, int]:
    """Удалить старые письма. Ноль дней — хранить вечно."""
    from shared.database import db_service

    removed_inbox = removed_queue = 0
    try:
        async with db_service.acquire() as conn:
            if inbox_days > 0:
                result = await conn.execute(
                    f"DELETE FROM {EMAIL_INBOX_TABLE} "
                    f"WHERE created_at < NOW() - ($1 || ' days')::INTERVAL",
                    str(inbox_days),
                )
                removed_inbox = int(str(result).rsplit(" ", 1)[-1] or 0)
            if queue_days > 0:
                # Неотправленное не трогаем: письмо может ждать своей попытки
                # дольше срока хранения, если адресат долго недоступен.
                result = await conn.execute(
                    f"DELETE FROM {EMAIL_QUEUE_TABLE} "
                    f"WHERE created_at < NOW() - ($1 || ' days')::INTERVAL "
                    f"AND status IN ('sent', 'failed', 'cancelled', 'bounced')",
                    str(queue_days),
                )
                removed_queue = int(str(result).rsplit(" ", 1)[-1] or 0)
    except Exception as e:  # noqa: BLE001
        logger.error("Mail cleanup failed: %s", e)

    if removed_inbox or removed_queue:
        logger.info("Mail cleanup: removed %d inbox, %d queue rows", removed_inbox, removed_queue)
    return (removed_inbox, removed_queue)


class MailProcessor:
    """Фоновый разбор служебной почты и уборка старых писем."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._last_cleanup = datetime.min.replace(tzinfo=timezone.utc)

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Mail processor started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self):
        while self._running:
            try:
                await asyncio.sleep(_POLL_SECONDS)
                await process_pending()
                await self._maybe_cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                logger.error("Mail processor loop error: %s", e)
                await asyncio.sleep(30)

    async def _maybe_cleanup(self):
        """Уборка раз в сутки — чаще незачем, реже начинает копиться."""
        now = datetime.now(timezone.utc)
        if now - self._last_cleanup < timedelta(hours=24):
            return
        self._last_cleanup = now
        try:
            from shared.config_service import config_service
            inbox_days = int(config_service.get("mailserver_inbox_retention_days", 0) or 0)
            queue_days = int(config_service.get("mailserver_queue_retention_days", 90) or 0)
        except Exception:
            inbox_days, queue_days = 0, 90
        await cleanup_old(inbox_days, queue_days)


mail_processor = MailProcessor()

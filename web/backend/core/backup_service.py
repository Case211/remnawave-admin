"""Backup service — database dump, config export/import, user import."""
import asyncio
import gzip as gzip_module
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

from shared.db_schema import BOT_CONFIG_TABLE
from shared.db_query import select_sql, update_sql

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/app/backups"))

# Дамп и загрузки ходят через процесс кусками, а не целиком: на базе в 750 МБ
# бэкап поднимал RSS backend до гигабайта, на больших базах — до десятков.
_CHUNK_BYTES = 1 << 20
TELEGRAM_MAX_PART = 49 * 1024 * 1024  # лимит Telegram — 50 МБ на документ


class BackupTooLarge(Exception):
    """Загрузка превысила лимит размера."""


def ensure_backup_dir() -> Path:
    """Ensure the backup directory exists."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


# ── Database backup ──────────────────────────────────────────

async def create_database_backup(database_url: str) -> dict:
    """Create a PostgreSQL dump using pg_dump.

    Сжимает и пишет файл сам pg_dump — раньше весь plain-дамп проходил через
    память процесса (communicate + gzip). Пока дамп пишется, файл лежит под
    скрытым именем, чтобы не мелькать в списке бэкапов недописанным.

    Returns dict with filename, size_bytes, backup_type.
    """
    ensure_backup_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"db_backup_{ts}.sql.gz"
    filepath = BACKUP_DIR / filename
    partial = BACKUP_DIR / f".{filename}.part"

    try:
        proc = await asyncio.create_subprocess_exec(
            "pg_dump", database_url,
            "--no-owner", "--no-privileges", "--clean", "--if-exists",
            "--compress=6", f"--file={partial}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"pg_dump failed: {stderr.decode()}")

        partial.replace(filepath)
        size_bytes = filepath.stat().st_size

        from web.backend.core.webhook_security import fire_event
        fire_event("backup.created", {
            "filename": filename,
            "size_bytes": size_bytes,
            "backup_type": "database",
        })

        return {
            "filename": filename,
            "size_bytes": size_bytes,
            "backup_type": "database",
        }
    except FileNotFoundError:
        raise RuntimeError("pg_dump not found. Ensure PostgreSQL client tools are installed.")


async def restore_database_backup(database_url: str, filename: str) -> None:
    """Restore a PostgreSQL dump from a backup file.

    Дамп льётся в psql кусками прямо из файла: распакованный он больше базы,
    и держать его в памяти целиком — значит ловить OOM ровно в момент
    восстановления.
    """
    filepath = _safe_backup_path(filename)
    if filepath is None:
        raise ValueError(f"Invalid backup filename: {filename}")
    if not filepath.exists():
        raise FileNotFoundError(f"Backup file not found: {filename}")

    # ON_ERROR_STOP=1 makes psql abort (and return non-zero) on the first error
    # instead of silently skipping failed statements and reporting success.
    # --single-transaction wraps the whole restore in one transaction, so a
    # failure rolls everything back rather than leaving the DB half-restored
    # (the dump starts with DROP ... statements under --clean).
    psql = await asyncio.create_subprocess_exec(
        "psql", database_url,
        "-v", "ON_ERROR_STOP=1", "--single-transaction",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    # stderr читаем параллельно с подачей: иначе psql, забив буфер stderr,
    # встанет ждать нас, а мы — его.
    stderr_task = asyncio.create_task(psql.stderr.read())
    opener = gzip_module.open if filename.endswith(".gz") else open
    try:
        with opener(filepath, "rb") as src:
            while chunk := src.read(_CHUNK_BYTES):
                psql.stdin.write(chunk)
                await psql.stdin.drain()
    except (BrokenPipeError, ConnectionResetError):
        pass  # psql уже упал — причина в stderr ниже
    finally:
        psql.stdin.close()
    await psql.wait()
    stderr = await stderr_task

    if psql.returncode != 0:
        raise RuntimeError(f"psql restore failed: {stderr.decode()}")


# ── Config export/import ─────────────────────────────────────

async def export_config() -> dict:
    """Export all bot_config settings as JSON.

    Returns dict with filename, size_bytes, backup_type.
    """
    ensure_backup_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"config_backup_{ts}.json"
    filepath = BACKUP_DIR / filename

    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(BOT_CONFIG_TABLE,
                    "key, value, value_type, category, subcategory, "
                    "display_name, description, default_value, is_secret, is_readonly",
                    "ORDER BY category, key")
            )

        settings = []
        for row in rows:
            d = dict(row)
            # Don't export secret values
            if d.get("is_secret"):
                d["value"] = None
            settings.append(d)

        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0",
            "settings": settings,
        }

        filepath.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        size_bytes = filepath.stat().st_size

        from web.backend.core.webhook_security import fire_event
        fire_event("backup.created", {
            "filename": filename,
            "size_bytes": size_bytes,
            "backup_type": "config",
        })

        return {
            "filename": filename,
            "size_bytes": size_bytes,
            "backup_type": "config",
        }
    except Exception as e:
        logger.error("Failed to export config: %s", e, exc_info=True)
        raise


async def import_config(filename: str, overwrite: bool = False) -> dict:
    """Import settings from a config backup file.

    Returns dict with imported_count, skipped_count.
    """
    filepath = _safe_backup_path(filename)
    if filepath is None:
        raise ValueError(f"Invalid config filename: {filename}")
    if not filepath.exists():
        raise FileNotFoundError(f"Config file not found: {filename}")

    data = json.loads(filepath.read_text(encoding="utf-8"))
    settings = data.get("settings", [])

    imported = 0
    skipped = 0

    from shared.database import db_service
    async with db_service.acquire() as conn:
        for s in settings:
            key = s.get("key")
            value = s.get("value")
            if not key or value is None:
                skipped += 1
                continue

            if s.get("is_readonly"):
                skipped += 1
                continue

            if not overwrite:
                existing = await conn.fetchval(
                    select_sql(BOT_CONFIG_TABLE, "value", "WHERE key = $1"), key
                )
                if existing is not None:
                    skipped += 1
                    continue

            await conn.execute(
                update_sql(BOT_CONFIG_TABLE, "value = $2, updated_at = NOW()", "key = $1"),
                key, str(value),
            )
            imported += 1

    return {"imported_count": imported, "skipped_count": skipped}


# ── User import ──────────────────────────────────────────────

async def import_users_from_file(filename: str) -> dict:
    """Import users from a JSON file (Remnawave export format).

    Returns dict with imported_count, skipped_count, errors.
    """
    filepath = _safe_backup_path(filename)
    if filepath is None:
        raise ValueError(f"Invalid import filename: {filename}")
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filename}")

    data = json.loads(filepath.read_text(encoding="utf-8"))
    users = data if isinstance(data, list) else data.get("users", [])

    imported = 0
    skipped = 0
    errors = []

    from shared.api_client import api_client

    for user in users:
        try:
            username = user.get("username")
            if not username:
                skipped += 1
                continue

            await api_client.create_user(
                username=username,
                traffic_limit=user.get("trafficLimitBytes", 0),
                expire_at=user.get("expireAt"),
            )
            imported += 1
        except Exception as e:
            errors.append({"username": user.get("username", "?"), "error": str(e)})

    return {
        "imported_count": imported,
        "skipped_count": skipped,
        "errors": errors[:20],  # limit error list
    }


# ── File management ──────────────────────────────────────────

def list_backup_files() -> List[dict]:
    """List all backup files in the backup directory."""
    ensure_backup_dir()
    files = []
    for f in BACKUP_DIR.iterdir():
        if f.is_file() and not f.name.startswith("."):
            files.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "created_at": datetime.fromtimestamp(
                    f.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            })
    files.sort(key=lambda x: x["created_at"], reverse=True)
    return files


def _safe_backup_path(filename: str) -> Optional[Path]:
    """Resolve backup path with full path traversal protection."""
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return None
    filepath = (BACKUP_DIR / filename).resolve()
    if not str(filepath).startswith(str(BACKUP_DIR.resolve())):
        return None
    return filepath


def delete_backup_file(filename: str) -> bool:
    """Delete a backup file."""
    filepath = _safe_backup_path(filename)
    if filepath and filepath.exists() and filepath.is_file():
        filepath.unlink()
        return True
    return False


def get_backup_filepath(filename: str) -> Optional[Path]:
    """Get the full path to a backup file, with path traversal protection."""
    filepath = _safe_backup_path(filename)
    if filepath and filepath.exists() and filepath.is_file():
        return filepath
    return None


def preview_backup_file(filename: str) -> dict:
    """Return metadata about a backup file without restoring it.

    For config (.json): exported_at, schema version, settings count.
    For database (.sql.gz): PostgreSQL version from the dump header.
    """
    filepath = _safe_backup_path(filename)
    if not filepath or not filepath.exists() or not filepath.is_file():
        raise FileNotFoundError(f"Backup not found: {filename}")

    stat = filepath.stat()
    info = {
        "filename": filename,
        "size_bytes": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }

    if filename.endswith(".json"):
        info["type"] = "config"
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            info["exported_at"] = data.get("exported_at")
            info["schema_version"] = data.get("version")
            info["settings_count"] = len(data.get("settings", []))
        except Exception as e:
            info["error"] = f"Не удалось прочитать JSON: {e}"
    elif filename.endswith(".sql.gz"):
        info["type"] = "database"
        try:
            with gzip_module.open(filepath, "rt", encoding="utf-8", errors="ignore") as f:
                head = f.read(65536)
            m = re.search(r"Dumped from database version ([\d.]+)", head)
            if m:
                info["pg_version"] = m.group(1)
        except Exception as e:
            info["error"] = f"Не удалось прочитать дамп: {e}"
    else:
        info["type"] = "unknown"

    return info


# ── Disk usage ───────────────────────────────────────────────

def get_disk_usage() -> dict:
    """Get backup directory disk usage stats."""
    ensure_backup_dir()
    import shutil
    total_size = sum(f.stat().st_size for f in BACKUP_DIR.iterdir() if f.is_file())
    file_count = sum(1 for f in BACKUP_DIR.iterdir() if f.is_file())
    try:
        disk = shutil.disk_usage(BACKUP_DIR)
        disk_free = disk.free
        disk_total = disk.total
    except Exception:
        disk_free = 0
        disk_total = 0
    return {
        "backup_size_bytes": total_size,
        "file_count": file_count,
        "disk_free_bytes": disk_free,
        "disk_total_bytes": disk_total,
    }


# ── Auto-rotation ────────────────────────────────────────────

def rotate_backups(keep_count: int = 10, keep_days: int = 30) -> int:
    """Delete old backups beyond retention limits. Returns number deleted."""
    ensure_backup_dir()
    files = sorted(
        [f for f in BACKUP_DIR.iterdir() if f.is_file() and f.name.endswith('.sql.gz')],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    deleted = 0
    cutoff = time.time() - keep_days * 86400

    for i, f in enumerate(files):
        if i >= keep_count or f.stat().st_mtime < cutoff:
            try:
                f.unlink()
                deleted += 1
                logger.info("Rotated backup: %s", f.name)
            except Exception as e:
                logger.warning("Failed to rotate %s: %s", f.name, e)

    return deleted


# ── Upload ───────────────────────────────────────────────────

async def send_backup_to_telegram(
    filename: str,
    chat_id: str,
    topic_id: int | None = None,
    bot_token: str | None = None,
) -> dict:
    """Send backup file to Telegram chat. Splits if >49 MB."""
    import httpx
    import math

    filepath = _safe_backup_path(filename)
    if not filepath or not filepath.exists():
        raise FileNotFoundError(f"Backup not found: {filename}")

    if not bot_token:
        from web.backend.core.config import get_web_settings
        bot_token = get_web_settings().telegram_bot_token
    if not bot_token:
        raise ValueError("No Telegram bot token configured")

    file_size = filepath.stat().st_size
    parts_sent = 0

    if file_size <= TELEGRAM_MAX_PART:
        async with httpx.AsyncClient(timeout=120) as client:
            data = {"chat_id": chat_id}
            if topic_id:
                data["message_thread_id"] = str(topic_id)
            with open(filepath, "rb") as f:
                resp = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendDocument",
                    data=data,
                    files={"document": (filename, f)},
                )
            if resp.status_code != 200:
                raise RuntimeError(f"Telegram send failed: {resp.text[:200]}")
            parts_sent = 1
    else:
        total_parts = math.ceil(file_size / TELEGRAM_MAX_PART)
        for i in range(total_parts):
            chunk = _read_part(filepath, i * TELEGRAM_MAX_PART, TELEGRAM_MAX_PART)
            part_name = f"{filename}.part{i + 1}of{total_parts}"
            async with httpx.AsyncClient(timeout=120) as client:
                data = {
                    "chat_id": chat_id,
                    "caption": f"Part {i + 1}/{total_parts} — {filename}" if total_parts > 1 else filename,
                }
                if topic_id:
                    data["message_thread_id"] = str(topic_id)
                resp = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendDocument",
                    data=data,
                    files={"document": (part_name, chunk)},
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"Telegram send part {i + 1} failed: {resp.text[:200]}")
            parts_sent += 1
            logger.info("Sent backup part %d/%d to Telegram", i + 1, total_parts)

    return {"filename": filename, "parts_sent": parts_sent, "size_bytes": file_size}


def _read_part(path: Path, offset: int, size: int) -> bytes:
    with open(path, "rb") as f:
        f.seek(offset)
        return f.read(size)


async def save_uploaded_file(filename: str, source, max_bytes: int) -> dict:
    """Save an uploaded backup file. Returns file info.

    ``source`` — файловый объект загрузки (Starlette уже сложил тело во
    временный файл); копируем на диск кусками в отдельном потоке, лимит
    проверяем по ходу.
    """
    import re
    ensure_backup_dir()

    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    if not (safe_name.endswith('.sql.gz') or safe_name.endswith('.json')):
        raise ValueError("Only .sql.gz and .json files are accepted")

    filepath = BACKUP_DIR / safe_name
    if filepath.exists():
        raise FileExistsError(f"File already exists: {safe_name}")

    def _copy() -> int:
        written = 0
        with open(filepath, "wb") as dst:
            while chunk := source.read(_CHUNK_BYTES):
                written += len(chunk)
                if written > max_bytes:
                    raise BackupTooLarge(max_bytes)
                dst.write(chunk)
        return written

    try:
        size_bytes = await asyncio.to_thread(_copy)
    except BaseException:
        filepath.unlink(missing_ok=True)
        raise
    return {
        "filename": safe_name,
        "size_bytes": size_bytes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Scheduled auto-backup ────────────────────────────────────

_last_auto_backup_ts: Optional[datetime] = None
_last_deadman_alert_date: Optional[str] = None


async def _notify_backup_failed(title: str, body: str, group_key: str = "backup_failed") -> None:
    """Send a critical alert to admins (in-app + Telegram 'errors' topic)."""
    try:
        from web.backend.core.notification_service import create_notification
        await create_notification(
            title=title,
            body=body,
            type="alert",
            severity="critical",
            channels=["in_app", "telegram"],
            topic_type="errors",
            source="backup",
            group_key=group_key,
        )
    except Exception as exc:
        logger.warning("Failed to send backup alert: %s", exc)


async def _get_last_successful_backup_ts() -> Optional[datetime]:
    """created_at of the most recent successful DB/config backup, or None."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT created_at FROM backup_log "
                "WHERE backup_type IN ('database','config') "
                "AND status IN ('completed','success') "
                "ORDER BY created_at DESC LIMIT 1"
            )
        return row["created_at"] if row else None
    except Exception as exc:
        logger.debug("Failed to read last backup: %s", exc)
        return None


async def _check_deadman() -> None:
    """Alert (once a day) if no successful backup within backup_deadman_hours."""
    global _last_deadman_alert_date
    from shared.config_service import config_service

    hours = int(config_service.get("backup_deadman_hours", 0) or 0)
    if hours <= 0:
        return

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    if _last_deadman_alert_date == today:
        return  # already alerted today

    last = await _get_last_successful_backup_ts()
    if last is not None and (now - last) <= timedelta(hours=hours):
        return  # backup fresh enough

    _last_deadman_alert_date = today
    if last is None:
        age = "успешных бэкапов не найдено"
    else:
        hrs = int((now - last).total_seconds() // 3600)
        age = f"последний успешный бэкап был ~{hrs} ч назад"
    await _notify_backup_failed(
        title="Давно не было бэкапа",
        body=f"Порог — {hours} ч, но {age}. Проверьте авто-бэкап.",
        group_key="backup_deadman",
    )


async def _log_and_maybe_send(filename: str, backup_type: str, size_bytes: int, send_tg: bool) -> None:
    """Write a history entry and optionally send the backup file to Telegram."""
    try:
        from web.backend.api.v2.backup import _log_backup

        class _SchedulerAdmin:
            id = None
            username = "scheduler"
            telegram_id = 0

        await _log_backup(
            filename=filename,
            backup_type=backup_type,
            size_bytes=size_bytes,
            admin=_SchedulerAdmin(),
            notes="Автоматический бэкап по расписанию",
        )
    except Exception as exc:
        logger.debug("Scheduled backup log failed: %s", exc)

    if not send_tg:
        return
    try:
        chat_id, topic_id = resolve_backup_tg_destination()
        if not chat_id:
            logger.warning("Scheduled backup: Telegram enabled but notifications_chat_id not set")
            return
        await send_backup_to_telegram(filename=filename, chat_id=chat_id, topic_id=topic_id)
        logger.info("Scheduled backup %s sent to Telegram", filename)
    except Exception as exc:
        logger.warning("Scheduled backup Telegram send failed: %s", exc)


def resolve_backup_tg_destination() -> tuple:
    """Куда слать бэкап в Telegram: (chat_id | None, topic_id | None).

    Настройки заданные через UI живут в БД (bot_config), env — фолбэк.
    Раньше web-backend читал ТОЛЬКО env: notifications_chat_id, сохранённый
    из UI, игнорировался — и отправка бэкапа падала NO_CHAT_ID, хотя
    обычные уведомления (их шлёт бот, читающий БД) в тот же чат доходили.
    """
    from shared.notification_config import (
        resolve_notification_topic,
        resolve_notifications_chat_id,
    )
    from web.backend.core.config import get_web_settings

    settings = get_web_settings()
    # Та же цепочка, что у обычных уведомлений: свой топик из БД → общий
    # из БД → env. Раньше общий топик, заданный через UI, здесь терялся —
    # бэкап уходил в корень чата, хотя уведомления шли в топик.
    chat_id = resolve_notifications_chat_id(settings.notifications_chat_id)
    topic_raw = resolve_notification_topic(
        "service",
        type_fallback=settings.get_topic_for("service"),
        general_fallback=settings.notifications_topic_id,
    )
    topic_id = None
    if topic_raw:
        try:
            topic_id = int(topic_raw)
        except (TypeError, ValueError):
            topic_id = None
    return (str(chat_id) if chat_id else None), topic_id


async def _run_auto_backup_if_due() -> None:
    """Create a DB (and optionally config) backup when the schedule is due.

    Two modes, config-driven:
    - daily:    once a day at backup_auto_time (HH:MM UTC).
    - interval: first at backup_auto_time, then every backup_auto_interval_hours.
    """
    global _last_auto_backup_ts
    from shared.config_service import config_service

    if not config_service.get("backup_auto_enabled", False):
        return

    now = datetime.now(timezone.utc)
    current_time = now.strftime("%H:%M")
    schedule_time = str(config_service.get("backup_auto_time", "03:00") or "03:00")
    interval_hours = int(config_service.get("backup_auto_interval_hours", 0) or 0)

    if interval_hours > 0:
        # Interval mode: kick off at schedule_time, then every N hours
        if _last_auto_backup_ts is None:
            if current_time != schedule_time:
                return
        elif (now - _last_auto_backup_ts) < timedelta(hours=interval_hours) - timedelta(seconds=30):
            return
    else:
        # Daily mode: once per day at schedule_time
        if _last_auto_backup_ts is not None and \
                _last_auto_backup_ts.strftime("%Y-%m-%d") == now.strftime("%Y-%m-%d"):
            return
        if current_time != schedule_time:
            return

    # Mark timestamp first to avoid a double run within the same minute
    _last_auto_backup_ts = now

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.warning("Scheduled backup skipped: DATABASE_URL not configured")
        return

    send_tg = bool(config_service.get("backup_auto_telegram", False))
    also_config = bool(config_service.get("backup_auto_config", False))

    # Database backup
    logger.info("Running scheduled database backup...")
    try:
        result = await create_database_backup(database_url)
    except Exception as exc:
        logger.error("Scheduled DB backup failed: %s", exc, exc_info=True)
        await _notify_backup_failed("Бэкап БД не выполнен", f"Автоматический бэкап БД упал: {exc}")
        return
    logger.info("Scheduled DB backup created: %s (%s bytes)", result["filename"], result["size_bytes"])
    await _log_and_maybe_send(result["filename"], "database", result["size_bytes"], send_tg)

    # Config backup (optional)
    if also_config:
        try:
            cfg = await export_config()
            logger.info("Scheduled config backup created: %s (%s bytes)", cfg["filename"], cfg["size_bytes"])
            await _log_and_maybe_send(cfg["filename"], "config", cfg["size_bytes"], send_tg)
        except Exception as exc:
            logger.warning("Scheduled config backup failed: %s", exc)
            await _notify_backup_failed("Бэкап конфига не выполнен", f"Автоматический бэкап конфига упал: {exc}")

    # Rotate old backups
    try:
        keep_count = int(config_service.get("backup_auto_keep_count", 10) or 10)
        keep_days = int(config_service.get("backup_auto_keep_days", 30) or 30)
        deleted = rotate_backups(keep_count=keep_count, keep_days=keep_days)
        if deleted:
            logger.info("Scheduled backup rotation: %d old backups removed", deleted)
    except Exception as exc:
        logger.warning("Scheduled backup rotation failed: %s", exc)


async def backup_scheduler_loop() -> None:
    """Background loop that triggers scheduled DB backups (config-driven)."""
    await asyncio.sleep(120)  # startup delay
    while True:
        try:
            await _run_auto_backup_if_due()
        except Exception as exc:
            logger.warning("Backup scheduler tick failed: %s", exc)
        try:
            await _check_deadman()
        except Exception as exc:
            logger.debug("Dead-man check failed: %s", exc)
        await asyncio.sleep(60)

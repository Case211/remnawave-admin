"""Backup service — database dump, config export/import, user import."""
import asyncio
import gzip as gzip_module
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/app/backups"))


def ensure_backup_dir() -> Path:
    """Ensure the backup directory exists."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


# ── Database backup ──────────────────────────────────────────

async def create_database_backup(database_url: str) -> dict:
    """Create a PostgreSQL dump using pg_dump.

    Returns dict with filename, size_bytes, backup_type.
    """
    ensure_backup_dir()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"db_backup_{ts}.sql.gz"
    filepath = BACKUP_DIR / filename

    try:
        proc = await asyncio.create_subprocess_exec(
            "pg_dump", database_url,
            "--no-owner", "--no-privileges", "--clean", "--if-exists",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {stderr.decode()}")

        # Compress with Python gzip (no need for external gzip binary)
        with gzip_module.open(filepath, "wb") as f:
            f.write(stdout)

        size_bytes = filepath.stat().st_size

        return {
            "filename": filename,
            "size_bytes": size_bytes,
            "backup_type": "database",
        }
    except FileNotFoundError:
        raise RuntimeError("pg_dump not found. Ensure PostgreSQL client tools are installed.")


async def restore_database_backup(database_url: str, filename: str) -> None:
    """Restore a PostgreSQL dump from a backup file."""
    filepath = BACKUP_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Backup file not found: {filename}")

    # Read SQL data (decompress if gzipped)
    if filename.endswith(".gz"):
        with gzip_module.open(filepath, "rb") as f:
            sql_data = f.read()
    else:
        sql_data = filepath.read_bytes()

    # Feed SQL to psql via stdin
    psql = await asyncio.create_subprocess_exec(
        "psql", database_url,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await psql.communicate(input=sql_data)

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
                "SELECT key, value, value_type, category, subcategory, "
                "display_name, description, default_value, is_secret, is_readonly "
                "FROM bot_config ORDER BY category, key"
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

        return {
            "filename": filename,
            "size_bytes": size_bytes,
            "backup_type": "config",
        }
    except Exception as e:
        logger.error("Failed to export config: %s", e)
        raise


async def import_config(filename: str, overwrite: bool = False) -> dict:
    """Import settings from a config backup file.

    Returns dict with imported_count, skipped_count.
    """
    filepath = BACKUP_DIR / filename
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
                    "SELECT value FROM bot_config WHERE key = $1", key
                )
                if existing is not None:
                    skipped += 1
                    continue

            await conn.execute(
                "UPDATE bot_config SET value = $2, updated_at = NOW() WHERE key = $1",
                key, str(value),
            )
            imported += 1

    return {"imported_count": imported, "skipped_count": skipped}


# ── User import ──────────────────────────────────────────────

async def import_users_from_file(filename: str) -> dict:
    """Import users from a JSON file (Remnawave export format).

    Returns dict with imported_count, skipped_count, errors.
    """
    filepath = BACKUP_DIR / filename
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
    max_chunk = 49 * 1024 * 1024  # 49 MB (Telegram limit 50 MB)
    parts_sent = 0

    if file_size <= max_chunk:
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
        total_parts = math.ceil(file_size / max_chunk)
        raw = filepath.read_bytes()
        for i in range(total_parts):
            chunk = raw[i * max_chunk : (i + 1) * max_chunk]
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


def save_uploaded_file(filename: str, content: bytes) -> dict:
    """Save an uploaded backup file. Returns file info."""
    import re
    ensure_backup_dir()

    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    if not (safe_name.endswith('.sql.gz') or safe_name.endswith('.json')):
        raise ValueError("Only .sql.gz and .json files are accepted")

    filepath = BACKUP_DIR / safe_name
    if filepath.exists():
        raise FileExistsError(f"File already exists: {safe_name}")

    filepath.write_bytes(content)
    return {
        "filename": safe_name,
        "size_bytes": len(content),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

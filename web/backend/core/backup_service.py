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

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/data/backups"))


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


def delete_backup_file(filename: str) -> bool:
    """Delete a backup file."""
    filepath = BACKUP_DIR / filename
    # Prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        return False
    if filepath.exists() and filepath.is_file():
        filepath.unlink()
        return True
    return False


def get_backup_filepath(filename: str) -> Optional[Path]:
    """Get the full path to a backup file, with path traversal protection."""
    if ".." in filename or "/" in filename or "\\" in filename:
        return None
    filepath = BACKUP_DIR / filename
    if filepath.exists() and filepath.is_file():
        return filepath
    return None

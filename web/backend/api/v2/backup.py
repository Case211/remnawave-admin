"""Backup & Import API endpoints.

Provides database backup/restore, config export/import,
user import, and backup file management.
"""
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, Request, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core.errors import api_error, E

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────

class BackupFileItem(BaseModel):
    filename: str
    size_bytes: int
    created_at: str


class BackupResult(BaseModel):
    filename: str
    size_bytes: int
    backup_type: str


class RestoreRequest(BaseModel):
    filename: str


class ImportConfigRequest(BaseModel):
    filename: str
    overwrite: bool = False


class ImportConfigResult(BaseModel):
    imported_count: int
    skipped_count: int


class ImportUsersRequest(BaseModel):
    filename: str


class ImportUsersResult(BaseModel):
    imported_count: int
    skipped_count: int
    errors: List[dict] = []


class BackupLogItem(BaseModel):
    id: int
    filename: str
    backup_type: str
    size_bytes: int
    status: str
    created_by_username: Optional[str] = None
    notes: Optional[str] = None
    created_at: str


# ── List backups ─────────────────────────────────────────────────

@router.get("/", response_model=List[BackupFileItem])
async def list_backups(
    admin: AdminUser = Depends(require_permission("backups", "view")),
):
    """List all backup files on disk."""
    from web.backend.core.backup_service import list_backup_files
    return list_backup_files()


# ── Backup log (history) ────────────────────────────────────────

@router.get("/log", response_model=List[BackupLogItem])
async def get_backup_log(
    limit: int = 50,
    admin: AdminUser = Depends(require_permission("backups", "view")),
):
    """Get backup operation history."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return []
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, filename, backup_type, size_bytes, status, "
                "created_by_username, notes, created_at "
                "FROM backup_log ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        result = []
        for r in rows:
            d = dict(r)
            if d.get("created_at"):
                d["created_at"] = d["created_at"].isoformat()
            result.append(BackupLogItem(**d))
        return result
    except Exception as e:
        logger.error("Error fetching backup log: %s", e)
        return []


# ── Create database backup ──────────────────────────────────────

@router.post("/database", response_model=BackupResult, status_code=201)
async def create_db_backup(
    admin: AdminUser = Depends(require_permission("backups", "create")),
):
    """Create a PostgreSQL database dump."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise api_error(500, E.DB_UNAVAILABLE, "DATABASE_URL not configured")

    try:
        from web.backend.core.backup_service import create_database_backup
        result = await create_database_backup(database_url)

        # Log the operation
        await _log_backup(
            filename=result["filename"],
            backup_type="database",
            size_bytes=result["size_bytes"],
            admin=admin,
        )

        return BackupResult(**result)
    except Exception as e:
        logger.error("Database backup failed: %s", e, exc_info=True)
        raise api_error(500, E.BACKUP_CREATE_FAILED, str(e))


# ── Create config backup ────────────────────────────────────────

@router.post("/config", response_model=BackupResult, status_code=201)
async def create_config_backup(
    admin: AdminUser = Depends(require_permission("backups", "create")),
):
    """Export all configuration settings as JSON."""
    try:
        from web.backend.core.backup_service import export_config
        result = await export_config()

        await _log_backup(
            filename=result["filename"],
            backup_type="config",
            size_bytes=result["size_bytes"],
            admin=admin,
        )

        return BackupResult(**result)
    except Exception as e:
        raise api_error(500, E.BACKUP_CREATE_FAILED, str(e))


# ── Download backup file ────────────────────────────────────────

@router.get("/download/{filename}")
async def download_backup(
    filename: str,
    admin: AdminUser = Depends(require_permission("backups", "view")),
):
    """Download a backup file."""
    from web.backend.core.backup_service import get_backup_filepath
    filepath = get_backup_filepath(filename)
    if not filepath:
        raise api_error(404, E.BACKUP_NOT_FOUND)

    media_type = "application/gzip" if filename.endswith(".gz") else "application/octet-stream"
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type=media_type,
    )


# ── Delete backup file ──────────────────────────────────────────

@router.delete("/{filename}", status_code=204)
async def delete_backup(
    filename: str,
    admin: AdminUser = Depends(require_permission("backups", "delete")),
):
    """Delete a backup file from disk."""
    from web.backend.core.backup_service import delete_backup_file
    if not delete_backup_file(filename):
        raise api_error(404, E.BACKUP_NOT_FOUND)


# ── Restore database ────────────────────────────────────────────

@router.post("/restore")
async def restore_db_backup(
    body: RestoreRequest,
    admin: AdminUser = Depends(require_permission("backups", "create")),
):
    """Restore a database from a backup file."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise api_error(500, E.DB_UNAVAILABLE, "DATABASE_URL not configured")

    try:
        from web.backend.core.backup_service import restore_database_backup
        await restore_database_backup(database_url, body.filename)

        await _log_backup(
            filename=body.filename,
            backup_type="restore",
            size_bytes=0,
            admin=admin,
            notes="Database restored",
        )

        return {"status": "ok", "message": "Database restored successfully"}
    except FileNotFoundError:
        raise api_error(404, E.BACKUP_NOT_FOUND)
    except RuntimeError as e:
        raise api_error(500, E.BACKUP_RESTORE_FAILED, str(e))


# ── Import config ───────────────────────────────────────────────

@router.post("/import-config", response_model=ImportConfigResult)
async def import_config(
    body: ImportConfigRequest,
    admin: AdminUser = Depends(require_permission("backups", "create")),
):
    """Import settings from a config backup file."""
    try:
        from web.backend.core.backup_service import import_config as do_import
        result = await do_import(body.filename, overwrite=body.overwrite)

        await _log_backup(
            filename=body.filename,
            backup_type="config_import",
            size_bytes=0,
            admin=admin,
            notes=f"Imported {result['imported_count']}, skipped {result['skipped_count']}",
        )

        return ImportConfigResult(**result)
    except FileNotFoundError:
        raise api_error(404, E.BACKUP_NOT_FOUND)
    except Exception as e:
        raise api_error(500, E.IMPORT_FAILED, str(e))


# ── Import users ────────────────────────────────────────────────

@router.post("/import-users", response_model=ImportUsersResult)
async def import_users(
    body: ImportUsersRequest,
    admin: AdminUser = Depends(require_permission("backups", "create")),
):
    """Import users from a JSON file."""
    try:
        from web.backend.core.backup_service import import_users_from_file
        result = await import_users_from_file(body.filename)

        await _log_backup(
            filename=body.filename,
            backup_type="user_import",
            size_bytes=0,
            admin=admin,
            notes=f"Imported {result['imported_count']}, skipped {result['skipped_count']}",
        )

        return ImportUsersResult(**result)
    except FileNotFoundError:
        raise api_error(404, E.BACKUP_NOT_FOUND)
    except Exception as e:
        raise api_error(500, E.IMPORT_FAILED, str(e))


# ── Helper ──────────────────────────────────────────────────────

async def _log_backup(
    filename: str,
    backup_type: str,
    size_bytes: int,
    admin: AdminUser,
    notes: str | None = None,
) -> None:
    """Write an entry to backup_log table."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return
        admin_id = admin.id if hasattr(admin, "id") else None
        admin_username = admin.username or str(admin.telegram_id)
        async with db_service.acquire() as conn:
            await conn.execute(
                "INSERT INTO backup_log "
                "(filename, backup_type, size_bytes, status, created_by_admin_id, created_by_username, notes) "
                "VALUES ($1, $2, $3, 'completed', $4, $5, $6)",
                filename, backup_type, size_bytes, admin_id, admin_username, notes,
            )
    except Exception as e:
        logger.warning("Failed to log backup operation: %s", e)


# ══════════════════════════════════════════════════════════════════
# Full Config Export / Import
# ══════════════════════════════════════════════════════════════════


@router.post("/export-full-config")
async def export_full_config(
    admin: AdminUser = Depends(require_permission("backups", "create")),
):
    """Export all configuration as single JSON: roles, permissions, automation rules,
    alert rules, scripts, settings, notification channels, scheduled tasks."""
    import json as _json
    from datetime import datetime, timezone
    from shared.database import db_service

    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    sections = {}

    async with db_service.acquire() as conn:
        # Roles
        rows = await conn.fetch("SELECT * FROM roles ORDER BY id")
        sections["roles"] = [dict(r) for r in rows]

        # Permissions
        rows = await conn.fetch("SELECT * FROM admin_permissions ORDER BY role_id, resource")
        sections["permissions"] = [dict(r) for r in rows]

        # Automation rules
        rows = await conn.fetch("SELECT * FROM automation_rules ORDER BY id")
        sections["automation_rules"] = [dict(r) for r in rows]

        # Alert rules
        rows = await conn.fetch("SELECT * FROM alert_rules ORDER BY id")
        sections["alert_rules"] = [dict(r) for r in rows]

        # Scripts
        rows = await conn.fetch(
            "SELECT id, name, display_name, description, category, script_content, "
            "timeout_seconds, requires_root, is_builtin, source_url "
            "FROM node_scripts ORDER BY id"
        )
        sections["scripts"] = [dict(r) for r in rows]

        # Settings
        rows = await conn.fetch("SELECT key, value, category FROM settings ORDER BY key")
        sections["settings"] = [dict(r) for r in rows]

        # Notification channels (mask secrets)
        rows = await conn.fetch("SELECT * FROM notification_channel_configs ORDER BY id")
        channels = []
        for r in rows:
            d = dict(r)
            config = d.get("config")
            if isinstance(config, dict):
                for secret_key in ("webhook_url", "bot_token", "password", "api_key"):
                    if secret_key in config and config[secret_key]:
                        config[secret_key] = "***REDACTED***"
            channels.append(d)
        sections["notification_channels"] = channels

        # Scheduled tasks
        try:
            rows = await conn.fetch("SELECT * FROM scheduled_tasks ORDER BY id")
            sections["scheduled_tasks"] = [dict(r) for r in rows]
        except Exception:
            sections["scheduled_tasks"] = []

    # Serialize
    def _default(obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if isinstance(obj, (set, frozenset)):
            return list(obj)
        return str(obj)

    export_data = {
        "version": "2.8.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_by": admin.username,
        "sections": sections,
    }

    return export_data


class ImportConfigRequest(BaseModel):
    config: dict
    strategy: str = "skip"  # skip, overwrite
    sections: Optional[List[str]] = None  # None = all


@router.post("/import-full-config")
async def import_full_config(
    body: ImportConfigRequest,
    admin: AdminUser = Depends(require_permission("backups", "create")),
):
    """Import configuration from exported JSON. Strategy: skip (don't touch existing), overwrite."""
    from shared.database import db_service

    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    config = body.config
    strategy = body.strategy
    selected = set(body.sections) if body.sections else None

    if "sections" not in config:
        raise api_error(400, "INVALID_FORMAT", "Missing 'sections' key in config")

    sections = config["sections"]
    result = {"imported": {}, "skipped": {}, "errors": []}

    async with db_service.acquire() as conn:
        async with conn.transaction():
            # Settings
            if "settings" in sections and (not selected or "settings" in selected):
                imported, skipped = 0, 0
                for s in sections["settings"]:
                    key = s.get("key")
                    value = s.get("value")
                    if not key:
                        continue
                    existing = await conn.fetchrow("SELECT key FROM settings WHERE key = $1", key)
                    if existing and strategy == "skip":
                        skipped += 1
                        continue
                    await conn.execute(
                        "INSERT INTO settings (key, value, category) VALUES ($1, $2, $3) "
                        "ON CONFLICT (key) DO UPDATE SET value = $2",
                        key, value, s.get("category", "general"),
                    )
                    imported += 1
                result["imported"]["settings"] = imported
                result["skipped"]["settings"] = skipped

            # Roles
            if "roles" in sections and (not selected or "roles" in selected):
                imported, skipped = 0, 0
                for r in sections["roles"]:
                    name = r.get("name")
                    if not name:
                        continue
                    existing = await conn.fetchrow("SELECT id FROM roles WHERE name = $1", name)
                    if existing and strategy == "skip":
                        skipped += 1
                        continue
                    if existing and strategy == "overwrite":
                        await conn.execute(
                            "UPDATE roles SET description = $2, is_system = $3 WHERE name = $1",
                            name, r.get("description"), r.get("is_system", False),
                        )
                    else:
                        await conn.execute(
                            "INSERT INTO roles (name, description, is_system) VALUES ($1, $2, $3) "
                            "ON CONFLICT (name) DO NOTHING",
                            name, r.get("description"), r.get("is_system", False),
                        )
                    imported += 1
                result["imported"]["roles"] = imported
                result["skipped"]["roles"] = skipped

            # Scripts
            if "scripts" in sections and (not selected or "scripts" in selected):
                imported, skipped = 0, 0
                for s in sections["scripts"]:
                    name = s.get("name")
                    if not name:
                        continue
                    existing = await conn.fetchrow("SELECT id FROM node_scripts WHERE name = $1", name)
                    if existing and strategy == "skip":
                        skipped += 1
                        continue
                    if existing and strategy == "overwrite":
                        await conn.execute(
                            "UPDATE node_scripts SET script_content = $2, description = $3, "
                            "display_name = $4, category = $5, timeout_seconds = $6, "
                            "requires_root = $7 WHERE name = $1",
                            name, s.get("script_content", s.get("content", "")), s.get("description"),
                            s.get("display_name"), s.get("category"),
                            s.get("timeout_seconds", 300), s.get("requires_root", False),
                        )
                    else:
                        await conn.execute(
                            "INSERT INTO node_scripts (name, display_name, description, category, "
                            "script_content, timeout_seconds, requires_root, is_builtin) "
                            "VALUES ($1, $2, $3, $4, $5, $6, $7, false) ON CONFLICT DO NOTHING",
                            name, s.get("display_name"), s.get("description"),
                            s.get("category"), s.get("script_content", s.get("content", "")),
                            s.get("timeout_seconds", 300), s.get("requires_root", False),
                        )
                    imported += 1
                result["imported"]["scripts"] = imported
                result["skipped"]["scripts"] = skipped

            # Alert rules
            if "alert_rules" in sections and (not selected or "alert_rules" in selected):
                imported, skipped = 0, 0
                for r in sections["alert_rules"]:
                    name = r.get("name")
                    if not name:
                        continue
                    existing = await conn.fetchrow("SELECT id FROM alert_rules WHERE name = $1", name)
                    if existing and strategy == "skip":
                        skipped += 1
                        continue
                    if existing and strategy == "overwrite":
                        await conn.execute("DELETE FROM alert_rules WHERE name = $1", name)
                    import json as _json
                    channels = r.get("channels", ["in_app"])
                    if isinstance(channels, list):
                        channels = _json.dumps(channels)
                    await conn.execute(
                        "INSERT INTO alert_rules (name, description, is_enabled, rule_type, "
                        "metric, operator, threshold, duration_minutes, channels, severity, "
                        "cooldown_minutes, group_key, title_template, body_template) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, $13, $14)",
                        name, r.get("description"), r.get("is_enabled", True),
                        r.get("rule_type", "threshold"), r.get("metric"), r.get("operator"),
                        r.get("threshold"), r.get("duration_minutes", 0),
                        channels if isinstance(channels, str) else _json.dumps(channels),
                        r.get("severity", "warning"), r.get("cooldown_minutes", 30),
                        r.get("group_key"), r.get("title_template"), r.get("body_template"),
                    )
                    imported += 1
                result["imported"]["alert_rules"] = imported
                result["skipped"]["alert_rules"] = skipped

    return result


# ── Disk usage ──────────────────────────────────────────────────

@router.get("/disk-usage")
async def get_disk_usage(
    admin: AdminUser = Depends(require_permission("backups", "view")),
):
    """Get backup directory disk usage stats."""
    from web.backend.core.backup_service import get_disk_usage
    return get_disk_usage()


# ── Upload backup file ──────────────────────────────────────────

@router.post("/upload", response_model=BackupFileItem, status_code=201)
async def upload_backup(
    file: UploadFile = File(...),
    admin: AdminUser = Depends(require_permission("backups", "create")),
):
    """Upload a backup file (.sql.gz or .json)."""
    from web.backend.core.backup_service import save_uploaded_file

    if not file.filename:
        raise api_error(400, "INVALID_FILENAME")

    content = await file.read()
    max_size = 500 * 1024 * 1024  # 500 MB
    if len(content) > max_size:
        raise api_error(400, "FILE_TOO_LARGE", f"Max size: {max_size // 1024 // 1024} MB")

    try:
        result = save_uploaded_file(file.filename, content)
    except ValueError as e:
        raise api_error(400, "INVALID_FILE_TYPE", str(e))
    except FileExistsError as e:
        raise api_error(409, "FILE_EXISTS", str(e))

    try:
        from shared.database import db_service
        if db_service.is_connected:
            async with db_service.acquire() as conn:
                await conn.execute(
                    "INSERT INTO backup_log (filename, backup_type, size_bytes, status, created_by_username) "
                    "VALUES ($1, 'upload', $2, 'success', $3)",
                    result["filename"], result["size_bytes"], admin.username,
                )
    except Exception:
        pass

    return BackupFileItem(**result)


# ── Rotate backups ──────────────────────────────────────────────

@router.post("/rotate")
async def rotate_backups_endpoint(
    keep_count: int = 10,
    keep_days: int = 30,
    admin: AdminUser = Depends(require_permission("backups", "delete")),
):
    """Manually rotate old backups (keep N newest or within N days)."""
    from web.backend.core.backup_service import rotate_backups
    deleted = rotate_backups(keep_count=keep_count, keep_days=keep_days)
    return {"status": "ok", "deleted": deleted}


# ── Send backup to Telegram ─────────────────────────────────────

class TelegramSendRequest(BaseModel):
    filename: str
    chat_id: Optional[str] = None
    topic_id: Optional[int] = None


@router.post("/send-telegram")
async def send_backup_telegram(
    data: TelegramSendRequest,
    admin: AdminUser = Depends(require_permission("backups", "view")),
):
    """Send a backup file to a Telegram chat/topic. Auto-splits files >49 MB."""
    from web.backend.core.backup_service import send_backup_to_telegram
    from web.backend.core.config import get_web_settings

    settings = get_web_settings()
    chat_id = data.chat_id or settings.notifications_chat_id
    if not chat_id:
        raise api_error(400, "NO_CHAT_ID", "Specify chat_id or configure NOTIFICATIONS_CHAT_ID")

    try:
        result = await send_backup_to_telegram(
            filename=data.filename,
            chat_id=chat_id,
            topic_id=data.topic_id,
        )
        return result
    except FileNotFoundError:
        raise api_error(404, "FILE_NOT_FOUND")
    except Exception as e:
        logger.error("Failed to send backup to Telegram: %s", e)
        raise api_error(500, "TELEGRAM_SEND_FAILED", str(e))

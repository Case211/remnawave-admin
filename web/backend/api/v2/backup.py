"""Backup & Import API endpoints.

Provides database backup/restore, config export/import,
user import, and backup file management.
"""
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, Request
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

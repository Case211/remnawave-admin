"""System Logs API — streaming and retrieval of backend/bot logs."""
import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from web.backend.api.deps import (
    require_permission,
    get_current_admin_ws,
    AdminUser,
)

logger = logging.getLogger(__name__)
router = APIRouter()

LOG_DIR = Path("/app/logs")

# Available log files
LOG_FILES = {
    "web_info": "web_INFO.log",
    "web_warning": "web_WARNING.log",
    "bot_info": "bot_INFO.log",
    "bot_warning": "bot_WARNING.log",
}

# Regex for parsing log lines
# Format: 2026-02-10 14:30:00 | INFO    | web        | Message
LOG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*\|\s*(\w+)\s*\|\s*([\w\.-]+)\s*\|\s*(.*)$"
)


def _parse_log_line(line: str) -> Optional[dict]:
    """Parse a single log line into structured data."""
    line = line.strip()
    if not line:
        return None
    m = LOG_PATTERN.match(line)
    if m:
        return {
            "timestamp": m.group(1),
            "level": m.group(2).strip(),
            "source": m.group(3).strip(),
            "message": m.group(4).strip(),
        }
    # Continuation line (e.g., traceback) — return as-is
    return {
        "timestamp": None,
        "level": None,
        "source": None,
        "message": line,
    }


def _read_log_tail(file_path: Path, lines: int = 200) -> List[dict]:
    """Read last N lines from a log file."""
    if not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = all_lines[-lines:]
        result = []
        for raw in tail:
            parsed = _parse_log_line(raw)
            if parsed:
                result.append(parsed)
        return result
    except Exception as e:
        logger.error("Failed to read log file %s: %s", file_path, e)
        return []


@router.get("/files")
async def list_log_files(
    admin: AdminUser = Depends(require_permission("settings", "view")),
):
    """List available log files with sizes."""
    files = []
    for key, filename in LOG_FILES.items():
        path = LOG_DIR / filename
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        files.append({
            "key": key,
            "filename": filename,
            "exists": exists,
            "size_bytes": size,
            "modified_at": (
                datetime.fromtimestamp(path.stat().st_mtime).isoformat()
                if exists else None
            ),
        })
    return files


@router.get("/tail")
async def tail_log(
    file: str = Query("web_info", description="Log file key"),
    lines: int = Query(200, ge=10, le=2000),
    level: Optional[str] = Query(None, description="Filter by level: INFO, WARNING, ERROR"),
    search: Optional[str] = Query(None, description="Filter by message content"),
    admin: AdminUser = Depends(require_permission("settings", "view")),
):
    """Read last N lines from a log file with optional filtering."""
    filename = LOG_FILES.get(file)
    if not filename:
        return {"items": [], "file": file, "error": "Unknown log file"}

    path = LOG_DIR / filename
    entries = _read_log_tail(path, lines * 2)  # read extra for filtering

    # Filter by level
    if level:
        level_upper = level.upper()
        entries = [e for e in entries if e.get("level") == level_upper or e.get("level") is None]

    # Filter by search
    if search:
        search_lower = search.lower()
        entries = [
            e for e in entries
            if search_lower in (e.get("message") or "").lower()
            or search_lower in (e.get("source") or "").lower()
        ]

    # Take last N entries
    entries = entries[-lines:]

    return {"items": entries, "file": file, "total": len(entries)}


@router.websocket("/stream")
async def stream_logs(
    websocket: WebSocket,
    token: str = Query(...),
    file: str = Query("web_info"),
):
    """WebSocket endpoint for real-time log streaming.

    Tails the log file and sends new lines to the client.
    """
    try:
        admin = await get_current_admin_ws(websocket, token)
    except Exception:
        return

    filename = LOG_FILES.get(file)
    if not filename:
        await websocket.close(code=4000, reason="Unknown log file")
        return

    await websocket.accept()
    path = LOG_DIR / filename

    logger.info("Log stream started: %s by %s", file, admin.username)

    try:
        # Track file position
        if path.exists():
            fp = open(path, "r", encoding="utf-8", errors="replace")
            fp.seek(0, 2)  # Go to end
        else:
            fp = None

        while True:
            try:
                # Check for new lines
                if fp and path.exists():
                    new_lines = fp.readlines()
                    for line in new_lines:
                        parsed = _parse_log_line(line)
                        if parsed:
                            await websocket.send_json({
                                "type": "log_line",
                                "data": parsed,
                            })
                elif not fp and path.exists():
                    # File appeared, open it
                    fp = open(path, "r", encoding="utf-8", errors="replace")
                    fp.seek(0, 2)

                # Check for client messages (ping/pong, file switch)
                try:
                    msg = await asyncio.wait_for(
                        websocket.receive_text(), timeout=1.0
                    )
                    if msg == "ping":
                        await websocket.send_text("pong")
                    elif msg.startswith("{"):
                        import json
                        data = json.loads(msg)
                        if data.get("type") == "switch_file":
                            new_file = data.get("file", "")
                            new_filename = LOG_FILES.get(new_file)
                            if new_filename:
                                if fp:
                                    fp.close()
                                file = new_file
                                filename = new_filename
                                path = LOG_DIR / filename
                                if path.exists():
                                    fp = open(path, "r", encoding="utf-8", errors="replace")
                                    fp.seek(0, 2)
                                else:
                                    fp = None
                                await websocket.send_json({
                                    "type": "file_switched",
                                    "data": {"file": new_file},
                                })
                except asyncio.TimeoutError:
                    pass

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.debug("Log stream error: %s", e)
                await asyncio.sleep(1)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Log stream error: %s", e)
    finally:
        if fp:
            fp.close()
        logger.info("Log stream ended: %s", file)

"""System Logs API — streaming and retrieval of backend/bot/infrastructure logs."""
import asyncio
import logging
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

# ── Available log files ──────────────────────────────────────────
# key -> (filename, format)
# format: "admin" = standard admin log, "nginx_error" = nginx error log,
#          "postgres" = PostgreSQL log, "raw" = plain text lines

LOG_FILES = {
    # Web Backend
    "web_info": ("web_INFO.log", "admin"),
    "web_warning": ("web_WARNING.log", "admin"),
    # Telegram Bot
    "bot_info": ("bot_INFO.log", "admin"),
    "bot_warning": ("bot_WARNING.log", "admin"),
    # Nginx
    "nginx_access": ("nginx_access.log", "admin"),
    "nginx_error": ("nginx_error.log", "nginx_error"),
    # PostgreSQL
    "postgres": ("postgres.log", "postgres"),
    # Node Agent
    "nodeagent_info": ("nodeagent_INFO.log", "admin"),
    "nodeagent_warning": ("nodeagent_WARNING.log", "admin"),
}

# ── Log line parsers ─────────────────────────────────────────────

# Admin format: 2026-02-10 14:30:00 | INFO    | web        | Message
# Also handles ISO timestamps from nginx: 2026-02-10T14:30:00+03:00 | ...
ADMIN_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(?:[+\-]\d{2}:\d{2})?\s*\|\s*(\w+)\s*\|\s*([\w\.-]+)\s*\|\s*(.*)$"
)

# Nginx error format: 2026/02/10 14:30:00 [error] 1234#0: *1 message
NGINX_ERROR_PATTERN = re.compile(
    r"^(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})\s+\[(\w+)\]\s+\d+#\d+:\s*(?:\*\d+\s+)?(.*)$"
)

# PostgreSQL format: 2026-02-10 14:30:00.123 UTC [1] LOG:  message
PG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\.\d+\s+\w+\s+\[\d+\]\s+(\w+):\s+(.*)$"
)


def _parse_admin_line(line: str) -> Optional[dict]:
    m = ADMIN_PATTERN.match(line)
    if m:
        ts = m.group(1).replace("T", " ")
        return {
            "timestamp": ts,
            "level": m.group(2).strip(),
            "source": m.group(3).strip(),
            "message": m.group(4).strip(),
        }
    return None


def _parse_nginx_error_line(line: str) -> Optional[dict]:
    m = NGINX_ERROR_PATTERN.match(line)
    if m:
        ts = m.group(1).replace("/", "-")
        level = m.group(2).upper()
        if level == "WARN":
            level = "WARNING"
        elif level == "EMERG" or level == "ALERT" or level == "CRIT":
            level = "ERROR"
        return {
            "timestamp": ts,
            "level": level,
            "source": "nginx",
            "message": m.group(3).strip(),
        }
    return None


def _parse_pg_line(line: str) -> Optional[dict]:
    m = PG_PATTERN.match(line)
    if m:
        level = m.group(2).upper()
        if level == "LOG":
            level = "INFO"
        elif level == "FATAL" or level == "PANIC":
            level = "ERROR"
        elif level == "NOTICE":
            level = "INFO"
        return {
            "timestamp": m.group(1),
            "level": level,
            "source": "postgres",
            "message": m.group(3).strip(),
        }
    return None


def _parse_log_line(line: str, fmt: str = "admin") -> Optional[dict]:
    """Parse a single log line into structured data."""
    line = line.strip()
    if not line:
        return None

    parsed = None
    if fmt == "admin":
        parsed = _parse_admin_line(line)
    elif fmt == "nginx_error":
        parsed = _parse_nginx_error_line(line)
    elif fmt == "postgres":
        parsed = _parse_pg_line(line)

    if parsed:
        return parsed

    # Continuation line (e.g., traceback) — return as-is
    return {
        "timestamp": None,
        "level": None,
        "source": None,
        "message": line,
    }


def _read_log_tail(file_path: Path, lines: int = 200, fmt: str = "admin") -> List[dict]:
    """Read last N lines from a log file."""
    if not file_path.exists():
        return []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        tail = all_lines[-lines:]
        result = []
        for raw in tail:
            parsed = _parse_log_line(raw, fmt)
            if parsed:
                result.append(parsed)
        return result
    except Exception as e:
        logger.error("Failed to read log file %s: %s", file_path, e)
        return []


@router.get("/files")
async def list_log_files(
    admin: AdminUser = Depends(require_permission("logs", "view")),
):
    """List available log files with sizes."""
    files = []
    for key, (filename, _fmt) in LOG_FILES.items():
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
    admin: AdminUser = Depends(require_permission("logs", "view")),
):
    """Read last N lines from a log file with optional filtering."""
    file_info = LOG_FILES.get(file)
    if not file_info:
        return {"items": [], "file": file, "error": "Unknown log file"}

    filename, fmt = file_info
    path = LOG_DIR / filename
    entries = _read_log_tail(path, lines * 2, fmt)  # read extra for filtering

    # Filter by level
    if level:
        level_upper = level.upper()
        entries = [e for e in entries if e.get("level") == level_upper or e.get("level") is None]

    # Filter by search (case-insensitive)
    if search:
        search_lower = search.lower()
        entries = [
            e for e in entries
            if search_lower in (e.get("message") or "").lower()
            or search_lower in (e.get("source") or "").lower()
            or search_lower in (e.get("level") or "").lower()
            or search_lower in (e.get("timestamp") or "").lower()
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

    file_info = LOG_FILES.get(file)
    if not file_info:
        await websocket.close(code=4000, reason="Unknown log file")
        return

    filename, fmt = file_info
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
                        parsed = _parse_log_line(line, fmt)
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
                            new_file_info = LOG_FILES.get(new_file)
                            if new_file_info:
                                if fp:
                                    fp.close()
                                file = new_file
                                filename, fmt = new_file_info
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

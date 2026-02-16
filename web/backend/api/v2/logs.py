"""System Logs API — streaming and retrieval of backend/bot/frontend/violations/postgres logs."""
import asyncio
import json
import logging
import os
import re
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from web.backend.api.deps import (
    require_permission,
    get_current_admin_ws,
    AdminUser,
)

logger = logging.getLogger(__name__)
router = APIRouter()

LOG_DIR = Path("/app/logs")

# ── Available log sources ────────────────────────────────────────
# key -> (filename | None, format)
# format: "json" = structlog JSON, "postgres" = PostgreSQL, "memory" = in-memory buffer

LOG_FILES = {
    "backend": ("backend.log", "json"),
    "bot": ("bot.log", "json"),
    "frontend": (None, "memory"),
    "violations": ("violations.log", "json"),
    "postgres": ("postgres.log", "postgres"),
}

# ── Frontend log buffer (in-memory ring buffer) ──────────────────

_frontend_log_buffer: deque[dict] = deque(maxlen=5000)


class FrontendLogEntry(BaseModel):
    level: str = "ERROR"
    message: str
    source: Optional[str] = None
    stack: Optional[str] = None
    url: Optional[str] = None
    userAgent: Optional[str] = None
    timestamp: Optional[str] = None


# ── Log line parsers ─────────────────────────────────────────────

def _format_event(data: dict) -> str:
    """Format special event types into human-readable messages."""
    event = data.get("event", "")

    if event == "api_call":
        method = data.pop("method", "")
        endpoint = data.pop("endpoint", "")
        status = data.pop("status_code", "")
        duration = data.pop("duration_ms", "")
        parts = []
        if method and endpoint:
            parts.append(f"{method} {endpoint}")
        if status:
            parts.append(f"\u2192 {status}")
        if duration:
            parts.append(f"({duration}ms)")
        return " ".join(parts) if parts else event

    if event == "api_error":
        method = data.pop("method", "")
        endpoint = data.pop("endpoint", "")
        status = data.pop("status_code", "")
        error = data.pop("error", "")
        parts = []
        if method and endpoint:
            parts.append(f"{method} {endpoint}")
        if status:
            parts.append(f"\u2192 {status}")
        if error:
            parts.append(f"| {error}")
        return " ".join(parts) if parts else event

    if event == "button_click":
        callback = data.pop("callback", "")
        return f"\u229e {callback}" if callback else event

    if event == "command":
        cmd = data.pop("cmd", "")
        args = data.pop("args", "")
        parts = [f"/{cmd}"] if cmd else []
        if args:
            parts.append(args)
        return " ".join(parts) if parts else event

    if event == "input":
        field = data.pop("field", "")
        preview = data.pop("preview", "")
        parts = []
        if field:
            parts.append(field)
        if preview:
            parts.append(f"\u2192 {preview}")
        return " ".join(parts) if parts else event

    return event


def _parse_json_line(line: str) -> Optional[dict]:
    """Parse a structlog JSON line."""
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
        # structlog JSON format: {"event": "...", "level": "...", "logger": "...", "timestamp": "..."}
        message = _format_event(data)
        extra = {k: v for k, v in data.items()
                 if k not in ("event", "level", "logger", "timestamp")}
        return {
            "timestamp": data.get("timestamp"),
            "level": (data.get("level") or "").upper(),
            "source": data.get("logger", ""),
            "message": message,
            "extra": extra if extra else None,
        }
    except (json.JSONDecodeError, TypeError):
        return None


# PostgreSQL format: 2026-02-10 14:30:00.123 UTC [1] LOG:  message
PG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\.\d+\s+\w+\s+\[\d+\]\s+(\w+):\s+(.*)$"
)


def _parse_pg_line(line: str) -> Optional[dict]:
    m = PG_PATTERN.match(line.strip())
    if m:
        level = m.group(2).upper()
        if level == "LOG":
            level = "INFO"
        elif level in ("FATAL", "PANIC"):
            level = "ERROR"
        elif level == "NOTICE":
            level = "INFO"
        return {
            "timestamp": m.group(1),
            "level": level,
            "source": "postgres",
            "message": m.group(3).strip(),
            "extra": None,
        }
    return None


# Legacy admin format (for backward compatibility with old log files)
ADMIN_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(?:[+\-]\d{2}:\d{2})?\s*\|\s*(\w+)\s*\|\s*([\w\.-]+)\s*\|\s*(.*)$"
)


def _parse_admin_line(line: str) -> Optional[dict]:
    m = ADMIN_PATTERN.match(line.strip())
    if m:
        return {
            "timestamp": m.group(1).replace("T", " "),
            "level": m.group(2).strip().upper(),
            "source": m.group(3).strip(),
            "message": m.group(4).strip(),
            "extra": None,
        }
    return None


def _parse_log_line(line: str, fmt: str = "json") -> Optional[dict]:
    """Parse a single log line into structured data."""
    line = line.strip()
    if not line:
        return None

    parsed = None
    if fmt == "json":
        parsed = _parse_json_line(line)
        if not parsed:
            # Fallback to legacy admin format
            parsed = _parse_admin_line(line)
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
        "extra": None,
    }


def _read_log_tail(file_path: Path, lines: int = 200, fmt: str = "json") -> List[dict]:
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


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/files")
async def list_log_files(
    admin: AdminUser = Depends(require_permission("logs", "view")),
):
    """List available log sources with sizes."""
    files = []
    for key, (filename, fmt) in LOG_FILES.items():
        if fmt == "memory":
            files.append({
                "key": key,
                "filename": None,
                "exists": True,
                "size_bytes": len(_frontend_log_buffer),
                "modified_at": None,
            })
            continue

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
    file: str = Query("backend", description="Log source key"),
    lines: int = Query(200, ge=10, le=2000),
    level: Optional[str] = Query(None, description="Filter by level: DEBUG, INFO, WARNING, ERROR"),
    search: Optional[str] = Query(None, description="Filter by message content"),
    admin: AdminUser = Depends(require_permission("logs", "view")),
):
    """Read last N lines from a log source with optional filtering."""
    file_info = LOG_FILES.get(file)
    if not file_info:
        return {"items": [], "file": file, "error": "Unknown log source"}

    filename, fmt = file_info

    # Frontend logs from memory buffer
    if fmt == "memory":
        entries = list(_frontend_log_buffer)
    else:
        path = LOG_DIR / filename
        entries = _read_log_tail(path, lines * 2, fmt)

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


@router.post("/frontend")
async def ingest_frontend_logs(
    entries: List[FrontendLogEntry],
    admin: AdminUser = Depends(require_permission("logs", "view")),
):
    """Ingest frontend error logs into in-memory buffer."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for entry in entries:
        _frontend_log_buffer.append({
            "timestamp": entry.timestamp or now,
            "level": entry.level.upper(),
            "source": entry.source or "frontend",
            "message": entry.message,
            "extra": {
                k: v for k, v in {
                    "stack": entry.stack,
                    "url": entry.url,
                    "userAgent": entry.userAgent,
                }.items() if v
            } or None,
        })
    return {"ingested": len(entries)}


@router.get("/level")
async def get_log_levels(
    admin: AdminUser = Depends(require_permission("logs", "view")),
):
    """Get current log levels for backend and bot."""
    # Backend level: read from root logger's console handler
    root = logging.getLogger()
    backend_level = "INFO"
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.handlers.RotatingFileHandler):
            backend_level = logging.getLevelName(handler.level)
            break

    # Bot level: read from config_service if available
    bot_level = "INFO"
    try:
        from shared.config_service import config_service
        bot_level = await config_service.get("log_level", "INFO")
    except Exception:
        pass

    return {"backend": backend_level, "bot": bot_level}


@router.put("/level")
async def set_log_level(
    component: str = Query(..., description="Component: backend or bot"),
    level: str = Query(..., description="Level: DEBUG, INFO, WARNING, ERROR"),
    admin: AdminUser = Depends(require_permission("logs", "edit")),
):
    """Dynamically change log level for backend or bot."""
    level_upper = level.upper()
    if level_upper not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        return {"error": "Invalid level"}

    if component == "backend":
        numeric_level = getattr(logging, level_upper, logging.INFO)
        root = logging.getLogger()
        for handler in root.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.handlers.RotatingFileHandler):
                handler.setLevel(numeric_level)
            elif isinstance(handler, logging.handlers.RotatingFileHandler):
                base = os.path.basename(handler.baseFilename)
                if "violations" not in base:
                    handler.setLevel(numeric_level)
        logger.info("Backend log level changed to %s by %s", level_upper, admin.username)
        return {"component": "backend", "level": level_upper}

    elif component == "bot":
        try:
            from shared.config_service import config_service
            await config_service.set("log_level", level_upper)
            logger.info("Bot log level changed to %s by %s", level_upper, admin.username)
            return {"component": "bot", "level": level_upper}
        except Exception as e:
            return {"error": f"Failed to set bot level: {e}"}

    return {"error": "Unknown component (use 'backend' or 'bot')"}


@router.websocket("/stream")
async def stream_logs(
    websocket: WebSocket,
    token: str = Query(...),
    file: str = Query("backend"),
):
    """WebSocket endpoint for real-time log streaming."""
    try:
        admin = await get_current_admin_ws(websocket, token)
    except Exception as e:
        logger.debug("Non-critical: %s", e)
        return

    file_info = LOG_FILES.get(file)
    if not file_info:
        await websocket.close(code=4000, reason="Unknown log source")
        return

    filename, fmt = file_info
    await websocket.accept()

    logger.info("Log stream started: %s by %s", file, admin.username)

    try:
        if fmt == "memory":
            # Stream frontend logs from memory buffer
            last_idx = len(_frontend_log_buffer)
            while True:
                try:
                    current_len = len(_frontend_log_buffer)
                    if current_len > last_idx:
                        items = list(_frontend_log_buffer)
                        new_items = items[last_idx:]
                        for item in new_items:
                            await websocket.send_json({
                                "type": "log_line",
                                "data": item,
                            })
                        last_idx = current_len

                    try:
                        msg = await asyncio.wait_for(
                            websocket.receive_text(), timeout=1.0
                        )
                        if msg == "ping":
                            await websocket.send_text("pong")
                        elif msg.startswith("{"):
                            data = json.loads(msg)
                            if data.get("type") == "switch_file":
                                new_file = data.get("file", "")
                                new_info = LOG_FILES.get(new_file)
                                if new_info:
                                    file = new_file
                                    filename, fmt = new_info
                                    await websocket.send_json({
                                        "type": "file_switched",
                                        "data": {"file": new_file},
                                    })
                                    if fmt != "memory":
                                        break  # Switch to file-based streaming
                                    last_idx = len(_frontend_log_buffer)
                    except asyncio.TimeoutError:
                        pass
                except WebSocketDisconnect:
                    return
                except Exception as e:
                    logger.debug("Log stream error: %s", e)
                    await asyncio.sleep(1)

            # If we broke out to switch to file-based streaming, fall through
            if fmt == "memory":
                return

        # File-based streaming
        path = LOG_DIR / filename
        fp = None

        try:
            if path.exists():
                fp = open(path, "r", encoding="utf-8", errors="replace")
                fp.seek(0, 2)  # Go to end

            while True:
                try:
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
                        fp = open(path, "r", encoding="utf-8", errors="replace")
                        fp.seek(0, 2)

                    try:
                        msg = await asyncio.wait_for(
                            websocket.receive_text(), timeout=1.0
                        )
                        if msg == "ping":
                            await websocket.send_text("pong")
                        elif msg.startswith("{"):
                            data = json.loads(msg)
                            if data.get("type") == "switch_file":
                                new_file = data.get("file", "")
                                new_file_info = LOG_FILES.get(new_file)
                                if new_file_info:
                                    if fp:
                                        fp.close()
                                        fp = None
                                    file = new_file
                                    filename, fmt = new_file_info
                                    if fmt == "memory":
                                        await websocket.send_json({
                                            "type": "file_switched",
                                            "data": {"file": new_file},
                                        })
                                        # Restart with memory streaming
                                        last_idx = len(_frontend_log_buffer)
                                        while True:
                                            current_len = len(_frontend_log_buffer)
                                            if current_len > last_idx:
                                                items = list(_frontend_log_buffer)
                                                for item in items[last_idx:]:
                                                    await websocket.send_json({
                                                        "type": "log_line",
                                                        "data": item,
                                                    })
                                                last_idx = current_len
                                            try:
                                                msg2 = await asyncio.wait_for(
                                                    websocket.receive_text(), timeout=1.0
                                                )
                                                if msg2 == "ping":
                                                    await websocket.send_text("pong")
                                                elif msg2.startswith("{"):
                                                    d2 = json.loads(msg2)
                                                    if d2.get("type") == "switch_file":
                                                        sf = d2.get("file", "")
                                                        si = LOG_FILES.get(sf)
                                                        if si:
                                                            file = sf
                                                            filename, fmt = si
                                                            await websocket.send_json({
                                                                "type": "file_switched",
                                                                "data": {"file": sf},
                                                            })
                                                            if fmt != "memory":
                                                                path = LOG_DIR / filename
                                                                if path.exists():
                                                                    fp = open(path, "r", encoding="utf-8", errors="replace")
                                                                    fp.seek(0, 2)
                                                                break
                                                            last_idx = len(_frontend_log_buffer)
                                                    elif d2.get("type") == "stop":
                                                        return
                                            except asyncio.TimeoutError:
                                                pass
                                    else:
                                        path = LOG_DIR / filename
                                        if path.exists():
                                            fp = open(path, "r", encoding="utf-8", errors="replace")
                                            fp.seek(0, 2)
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

        finally:
            if fp:
                fp.close()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Log stream error: %s", e)
    finally:
        logger.info("Log stream ended: %s", file)

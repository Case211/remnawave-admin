"""Script catalog API endpoints.

CRUD for scripts + execution on nodes via Agent v2 WebSocket.
Import from GitHub URLs and repositories.
"""
import json
import logging
import re
from datetime import datetime
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from web.backend.core.errors import api_error, E
from pydantic import BaseModel, ConfigDict

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core.agent_manager import agent_manager
from web.backend.core.agent_hmac import sign_command_with_ts
from web.backend.core.rate_limit import limiter, RATE_ANALYTICS

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────

class ScriptListItem(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    category: str
    timeout_seconds: int = 60
    requires_root: bool = False
    is_builtin: bool = False


class ScriptDetail(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    category: str
    script_content: str
    timeout_seconds: int = 60
    requires_root: bool = False
    is_builtin: bool = False
    source_url: Optional[str] = None
    imported_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ScriptCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    category: str = 'custom'
    script_content: str
    timeout_seconds: int = 60
    requires_root: bool = False


class ScriptUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    script_content: Optional[str] = None
    timeout_seconds: Optional[int] = None
    requires_root: Optional[bool] = None


class ExecScriptRequest(BaseModel):
    script_id: int
    node_uuid: str
    env_vars: Optional[dict] = None


class ExecScriptResponse(BaseModel):
    exec_id: int
    status: str = 'pending'


class ExecStatusResponse(BaseModel):
    id: int
    node_uuid: str
    status: str
    output: Optional[str] = None
    exit_code: Optional[int] = None
    started_at: str
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None


# ── Script CRUD ──────────────────────────────────────────────────

@router.get("/scripts", response_model=List[ScriptListItem])
@limiter.limit(RATE_ANALYTICS)
async def list_scripts(
    request: Request,
    category: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """List all scripts, optionally filtered by category."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return []

        async with db_service.acquire() as conn:
            if category:
                rows = await conn.fetch(
                    "SELECT id, name, display_name, description, category, timeout_seconds, requires_root, is_builtin "
                    "FROM node_scripts WHERE category = $1 ORDER BY is_builtin DESC, display_name",
                    category,
                )
            else:
                rows = await conn.fetch(
                    "SELECT id, name, display_name, description, category, timeout_seconds, requires_root, is_builtin "
                    "FROM node_scripts ORDER BY category, is_builtin DESC, display_name",
                )

        return [ScriptListItem(**dict(r)) for r in rows]
    except Exception as e:
        logger.error("Error listing scripts: %s", e)
        return []


@router.get("/scripts/{script_id}", response_model=ScriptDetail)
@limiter.limit(RATE_ANALYTICS)
async def get_script(
    request: Request,
    script_id: int,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Get full script details including content."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM node_scripts WHERE id = $1", script_id,
        )
    if not row:
        raise api_error(404, E.SCRIPT_NOT_FOUND)

    r = dict(row)
    for dt_field in ('created_at', 'updated_at', 'imported_at'):
        if r.get(dt_field):
            r[dt_field] = r[dt_field].isoformat()
    return ScriptDetail(**r)


@router.post("/scripts", response_model=ScriptDetail, status_code=201)
async def create_script(
    body: ScriptCreate,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Create a custom script."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    admin_id = admin.id if hasattr(admin, 'id') else None

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO node_scripts (name, display_name, description, category,
                                      script_content, timeout_seconds, requires_root,
                                      is_builtin, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7, false, $8)
            RETURNING *
            """,
            body.name, body.display_name, body.description, body.category,
            body.script_content, body.timeout_seconds, body.requires_root,
            admin_id,
        )

    r = dict(row)
    for dt_field in ('created_at', 'updated_at', 'imported_at'):
        if r.get(dt_field):
            r[dt_field] = r[dt_field].isoformat()
    return ScriptDetail(**r)


@router.patch("/scripts/{script_id}", response_model=ScriptDetail)
async def update_script(
    script_id: int,
    body: ScriptUpdate,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Update a script. Cannot modify built-in scripts."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    async with db_service.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT is_builtin FROM node_scripts WHERE id = $1", script_id,
        )
        if not existing:
            raise api_error(404, E.SCRIPT_NOT_FOUND)
        if existing["is_builtin"]:
            raise api_error(403, E.BUILTIN_SCRIPT_PROTECTED)

        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            raise api_error(400, E.NO_FIELDS_TO_UPDATE)

        set_clauses = []
        params = []
        idx = 1
        for key, val in updates.items():
            set_clauses.append(f"{key} = ${idx}")
            params.append(val)
            idx += 1
        params.append(script_id)

        row = await conn.fetchrow(
            f"UPDATE node_scripts SET {', '.join(set_clauses)}, updated_at = NOW() "
            f"WHERE id = ${idx} RETURNING *",
            *params,
        )

    r = dict(row)
    for dt_field in ('created_at', 'updated_at', 'imported_at'):
        if r.get(dt_field):
            r[dt_field] = r[dt_field].isoformat()
    return ScriptDetail(**r)


@router.delete("/scripts/{script_id}", status_code=204)
async def delete_script(
    script_id: int,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Delete a custom script. Cannot delete built-in scripts."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    async with db_service.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT is_builtin FROM node_scripts WHERE id = $1", script_id,
        )
        if not existing:
            raise api_error(404, E.SCRIPT_NOT_FOUND)
        if existing["is_builtin"]:
            raise api_error(403, E.BUILTIN_SCRIPT_PROTECTED)

        await conn.execute("DELETE FROM node_scripts WHERE id = $1", script_id)


# ── Script Execution ─────────────────────────────────────────────

@router.post("/exec-script", response_model=ExecScriptResponse)
async def exec_script(
    body: ExecScriptRequest,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Execute a script on a node via Agent v2 WebSocket."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    # Check agent connected
    if not agent_manager.is_connected(body.node_uuid):
        raise api_error(400, E.AGENT_NOT_CONNECTED)

    # Get script
    async with db_service.acquire() as conn:
        script = await conn.fetchrow(
            "SELECT * FROM node_scripts WHERE id = $1", body.script_id,
        )
    if not script:
        raise api_error(404, E.SCRIPT_NOT_FOUND)

    # Get agent token
    agent_token = None
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT agent_token FROM nodes WHERE uuid = $1", body.node_uuid,
        )
        if row:
            agent_token = row["agent_token"]
    if not agent_token:
        raise api_error(400, E.AGENT_TOKEN_NOT_FOUND)

    admin_id = admin.id if hasattr(admin, 'id') else None
    admin_username = admin.username or str(admin.telegram_id)

    # Create command log entry
    async with db_service.acquire() as conn:
        cmd_row = await conn.fetchrow(
            """
            INSERT INTO node_command_log
                (node_uuid, admin_id, admin_username, command_type, command_data, status)
            VALUES ($1, $2, $3, 'exec_script', $4, 'running')
            RETURNING id
            """,
            body.node_uuid, admin_id, admin_username,
            f"script={script['name']}" + (f" env={list(body.env_vars.keys())}" if body.env_vars else ""),
        )
        exec_id = cmd_row["id"]

    # Prepend env vars as export statements if provided
    script_content = script["script_content"]
    if body.env_vars:
        import shlex
        exports = "\n".join(
            f"export {k}={shlex.quote(str(v))}"
            for k, v in body.env_vars.items()
            if k.isidentifier()
        )
        if exports:
            # Insert exports after shebang line if present
            if script_content.startswith("#!"):
                first_nl = script_content.index("\n")
                script_content = (
                    script_content[:first_nl + 1]
                    + exports + "\n"
                    + script_content[first_nl + 1:]
                )
            else:
                script_content = exports + "\n" + script_content

    # Send command to agent
    cmd_payload = {
        "type": "exec_script",
        "command_id": exec_id,
        "script_content": script_content,
        "timeout": script["timeout_seconds"],
    }
    payload_with_ts, sig = sign_command_with_ts(cmd_payload, agent_token)
    payload_with_ts["_sig"] = sig

    sent = await agent_manager.send_command(body.node_uuid, payload_with_ts)
    if not sent:
        # Update log to error
        async with db_service.acquire() as conn:
            await conn.execute(
                "UPDATE node_command_log SET status = 'error', output = 'Failed to send to agent' "
                "WHERE id = $1", exec_id,
            )
        raise api_error(500, E.AGENT_COMMAND_FAILED)

    return ExecScriptResponse(exec_id=exec_id, status="running")


@router.get("/exec/{exec_id}", response_model=ExecStatusResponse)
@limiter.limit(RATE_ANALYTICS)
async def get_exec_status(
    request: Request,
    exec_id: int,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Get execution status and output."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, node_uuid, status, output, exit_code,
                   started_at, finished_at, duration_ms
            FROM node_command_log WHERE id = $1
            """,
            exec_id,
        )
    if not row:
        raise api_error(404, E.EXECUTION_NOT_FOUND)

    r = dict(row)

    # Auto-timeout: if script is "running" for too long, mark as timed out
    if r.get("status") == "running" and r.get("started_at"):
        from datetime import datetime, timezone
        started = r["started_at"]
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        # Default timeout 180s + 30s grace
        if elapsed > 210:
            async with db_service.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE node_command_log
                    SET status = 'error', output = 'Timed out: agent did not respond',
                        finished_at = NOW(),
                        duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER * 1000
                    WHERE id = $1 AND status = 'running'
                    """,
                    exec_id,
                )
            r["status"] = "error"
            r["output"] = "Timed out: agent did not respond"
            r["duration_ms"] = int(elapsed * 1000)

    for dt_field in ('started_at', 'finished_at'):
        if r.get(dt_field):
            r[dt_field] = r[dt_field].isoformat()
        elif dt_field == 'started_at':
            r[dt_field] = ''
    return ExecStatusResponse(**r)


# ── GitHub Import ────────────────────────────────────────────────


class ImportUrlRequest(BaseModel):
    url: str
    name: str
    display_name: str
    description: Optional[str] = None
    category: str = 'custom'
    timeout_seconds: int = 60
    requires_root: bool = False


class BrowseRepoRequest(BaseModel):
    repo_url: str


class RepoFileItem(BaseModel):
    path: str
    name: str
    size: int
    download_url: str


class BrowseRepoResponse(BaseModel):
    repo: str
    files: List[RepoFileItem] = []
    truncated: bool = False


class BulkImportRequest(BaseModel):
    files: List[ImportUrlRequest]


class BulkImportResponse(BaseModel):
    imported: int = 0
    errors: List[str] = []


def _normalize_github_url(url: str) -> str:
    """Convert github.com file URL to raw.githubusercontent.com."""
    m = re.match(r'https?://github\.com/([^/]+)/([^/]+)/blob/(.+)', url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return url


def _parse_repo_url(url: str) -> tuple:
    """Parse GitHub repo URL -> (owner, repo)."""
    m = re.match(r'https?://github\.com/([^/]+)/([^/\s#?.]+)', url)
    if not m:
        raise api_error(400, E.INVALID_GITHUB_URL)
    return m.group(1), m.group(2).replace('.git', '')


async def _download_script_content(url: str) -> str:
    """Download script content from URL. Max 1MB. Only allows github.com/raw.githubusercontent.com."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    allowed_hosts = {"github.com", "raw.githubusercontent.com"}
    if parsed.hostname not in allowed_hosts:
        raise api_error(400, E.INVALID_GITHUB_URL)
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "remnawave-admin/script-import"})
        resp.raise_for_status()
        if len(resp.content) > 1_048_576:
            raise api_error(400, E.CONTENT_TOO_LARGE)
        return resp.text


@router.post("/scripts/import-url", response_model=ScriptDetail, status_code=201)
async def import_script_from_url(
    body: ImportUrlRequest,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Import a script by downloading content from a URL."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    url = _normalize_github_url(body.url.strip())

    try:
        content = await _download_script_content(url)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=400, detail=f"Failed to download: HTTP {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=400, detail="Failed to download script")

    admin_id = admin.id if hasattr(admin, 'id') else None

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO node_scripts (name, display_name, description, category,
                                      script_content, timeout_seconds, requires_root,
                                      is_builtin, created_by, source_url, imported_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, false, $8, $9, NOW())
            RETURNING *
            """,
            body.name, body.display_name, body.description, body.category,
            content, body.timeout_seconds, body.requires_root,
            admin_id, url,
        )

    r = dict(row)
    for dt_field in ('created_at', 'updated_at', 'imported_at'):
        if r.get(dt_field):
            r[dt_field] = r[dt_field].isoformat()
    return ScriptDetail(**r)


@router.post("/scripts/browse-repo", response_model=BrowseRepoResponse)
@limiter.limit(RATE_ANALYTICS)
async def browse_github_repo(
    request: Request,
    body: BrowseRepoRequest,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Browse a GitHub repository and list .sh files."""
    owner, repo = _parse_repo_url(body.repo_url.strip())

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Get default branch
            repo_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "remnawave-admin",
                },
            )
            repo_resp.raise_for_status()
            default_branch = repo_resp.json().get("default_branch", "main")

            # Get tree recursively
            tree_resp = await client.get(
                f"https://api.github.com/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1",
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "remnawave-admin",
                },
            )
            tree_resp.raise_for_status()
            data = tree_resp.json()

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise api_error(404, E.REPO_NOT_FOUND)
        raise HTTPException(status_code=400, detail="GitHub API error")
    except Exception as e:
        raise HTTPException(status_code=400, detail="GitHub API error")

    files = []
    for item in data.get("tree", []):
        if item.get("type") == "blob" and item["path"].endswith(".sh"):
            files.append(RepoFileItem(
                path=item["path"],
                name=item["path"].split("/")[-1],
                size=item.get("size", 0),
                download_url=f"https://raw.githubusercontent.com/{owner}/{repo}/{default_branch}/{item['path']}",
            ))

    return BrowseRepoResponse(
        repo=f"{owner}/{repo}",
        files=files,
        truncated=data.get("truncated", False),
    )


@router.post("/scripts/bulk-import", response_model=BulkImportResponse, status_code=201)
async def bulk_import_scripts(
    body: BulkImportRequest,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Bulk import scripts from URLs."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    admin_id = admin.id if hasattr(admin, 'id') else None
    imported = 0
    errors = []

    for item in body.files:
        url = _normalize_github_url(item.url.strip())
        try:
            content = await _download_script_content(url)

            async with db_service.acquire() as conn:
                await conn.fetchrow(
                    """
                    INSERT INTO node_scripts (name, display_name, description, category,
                                              script_content, timeout_seconds, requires_root,
                                              is_builtin, created_by, source_url, imported_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, false, $8, $9, NOW())
                    RETURNING id
                    """,
                    item.name, item.display_name, item.description, item.category,
                    content, item.timeout_seconds, item.requires_root,
                    admin_id, url,
                )
            imported += 1
        except Exception as e:
            errors.append(f"{item.name}: {e}")

    return BulkImportResponse(imported=imported, errors=errors)


# ══════════════════════════════════════════════════════════════════
# Scheduled Tasks (Cron)
# ══════════════════════════════════════════════════════════════════


class ScheduledTaskCreate(BaseModel):
    script_id: int
    node_uuid: str
    cron_expression: str
    is_enabled: bool = True
    env_vars: dict = {}


class ScheduledTaskUpdate(BaseModel):
    cron_expression: Optional[str] = None
    is_enabled: Optional[bool] = None
    env_vars: Optional[dict] = None


class ScheduledTaskItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    script_id: int
    node_uuid: str
    cron_expression: str
    is_enabled: bool = True
    env_vars: Optional[dict] = None
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    next_run_at: Optional[datetime] = None
    run_count: int = 0
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    # Joined fields
    script_name: Optional[str] = None
    node_name: Optional[str] = None


def _normalize_scheduled_task_row(row) -> dict:
    """Normalize asyncpg row to dict compatible with ScheduledTaskItem.

    asyncpg returns UUID columns as uuid.UUID and JSONB as str; Pydantic expects str/dict.
    """
    d = dict(row)
    if d.get("node_uuid") is not None:
        d["node_uuid"] = str(d["node_uuid"])
    if isinstance(d.get("env_vars"), str):
        d["env_vars"] = json.loads(d["env_vars"])
    return d


@router.get("/scheduled-tasks")
async def list_scheduled_tasks(
    admin: AdminUser = Depends(require_permission("fleet", "view")),
):
    """List all scheduled tasks with script and node names."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT st.*, ns.name AS script_name, n.name AS node_name
            FROM scheduled_tasks st
            LEFT JOIN node_scripts ns ON ns.id = st.script_id
            LEFT JOIN nodes n ON n.uuid = st.node_uuid
            ORDER BY st.created_at DESC
            """
        )
    items = [ScheduledTaskItem(**_normalize_scheduled_task_row(r)) for r in rows]
    return {"items": items, "total": len(items)}


@router.post("/scheduled-tasks", status_code=201)
async def create_scheduled_task(
    body: ScheduledTaskCreate,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Create a new scheduled task."""
    # Validate cron expression
    from web.backend.core.automation_engine import cron_matches_now
    try:
        parts = body.cron_expression.strip().split()
        if len(parts) != 5:
            raise ValueError("Expected 5 parts")
    except Exception:
        raise api_error(400, "INVALID_CRON", "Invalid CRON expression, expected 5 fields: min hour dom month dow")

    from shared.database import db_service
    env_json = json.dumps(body.env_vars) if body.env_vars else "{}"
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO scheduled_tasks (script_id, node_uuid, cron_expression, is_enabled, env_vars, created_by)
            VALUES ($1, $2::uuid, $3, $4, $5::jsonb, $6)
            RETURNING *
            """,
            body.script_id, body.node_uuid, body.cron_expression,
            body.is_enabled, env_json, admin.account_id,
        )
    return ScheduledTaskItem(**_normalize_scheduled_task_row(row))


@router.patch("/scheduled-tasks/{task_id}")
async def update_scheduled_task(
    task_id: int,
    body: ScheduledTaskUpdate,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Update a scheduled task."""
    from shared.database import db_service
    updates = []
    args = [task_id]
    idx = 1

    if body.cron_expression is not None:
        parts = body.cron_expression.strip().split()
        if len(parts) != 5:
            raise api_error(400, "INVALID_CRON", "Invalid CRON expression")
        idx += 1
        updates.append(f"cron_expression = ${idx}")
        args.append(body.cron_expression)

    if body.is_enabled is not None:
        idx += 1
        updates.append(f"is_enabled = ${idx}")
        args.append(body.is_enabled)

    if body.env_vars is not None:
        idx += 1
        updates.append(f"env_vars = ${idx}::jsonb")
        args.append(json.dumps(body.env_vars))

    if not updates:
        raise api_error(400, "NO_CHANGES")

    updates.append("updated_at = NOW()")

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE scheduled_tasks SET {', '.join(updates)} WHERE id = $1 RETURNING *",
            *args,
        )
    if not row:
        raise api_error(404, "NOT_FOUND")

    return ScheduledTaskItem(**_normalize_scheduled_task_row(row))


@router.delete("/scheduled-tasks/{task_id}")
async def delete_scheduled_task(
    task_id: int,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Delete a scheduled task."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "DELETE FROM scheduled_tasks WHERE id = $1 RETURNING id", task_id
        )
    if not row:
        raise api_error(404, "NOT_FOUND")
    return {"status": "ok"}


@router.post("/scheduled-tasks/{task_id}/toggle")
async def toggle_scheduled_task(
    task_id: int,
    admin: AdminUser = Depends(require_permission("fleet", "scripts")),
):
    """Toggle enabled/disabled."""
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE scheduled_tasks SET is_enabled = NOT is_enabled, updated_at = NOW() "
            "WHERE id = $1 RETURNING *",
            task_id,
        )
    if not row:
        raise api_error(404, "NOT_FOUND")
    return ScheduledTaskItem(**_normalize_scheduled_task_row(row))

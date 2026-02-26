"""Update checker — compares locally installed version against GitHub Releases."""
import logging
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import httpx

logger = logging.getLogger(__name__)

GITHUB_REPO = "Case211/remnawave-admin"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# Fallback version shown when version detection fails
_FALLBACK_VERSION = "unknown"

# Cache: check at most once every 30 minutes
_cache: Dict[str, Any] = {}
_cache_ts: float = 0
_CACHE_TTL = 1800  # 30 min

# Local version is determined once at startup
_local_version: Optional[str] = None


def _detect_local_version() -> str:
    """Detect installed version from git tags, VERSION file, or env var.

    Priority:
    1. APP_VERSION environment variable (set in Docker or .env)
    2. Git tag on current commit (e.g. "2.4" from tag "2.4" or "v2.4")
    3. VERSION file in project root (written during Docker build)
    4. Fallback "unknown"
    """
    global _local_version
    if _local_version is not None:
        return _local_version

    # 1. Check environment variable
    import os
    env_ver = os.environ.get("APP_VERSION", "").strip().lstrip("v")
    if env_ver and env_ver != "unknown":
        _local_version = env_ver
        return _local_version

    # Find project root (walk up from this file)
    project_root = Path(__file__).resolve().parent.parent.parent.parent

    # 2. Try VERSION file first (works in Docker where .git is absent)
    version_file = project_root / "VERSION"
    if version_file.exists():
        ver = version_file.read_text().strip().lstrip("v")
        if ver and ver != "unknown":
            _local_version = ver
            return _local_version

    # 3. Try git describe --tags
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            tag = result.stdout.strip().lstrip("v")
            # Check if we're exactly on the tag or ahead
            result2 = subprocess.run(
                ["git", "describe", "--tags", "--long"],
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result2.returncode == 0:
                # Format: "2.4-0-gabcdef" (0 means exactly on tag)
                parts = result2.stdout.strip().rsplit("-", 2)
                if len(parts) == 3 and parts[1] != "0":
                    _local_version = f"{tag}+{parts[1]}"
                else:
                    _local_version = tag
            else:
                _local_version = tag
            return _local_version
    except Exception as e:
        logger.debug("git describe failed: %s", e)

    _local_version = _FALLBACK_VERSION
    return _local_version


def _parse_version(ver: str) -> Tuple[int, ...]:
    """Parse version string like '2.4.1' into tuple (2, 4, 1) for comparison."""
    # Strip any +N suffix (e.g. "2.4+3")
    base = ver.split("+")[0]
    parts = []
    for p in base.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            break
    return tuple(parts) if parts else (0,)


async def _fetch_latest_release() -> Optional[Dict[str, Any]]:
    """Fetch latest release data from GitHub API. Returns None on failure."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GITHUB_API_URL,
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "remnawave-admin/update-checker",
                },
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("GitHub API request failed: %s", e)
        return None


async def get_latest_version() -> str:
    """Return the locally installed version."""
    return _detect_local_version()


async def check_for_updates() -> Dict[str, Any]:
    """Check GitHub for latest release. Returns version info with changelog."""
    global _cache, _cache_ts

    if time.time() - _cache_ts < _CACHE_TTL and _cache:
        return _cache

    current = _detect_local_version()
    data = await _fetch_latest_release()

    if data is None:
        result = {
            "current_version": current,
            "latest_version": None,
            "update_available": False,
            "release_url": None,
            "changelog": None,
            "published_at": None,
        }
        _cache = result
        _cache_ts = time.time()
        return result

    latest_tag = data.get("tag_name", "").lstrip("v")
    release_url = data.get("html_url", "")
    changelog = data.get("body", "")
    published_at = data.get("published_at")

    # Compare versions
    update_available = False
    if current != _FALLBACK_VERSION and latest_tag:
        try:
            update_available = _parse_version(latest_tag) > _parse_version(current)
        except Exception:
            pass

    result = {
        "current_version": current,
        "latest_version": latest_tag or None,
        "update_available": update_available,
        "release_url": release_url,
        "changelog": changelog[:2000] if changelog else None,
        "published_at": published_at,
    }
    _cache = result
    _cache_ts = time.time()
    return result


async def get_dependency_versions() -> Dict[str, Any]:
    """Collect versions of key dependencies."""
    deps = {}

    # Python version
    import sys
    deps["python"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # PostgreSQL version
    try:
        from shared.database import db_service
        if db_service.is_connected:
            async with db_service.acquire() as conn:
                row = await conn.fetchval("SELECT version()")
                if row:
                    # "PostgreSQL 16.1 ..."
                    parts = row.split()
                    deps["postgresql"] = parts[1] if len(parts) > 1 else row
    except Exception:
        deps["postgresql"] = None

    # FastAPI version
    try:
        import fastapi
        deps["fastapi"] = fastapi.__version__
    except Exception:
        deps["fastapi"] = None

    # Xray versions on nodes (extract from raw_data JSON if available)
    try:
        from shared.database import db_service
        if db_service.is_connected:
            async with db_service.acquire() as conn:
                # Check if xray_version column exists
                col_exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'nodes' AND column_name = 'xray_version'
                    )
                    """
                )
                if col_exists:
                    rows = await conn.fetch(
                        "SELECT name, xray_version FROM nodes WHERE xray_version IS NOT NULL"
                    )
                    deps["xray_nodes"] = {r["name"]: r["xray_version"] for r in rows}
                else:
                    # Try extracting from raw_data JSON
                    rows = await conn.fetch(
                        "SELECT name, raw_data FROM nodes WHERE raw_data IS NOT NULL"
                    )
                    xray_versions = {}
                    for r in rows:
                        rd = r["raw_data"] if isinstance(r["raw_data"], dict) else {}
                        ver = rd.get("xray_version") or rd.get("xrayVersion")
                        if ver and r["name"]:
                            xray_versions[r["name"]] = ver
                    deps["xray_nodes"] = xray_versions
    except Exception:
        deps["xray_nodes"] = {}

    return deps

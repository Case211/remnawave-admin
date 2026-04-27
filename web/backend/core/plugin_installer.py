"""Wheel-based plugin installer.

The panel scans ``RWA_PLUGINS_DIR`` (default ``/app/plugins``) at startup
and ``pip install``-s every wheel that isn't already present in the
running Python's site-packages. Operators can drop wheels there
manually or upload them through the admin UI (``api/v2/admin_plugins.py``);
both paths funnel into the same code in this module.

Why we ask ``importlib.metadata`` instead of trusting a sentinel file:
the plugins directory is a bind-mount, so it survives ``docker compose
down/up``, but the *container's* site-packages does not. After a
``docker compose pull`` operators get a fresh container with the wheel
file still on the volume but no pip install — a marker-based check
would see the marker and skip install, leaving the plugin half-present
(its DB migrations are recorded but its Python package isn't there).
Distribution lookup catches this case automatically.

- We use ``--no-deps`` because plugin authors are expected to depend
  only on libraries the panel itself already has. Pulling in arbitrary
  transitive dependencies from third-party wheels is a security
  liability we don't want to take on.
- We deliberately don't import the new package after install. Python's
  import machinery doesn't reliably re-discover entry points without a
  process restart, so the contract is "install + restart" rather than
  "install + magic". The admin UI surfaces this.
"""
from __future__ import annotations

import importlib.metadata
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


PLUGINS_DIR_ENV = "RWA_PLUGINS_DIR"
DEFAULT_PLUGINS_DIR = "/app/plugins"

# Hard cap on the size of an uploaded wheel — anything bigger than 50 MB
# is almost certainly a mistake and we don't want to absorb it on the
# panel's filesystem.
MAX_WHEEL_BYTES = 50 * 1024 * 1024

# Wheel filenames look like: ``name-1.2.3-py3-none-any.whl``.
# We use the first dash-separated segment as the package name. This is the
# pip convention; ``pkginfo`` would be more rigorous but adding a dep for
# a one-off parse isn't worth it.
_WHEEL_RE = re.compile(r"^(?P<name>[A-Za-z0-9_]+)-(?P<version>[A-Za-z0-9_.]+)(?:-.+)?\.whl$")


@dataclass(frozen=True)
class InstalledWheel:
    path: Path
    package_name: str
    version: str


def plugins_dir() -> Path:
    """Resolve the plugins directory, creating it if missing."""
    raw = os.environ.get(PLUGINS_DIR_ENV) or DEFAULT_PLUGINS_DIR
    p = Path(raw)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Read-only mounts are valid (the operator may want immutable
        # plugin sets). Just log and let downstream code handle it.
        logger.info("plugins_dir.readonly", extra={"path": str(p)})
    return p


def installed_marker_dir() -> Path:
    p = plugins_dir() / ".installed"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def parse_wheel_name(filename: str) -> Optional[InstalledWheel]:
    """Pull the package name + version out of a wheel filename.

    Returns ``None`` for filenames that don't look like wheels — callers
    skip them rather than blowing up. The name is normalised by replacing
    underscores with hyphens, since pip treats ``foo_bar`` and ``foo-bar``
    as the same distribution.
    """
    match = _WHEEL_RE.match(filename)
    if not match:
        return None
    return InstalledWheel(
        path=Path(filename),
        package_name=match.group("name").replace("_", "-").lower(),
        version=match.group("version"),
    )


def list_wheel_files() -> List[Path]:
    """Every ``*.whl`` directly under the plugins directory."""
    d = plugins_dir()
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.whl") if p.is_file())


def is_distribution_installed(package_name: str, version: Optional[str] = None) -> bool:
    """True if the *running* Python has this distribution importable.

    Optional version pin lets us treat a wheel-version mismatch as
    "needs reinstall" — useful when the operator drops a newer wheel
    on top of an older one without going through the upload flow.
    """
    try:
        dist = importlib.metadata.distribution(package_name)
    except importlib.metadata.PackageNotFoundError:
        return False
    if version and dist.version != version:
        return False
    return True


def mark_installed(wheel: Path) -> None:
    """Optional: drop a sentinel file. Kept around for forensic logging
    (``ls /app/plugins/.installed`` shows the last install pass) but no
    longer authoritative. ``is_distribution_installed`` is the source of
    truth.
    """
    try:
        (installed_marker_dir() / wheel.name).touch()
    except OSError:
        logger.warning("plugin_installer.mark_failed", extra={"wheel": wheel.name})


def scan_and_install_wheels() -> List[str]:
    """Install any wheels whose distribution isn't importable yet.

    Returns the list of wheel filenames that were actually installed.
    Idempotent: when the distribution is already present at the wheel's
    version we skip pip entirely.
    """
    installed: List[str] = []
    for wheel in list_wheel_files():
        meta = parse_wheel_name(wheel.name)
        if meta is None:
            logger.warning("plugin_installer.unrecognised_wheel", extra={"wheel": wheel.name})
            continue
        if is_distribution_installed(meta.package_name, version=meta.version):
            continue
        try:
            _pip_install(wheel)
            mark_installed(wheel)
            installed.append(wheel.name)
            logger.info(
                "plugin_installer.installed",
                extra={"package": meta.package_name, "version": meta.version},
            )
        except subprocess.CalledProcessError as exc:
            logger.error(
                "plugin_installer.pip_failed",
                extra={"wheel": wheel.name, "rc": exc.returncode},
            )
    return installed


def _pip_install(wheel: Path) -> None:
    """``pip install --no-deps`` against the running interpreter."""
    cmd = [sys.executable, "-m", "pip", "install", "--no-deps", "--quiet", str(wheel)]
    subprocess.run(cmd, check=True, timeout=120)


def accept_uploaded_wheel(*, filename: str, contents: bytes) -> InstalledWheel:
    """Persist an uploaded wheel into the plugins directory and pip-install it.

    Validates filename + size before touching disk. Raises ``ValueError``
    on bad input — caller is responsible for surfacing that to the
    operator. ``pip install`` runs immediately so subsequent module
    discovery (after a restart) doesn't need a second pass over
    ``scan_and_install_wheels``. If pip itself fails the caller gets
    ``RuntimeError``.
    """
    if len(contents) > MAX_WHEEL_BYTES:
        raise ValueError("wheel exceeds maximum allowed size")
    safe_name = os.path.basename(filename)
    if not safe_name.endswith(".whl"):
        raise ValueError("only .whl files are accepted")
    meta = parse_wheel_name(safe_name)
    if meta is None:
        raise ValueError("filename is not a recognised wheel")

    target = plugins_dir() / safe_name
    # Replace any existing copy with the same filename (typical re-upload
    # of the same version), but if a *different* version of the same
    # package exists we leave both — uninstall is an explicit operation.
    target.write_bytes(contents)
    try:
        _pip_install(target)
    except subprocess.CalledProcessError as exc:
        # Don't leave a wheel on disk that pip refused — operator should
        # see exactly what's installed.
        try:
            target.unlink()
        except OSError:
            pass
        raise RuntimeError(f"pip install failed (rc={exc.returncode})") from exc
    mark_installed(target)
    return InstalledWheel(path=target, package_name=meta.package_name, version=meta.version)


def remove_wheel(wheel_filename: str) -> bool:
    """Delete a wheel file and its install marker. Idempotent."""
    safe = os.path.basename(wheel_filename)
    target = plugins_dir() / safe
    marker = installed_marker_dir() / safe
    removed = False
    if target.exists():
        try:
            target.unlink()
            removed = True
        except OSError:
            logger.warning("plugin_installer.remove_failed", extra={"wheel": safe})
    if marker.exists():
        try:
            marker.unlink()
        except OSError:
            pass
    return removed


def pip_uninstall(package_name: str) -> bool:
    """Best-effort ``pip uninstall``. Reports success but a process
    restart is still required for FastAPI to drop the routes."""
    cmd = [sys.executable, "-m", "pip", "uninstall", "-y", "--quiet", package_name]
    try:
        subprocess.run(cmd, check=True, timeout=60)
        return True
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "plugin_installer.uninstall_failed",
            extra={"package": package_name, "rc": exc.returncode},
        )
        return False


def reset_plugins_dir() -> None:
    """Wipe the plugins directory. Used by tests; keep it explicit."""
    d = plugins_dir()
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True, exist_ok=True)

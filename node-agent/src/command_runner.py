"""
Agent Command Runner — routes and executes commands from the backend.

Handles command types: exec_script, shell_session, pty_input, service_status.
Includes HMAC signature verification and forbidden pattern blocking.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
from typing import Any, Callable, Awaitable, Dict, Optional

from .config import Settings

logger = logging.getLogger(__name__)

# ── Security: Forbidden Patterns ──────────────────────────────────

FORBIDDEN_PATTERNS = [
    re.compile(r'rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\s*$', re.IGNORECASE),     # rm -rf /
    re.compile(r'rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\*', re.IGNORECASE),        # rm -rf /*
    re.compile(r'mkfs\b', re.IGNORECASE),                                       # mkfs
    re.compile(r'dd\s+if=', re.IGNORECASE),                                     # dd if=
    re.compile(r':\(\)\s*\{\s*:\|\s*:\s*&\s*\}\s*;', re.IGNORECASE),          # fork bomb
    re.compile(r'shutdown\s+(-[hPr]\s+)?now', re.IGNORECASE),                  # shutdown
    re.compile(r'init\s+0', re.IGNORECASE),                                     # init 0
    re.compile(r'halt\b', re.IGNORECASE),                                       # halt
    re.compile(r'poweroff\b', re.IGNORECASE),                                   # poweroff
    re.compile(r'>\s*/dev/sd[a-z]', re.IGNORECASE),                            # write to disk device
    re.compile(r'chmod\s+-R\s+777\s+/', re.IGNORECASE),                         # chmod -R 777 /
]

ALLOWED_COMMAND_TYPES = {
    "exec_script",
    "shell_session",
    "pty_input",
    "pty_resize",
    "service_status",
    "ping",
}


def _is_forbidden(command_text: str) -> bool:
    """Check if a command matches any forbidden pattern."""
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(command_text):
            return True
    return False


# ── HMAC Verification ────────────────────────────────────────────

def _derive_key(secret_key: str, agent_token: str) -> bytes:
    """Derive HMAC key from secret + agent token."""
    return hashlib.sha256(f"{secret_key}:{agent_token}".encode()).digest()


def verify_signature(
    payload: Dict[str, Any],
    signature: str,
    secret_key: str,
    agent_token: str,
    max_age_seconds: int = 60,
) -> bool:
    """Verify HMAC-SHA256 signature and timestamp freshness."""
    ts = payload.get("_ts")
    if ts is None:
        return False

    now = int(time.time())
    if abs(now - ts) > max_age_seconds:
        return False

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    key = _derive_key(secret_key, agent_token)
    expected = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── Command Runner ───────────────────────────────────────────────

class CommandRunner:
    """Routes and executes commands received via Agent v2 WebSocket."""

    def __init__(
        self,
        settings: Settings,
        send_fn: Callable[[dict], Awaitable[bool]],
    ):
        self._settings = settings
        self._send = send_fn

    async def handle(self, msg: dict) -> None:
        """Route an incoming command message."""
        msg_type = msg.get("type")
        if not msg_type:
            return

        if msg_type not in ALLOWED_COMMAND_TYPES:
            logger.warning("Unknown command type: %s", msg_type)
            return

        # Verify HMAC signature (skip for ping)
        if msg_type != "ping":
            signature = msg.get("_sig")
            payload = {k: v for k, v in msg.items() if k != "_sig"}

            if not signature or not verify_signature(
                payload,
                signature,
                self._settings.ws_secret_key,
                self._settings.auth_token,
            ):
                logger.warning("HMAC verification failed for %s", msg_type)
                await self._send({
                    "type": "command_result",
                    "command_id": msg.get("command_id"),
                    "status": "error",
                    "output": "HMAC signature verification failed",
                    "exit_code": -1,
                })
                return

        # Dispatch
        if msg_type == "exec_script":
            await self._exec_script(msg)
        elif msg_type == "shell_session":
            await self._shell_session(msg)
        elif msg_type == "pty_input":
            await self._pty_input(msg)
        elif msg_type == "pty_resize":
            await self._pty_resize(msg)
        elif msg_type == "service_status":
            await self._service_status(msg)

    async def _exec_script(self, msg: dict) -> None:
        """Execute a script on this node."""
        script_content = msg.get("script_content", "")
        command_id = msg.get("command_id")
        timeout = msg.get("timeout", 60)

        # Security check
        if _is_forbidden(script_content):
            logger.warning("Blocked forbidden script (cmd_id=%s)", command_id)
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "blocked",
                "output": "Command blocked by security policy",
                "exit_code": -1,
            })
            return

        logger.info("Executing script (cmd_id=%s, timeout=%ds)", command_id, timeout)

        try:
            proc = await asyncio.create_subprocess_shell(
                script_content,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
                output = stdout.decode("utf-8", errors="replace") if stdout else ""
                exit_code = proc.returncode or 0
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                output = "Command timed out"
                exit_code = -1

            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "completed" if exit_code == 0 else "error",
                "output": output[-50000:],  # Limit output size
                "exit_code": exit_code,
            })

        except Exception as e:
            logger.exception("Script execution error (cmd_id=%s): %s", command_id, e)
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "error",
                "output": str(e),
                "exit_code": -1,
            })

    async def _shell_session(self, msg: dict) -> None:
        """Start a shell session (placeholder for Iteration 3)."""
        await self._send({
            "type": "command_result",
            "command_id": msg.get("command_id"),
            "status": "error",
            "output": "Shell sessions not yet implemented",
            "exit_code": -1,
        })

    async def _pty_input(self, msg: dict) -> None:
        """Handle PTY input (placeholder for Iteration 3)."""
        pass

    async def _pty_resize(self, msg: dict) -> None:
        """Handle PTY resize (placeholder for Iteration 3)."""
        pass

    async def _service_status(self, msg: dict) -> None:
        """Get service status information."""
        command_id = msg.get("command_id")
        try:
            proc = await asyncio.create_subprocess_shell(
                "systemctl is-active xray remnanode docker 2>/dev/null || true",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode("utf-8", errors="replace") if stdout else ""

            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "completed",
                "output": output.strip(),
                "exit_code": proc.returncode or 0,
            })
        except Exception as e:
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "error",
                "output": str(e),
                "exit_code": -1,
            })

"""Terminal session manager.

Tracks active terminal sessions, enforces limits (1 per node per admin),
and manages idle timeouts (30 minutes).
"""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)

IDLE_TIMEOUT_SECONDS = 30 * 60  # 30 minutes
MAX_SESSIONS_PER_NODE = 1
SESSION_COOLDOWN_SECONDS = 2  # Min seconds between sessions for same node


@dataclass
class TerminalSession:
    """A single terminal session."""
    session_id: str
    node_uuid: str
    admin_id: int
    admin_username: str
    browser_ws: Optional[WebSocket] = None
    cols: int = 80
    rows: int = 24
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = time.time()

    @property
    def is_idle(self) -> bool:
        return (time.time() - self.last_activity) > IDLE_TIMEOUT_SECONDS

    @property
    def duration_seconds(self) -> int:
        return int(time.time() - self.created_at)


class TerminalSessionManager:
    """Manages active terminal sessions across all nodes."""

    def __init__(self):
        self._sessions: Dict[str, TerminalSession] = {}  # session_id → session
        self._node_sessions: Dict[str, str] = {}  # node_uuid → session_id
        self._node_last_close: Dict[str, float] = {}  # node_uuid → close timestamp
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None

    def start_cleanup_loop(self) -> None:
        """Start the periodic idle session cleanup."""
        if not self._cleanup_task or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        """Periodically close idle sessions."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                await self._cleanup_idle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Cleanup error: %s", e)

    async def _cleanup_idle(self) -> None:
        """Close all idle sessions."""
        async with self._lock:
            idle_ids = [
                sid for sid, session in self._sessions.items()
                if session.is_idle
            ]

        for sid in idle_ids:
            logger.info("Closing idle terminal session: %s", sid)
            await self.close_session(sid, reason="idle_timeout")

    async def create_session(
        self,
        node_uuid: str,
        admin_id: int,
        admin_username: str,
        browser_ws: WebSocket,
        cols: int = 80,
        rows: int = 24,
    ) -> Optional[TerminalSession]:
        """Create a new terminal session.

        Returns the session, or None if a session already exists for this node.
        """
        async with self._lock:
            # Check if a session already exists for this node
            existing_sid = self._node_sessions.get(node_uuid)
            if existing_sid and existing_sid in self._sessions:
                existing = self._sessions[existing_sid]
                if not existing.is_idle:
                    return None  # Active session exists

                # Close the idle session
                del self._sessions[existing_sid]
                del self._node_sessions[node_uuid]

            # Cooldown: prevent rapid session re-creation (e.g. from
            # React StrictMode double-mount or browser reconnect loops)
            last_close = self._node_last_close.get(node_uuid, 0.0)
            if time.time() - last_close < SESSION_COOLDOWN_SECONDS:
                logger.debug(
                    "Session cooldown active for node %s (%.1fs remaining)",
                    node_uuid, SESSION_COOLDOWN_SECONDS - (time.time() - last_close),
                )
                return None

            session_id = str(uuid.uuid4())
            session = TerminalSession(
                session_id=session_id,
                node_uuid=node_uuid,
                admin_id=admin_id,
                admin_username=admin_username,
                browser_ws=browser_ws,
                cols=cols,
                rows=rows,
            )

            self._sessions[session_id] = session
            self._node_sessions[node_uuid] = session_id

        logger.info(
            "Terminal session created: %s (node=%s, admin=%s)",
            session_id, node_uuid, admin_username,
        )

        # Log to command audit
        await self._log_session_start(session)

        return session

    async def close_session(self, session_id: str, reason: str = "closed") -> None:
        """Close a terminal session."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session:
                self._node_sessions.pop(session.node_uuid, None)
                self._node_last_close[session.node_uuid] = time.time()

        if not session:
            return

        # Close browser WebSocket
        if session.browser_ws:
            try:
                await session.browser_ws.close(code=1000, reason=reason)
            except Exception:
                pass

        # Log session end
        await self._log_session_end(session, reason)

        logger.info(
            "Terminal session closed: %s (node=%s, reason=%s, duration=%ds)",
            session_id, session.node_uuid, reason, session.duration_seconds,
        )

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        return self._sessions.get(session_id)

    def get_session_for_node(self, node_uuid: str) -> Optional[TerminalSession]:
        sid = self._node_sessions.get(node_uuid)
        return self._sessions.get(sid) if sid else None

    @property
    def active_count(self) -> int:
        return len(self._sessions)

    async def _log_session_start(self, session: TerminalSession) -> None:
        """Record session start in node_command_log."""
        try:
            from shared.database import db_service
            if not db_service.is_connected:
                return
            async with db_service.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO node_command_log
                        (node_uuid, admin_id, admin_username, command_type, command_data, status)
                    VALUES ($1, $2, $3, 'terminal', $4, 'running')
                    """,
                    session.node_uuid,
                    session.admin_id,
                    session.admin_username,
                    f"session_id={session.session_id}",
                )
        except Exception as e:
            logger.debug("Failed to log terminal session start: %s", e)

    async def _log_session_end(self, session: TerminalSession, reason: str) -> None:
        """Update session record in node_command_log."""
        try:
            from shared.database import db_service
            if not db_service.is_connected:
                return
            async with db_service.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE node_command_log
                    SET status = 'completed',
                        output = $1,
                        finished_at = NOW(),
                        duration_ms = $2
                    WHERE node_uuid = $3
                      AND command_type = 'terminal'
                      AND command_data = $4
                      AND status = 'running'
                    """,
                    f"reason={reason}",
                    session.duration_seconds * 1000,
                    session.node_uuid,
                    f"session_id={session.session_id}",
                )
        except Exception as e:
            logger.debug("Failed to log terminal session end: %s", e)


# Global singleton
terminal_manager = TerminalSessionManager()

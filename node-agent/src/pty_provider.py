"""
PTY session provider for Agent v2 terminal.

Creates a pseudo-terminal running /bin/bash and provides read/write/resize
interfaces. Streams output via a callback for forwarding over WebSocket.
"""
import asyncio
import fcntl
import logging
import os
import pty
import signal
import struct
import termios
from typing import Callable, Awaitable, Optional

logger = logging.getLogger(__name__)


class PTYSession:
    """Manages a single pseudo-terminal session."""

    def __init__(self, session_id: str, on_output: Callable[[str, bytes], Awaitable[None]]):
        """
        Args:
            session_id: Unique session identifier.
            on_output: Async callback(session_id, data_bytes) for output streaming.
        """
        self._session_id = session_id
        self._on_output = on_output
        self._master_fd: Optional[int] = None
        self._pid: Optional[int] = None
        self._running = False
        self._read_task: Optional[asyncio.Task] = None

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self, cols: int = 80, rows: int = 24) -> None:
        """Fork a new PTY process running /bin/bash."""
        if self._running:
            return

        pid, master_fd = pty.openpty()

        # The pty.openpty() returns (master, slave) fd pair
        # We need pty.fork() to get a proper child process
        child_pid = os.fork()

        if child_pid == 0:
            # Child process
            os.close(master_fd)
            os.setsid()

            # Open slave PTY
            slave_fd = pid  # pid from openpty is actually the slave fd

            # Set up stdin/stdout/stderr
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)

            if slave_fd > 2:
                os.close(slave_fd)

            # Set terminal size
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(0, termios.TIOCSWINSZ, winsize)

            # Set environment
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["SHELL"] = "/bin/bash"

            # Execute bash
            os.execve("/bin/bash", ["/bin/bash", "--login"], env)

        else:
            # Parent process
            os.close(pid)  # Close slave fd in parent
            self._master_fd = master_fd
            self._pid = child_pid
            self._running = True

            # Set master fd to non-blocking
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            # Set initial terminal size
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

            # Start reading output
            self._read_task = asyncio.create_task(self._read_loop())

            logger.info("PTY session started: %s (pid=%d)", self._session_id, child_pid)

    async def write(self, data: bytes) -> None:
        """Write data to the PTY (keyboard input from browser)."""
        if not self._running or self._master_fd is None:
            return

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, os.write, self._master_fd, data)
        except OSError as e:
            logger.debug("PTY write error: %s", e)
            await self.close()

    def resize(self, cols: int, rows: int) -> None:
        """Resize the terminal."""
        if not self._running or self._master_fd is None:
            return

        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)
        except OSError as e:
            logger.debug("PTY resize error: %s", e)

    async def close(self) -> None:
        """Terminate the PTY session."""
        if not self._running:
            return

        self._running = False

        # Cancel read task
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        # Close master fd
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

        # Kill child process
        if self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGTERM)
                # Wait briefly, then force kill
                await asyncio.sleep(0.5)
                try:
                    os.kill(self._pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(self._pid, os.WNOHANG)
            except (ProcessLookupError, ChildProcessError):
                pass
            self._pid = None

        logger.info("PTY session closed: %s", self._session_id)

    async def _read_loop(self) -> None:
        """Continuously read PTY output and forward via callback."""
        loop = asyncio.get_event_loop()

        while self._running and self._master_fd is not None:
            try:
                data = await loop.run_in_executor(
                    None, self._blocking_read,
                )
                if data:
                    await self._on_output(self._session_id, data)
                else:
                    # EOF — process exited
                    break
            except asyncio.CancelledError:
                break
            except OSError:
                break
            except Exception as e:
                logger.debug("PTY read error: %s", e)
                break

        # Process ended
        if self._running:
            await self.close()

    def _blocking_read(self) -> Optional[bytes]:
        """Blocking read from master fd (run in executor)."""
        if self._master_fd is None:
            return None

        import select
        try:
            readable, _, _ = select.select([self._master_fd], [], [], 0.1)
            if readable:
                return os.read(self._master_fd, 4096)
            return b""  # No data yet but still alive
        except OSError:
            return None


class PTYManager:
    """Manages multiple PTY sessions."""

    def __init__(self):
        self._sessions: dict[str, PTYSession] = {}

    async def create_session(
        self,
        session_id: str,
        on_output: Callable[[str, bytes], Awaitable[None]],
        cols: int = 80,
        rows: int = 24,
    ) -> PTYSession:
        """Create and start a new PTY session."""
        # Close existing session with same ID
        if session_id in self._sessions:
            await self._sessions[session_id].close()

        session = PTYSession(session_id, on_output)
        await session.start(cols, rows)
        self._sessions[session_id] = session
        return session

    async def close_session(self, session_id: str) -> None:
        """Close a PTY session."""
        session = self._sessions.pop(session_id, None)
        if session:
            await session.close()

    async def close_all(self) -> None:
        """Close all active sessions."""
        for session in list(self._sessions.values()):
            await session.close()
        self._sessions.clear()

    def get_session(self, session_id: str) -> Optional[PTYSession]:
        return self._sessions.get(session_id)

    @property
    def active_count(self) -> int:
        return len(self._sessions)


# Global PTY manager for the agent
pty_manager = PTYManager()

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
import time
from typing import Callable, Awaitable, Optional

logger = logging.getLogger(__name__)


def _install_sigchld_handler() -> None:
    """Install a SIGCHLD handler that reaps zombie children.

    Without this, children forked via pty.fork() become zombies until
    explicitly waited.  The default asyncio child-watcher only tracks
    children started through asyncio.create_subprocess_*, so manually
    forked children would accumulate as zombies and may interfere with
    the event loop's signal handling on rapid fork/kill cycles.
    """
    def _reap_children(signum, frame):  # noqa: ARG001
        while True:
            try:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid == 0:
                    break
            except ChildProcessError:
                break

    signal.signal(signal.SIGCHLD, _reap_children)


# Install once at import time
_install_sigchld_handler()


class PTYSession:
    """Manages a single pseudo-terminal session."""

    def __init__(
        self,
        session_id: str,
        on_output: Callable[[str, bytes], Awaitable[None]],
        host_mode: bool = False,
    ):
        """
        Args:
            session_id: Unique session identifier.
            on_output: Async callback(session_id, data_bytes) for output streaming.
            host_mode: If True, spawn shell on host via nsenter.
        """
        self._session_id = session_id
        self._on_output = on_output
        self._host_mode = host_mode
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

        # pty.fork() correctly handles the master/slave PTY setup:
        #   - child gets slave as stdin/stdout/stderr with proper controlling terminal
        #   - parent gets the master fd for reading/writing
        child_pid, master_fd = pty.fork()

        if child_pid == 0:
            # ── Child process ─────────────────────────────────
            # Reset signal handlers to defaults so the parent's asyncio
            # handlers don't interfere with the child / bash process.
            for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP,
                        signal.SIGCHLD, signal.SIGQUIT, signal.SIGTSTP):
                try:
                    signal.signal(sig, signal.SIG_DFL)
                except OSError:
                    pass

            # Explicitly acquire controlling terminal.
            # pty.fork() internally calls setsid() + tries ttyname()+open()
            # to set the controlling terminal, but this silently fails in
            # Docker containers where /dev/pts isn't fully mounted.
            # TIOCSCTTY is the reliable way to acquire it after setsid().
            _TIOCSCTTY = getattr(termios, "TIOCSCTTY", 0x540E)
            try:
                fcntl.ioctl(0, _TIOCSCTTY, 0)
            except OSError:
                pass

            # Set terminal size
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            try:
                fcntl.ioctl(0, termios.TIOCSWINSZ, winsize)
            except OSError:
                pass

            # Set environment
            env = os.environ.copy()
            env["TERM"] = "xterm-256color"
            env["SHELL"] = "/bin/bash"
            # Remove vars that can interfere with bash initialization
            for var in ("BASH_ENV", "ENV", "PROMPT_COMMAND", "CDPATH"):
                env.pop(var, None)

            # Execute shell — on success this never returns
            try:
                if self._host_mode:
                    # Launch bash on HOST via nsenter
                    os.execve(
                        "/usr/bin/nsenter",
                        [
                            "nsenter",
                            "--target", "1",
                            "--mount", "--uts", "--ipc", "--net", "--pid",
                            "--", "/bin/bash", "--login",
                        ],
                        env,
                    )
                else:
                    os.execve("/bin/bash", ["bash", "--login"], env)
            except Exception:
                os._exit(1)

        else:
            # ── Parent process ────────────────────────────────
            self._master_fd = master_fd
            self._pid = child_pid
            self._running = True

            # Set initial terminal size on the master side
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
                # Brief non-blocking wait, then force kill
                await asyncio.sleep(0.3)
                try:
                    os.kill(self._pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                # SIGCHLD handler will reap; also try here for completeness
                try:
                    os.waitpid(self._pid, os.WNOHANG)
                except ChildProcessError:
                    pass  # Already reaped by SIGCHLD handler
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
                if data is None:
                    # EOF or fatal error — process exited
                    break
                if data:
                    await self._on_output(self._session_id, data)
                # else: b"" — select timed out, no data yet, keep waiting
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
        """Blocking read from master fd (run in executor).

        Returns:
            bytes: Data read from the PTY.
            b"": No data available yet (select timeout), process still alive.
            None: EOF or fatal error — process exited.
        """
        if self._master_fd is None:
            return None

        import select
        try:
            readable, _, _ = select.select([self._master_fd], [], [], 0.1)
            if readable:
                data = os.read(self._master_fd, 4096)
                if not data:
                    return None  # EOF — child process exited
                return data
            return b""  # Select timeout — no data yet but still alive
        except OSError:
            return None


# Minimum seconds between PTY forks to avoid signal storms
_MIN_FORK_INTERVAL = 1.0


class PTYManager:
    """Manages multiple PTY sessions."""

    def __init__(self):
        self._sessions: dict[str, PTYSession] = {}
        self._last_fork_time: float = 0.0
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        session_id: str,
        on_output: Callable[[str, bytes], Awaitable[None]],
        cols: int = 80,
        rows: int = 24,
        host_mode: bool = False,
    ) -> PTYSession:
        """Create and start a new PTY session."""
        async with self._lock:
            # Close existing session with same ID
            if session_id in self._sessions:
                await self._sessions[session_id].close()

            # Rate-limit forks to prevent signal storms from rapid open/close
            now = time.monotonic()
            wait = self._last_fork_time + _MIN_FORK_INTERVAL - now
            if wait > 0:
                logger.debug("PTY rate-limit: waiting %.2fs before fork", wait)
                await asyncio.sleep(wait)

            session = PTYSession(session_id, on_output, host_mode=host_mode)
            await session.start(cols, rows)
            self._last_fork_time = time.monotonic()
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

"""
Agent v2 WebSocket client — persistent connection to backend.

Maintains a WebSocket connection to the backend for receiving commands
(exec_script, shell_session, pty_input). Implements reconnection with
exponential backoff and ping/pong keepalive.
"""
import asyncio
import json
import logging
from typing import Optional, Callable, Awaitable

import websockets
from websockets.client import WebSocketClientProtocol

from .config import Settings

logger = logging.getLogger(__name__)

# Reconnect delays in seconds
RECONNECT_DELAYS = [1, 2, 4, 8, 15, 30]
PING_INTERVAL = 30  # seconds


class AgentWSClient:
    """Persistent WebSocket client for Agent v2 command channel."""

    def __init__(
        self,
        settings: Settings,
        command_handler: Optional[Callable[[dict], Awaitable[None]]] = None,
    ):
        self._settings = settings
        self._command_handler = command_handler
        self._ws: Optional[WebSocketClientProtocol] = None
        self._reconnect_attempt = 0
        self._running = False

    @property
    def ws_url(self) -> str:
        """Build WebSocket URL from collector_url."""
        base = self._settings.ws_url or self._settings.collector_url
        # Convert http(s):// to ws(s)://
        if base.startswith("https://"):
            base = "wss://" + base[8:]
        elif base.startswith("http://"):
            base = "ws://" + base[7:]
        elif not base.startswith("ws"):
            base = "ws://" + base

        # Remove trailing slash
        base = base.rstrip("/")

        return (
            f"{base}/api/v2/agent/ws"
            f"?token={self._settings.auth_token}"
            f"&node_uuid={self._settings.node_uuid}"
        )

    async def run(self, shutdown_event: asyncio.Event) -> None:
        """Main loop: connect, listen, reconnect on failure."""
        self._running = True
        logger.info("Agent v2 WS client starting (node=%s)", self._settings.node_uuid)

        while self._running and not shutdown_event.is_set():
            try:
                await self._connect_and_listen(shutdown_event)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("WS connection error: %s", e)

            if shutdown_event.is_set():
                break

            # Reconnect with backoff
            delay = RECONNECT_DELAYS[
                min(self._reconnect_attempt, len(RECONNECT_DELAYS) - 1)
            ]
            self._reconnect_attempt += 1
            logger.info("Reconnecting in %ds (attempt %d)...", delay, self._reconnect_attempt)

            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=delay)
                break  # shutdown requested during wait
            except asyncio.TimeoutError:
                pass  # timeout expired, retry

        self._running = False
        logger.info("Agent v2 WS client stopped")

    async def _connect_and_listen(self, shutdown_event: asyncio.Event) -> None:
        """Single connection lifecycle."""
        url = self.ws_url
        logger.info("Connecting to %s", url.split("?")[0])  # Don't log token

        async with websockets.connect(
            url,
            ping_interval=None,  # We handle our own ping/pong
            close_timeout=5,
            max_size=10 * 1024 * 1024,  # 10 MB max message
        ) as ws:
            self._ws = ws
            self._reconnect_attempt = 0
            logger.info("Agent v2 WS connected")

            # Run ping sender and message listener concurrently
            ping_task = asyncio.create_task(self._ping_loop(ws, shutdown_event))
            listen_task = asyncio.create_task(self._listen_loop(ws, shutdown_event))

            try:
                done, pending = await asyncio.wait(
                    [ping_task, listen_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            finally:
                self._ws = None

    async def _ping_loop(self, ws: WebSocketClientProtocol, shutdown_event: asyncio.Event) -> None:
        """Send ping every PING_INTERVAL seconds."""
        while not shutdown_event.is_set():
            try:
                await ws.send(json.dumps({"type": "ping"}))
            except Exception:
                return  # Connection broken

            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=PING_INTERVAL)
                return  # Shutdown requested
            except asyncio.TimeoutError:
                pass

    async def _listen_loop(self, ws: WebSocketClientProtocol, shutdown_event: asyncio.Event) -> None:
        """Listen for messages from backend."""
        try:
            async for raw in ws:
                if shutdown_event.is_set():
                    return

                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue

                msg_type = msg.get("type")

                if msg_type == "pong":
                    continue  # Keepalive response

                if self._command_handler:
                    try:
                        await self._command_handler(msg)
                    except Exception as e:
                        logger.exception("Command handler error: %s", e)
        except Exception as e:
            logger.warning("WS listen loop ended: %s", e)

    async def send(self, message: dict) -> bool:
        """Send a message to the backend."""
        if not self._ws:
            return False
        try:
            await self._ws.send(json.dumps(message, default=str))
            return True
        except Exception as e:
            logger.warning("Failed to send WS message: %s", e)
            return False

    def stop(self) -> None:
        """Signal the client to stop."""
        self._running = False

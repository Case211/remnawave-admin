"""Agent Connection Manager — tracks active Agent v2 WebSocket connections.

Singleton that maps node_uuid → WebSocket for the agent command channel.
Thread-safe via asyncio.Lock.
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class AgentConnectionManager:
    """Manages persistent WebSocket connections from Node Agents."""

    def __init__(self):
        self._connections: Dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def register(self, node_uuid: str, websocket: WebSocket) -> None:
        """Register a new agent connection."""
        async with self._lock:
            old = self._connections.get(node_uuid)
            if old:
                # Close stale connection
                try:
                    await old.close(code=4000, reason="replaced")
                except Exception:
                    pass
            self._connections[node_uuid] = websocket
        logger.info("Agent registered: %s (total: %d)", node_uuid, len(self._connections))

    async def unregister(self, node_uuid: str) -> None:
        """Remove agent connection."""
        async with self._lock:
            self._connections.pop(node_uuid, None)
        logger.info("Agent unregistered: %s (total: %d)", node_uuid, len(self._connections))

    def is_connected(self, node_uuid: str) -> bool:
        """Check if an agent is connected."""
        return node_uuid in self._connections

    def list_connected(self) -> List[str]:
        """Return list of connected node UUIDs."""
        return list(self._connections.keys())

    @property
    def count(self) -> int:
        return len(self._connections)

    async def send_command(
        self,
        node_uuid: str,
        command: Dict[str, Any],
    ) -> bool:
        """Send a command to a specific agent.

        Returns True if sent successfully, False if agent is not connected.
        """
        ws = self._connections.get(node_uuid)
        if not ws:
            return False

        try:
            await ws.send_text(json.dumps(command, default=str))
            return True
        except Exception as e:
            logger.warning("Failed to send command to %s: %s", node_uuid, e)
            # Connection broken — remove it
            async with self._lock:
                self._connections.pop(node_uuid, None)
            return False

    async def get_websocket(self, node_uuid: str) -> Optional[WebSocket]:
        """Get the WebSocket for a node (for direct streaming like terminal)."""
        return self._connections.get(node_uuid)


# Global singleton
agent_manager = AgentConnectionManager()

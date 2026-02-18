"""Agent v2 WebSocket endpoint.

Persistent bidirectional channel between Node Agent and backend.
Handles: ping/pong keepalive, command routing (exec_script, shell_session, pty_input/output).

Connection: WS /api/v2/agent/ws?token={agent_token}&node_uuid={uuid}
Auth: agent_token verified against nodes.agent_token in DB.
"""
import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from web.backend.core.agent_manager import agent_manager

logger = logging.getLogger(__name__)
router = APIRouter()


async def _verify_agent(token: str, node_uuid: str) -> bool:
    """Verify agent token against the database."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return False
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT agent_token FROM nodes WHERE uuid = $1",
                node_uuid,
            )
            if not row or not row["agent_token"]:
                return False
            return row["agent_token"] == token
    except Exception as e:
        logger.error("Agent auth error: %s", e)
        return False


async def _set_agent_v2_status(node_uuid: str, connected: bool) -> None:
    """Update agent_v2_connected and agent_v2_last_ping in the DB."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            if connected:
                await conn.execute(
                    "UPDATE nodes SET agent_v2_connected = true, agent_v2_last_ping = NOW() WHERE uuid = $1",
                    node_uuid,
                )
            else:
                await conn.execute(
                    "UPDATE nodes SET agent_v2_connected = false WHERE uuid = $1",
                    node_uuid,
                )
    except Exception as e:
        logger.debug("Failed to update agent v2 status: %s", e)


async def _broadcast_agent_status(node_uuid: str, connected: bool) -> None:
    """Broadcast agent v2 status change to frontend WebSocket clients."""
    try:
        from web.backend.api.v2.websocket import manager
        await manager.broadcast({
            "type": "agent_v2_status",
            "data": {
                "node_uuid": node_uuid,
                "connected": connected,
            },
            "timestamp": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.debug("Failed to broadcast agent status: %s", e)


@router.websocket("/agent/ws")
async def agent_websocket(
    websocket: WebSocket,
    token: str = Query(...),
    node_uuid: str = Query(...),
):
    """Agent v2 WebSocket endpoint.

    Protocol:
    - Agent sends: {"type": "ping"} every 30s
    - Backend replies: {"type": "pong"}
    - Backend sends commands: {"type": "exec_script"|"shell_session"|"pty_input", ...}
    - Agent replies: {"type": "command_result"|"pty_output"|"script_output", ...}
    """
    # Auth
    if not await _verify_agent(token, node_uuid):
        await websocket.close(code=4001, reason="auth_failed")
        return

    await websocket.accept()
    logger.info("Agent v2 connected: %s", node_uuid)

    # Register
    await agent_manager.register(node_uuid, websocket)
    await _set_agent_v2_status(node_uuid, True)
    await _broadcast_agent_status(node_uuid, True)

    try:
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=90.0,  # Expect ping within 90s (agent sends every 30s)
                )

                if not data:
                    continue

                try:
                    msg = json.loads(data)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type")

                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                    # Update last ping
                    try:
                        from shared.database import db_service
                        if db_service.is_connected:
                            async with db_service.acquire() as conn:
                                await conn.execute(
                                    "UPDATE nodes SET agent_v2_last_ping = NOW() WHERE uuid = $1",
                                    node_uuid,
                                )
                    except Exception:
                        pass

                elif msg_type == "command_result":
                    # Agent finished executing a command — log it
                    await _handle_command_result(node_uuid, msg)

                elif msg_type == "script_output":
                    # Streaming script output — forward to frontend SSE/WS
                    await _handle_script_output(node_uuid, msg)

                elif msg_type == "pty_output":
                    # Terminal output — forward to frontend terminal WS
                    await _handle_pty_output(node_uuid, msg)

            except asyncio.TimeoutError:
                # No ping received — assume agent disconnected
                logger.warning("Agent %s ping timeout", node_uuid)
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Agent WS error (%s): %s", node_uuid, e)
    finally:
        await agent_manager.unregister(node_uuid)
        await _set_agent_v2_status(node_uuid, False)
        await _broadcast_agent_status(node_uuid, False)
        logger.info("Agent v2 disconnected: %s", node_uuid)


async def _handle_command_result(node_uuid: str, msg: dict) -> None:
    """Update command log entry with result."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return

        cmd_id = msg.get("command_id")
        if not cmd_id:
            return

        async with db_service.acquire() as conn:
            await conn.execute(
                """
                UPDATE node_command_log
                SET status = $1, output = $2, exit_code = $3,
                    finished_at = NOW(),
                    duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER * 1000
                WHERE id = $4 AND node_uuid = $5
                """,
                msg.get("status", "completed"),
                msg.get("output", ""),
                msg.get("exit_code"),
                int(cmd_id),
                node_uuid,
            )
    except Exception as e:
        logger.debug("Failed to update command result: %s", e)


async def _handle_script_output(node_uuid: str, msg: dict) -> None:
    """Forward streaming script output to frontend (placeholder for SSE)."""
    # Will be implemented in Iteration 4 (Script Catalog)
    pass


async def _handle_pty_output(node_uuid: str, msg: dict) -> None:
    """Forward PTY output to the frontend terminal WebSocket."""
    try:
        from web.backend.core.terminal_sessions import terminal_manager

        session_id = msg.get("session_id")
        data_b64 = msg.get("data", "")

        if not session_id or not data_b64:
            return

        session = terminal_manager.get_session(session_id)
        if not session or not session.browser_ws:
            return

        session.touch()
        # Forward base64-encoded output directly to browser
        await session.browser_ws.send_text(data_b64)
    except Exception as e:
        logger.debug("Failed to forward pty output: %s", e)

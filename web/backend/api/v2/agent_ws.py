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

from shared.db_schema import NODES_TABLE, NODE_COMMAND_LOG_TABLE
from shared.db_query import select_sql, update_sql

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
                select_sql(NODES_TABLE, "agent_token", "WHERE uuid = $1"),
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
                    update_sql(NODES_TABLE, "agent_v2_connected = true, agent_v2_last_ping = NOW()", "uuid = $1"),
                    node_uuid,
                )
            else:
                await conn.execute(
                    update_sql(NODES_TABLE, "agent_v2_connected = false", "uuid = $1"),
                    node_uuid,
                )
    except Exception as e:
        logger.warning("Failed to update agent v2 status for %s: %s", node_uuid, e)


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
        logger.warning("Agent auth failed: node_uuid=%s, ip=%s", node_uuid, websocket.client.host if websocket.client else "unknown")
        await websocket.close(code=4001, reason="auth_failed")
        return

    await websocket.accept()
    logger.info("Agent v2 connected: %s", node_uuid)

    # Register
    await agent_manager.register(node_uuid, websocket)
    await _set_agent_v2_status(node_uuid, True)
    await _broadcast_agent_status(node_uuid, True)

    # Реконнект агента = подтверждение успешного «Обновления агента»: сам
    # скрипт умирает вместе со старым контейнером и не всегда успевает
    # доложить финальный статус — команда зависала в running и позже падала
    # в «Timed out»/Error при фактически УСПЕШНОМ обновлении.
    await _resolve_pending_update_commands(node_uuid)

    # Push blocked IPs to newly connected agent (always send, even if empty — clears stale rules)
    try:
        from shared.database import db_service
        blocked = await db_service.get_all_active_blocked_ips()
        from web.backend.core.agent_hmac import sign_command_with_ts
        cmd = {"type": "sync_blocked_ips", "ips": blocked, "mode": "replace"}
        payload, sig = sign_command_with_ts(cmd, token)
        payload["_sig"] = sig
        await agent_manager.send_command(node_uuid, payload)
        logger.info("Pushed %d blocked IPs to agent %s", len(blocked), node_uuid)
    except Exception as e:
        logger.debug("Failed to push blocked IPs to agent %s: %s", node_uuid, e)

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
                                    update_sql(NODES_TABLE, "agent_v2_last_ping = NOW()", "uuid = $1"),
                                    node_uuid,
                                )
                    except Exception as e:
                        logger.debug("Failed to update agent ping timestamp: %s", e)

                elif msg_type == "command_result":
                    # Agent finished executing a command — log it
                    await _handle_command_result(node_uuid, msg)

                elif msg_type == "script_output":
                    # Streaming script output — forward to frontend SSE/WS
                    await _handle_script_output(node_uuid, msg)

                elif msg_type == "pty_output":
                    # Terminal output — forward to frontend terminal WS
                    await _handle_pty_output(node_uuid, msg)

                elif msg_type == "pty_close":
                    # Agent closed PTY session — clean up and notify browser
                    await _handle_pty_close(node_uuid, msg)

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


async def _resolve_pending_update_commands(node_uuid: str) -> None:
    """Закрыть зависшие running-команды update_agent при реконнекте агента.

    Перекат убивает агента до/во время отправки command_result — реконнект
    с новой версией и есть фактическое подтверждение успеха обновления.
    """
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return
        async with db_service.acquire() as conn:
            updated = await conn.execute(
                update_sql(
                    NODE_COMMAND_LOG_TABLE,
                    "status = 'completed', exit_code = 0, finished_at = NOW(), "
                    "duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER * 1000, "
                    "output = COALESCE(output, '') || E'\\n[агент переподключился — обновление применено]'",
                    "node_uuid = $1 AND status = 'running' "
                    "AND command_data LIKE 'script=update_agent%'",
                ),
                node_uuid,
            )
        if updated and not str(updated).endswith(" 0"):
            logger.info("Resolved pending update_agent command for %s (agent reconnected)", node_uuid)
    except Exception as e:
        logger.debug("Failed to resolve pending update commands for %s: %s", node_uuid, e)


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
                update_sql(NODE_COMMAND_LOG_TABLE,
                    "status = $1, output = $2, exit_code = $3, finished_at = NOW(), duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER * 1000",
                    "id = $4 AND node_uuid = $5"),
                msg.get("status", "completed"),
                msg.get("output", ""),
                msg.get("exit_code"),
                int(cmd_id),
                node_uuid,
            )
    except Exception as e:
        logger.warning("Failed to update command result for node %s: %s", node_uuid, e)


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
        logger.warning("Failed to forward pty output for session %s: %s", msg.get("session_id"), e)


async def _handle_pty_close(node_uuid: str, msg: dict) -> None:
    """Handle PTY session close from agent (shell exited or PTY creation failed)."""
    try:
        from web.backend.core.terminal_sessions import terminal_manager

        session_id = msg.get("session_id")
        reason = msg.get("reason", "agent_pty_close")

        if not session_id:
            return

        session = terminal_manager.get_session(session_id)
        if not session or not session.browser_ws:
            return

        # Notify browser
        try:
            await session.browser_ws.send_json({
                "type": "error",
                "message": f"Shell closed: {reason}",
            })
        except Exception:
            pass

        await terminal_manager.close_session(session_id, reason=reason)
        logger.info("PTY closed by agent: session=%s, reason=%s", session_id, reason)
    except Exception as e:
        logger.warning("Failed to handle pty close for node %s: %s", node_uuid, e)

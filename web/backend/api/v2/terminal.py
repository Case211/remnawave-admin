"""Terminal WebSocket proxy.

Bridges browser xterm.js ↔ backend ↔ agent PTY session.

WS /api/v2/fleet/{node_uuid}/terminal?token={jwt}
Permission: fleet.terminal (superadmin only).
"""
import asyncio
import base64
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from web.backend.api.deps import get_current_admin_ws
from web.backend.core.agent_manager import agent_manager
from web.backend.core.agent_hmac import sign_command_with_ts
from web.backend.core.terminal_sessions import terminal_manager

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_agent_token(node_uuid: str) -> str | None:
    """Get agent auth token from DB for HMAC signing."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return None
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT agent_token FROM nodes WHERE uuid = $1",
                node_uuid,
            )
            return row["agent_token"] if row and row["agent_token"] else None
    except Exception:
        return None


@router.websocket("/fleet/{node_uuid}/terminal")
async def terminal_websocket(
    websocket: WebSocket,
    node_uuid: str,
    token: str = Query(...),
):
    """Browser terminal WebSocket endpoint.

    Protocol:
    - Browser sends: base64-encoded keyboard input
    - Browser sends: JSON {"type": "resize", "cols": N, "rows": N}
    - Server sends: base64-encoded terminal output
    - Server sends: JSON {"type": "error", "message": "..."}
    """
    # Auth
    try:
        admin = await get_current_admin_ws(websocket, token)
    except Exception as e:
        logger.warning("Terminal auth failed: %s", e)
        return

    # Check permission: fleet.terminal
    has_perm = (
        admin.account_id is None  # legacy env admin = superadmin
        or admin.role == "superadmin"
        or admin.has_permission("fleet", "terminal")
    )
    if not has_perm:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Permission denied: fleet.terminal required"})
        await websocket.close(code=4003, reason="permission_denied")
        return

    # Check agent is connected
    if not agent_manager.is_connected(node_uuid):
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Agent not connected"})
        await websocket.close(code=4004, reason="agent_not_connected")
        return

    await websocket.accept()

    # Get agent token for HMAC signing
    agent_token = await _get_agent_token(node_uuid)
    if not agent_token:
        await websocket.send_json({"type": "error", "message": "Agent token not found"})
        await websocket.close(code=4005, reason="no_agent_token")
        return

    # Create terminal session
    session = await terminal_manager.create_session(
        node_uuid=node_uuid,
        admin_id=admin.id if hasattr(admin, 'id') else 0,
        admin_username=admin.username or str(admin.telegram_id),
        browser_ws=websocket,
    )

    if not session:
        await websocket.send_json({"type": "error", "message": "A terminal session already exists for this node"})
        await websocket.close(code=4006, reason="session_exists")
        return

    logger.info(
        "Terminal session started: node=%s, admin=%s, session=%s",
        node_uuid, session.admin_username, session.session_id,
    )

    # Send shell_session open command to agent
    cmd_payload = {
        "type": "shell_session",
        "action": "open",
        "session_id": session.session_id,
        "cols": session.cols,
        "rows": session.rows,
        "command_id": 0,
    }
    payload_with_ts, sig = sign_command_with_ts(cmd_payload, agent_token)
    payload_with_ts["_sig"] = sig
    await agent_manager.send_command(node_uuid, payload_with_ts)

    # Notify browser that terminal is ready
    await websocket.send_json({"type": "ready", "session_id": session.session_id})

    try:
        # Start background task to relay agent output → browser
        relay_task = asyncio.create_task(
            _relay_agent_to_browser(node_uuid, session.session_id, websocket)
        )

        # Listen for browser input
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                # Send ping to keep alive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                continue

            session.touch()

            # Try JSON first (resize, close)
            if data.startswith("{"):
                try:
                    msg = json.loads(data)
                    msg_type = msg.get("type")

                    if msg_type == "resize":
                        cols = msg.get("cols", 80)
                        rows = msg.get("rows", 24)
                        session.cols = cols
                        session.rows = rows

                        resize_payload = {
                            "type": "pty_resize",
                            "session_id": session.session_id,
                            "cols": cols,
                            "rows": rows,
                        }
                        p, s = sign_command_with_ts(resize_payload, agent_token)
                        p["_sig"] = s
                        await agent_manager.send_command(node_uuid, p)

                    elif msg_type == "close":
                        break

                    elif msg_type == "pong":
                        continue

                    continue
                except json.JSONDecodeError:
                    pass

            # Otherwise, treat as base64-encoded keyboard input
            input_payload = {
                "type": "pty_input",
                "session_id": session.session_id,
                "data": data,
            }
            p, s = sign_command_with_ts(input_payload, agent_token)
            p["_sig"] = s
            await agent_manager.send_command(node_uuid, p)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Terminal WS error: %s", e)
    finally:
        # Clean up
        relay_task.cancel()
        try:
            await relay_task
        except asyncio.CancelledError:
            pass

        # Send close command to agent
        close_payload = {
            "type": "shell_session",
            "action": "close",
            "session_id": session.session_id,
            "command_id": 0,
        }
        p, s = sign_command_with_ts(close_payload, agent_token)
        p["_sig"] = s
        await agent_manager.send_command(node_uuid, p)

        await terminal_manager.close_session(session.session_id, reason="browser_disconnect")
        logger.info("Terminal session ended: %s", session.session_id)


async def _relay_agent_to_browser(
    node_uuid: str,
    session_id: str,
    browser_ws: WebSocket,
) -> None:
    """Relay pty_output messages from agent to browser.

    This task subscribes to the agent's WebSocket messages and forwards
    matching pty_output to the browser. Since agent_ws.py calls
    _handle_pty_output, we override that to forward here.
    """
    # For now, the relay is handled by the agent_ws.py _handle_pty_output
    # calling back into terminal_manager. We just keep this task alive
    # as a placeholder for the relay mechanism.
    # The actual forwarding happens via _handle_pty_output in agent_ws.py.
    try:
        while True:
            await asyncio.sleep(30)
    except asyncio.CancelledError:
        pass

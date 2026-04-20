"""Background scheduler for cron-based script execution on nodes."""
import asyncio
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def task_scheduler_loop():
    """Check scheduled_tasks every 60s and execute matching cron entries."""
    await asyncio.sleep(10)  # initial startup delay
    while True:
        try:
            from shared.database import db_service
            if not db_service.is_connected:
                await asyncio.sleep(60)
                continue

            from web.backend.core.automation_engine import cron_matches_now

            async with db_service.acquire() as conn:
                tasks = await conn.fetch(
                    """
                    SELECT st.id, st.script_id, st.node_uuid::text, st.cron_expression,
                           st.env_vars, ns.script_content, ns.name AS script_name,
                           ns.timeout_seconds, ns.requires_root
                    FROM scheduled_tasks st
                    JOIN node_scripts ns ON ns.id = st.script_id
                    WHERE st.is_enabled = true
                    """
                )

            for task in tasks:
                try:
                    if not cron_matches_now(task["cron_expression"]):
                        continue

                    task_id = task["id"]
                    node_uuid = task["node_uuid"]
                    script_name = task["script_name"]

                    logger.info(
                        "Scheduled task %d (%s) triggered for node %s",
                        task_id, script_name, node_uuid,
                    )

                    status = "failed"
                    try:
                        from web.backend.core.agent_manager import agent_manager
                        from web.backend.core.agent_hmac import sign_command_with_ts

                        if not agent_manager.is_connected(node_uuid):
                            logger.warning("Agent %s not connected, task %d skipped", node_uuid, task_id)
                            await _update_task_status(db_service, task_id, "failed")
                            continue

                        agent_token = None
                        async with db_service.acquire() as conn:
                            row = await conn.fetchrow(
                                "SELECT agent_token FROM nodes WHERE uuid = $1", node_uuid
                            )
                            if row:
                                agent_token = row["agent_token"]

                        if not agent_token:
                            logger.warning("No agent token for node %s, skipping task %d", node_uuid, task_id)
                            await _update_task_status(db_service, task_id, "failed")
                            continue

                        env_vars = task["env_vars"]
                        if isinstance(env_vars, str):
                            env_vars = json.loads(env_vars)

                        # Prepend env vars as export statements (same as exec-script endpoint)
                        script_content = task["script_content"]
                        if env_vars:
                            import shlex
                            exports = "\n".join(
                                f"export {k}={shlex.quote(str(v))}"
                                for k, v in env_vars.items()
                                if k.isidentifier()
                            )
                            if exports:
                                if script_content.startswith("#!"):
                                    first_nl = script_content.index("\n")
                                    script_content = (
                                        script_content[:first_nl + 1]
                                        + exports + "\n"
                                        + script_content[first_nl + 1:]
                                    )
                                else:
                                    script_content = exports + "\n" + script_content

                        # Log command for result tracking (agent sends command_result by command_id)
                        async with db_service.acquire() as conn:
                            cmd_row = await conn.fetchrow(
                                """
                                INSERT INTO node_command_log
                                    (node_uuid, admin_id, admin_username, command_type,
                                     command_data, status)
                                VALUES ($1, NULL, 'scheduler', 'exec_script', $2, 'running')
                                RETURNING id
                                """,
                                node_uuid,
                                f"script={script_name} task_id={task_id}" + (
                                    f" env={list(env_vars.keys())}" if env_vars else ""
                                ),
                            )
                            exec_id = cmd_row["id"]

                        cmd_payload = {
                            "type": "exec_script",
                            "command_id": exec_id,
                            "script_content": script_content,
                            "timeout": task["timeout_seconds"] or 300,
                        }
                        payload_with_ts, sig = sign_command_with_ts(cmd_payload, agent_token)
                        payload_with_ts["_sig"] = sig

                        sent = await agent_manager.send_command(node_uuid, payload_with_ts)
                        status = "success" if sent else "failed"
                        if not sent:
                            logger.warning("Failed to send to agent %s, task %d", node_uuid, task_id)

                    except Exception as e:
                        logger.error("Failed to execute scheduled task %d: %s", task_id, e, exc_info=True)
                        status = "failed"

                    await _update_task_status(db_service, task_id, status)

                except Exception as e:
                    logger.error("Error processing scheduled task: %s", e)

        except Exception as e:
            logger.error("Task scheduler loop error: %s", e)

        await asyncio.sleep(60)


async def _update_task_status(db_service, task_id: int, status: str):
    """Update task last_run_at, last_status, run_count."""
    try:
        async with db_service.acquire() as conn:
            await conn.execute(
                """
                UPDATE scheduled_tasks
                SET last_run_at = NOW(), last_status = $2,
                    run_count = run_count + 1, updated_at = NOW()
                WHERE id = $1
                """,
                task_id, status,
            )
    except Exception as e:
        logger.error("Failed to update task %d status: %s", task_id, e)

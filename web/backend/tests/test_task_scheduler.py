"""Tests for task_scheduler — cron-based background script execution."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_task(
    task_id=1,
    script_id=10,
    node_uuid="aaaa-bbbb-cccc",
    cron_expression="*/5 * * * *",
    env_vars=None,
    script_content="echo ok",
    script_name="health_check",
    timeout_seconds=120,
    requires_root=False,
):
    """Build a dict mimicking an asyncpg Record for a scheduled_task row."""
    return {
        "id": task_id,
        "script_id": script_id,
        "node_uuid": node_uuid,
        "cron_expression": cron_expression,
        "env_vars": env_vars,
        "script_content": script_content,
        "script_name": script_name,
        "timeout_seconds": timeout_seconds,
        "requires_root": requires_root,
    }


def _mock_db_service(*, is_connected=True, tasks=None, agent_token_row=None,
                     cmd_log_id=777):
    """Mock db_service that routes acquire() calls by order:

    call 1  -> fetch(task list)
    call 2+ -> fetchrow sequence: agent_token, INSERT returning id, then None
    """
    db = MagicMock()
    db.is_connected = is_connected

    fetchrow_queue = [agent_token_row, {"id": cmd_log_id}]

    call_count = 0

    def _acquire():
        nonlocal call_count
        call_count += 1
        conn = AsyncMock()
        if call_count == 1:
            conn.fetch = AsyncMock(return_value=tasks or [])
        else:
            value = fetchrow_queue.pop(0) if fetchrow_queue else None
            conn.fetchrow = AsyncMock(return_value=value)
            conn.execute = AsyncMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        return cm

    db.acquire = _acquire
    return db


def _make_agent_manager(*, is_connected=True, send_result=True):
    am = MagicMock()
    am.is_connected = MagicMock(return_value=is_connected)
    am.send_command = AsyncMock(return_value=send_result)
    return am


class _StopLoop(Exception):
    """Sentinel to break out of the infinite scheduler loop."""


# ---------------------------------------------------------------------------
# _update_task_status
# ---------------------------------------------------------------------------

class TestUpdateTaskStatus:
    """Tests for the helper that records task execution results."""

    @pytest.mark.asyncio
    async def test_updates_status_in_db(self):
        from web.backend.core.task_scheduler import _update_task_status

        conn = AsyncMock()
        conn.execute = AsyncMock()

        db = MagicMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        db.acquire = MagicMock(return_value=cm)

        await _update_task_status(db, 42, "success")

        conn.execute.assert_awaited_once()
        args = conn.execute.call_args
        assert 42 in args[0]
        assert "success" in args[0]

    @pytest.mark.asyncio
    async def test_exception_is_logged_not_raised(self):
        """DB error must not propagate — just log."""
        from web.backend.core.task_scheduler import _update_task_status

        db = MagicMock()
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(side_effect=RuntimeError("db gone"))
        cm.__aexit__ = AsyncMock(return_value=False)
        db.acquire = MagicMock(return_value=cm)

        # Should NOT raise
        await _update_task_status(db, 1, "failed")


# ---------------------------------------------------------------------------
# task_scheduler_loop
# ---------------------------------------------------------------------------

class TestTaskSchedulerLoop:
    """Tests for the main scheduler loop (single-iteration via side_effect)."""

    @staticmethod
    def _sleep_side_effect():
        """First call (startup delay) passes; second call (end-of-loop) stops."""
        call = 0

        async def _sleep(seconds):
            nonlocal call
            call += 1
            if call >= 2:
                raise _StopLoop()

        return _sleep

    # -- DB not connected -> skip iteration ----------------------------------

    @pytest.mark.asyncio
    async def test_skips_when_db_not_connected(self):
        db = _mock_db_service(is_connected=False)

        call = 0

        async def _sleep(seconds):
            nonlocal call
            call += 1
            if call >= 3:
                raise _StopLoop()

        with (
            patch("asyncio.sleep", side_effect=_sleep),
            patch("shared.database.db_service", db),
        ):
            from web.backend.core.task_scheduler import task_scheduler_loop

            with pytest.raises(_StopLoop):
                await task_scheduler_loop()

    # -- No enabled tasks -> nothing happens ---------------------------------

    @pytest.mark.asyncio
    async def test_no_tasks(self):
        db = _mock_db_service(is_connected=True, tasks=[])

        with (
            patch("asyncio.sleep", side_effect=self._sleep_side_effect()),
            patch("shared.database.db_service", db),
        ):
            from web.backend.core.task_scheduler import task_scheduler_loop

            with pytest.raises(_StopLoop):
                await task_scheduler_loop()

    # -- Cron does not match -> task skipped ---------------------------------

    @pytest.mark.asyncio
    async def test_cron_not_matching_skips_task(self):
        task = _make_task()
        db = _mock_db_service(is_connected=True, tasks=[task])
        mock_sign = MagicMock(return_value=({"type": "exec_script"}, "sig"))
        mock_am = _make_agent_manager()

        with (
            patch("asyncio.sleep", side_effect=self._sleep_side_effect()),
            patch("shared.database.db_service", db),
            patch(
                "web.backend.core.automation_engine.cron_matches_now",
                return_value=False,
            ),
            patch("web.backend.core.agent_hmac.sign_command_with_ts", mock_sign),
            patch("web.backend.core.agent_manager.agent_manager", mock_am),
        ):
            from web.backend.core.task_scheduler import task_scheduler_loop

            with pytest.raises(_StopLoop):
                await task_scheduler_loop()

        mock_sign.assert_not_called()
        mock_am.send_command.assert_not_called()

    # -- Agent not connected -> status=failed, no token lookup ---------------

    @pytest.mark.asyncio
    async def test_agent_not_connected_marks_failed(self):
        task = _make_task()
        db = _mock_db_service(is_connected=True, tasks=[task])
        mock_sign = MagicMock(return_value=({}, "sig"))
        mock_am = _make_agent_manager(is_connected=False)

        with (
            patch("asyncio.sleep", side_effect=self._sleep_side_effect()),
            patch("shared.database.db_service", db),
            patch(
                "web.backend.core.automation_engine.cron_matches_now",
                return_value=True,
            ),
            patch("web.backend.core.agent_hmac.sign_command_with_ts", mock_sign),
            patch("web.backend.core.agent_manager.agent_manager", mock_am),
            patch(
                "web.backend.core.task_scheduler._update_task_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            from web.backend.core.task_scheduler import task_scheduler_loop

            with pytest.raises(_StopLoop):
                await task_scheduler_loop()

        mock_am.send_command.assert_not_called()
        mock_update.assert_awaited()
        assert mock_update.call_args_list[-1][0][2] == "failed"

    # -- No agent_token for node -> status=failed ----------------------------

    @pytest.mark.asyncio
    async def test_no_agent_token_marks_failed(self):
        task = _make_task()
        db = _mock_db_service(
            is_connected=True,
            tasks=[task],
            agent_token_row=None,  # no token
        )
        mock_sign = MagicMock(return_value=({"type": "exec_script"}, "sig"))
        mock_am = _make_agent_manager()

        with (
            patch("asyncio.sleep", side_effect=self._sleep_side_effect()),
            patch("shared.database.db_service", db),
            patch(
                "web.backend.core.automation_engine.cron_matches_now",
                return_value=True,
            ),
            patch("web.backend.core.agent_hmac.sign_command_with_ts", mock_sign),
            patch("web.backend.core.agent_manager.agent_manager", mock_am),
            patch(
                "web.backend.core.task_scheduler._update_task_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            from web.backend.core.task_scheduler import task_scheduler_loop

            with pytest.raises(_StopLoop):
                await task_scheduler_loop()

        mock_am.send_command.assert_not_called()
        mock_update.assert_awaited()
        assert mock_update.call_args_list[-1][0][2] == "failed"

    # -- Successful send -> status=success, payload matches manual exec ------

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        task = _make_task(env_vars={"FOO": "bar"})
        token_row = {"agent_token": "secret-token"}
        db = _mock_db_service(
            is_connected=True,
            tasks=[task],
            agent_token_row=token_row,
            cmd_log_id=777,
        )
        mock_sign = MagicMock(return_value=({"type": "exec_script"}, "sig123"))
        mock_am = _make_agent_manager(send_result=True)

        with (
            patch("asyncio.sleep", side_effect=self._sleep_side_effect()),
            patch("shared.database.db_service", db),
            patch(
                "web.backend.core.automation_engine.cron_matches_now",
                return_value=True,
            ),
            patch("web.backend.core.agent_hmac.sign_command_with_ts", mock_sign),
            patch("web.backend.core.agent_manager.agent_manager", mock_am),
            patch(
                "web.backend.core.task_scheduler._update_task_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            from web.backend.core.task_scheduler import task_scheduler_loop

            with pytest.raises(_StopLoop):
                await task_scheduler_loop()

        # sign_command_with_ts called with canonical exec_script payload
        mock_sign.assert_called_once()
        payload_arg, token_arg = mock_sign.call_args[0]
        assert payload_arg["type"] == "exec_script"
        assert payload_arg["command_id"] == 777
        assert payload_arg["timeout"] == 120
        assert "echo ok" in payload_arg["script_content"]
        assert "export FOO=bar" in payload_arg["script_content"]
        assert token_arg == "secret-token"

        # send_command called on agent_manager (not send_to_node!)
        mock_am.send_command.assert_awaited_once()
        send_args = mock_am.send_command.call_args[0]
        assert send_args[0] == "aaaa-bbbb-cccc"
        assert send_args[1].get("_sig") == "sig123"

        mock_update.assert_awaited_once()
        assert mock_update.call_args[0][2] == "success"

    # -- env_vars as JSON string -> decoded and applied as shell exports -----

    @pytest.mark.asyncio
    async def test_env_vars_json_string_decoded(self):
        env_dict = {"KEY": "value", "NUM": "42"}
        task = _make_task(env_vars=json.dumps(env_dict))
        token_row = {"agent_token": "tok"}
        db = _mock_db_service(
            is_connected=True, tasks=[task], agent_token_row=token_row,
        )
        mock_sign = MagicMock(return_value=({}, "s"))
        mock_am = _make_agent_manager()

        with (
            patch("asyncio.sleep", side_effect=self._sleep_side_effect()),
            patch("shared.database.db_service", db),
            patch(
                "web.backend.core.automation_engine.cron_matches_now",
                return_value=True,
            ),
            patch("web.backend.core.agent_hmac.sign_command_with_ts", mock_sign),
            patch("web.backend.core.agent_manager.agent_manager", mock_am),
            patch(
                "web.backend.core.task_scheduler._update_task_status",
                new_callable=AsyncMock,
            ),
        ):
            from web.backend.core.task_scheduler import task_scheduler_loop

            with pytest.raises(_StopLoop):
                await task_scheduler_loop()

        script_content = mock_sign.call_args[0][0]["script_content"]
        assert "export KEY=value" in script_content
        assert "export NUM=42" in script_content

    # -- env_vars is None -> script unchanged, no export prefix --------------

    @pytest.mark.asyncio
    async def test_env_vars_none_no_exports(self):
        task = _make_task(env_vars=None)
        token_row = {"agent_token": "tok"}
        db = _mock_db_service(
            is_connected=True, tasks=[task], agent_token_row=token_row,
        )
        mock_sign = MagicMock(return_value=({}, "s"))
        mock_am = _make_agent_manager()

        with (
            patch("asyncio.sleep", side_effect=self._sleep_side_effect()),
            patch("shared.database.db_service", db),
            patch(
                "web.backend.core.automation_engine.cron_matches_now",
                return_value=True,
            ),
            patch("web.backend.core.agent_hmac.sign_command_with_ts", mock_sign),
            patch("web.backend.core.agent_manager.agent_manager", mock_am),
            patch(
                "web.backend.core.task_scheduler._update_task_status",
                new_callable=AsyncMock,
            ),
        ):
            from web.backend.core.task_scheduler import task_scheduler_loop

            with pytest.raises(_StopLoop):
                await task_scheduler_loop()

        script_content = mock_sign.call_args[0][0]["script_content"]
        assert "export" not in script_content

    # -- timeout_seconds None -> default 300 ---------------------------------

    @pytest.mark.asyncio
    async def test_timeout_defaults_to_300(self):
        task = _make_task(timeout_seconds=None)
        token_row = {"agent_token": "tok"}
        db = _mock_db_service(
            is_connected=True, tasks=[task], agent_token_row=token_row,
        )
        mock_sign = MagicMock(return_value=({}, "s"))
        mock_am = _make_agent_manager()

        with (
            patch("asyncio.sleep", side_effect=self._sleep_side_effect()),
            patch("shared.database.db_service", db),
            patch(
                "web.backend.core.automation_engine.cron_matches_now",
                return_value=True,
            ),
            patch("web.backend.core.agent_hmac.sign_command_with_ts", mock_sign),
            patch("web.backend.core.agent_manager.agent_manager", mock_am),
            patch(
                "web.backend.core.task_scheduler._update_task_status",
                new_callable=AsyncMock,
            ),
        ):
            from web.backend.core.task_scheduler import task_scheduler_loop

            with pytest.raises(_StopLoop):
                await task_scheduler_loop()

        payload_arg = mock_sign.call_args[0][0]
        assert payload_arg["timeout"] == 300

    # -- Inner exception -> status=failed, loop continues --------------------

    @pytest.mark.asyncio
    async def test_inner_exception_marks_failed(self):
        task = _make_task()
        token_row = {"agent_token": "tok"}
        db = _mock_db_service(
            is_connected=True, tasks=[task], agent_token_row=token_row,
        )
        mock_sign = MagicMock(side_effect=RuntimeError("hmac broken"))
        mock_am = _make_agent_manager()

        with (
            patch("asyncio.sleep", side_effect=self._sleep_side_effect()),
            patch("shared.database.db_service", db),
            patch(
                "web.backend.core.automation_engine.cron_matches_now",
                return_value=True,
            ),
            patch("web.backend.core.agent_hmac.sign_command_with_ts", mock_sign),
            patch("web.backend.core.agent_manager.agent_manager", mock_am),
            patch(
                "web.backend.core.task_scheduler._update_task_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            from web.backend.core.task_scheduler import task_scheduler_loop

            with pytest.raises(_StopLoop):
                await task_scheduler_loop()

        mock_update.assert_awaited_once()
        assert mock_update.call_args[0][2] == "failed"

    # -- Outer exception -> loop does not crash -------------------------------

    @pytest.mark.asyncio
    async def test_outer_exception_does_not_crash_loop(self):
        """If db_service.acquire() itself raises, the outer except catches it."""
        db = MagicMock()
        db.is_connected = True
        db.acquire = MagicMock(side_effect=RuntimeError("pool exhausted"))

        with (
            patch("asyncio.sleep", side_effect=self._sleep_side_effect()),
            patch("shared.database.db_service", db),
        ):
            from web.backend.core.task_scheduler import task_scheduler_loop

            with pytest.raises(_StopLoop):
                await task_scheduler_loop()

    # -- Send fails -> status=failed ------------------------------------------

    @pytest.mark.asyncio
    async def test_send_failure_marks_failed(self):
        task = _make_task()
        token_row = {"agent_token": "tok"}
        db = _mock_db_service(
            is_connected=True, tasks=[task], agent_token_row=token_row,
        )
        mock_sign = MagicMock(return_value=({}, "s"))
        mock_am = _make_agent_manager(send_result=False)

        with (
            patch("asyncio.sleep", side_effect=self._sleep_side_effect()),
            patch("shared.database.db_service", db),
            patch(
                "web.backend.core.automation_engine.cron_matches_now",
                return_value=True,
            ),
            patch("web.backend.core.agent_hmac.sign_command_with_ts", mock_sign),
            patch("web.backend.core.agent_manager.agent_manager", mock_am),
            patch(
                "web.backend.core.task_scheduler._update_task_status",
                new_callable=AsyncMock,
            ) as mock_update,
        ):
            from web.backend.core.task_scheduler import task_scheduler_loop

            with pytest.raises(_StopLoop):
                await task_scheduler_loop()

        mock_update.assert_awaited_once()
        assert mock_update.call_args[0][2] == "failed"

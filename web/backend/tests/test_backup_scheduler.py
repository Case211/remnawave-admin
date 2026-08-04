"""Tests for scheduled auto-backup logic (_run_auto_backup_if_due)."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

import web.backend.core.backup_service as bs


def _fake_config(values):
    m = MagicMock()
    m.get.side_effect = lambda k, d=None: values.get(k, d)
    return m


def _now_hhmm():
    return datetime.now(timezone.utc).strftime("%H:%M")


@pytest.fixture(autouse=True)
def _reset_state():
    bs._last_auto_backup_ts = None
    bs._last_deadman_alert_date = None
    yield
    bs._last_auto_backup_ts = None
    bs._last_deadman_alert_date = None


class TestAutoBackupDue:
    @pytest.mark.asyncio
    async def test_disabled_does_nothing(self):
        cfg = _fake_config({"backup_auto_enabled": False})
        with patch("shared.config_service.config_service", cfg), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock) as mk:
            await bs._run_auto_backup_if_due()
            mk.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrong_time_does_nothing(self):
        # Daily mode, schedule time that can never match "HH:MM"
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": "99:99",
            "backup_auto_interval_hours": 0,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock) as mk:
            await bs._run_auto_backup_if_due()
            mk.assert_not_called()

    @pytest.mark.asyncio
    async def test_daily_due_creates_db_only(self):
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": _now_hhmm(),
            "backup_auto_interval_hours": 0, "backup_auto_telegram": False,
            "backup_auto_config": False, "backup_auto_keep_count": 10,
            "backup_auto_keep_days": 30,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.dict("os.environ", {"DATABASE_URL": "postgres://x"}), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock,
                             return_value={"filename": "db.sql.gz", "size_bytes": 1}) as mk_db, \
                patch.object(bs, "export_config", new_callable=AsyncMock) as mk_cfg, \
                patch.object(bs, "rotate_backups", return_value=0), \
                patch.object(bs, "_log_and_maybe_send", new_callable=AsyncMock):
            await bs._run_auto_backup_if_due()
            mk_db.assert_awaited_once()
            mk_cfg.assert_not_called()  # config backup disabled

    @pytest.mark.asyncio
    async def test_config_backup_when_enabled(self):
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": _now_hhmm(),
            "backup_auto_interval_hours": 0, "backup_auto_config": True,
            "backup_auto_telegram": False, "backup_auto_keep_count": 10,
            "backup_auto_keep_days": 30,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.dict("os.environ", {"DATABASE_URL": "postgres://x"}), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock,
                             return_value={"filename": "db.sql.gz", "size_bytes": 1}), \
                patch.object(bs, "export_config", new_callable=AsyncMock,
                             return_value={"filename": "cfg.json", "size_bytes": 1}) as mk_cfg, \
                patch.object(bs, "rotate_backups", return_value=0), \
                patch.object(bs, "_log_and_maybe_send", new_callable=AsyncMock):
            await bs._run_auto_backup_if_due()
            mk_cfg.assert_awaited_once()  # config backup enabled

    @pytest.mark.asyncio
    async def test_daily_not_twice_same_day(self):
        bs._last_auto_backup_ts = datetime.now(timezone.utc)  # already ran today
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": _now_hhmm(),
            "backup_auto_interval_hours": 0,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock) as mk:
            await bs._run_auto_backup_if_due()
            mk.assert_not_called()

    @pytest.mark.asyncio
    async def test_interval_due_after_n_hours(self):
        # interval 4h, last run 5h ago → due regardless of current clock time
        bs._last_auto_backup_ts = datetime.now(timezone.utc) - timedelta(hours=5)
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": "00:00",
            "backup_auto_interval_hours": 4, "backup_auto_telegram": False,
            "backup_auto_config": False, "backup_auto_keep_count": 10,
            "backup_auto_keep_days": 30,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.dict("os.environ", {"DATABASE_URL": "postgres://x"}), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock,
                             return_value={"filename": "db.sql.gz", "size_bytes": 1}) as mk_db, \
                patch.object(bs, "rotate_backups", return_value=0), \
                patch.object(bs, "_log_and_maybe_send", new_callable=AsyncMock):
            await bs._run_auto_backup_if_due()
            mk_db.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_interval_not_due_yet(self):
        # interval 4h, last run 1h ago → not due
        bs._last_auto_backup_ts = datetime.now(timezone.utc) - timedelta(hours=1)
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": "00:00",
            "backup_auto_interval_hours": 4,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock) as mk:
            await bs._run_auto_backup_if_due()
            mk.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_failure_triggers_alert(self):
        cfg = _fake_config({
            "backup_auto_enabled": True, "backup_auto_time": _now_hhmm(),
            "backup_auto_interval_hours": 0, "backup_auto_config": True,
        })
        with patch("shared.config_service.config_service", cfg), \
                patch.dict("os.environ", {"DATABASE_URL": "postgres://x"}), \
                patch.object(bs, "create_database_backup", new_callable=AsyncMock,
                             side_effect=RuntimeError("pg_dump boom")), \
                patch.object(bs, "export_config", new_callable=AsyncMock) as mk_cfg, \
                patch.object(bs, "_notify_backup_failed", new_callable=AsyncMock) as mk_alert:
            await bs._run_auto_backup_if_due()
            mk_alert.assert_awaited_once()   # alert on failure
            mk_cfg.assert_not_called()       # returned early — no config backup


class TestDeadman:
    @pytest.mark.asyncio
    async def test_deadman_alerts_when_stale(self):
        cfg = _fake_config({"backup_deadman_hours": 1})
        with patch("shared.config_service.config_service", cfg), \
                patch.object(bs, "_get_last_successful_backup_ts", new_callable=AsyncMock,
                             return_value=datetime.now(timezone.utc) - timedelta(hours=5)), \
                patch.object(bs, "_notify_backup_failed", new_callable=AsyncMock) as mk_alert:
            await bs._check_deadman()
            mk_alert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deadman_silent_when_fresh(self):
        cfg = _fake_config({"backup_deadman_hours": 24})
        with patch("shared.config_service.config_service", cfg), \
                patch.object(bs, "_get_last_successful_backup_ts", new_callable=AsyncMock,
                             return_value=datetime.now(timezone.utc) - timedelta(hours=1)), \
                patch.object(bs, "_notify_backup_failed", new_callable=AsyncMock) as mk_alert:
            await bs._check_deadman()
            mk_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_deadman_disabled(self):
        cfg = _fake_config({"backup_deadman_hours": 0})
        with patch("shared.config_service.config_service", cfg), \
                patch.object(bs, "_notify_backup_failed", new_callable=AsyncMock) as mk_alert:
            await bs._check_deadman()
            mk_alert.assert_not_called()


class TestApiErrorStringCode:
    """Баг: api_error(400, "NO_CHAT_ID") падал AttributeError на str.value —
    осмысленный 400 превращался в 500 Internal Server Error."""

    def test_string_code_does_not_crash(self):
        from web.backend.core.errors import api_error

        exc = api_error(400, "NO_CHAT_ID", "Specify chat_id")
        assert exc.status_code == 400
        assert exc.detail["code"] == "NO_CHAT_ID"
        assert exc.detail["detail"] == "Specify chat_id"

    def test_string_code_without_detail(self):
        from web.backend.core.errors import api_error

        exc = api_error(404, "SOME_UNKNOWN_CODE")
        assert exc.status_code == 404
        assert exc.detail["code"] == "SOME_UNKNOWN_CODE"
        assert exc.detail["detail"] == "SOME_UNKNOWN_CODE"

    def test_enum_code_still_works(self):
        from web.backend.core.errors import E, api_error

        exc = api_error(404, E.NOT_FOUND)
        assert exc.detail["code"] == E.NOT_FOUND.value
        assert exc.detail["detail"] == "Resource not found"


class TestResolveBackupTgDestination:
    """Баг: web-backend читал notifications_chat_id только из env — значение,
    заданное через UI (БД bot_config), игнорировалось, бэкап падал NO_CHAT_ID."""

    def _settings(self, chat_id=None, topic=None, general_topic=None):
        s = MagicMock()
        s.notifications_chat_id = chat_id
        # Задаём явно: у MagicMock любой атрибут «существует», а int() от
        # него молча даёт 1 — незаданный общий топик выглядел бы как топик №1.
        s.notifications_topic_id = general_topic
        s.get_topic_for.return_value = topic
        return s

    def _cfg(self, values):
        cfg = MagicMock()
        cfg.get.side_effect = lambda key, default=None: values.get(key, default)
        return cfg

    def test_db_value_wins_over_env(self):
        from web.backend.core import backup_service

        cfg = self._cfg({"notifications_chat_id": -100123,
                         "notifications_topic_service": 42})
        with patch("shared.notification_config.config_service", cfg), \
             patch("web.backend.core.config.get_web_settings",
                   return_value=self._settings(chat_id="-100999", topic="7")):
            chat_id, topic_id = backup_service.resolve_backup_tg_destination()
        assert chat_id == "-100123"
        assert topic_id == 42

    def test_general_db_topic_used_when_service_topic_unset(self):
        """Общий топик из UI раньше терялся — бэкап уходил в корень чата."""
        from web.backend.core import backup_service

        cfg = self._cfg({"notifications_chat_id": -100123,
                         "notifications_topic_id": 55})
        with patch("shared.notification_config.config_service", cfg), \
             patch("web.backend.core.config.get_web_settings",
                   return_value=self._settings(chat_id="-100999")):
            chat_id, topic_id = backup_service.resolve_backup_tg_destination()
        assert chat_id == "-100123"
        assert topic_id == 55

    def test_env_fallback_when_db_empty(self):
        from web.backend.core import backup_service

        with patch("shared.notification_config.config_service", self._cfg({})), \
             patch("web.backend.core.config.get_web_settings",
                   return_value=self._settings(chat_id="-100999", topic="7")):
            chat_id, topic_id = backup_service.resolve_backup_tg_destination()
        assert chat_id == "-100999"
        assert topic_id == 7

    def test_none_when_nothing_configured(self):
        from web.backend.core import backup_service

        with patch("shared.notification_config.config_service", self._cfg({})), \
             patch("web.backend.core.config.get_web_settings",
                   return_value=self._settings()):
            chat_id, topic_id = backup_service.resolve_backup_tg_destination()
        assert chat_id is None
        assert topic_id is None

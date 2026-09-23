"""Штрафы шейпера в панели: события от агента и состояние для бейджа."""
from datetime import timezone

import pytest

from web.backend.core import shaper_rollout


class TestCleanEvents:
    def test_valid_event_becomes_a_record(self):
        [ev] = shaper_rollout.clean_penalty_events([
            {"ip": " 1.2.3.4 ", "started_at": 1_700_000_000, "until": 1_700_000_900, "bytes": 42},
        ])
        assert ev["ip"] == "1.2.3.4"
        assert ev["started_at"].tzinfo == timezone.utc
        assert (ev["until"] - ev["started_at"]).total_seconds() == 900
        assert ev["bytes"] == 42

    @pytest.mark.parametrize("event", [
        {"ip": "not-an-ip", "started_at": 1, "until": 2},
        {"ip": "1.2.3.4", "started_at": "soon", "until": 2},
        {"ip": "1.2.3.4", "until": 2},
        "garbage",
    ])
    def test_garbage_is_dropped(self, event):
        assert shaper_rollout.clean_penalty_events([event]) == []

    def test_not_a_list(self):
        assert shaper_rollout.clean_penalty_events({"ip": "1.2.3.4"}) == []


class TestBadgeState:
    @pytest.mark.parametrize("enabled,status,expected", [
        (False, {"active": True}, None),
        (True, None, "waiting"),
        (True, {"active": True, "download_exact": True}, "active"),
        (True, {"active": True, "download_exact": False}, "rough"),
        (True, {"active": False, "error": "taken by another tool"}, "error"),
        (True, {"active": False}, "waiting"),
    ])
    def test_state(self, enabled, status, expected):
        assert shaper_rollout.state_of(enabled, status) == expected


def test_bytes_are_human_readable():
    assert shaper_rollout._format_bytes(3 * 1024**3) == "3.0 ГБ"
    assert shaper_rollout._format_bytes(5 * 1024**2) == "5.0 МБ"
    assert shaper_rollout._format_bytes(512) == "512 Б"

"""Regression guard for _db_row_to_api_format uuid handling under Panel v3.

Remnawave v3 identifies users by numeric id and its user payload carries no
`uuid` — the local `users.uuid` column (auto-generated) is the only uuid.
The API contract (and the frontend's user-scoped routes / RBAC scope checks)
require the formatted dict to include `uuid`.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from shared.db._base import _db_row_to_api_format


class _FakeRow:
    def __init__(self, data):
        self._d = data

    def __getitem__(self, key):
        return self._d[key]

    def keys(self):
        return self._d.keys()


def _row(uuid=None, panel_id=None, raw_data=None, **extra):
    data = {"uuid": uuid, "id": panel_id, "raw_data": raw_data}
    data.update(extra)
    return _FakeRow(data)


class TestV3UuidInjection:
    def test_v3_raw_data_without_uuid_gets_local_uuid(self):
        row = _row(
            uuid="11111111-2222-3333-4444-555555555555",
            panel_id=42,
            raw_data=json.dumps({"id": 42, "username": "alice", "status": "ACTIVE"}),
        )
        out = _db_row_to_api_format(row)
        assert out["uuid"] == "11111111-2222-3333-4444-555555555555"
        assert out["id"] == 42
        assert out["username"] == "alice"

    def test_v3_raw_data_as_dict_without_uuid(self):
        row = _row(
            uuid="aaaa-1111",
            panel_id=7,
            raw_data={"id": 7, "username": "bob"},
        )
        out = _db_row_to_api_format(row)
        assert out["uuid"] == "aaaa-1111"

    def test_v2_raw_data_with_uuid_not_overwritten(self):
        row = _row(
            uuid="aaaa-1111",
            panel_id=7,
            raw_data=json.dumps({"uuid": "aaaa-1111", "username": "bob", "id": 7}),
        )
        out = _db_row_to_api_format(row)
        assert out["uuid"] == "aaaa-1111"

    def test_no_raw_data_fallback_includes_uuid(self):
        row = _row(uuid="zzz-1", username="carol", status="ACTIVE", raw_data=None)
        out = _db_row_to_api_format(row)
        assert out["uuid"] == "zzz-1"

    def test_null_row(self):
        assert _db_row_to_api_format(None) == {}

"""Текстовая сводка снимка показывает индексы и параметры хранения таблиц.

Индексы и fillfactor нужны, чтобы снимать лишние индексы и ловить не-HOT
апдейты по цифрам с живой установки, а не по догадкам.
"""
from web.backend.api.v2.diagnostics import _as_text


def test_text_lists_indexes_and_table_options():
    full = {
        "taken_at": "2026-09-03T17:49:20+00:00",
        "host": {},
        "database": {
            "top_tables": [{
                "table": "user_connections_p2026_09", "live": 61054, "dead": 3277,
                "ins": 61054, "upd": 2076516, "hot_upd": 177941, "del": 0,
                "bytes": 33349632, "last_autovacuum": None, "options": ["fillfactor=90"],
            }],
            "top_indexes": [{
                "table": "user_connections_p2026_09", "index": "idx_uc_part_user_active",
                "scans": 0, "bytes": 5242880,
            }],
        },
        "processes": [],
    }
    text = _as_text(full)
    assert "user_connections_p2026_09: 31.8 МБ, 61054/3277, 61054/2076516/9%/0 [fillfactor=90]" in text
    assert "Индексы по размеру" in text
    assert "idx_uc_part_user_active на user_connections_p2026_09: 5.0 МБ, 0" in text

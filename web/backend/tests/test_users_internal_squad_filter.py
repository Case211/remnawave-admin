"""Фильтр списка пользователей по внутренним сквадам (API-фолбэк и нормализация)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.db.users import UsersMixin
from web.backend.api.v2.users import _filter_users_in_memory, _internal_squad_uuids


def _user(uuid: str, squads):
    return {"uuid": uuid, "username": uuid, "status": "ACTIVE", "activeInternalSquads": squads}


class TestInternalSquadUuids:
    def test_objects_and_strings_become_lowercase_uuids(self):
        value = [{"uuid": "AAA", "name": "Standard"}, "BBB", {"name": "no uuid"}, None]
        assert _internal_squad_uuids(value) == ["aaa", "bbb"]

    def test_non_list_is_empty(self):
        assert _internal_squad_uuids(None) == []
        assert _internal_squad_uuids("AAA") == []


class TestInMemoryFilter:
    USERS = [
        _user("u1", [{"uuid": "S1", "name": "Standard"}]),
        _user("u2", ["s1", "s3"]),
        _user("u3", [{"uuid": "S2"}]),
        _user("u4", None),
    ]

    def test_filters_members_of_squad(self):
        result, total = _filter_users_in_memory(self.USERS, internal_squad_uuids=["s1"])
        assert total == 2
        assert sorted(u["uuid"] for u in result) == ["u1", "u2"]

    def test_several_squads_mean_any_of_them(self):
        """Мультивыбор: юзер проходит, состоя хотя бы в одном из выбранных."""
        result, total = _filter_users_in_memory(self.USERS, internal_squad_uuids=["S2", "s3"])
        assert total == 2
        assert sorted(u["uuid"] for u in result) == ["u2", "u3"]

    def test_no_filter_keeps_everyone(self):
        _, total = _filter_users_in_memory(self.USERS)
        assert total == 4


class TestSqlFilter:
    """SQL-путь: raw_data — JSONB, фильтр обязан звать jsonb_*-функции."""

    @pytest.mark.asyncio
    async def test_query_uses_jsonb_functions_and_array_param(self):
        """Регрессия: json_typeof(jsonb) в PG нет — запрос падал, и список молча
        уезжал в фолбэк на API панели, где сквадов нет: пусто при любом выборе."""
        seen = {}

        async def fetch(sql, *args):
            seen["sql"], seen["args"] = sql, args
            return []

        async def fetchval(sql, *args):
            return 0

        conn = MagicMock()
        conn.fetch = fetch
        conn.fetchval = fetchval
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)

        class _Db(UsersMixin):
            is_connected = True

            def acquire(self):
                return cm

        users, total = await _Db().get_users_paginated(internal_squad_uuids=["S1", "s2"])

        assert (users, total) == ([], 0)
        sql = seen["sql"]
        assert "jsonb_array_elements(" in sql and "jsonb_typeof(raw_data->'activeInternalSquads')" in sql
        assert "'[]'::jsonb" in sql
        assert "json_typeof(" not in sql.replace("jsonb_typeof(", "") and "json_array_elements(" not in sql.replace("jsonb_array_elements(", "")
        assert "= ANY($1::text[])" in sql
        assert seen["args"][0] == ["s1", "s2"]

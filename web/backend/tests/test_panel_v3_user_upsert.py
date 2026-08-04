"""Апсерт пользователей с панели v3: защита от задвоения строк.

Панель 3.x не отдаёт uuid, поэтому апсерт матчится по users.id. У строк,
заведённых до обновления панели, id пустой — без предварительной привязки
по short_uuid ON CONFLICT (id) не срабатывает, и синк вставляет вторую
строку с uuid из дефолта gen_random_uuid(). Так в проде задвоились все
пользователи: история осталась на старых строках, а синк обновлял новые.
"""
from unittest.mock import AsyncMock

import pytest

from shared.db.users import UsersMixin


def _conn_mock(has_legacy=True):
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=1 if has_legacy else None)
    conn.execute = AsyncMock(return_value="INSERT 0 1")
    return conn


def _v3_user(panel_id=157, short_uuid="SU157"):
    return {"id": panel_id, "shortUuid": short_uuid, "username": "u1", "status": "ACTIVE"}


def _executed_sql(conn):
    return [call.args[0] for call in conn.execute.await_args_list if call.args]


class TestAdoptLegacyRows:
    @pytest.mark.asyncio
    async def test_binds_legacy_row_by_short_uuid(self):
        conn = _conn_mock()
        await UsersMixin._adopt_legacy_rows(conn, [(157, "SU157"), (158, "SU158")])
        sql = _executed_sql(conn)
        assert len(sql) == 1
        assert "UPDATE" in sql[0] and "short_uuid" in sql[0]
        args = conn.execute.await_args.args
        assert args[1] == [157, 158]
        assert args[2] == ["SU157", "SU158"]

    @pytest.mark.asyncio
    async def test_skips_when_no_legacy_rows(self):
        """Все строки уже с панельным id — лишний UPDATE на каждый синк не нужен."""
        conn = _conn_mock(has_legacy=False)
        await UsersMixin._adopt_legacy_rows(conn, [(157, "SU157")])
        conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_records_without_short_uuid(self):
        """Без short_uuid сопоставить не с чем — такие записи пропускаем."""
        conn = _conn_mock()
        await UsersMixin._adopt_legacy_rows(conn, [(157, None)])
        conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_binding_is_ambiguity_safe(self):
        """Привязка идёт только по однозначным совпадениям."""
        conn = _conn_mock()
        await UsersMixin._adopt_legacy_rows(conn, [(157, "SU157")])
        sql = _executed_sql(conn)[0]
        assert "HAVING count(*) = 1" in sql
        # Занятый панельный id второй раз не назначаем.
        assert "NOT EXISTS" in sql


class TestUpsertBindsBeforeInsert:
    @pytest.mark.asyncio
    async def test_v3_record_adopts_before_insert(self):
        """Привязка обязана идти ДО INSERT, иначе ON CONFLICT (id) не поймает строку."""
        conn = _conn_mock()
        await UsersMixin()._upsert_user_with_conn(conn, _v3_user())
        sql = _executed_sql(conn)
        assert len(sql) == 2
        assert "UPDATE" in sql[0]
        assert "ON CONFLICT (id)" in sql[1]

    @pytest.mark.asyncio
    async def test_v2_record_untouched(self):
        """У панели v2 uuid есть и матчинг идёт по нему — привязка не нужна."""
        conn = _conn_mock()
        await UsersMixin()._upsert_user_with_conn(
            conn, {"uuid": "11111111-1111-1111-1111-111111111111", "shortUuid": "SU1"}
        )
        sql = _executed_sql(conn)
        assert len(sql) == 1
        assert "ON CONFLICT (uuid)" in sql[0]

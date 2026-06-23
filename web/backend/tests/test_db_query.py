"""Tests for the generic SQL command builders (shared/db_query.py).

Regression guard for PR #255: update_sql()/delete_sql() prepend WHERE
themselves, so a caller passing a "WHERE ..." condition produced invalid
"... WHERE WHERE ..." SQL that silently reached production.
"""
import pytest

from shared.db_query import delete_sql, select_sql, update_sql


class TestUpdateSql:
    def test_basic(self):
        assert update_sql("t", "a = $1", "id = $2") == "UPDATE t SET a = $1 WHERE id = $2"

    def test_with_returning(self):
        assert (
            update_sql("t", "a = $1", "id = $2", returning="*")
            == "UPDATE t SET a = $1 WHERE id = $2 RETURNING *"
        )

    def test_rejects_redundant_where(self):
        with pytest.raises(ValueError):
            update_sql("t", "a = $1", "WHERE id = $2")

    def test_rejects_redundant_where_case_and_space_insensitive(self):
        with pytest.raises(ValueError):
            update_sql("t", "a = $1", "  where id = $2")


class TestDeleteSql:
    def test_basic(self):
        assert delete_sql("t", "id = $1") == "DELETE FROM t WHERE id = $1"

    def test_rejects_redundant_where(self):
        with pytest.raises(ValueError):
            delete_sql("t", "WHERE id = $1")

    def test_column_named_where_is_not_rejected(self):
        # "where_clause" is a column prefix, not the WHERE keyword — must pass.
        assert (
            delete_sql("t", "where_active = $1")
            == "DELETE FROM t WHERE where_active = $1"
        )


class TestSelectSql:
    def test_suffix_carries_where(self):
        # select_sql is intentionally different: the suffix owns WHERE/JOIN/etc.
        assert select_sql("t", "*", "WHERE id = $1") == "SELECT * FROM t WHERE id = $1"

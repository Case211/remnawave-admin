"""API уведомлений: массовая очистка прочитанных и порядок маршрутов."""
from unittest.mock import AsyncMock, patch

import pytest


def _db_with(cm):
    db = AsyncMock()
    db.acquire = lambda: cm
    return db


class TestDeleteReadNotifications:
    @pytest.mark.asyncio
    async def test_deletes_only_read_any_age(self, client, mock_db_acquire):
        mock_conn, cm = mock_db_acquire
        mock_conn.execute = AsyncMock(return_value="DELETE 1700")
        with patch("shared.database.db_service", _db_with(cm)):
            resp = await client.delete("/api/v2/notifications/read")
        assert resp.status_code == 200
        assert resp.json() == {"deleted": 1700}
        sql = mock_conn.execute.await_args.args[0]
        assert "is_read = true" in sql
        assert "created_at" not in sql  # без ограничения по возрасту
        assert mock_conn.execute.await_args.args[1] == 1  # свои + broadcast (admin_id NULL)

    @pytest.mark.asyncio
    async def test_route_not_shadowed_by_id_route(self, client, mock_db_acquire):
        """DELETE /notifications/read объявлен раньше /notifications/{id}, иначе был бы 422."""
        mock_conn, cm = mock_db_acquire
        mock_conn.execute = AsyncMock(return_value="DELETE 0")
        mock_conn.fetchval = AsyncMock(return_value=5)
        with patch("shared.database.db_service", _db_with(cm)):
            read = await client.delete("/api/v2/notifications/read")
            by_id = await client.delete("/api/v2/notifications/5")
        assert read.status_code == 200
        assert read.json()["deleted"] == 0
        assert by_id.status_code == 200  # удаление по id по-прежнему работает

    @pytest.mark.asyncio
    async def test_requires_delete_permission(self, viewer_client):
        resp = await viewer_client.delete("/api/v2/notifications/read")
        assert resp.status_code == 403

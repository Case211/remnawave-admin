"""Tests for users API — /api/v2/users/*."""
import pytest
from unittest.mock import patch, AsyncMock

from web.backend.api.deps import get_current_admin
from .conftest import make_admin


MOCK_USERS = [
    {
        "uuid": "aaa-111",
        "short_uuid": "aaa",
        "username": "alice",
        "status": "active",
        "subscription_uuid": "sub-1",
        "traffic_limit_bytes": 10_000_000_000,
        "used_traffic_bytes": 1_000_000,
        "lifetime_used_traffic_bytes": 5_000_000,
        "expire_at": "2026-12-31T00:00:00Z",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-02-01T00:00:00Z",
        "online_at": None,
        "telegram_id": None,
        "hwid_device_limit": 3,
        "hwid_device_count": 1,
        "note": "",

        "sub_revoked_at": None,
        "last_traffic_reset_at": None,
        "traffic_limit_strategy": "no_reset",
        "email": "alice@example.com",
        "tag": "VIP",
        "external_squad_uuid": "squad-aaa",
    },
    {
        "uuid": "bbb-222",
        "short_uuid": "bbb",
        "username": "bob",
        "status": "disabled",
        "subscription_uuid": "sub-2",
        "traffic_limit_bytes": 0,
        "used_traffic_bytes": 0,
        "lifetime_used_traffic_bytes": 0,
        "expire_at": None,
        "created_at": "2026-01-02T00:00:00Z",
        "updated_at": "2026-02-01T00:00:00Z",
        "online_at": None,
        "telegram_id": 12345,
        "hwid_device_limit": 0,
        "hwid_device_count": 0,
        "note": "test user",

        "sub_revoked_at": None,
        "last_traffic_reset_at": None,
        "traffic_limit_strategy": "no_reset",
        "email": None,
        "tag": None,
        "external_squad_uuid": None,
    },
]


class TestListUsers:
    """GET /api/v2/users."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=MOCK_USERS)
    @patch("shared.database.db_service")
    async def test_list_users_success(self, mock_db, mock_get, client):
        mock_db.is_connected = False  # Force API fallback path
        resp = await client.get("/api/v2/users")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=MOCK_USERS)
    @patch("shared.database.db_service")
    async def test_list_users_pagination(self, mock_db, mock_get, client):
        mock_db.is_connected = False
        resp = await client.get("/api/v2/users?page=1&per_page=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["total"] == 2

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=MOCK_USERS)
    @patch("shared.database.db_service")
    async def test_list_users_search(self, mock_db, mock_get, client):
        mock_db.is_connected = False
        resp = await client.get("/api/v2/users?search=alice")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["username"] == "alice"

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=MOCK_USERS)
    @patch("shared.database.db_service")
    async def test_list_users_filter_status(self, mock_db, mock_get, client):
        mock_db.is_connected = False
        resp = await client.get("/api/v2/users?status=active")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "active"

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=MOCK_USERS)
    @patch("shared.database.db_service")
    async def test_list_users_filter_external_squad(self, mock_db, mock_get, client):
        mock_db.is_connected = False
        resp = await client.get("/api/v2/users?external_squad_uuid=squad-aaa")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["username"] == "alice"

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=MOCK_USERS)
    @patch("shared.database.db_service")
    async def test_list_users_filter_tag(self, mock_db, mock_get, client):
        mock_db.is_connected = False
        resp = await client.get("/api/v2/users?tag=VIP")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["username"] == "alice"

    @pytest.mark.asyncio
    async def test_list_users_as_viewer_allowed(self, app, viewer):
        """Viewers have users.view permission."""
        app.dependency_overrides[get_current_admin] = lambda: viewer
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            with patch("shared.database.db_service") as mock_db:
                mock_db.is_connected = False
                with patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=[]):
                    resp = await ac.get("/api/v2/users")
                    assert resp.status_code == 200

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.users._get_users_list", new_callable=AsyncMock, return_value=[])
    @patch("shared.database.db_service")
    async def test_list_users_empty(self, mock_db, mock_get, client):
        mock_db.is_connected = False
        resp = await client.get("/api/v2/users")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0


class TestListUsersRBAC:
    """RBAC tests for user endpoints."""

    @pytest.mark.asyncio
    async def test_anon_get_users_unauthorized(self, anon_client):
        resp = await anon_client.get("/api/v2/users")
        assert resp.status_code == 401


class TestDetailFromPanel:
    """Ответ панели 3.0.0+ приходит без uuid — схема должна собираться всё равно."""

    def test_panel_v3_response_without_uuid(self):
        """Боевой случай: панель ответила 201, а панель показала «внутреннюю ошибку»."""
        from web.backend.api.v2.users import _detail_from_panel

        panel_response = {
            "id": 3823,
            "shortUuid": "aBcD1234",
            "username": "someone",
            "status": "ACTIVE",
            "hwid_device_count": 0,
        }

        detail = _detail_from_panel(panel_response, "11111111-2222-3333-4444-555555555555")

        assert detail.uuid == "11111111-2222-3333-4444-555555555555"
        assert detail.short_uuid == "aBcD1234"

    def test_panel_v2_uuid_wins(self):
        """У панели 2.x uuid свой — подменять его локальным нельзя."""
        from web.backend.api.v2.users import _detail_from_panel

        panel_response = {"uuid": "aaaaaaaa-0000-0000-0000-000000000000", "username": "someone"}

        detail = _detail_from_panel(panel_response, "99999999-9999-9999-9999-999999999999")

        assert detail.uuid == "aaaaaaaa-0000-0000-0000-000000000000"

    def test_unknown_uuid_does_not_break_the_response(self):
        """Пользователь создан. Ронять ответ из-за неизвестного uuid — худший исход."""
        from web.backend.api.v2.users import _detail_from_panel

        detail = _detail_from_panel({"id": 7, "username": "someone"}, "")

        assert detail.uuid == ""
        assert detail.username == "someone"


class TestEnsureSnakeCase:
    """Tests for _ensure_snake_case helper."""

    def test_maps_camel_to_snake(self):
        from web.backend.api.v2.users import _ensure_snake_case
        user = {"shortUuid": "abc", "subscriptionUuid": "sub-1"}
        result = _ensure_snake_case(user)
        assert result["short_uuid"] == "abc"
        assert result["subscription_uuid"] == "sub-1"

    def test_normalizes_status_to_lowercase(self):
        from web.backend.api.v2.users import _ensure_snake_case
        user = {"status": "ACTIVE"}
        result = _ensure_snake_case(user)
        assert result["status"] == "active"

    def test_flattens_user_traffic(self):
        from web.backend.api.v2.users import _ensure_snake_case
        user = {
            "userTraffic": {
                "usedTrafficBytes": 1000,
                "lifetimeUsedTrafficBytes": 5000,
                "onlineAt": "2026-01-01",
            }
        }
        result = _ensure_snake_case(user)
        assert result["used_traffic_bytes"] == 1000
        assert result["lifetime_used_traffic_bytes"] == 5000


class TestParseDt:
    """Tests for _parse_dt helper."""

    def test_none(self):
        from web.backend.api.v2.users import _parse_dt
        assert _parse_dt(None) is None

    def test_iso_string(self):
        from web.backend.api.v2.users import _parse_dt
        result = _parse_dt("2026-01-15T10:30:00Z")
        assert result is not None
        assert result.year == 2026

    def test_datetime_passthrough(self):
        from web.backend.api.v2.users import _parse_dt
        from datetime import datetime
        dt = datetime(2026, 1, 1)
        assert _parse_dt(dt) is dt

    def test_invalid_string(self):
        from web.backend.api.v2.users import _parse_dt
        assert _parse_dt("not-a-date") is None


class TestResolveUserByTelegramId:
    """POST /api/v2/users/resolve — цифры это и внутренний id панели, и Telegram ID."""

    @pytest.mark.asyncio
    async def test_falls_back_to_telegram_id_when_panel_id_misses(self, client):
        """Панель не знает такого id — ищем тот же номер как Telegram ID."""
        found = {"uuid": "344ddd21-fead-483a-ae23-8c49e6b83ddb",
                 "username": "GeologVPN_192647_6487", "shortUuid": "6U7X4Pn47FSb7JbumQJk"}

        with patch("shared.api_client.api_client.get_user_by_id",
                   new_callable=AsyncMock, side_effect=Exception("404")), \
                patch("web.backend.api.v2.users._lookup_user_by_telegram_id",
                      new_callable=AsyncMock, return_value={"response": found}), \
                patch("web.backend.api.v2.users._resolve_visible_user_uuid",
                      new_callable=AsyncMock, return_value=None):
            resp = await client.post("/api/v2/users/resolve", json={"query": "127192647"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["username"] == "GeologVPN_192647_6487"

    @pytest.mark.asyncio
    async def test_panel_id_still_wins(self, client):
        """Совпадение по внутреннему id панели по-прежнему возвращается первым."""
        panel_user = {"uuid": "11111111-1111-1111-1111-111111111111", "username": "by-panel-id"}
        tg_lookup = AsyncMock(return_value={"response": {"username": "by-telegram-id"}})

        with patch("shared.api_client.api_client.get_user_by_id",
                   new_callable=AsyncMock, return_value={"response": panel_user}), \
                patch("web.backend.api.v2.users._lookup_user_by_telegram_id", new=tg_lookup), \
                patch("web.backend.api.v2.users._resolve_visible_user_uuid",
                      new_callable=AsyncMock, return_value=None):
            resp = await client.post("/api/v2/users/resolve", json={"query": "42"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["username"] == "by-panel-id"
        tg_lookup.assert_not_awaited()


class TestLookupUserByTelegramId:
    """_lookup_user_by_telegram_id — обёртка над локальной таблицей."""

    @pytest.mark.asyncio
    async def test_returns_response_envelope(self):
        from web.backend.api.v2.users import _lookup_user_by_telegram_id

        user = {"uuid": "abc", "username": "tg-user"}
        with patch("shared.database.db_service") as db:
            db.is_connected = True
            db.get_user_by_telegram_id = AsyncMock(return_value=user)
            assert await _lookup_user_by_telegram_id("127192647") == {"response": user}
            db.get_user_by_telegram_id.assert_awaited_once_with(127192647)

    @pytest.mark.asyncio
    async def test_empty_when_not_found(self):
        from web.backend.api.v2.users import _lookup_user_by_telegram_id

        with patch("shared.database.db_service") as db:
            db.is_connected = True
            db.get_user_by_telegram_id = AsyncMock(return_value=None)
            assert await _lookup_user_by_telegram_id("1") == {}

    @pytest.mark.asyncio
    async def test_empty_without_db(self):
        from web.backend.api.v2.users import _lookup_user_by_telegram_id

        with patch("shared.database.db_service") as db:
            db.is_connected = False
            assert await _lookup_user_by_telegram_id("1") == {}


class TestResolveUserLocalFallback:
    """Локальный фолбэк resolve: описание/заметка/Telegram ID ищутся по таблице users."""

    @pytest.mark.asyncio
    async def test_non_uuid_query_reaches_local_search(self, client):
        """Регрессия: `uuid = $1` с текстом «vip-client» ронял запрос ошибкой
        asyncpg «invalid UUID», и поиск по описанию никогда не срабатывал."""
        from unittest.mock import MagicMock

        seen = {}

        async def fetchrow(sql, *args):
            seen["sql"] = sql
            seen["args"] = args
            return {"uuid": "344ddd21-fead-483a-ae23-8c49e6b83ddb",
                    "username": "by-description", "short_uuid": "6U7X4Pn47FSb7JbumQJk"}

        conn = MagicMock()
        conn.fetchrow = fetchrow
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        db = MagicMock()
        db.is_connected = True
        db.acquire = MagicMock(return_value=cm)

        with patch("shared.api_client.api_client.get_user_by_username",
                   new_callable=AsyncMock, side_effect=Exception("404")), \
                patch("shared.api_client.api_client.get_user_by_short_uuid",
                      new_callable=AsyncMock, side_effect=Exception("404")), \
                patch("shared.database.db_service", db), \
                patch("web.backend.api.v2.users._ensure_user_visible",
                      new_callable=AsyncMock, return_value=None):
            resp = await client.post("/api/v2/users/resolve", json={"query": "VIP-client"})

        assert resp.status_code == 200, resp.text
        assert resp.json()["username"] == "by-description"
        assert "uuid::text = $1" in seen["sql"]
        assert "WHERE uuid = $1" not in seen["sql"]
        assert seen["args"] == ("vip-client", "%vip-client%", "VIP-client")


class TestUserTrafficHourly:
    """/users/{uuid}/traffic-hourly — почасовой график по локальным дельтам синка."""

    @staticmethod
    def _hour(offset_hours: int):
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        return now - timedelta(hours=offset_hours)

    @pytest.mark.asyncio
    async def test_fills_empty_hours_with_zeros(self, client):
        """Час без трафика строки в истории не оставляет — сетку добивает бэкенд."""
        rows = [
            {"bucket": self._hour(2), "node_uuid": "node-a", "node_name": "Germany", "bytes": 100},
            {"bucket": self._hour(0), "node_uuid": "node-a", "node_name": "Germany", "bytes": 50},
            {"bucket": self._hour(0), "node_uuid": "node-bbbbbbbb", "node_name": None, "bytes": 200},
        ]
        with patch("shared.database.db_service") as db, \
                patch("web.backend.api.v2.users._ensure_user_visible",
                      new_callable=AsyncMock, return_value=None):
            db.is_connected = True
            db.get_user_traffic_hourly = AsyncMock(return_value=rows)
            resp = await client.get("/api/v2/users/aaa-111/traffic-hourly?hours=3")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert [p["total_bytes"] for p in data["points"]] == [100, 0, 250]
        assert data["total_bytes"] == 350
        assert data["peak_bytes"] == 250
        assert data["retention_hours"] == 48
        # Ноды — по убыванию трафика; у снятой ноды имени нет, остаётся обрезок uuid
        assert [n["node_uuid"] for n in data["nodes"]] == ["node-bbbbbbbb", "node-a"]
        assert data["nodes"][0]["node_name"] == "node-bbb"

    @pytest.mark.asyncio
    async def test_returns_empty_grid_without_db(self, client):
        with patch("shared.database.db_service") as db, \
                patch("web.backend.api.v2.users._ensure_user_visible",
                      new_callable=AsyncMock, return_value=None):
            db.is_connected = False
            resp = await client.get("/api/v2/users/aaa-111/traffic-hourly")

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["points"]) == 24
        assert data["total_bytes"] == 0
        assert data["nodes"] == []

    @pytest.mark.asyncio
    async def test_rejects_depth_beyond_retention(self, client):
        """Глубже ретеншна истории (48 ч) данных нет — просить бессмысленно."""
        with patch("web.backend.api.v2.users._ensure_user_visible",
                   new_callable=AsyncMock, return_value=None):
            resp = await client.get("/api/v2/users/aaa-111/traffic-hourly?hours=49")
        assert resp.status_code == 422

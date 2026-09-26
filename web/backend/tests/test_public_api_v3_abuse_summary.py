"""GET /api/v3/violations/summary — вердикт по клиенту для внешних интеграций.

Ручка отвечает на один вопрос: можно ли доверять этому человеку. Интеграции
(бот, кабинет) принимают по ней решения — выдавать ли триал и промокод, — и
цена ошибки здесь несимметричная: лишний отказ бьёт по честному клиенту, а
лишнее «чист» просто оставляет всё как было. Поэтому аннулированные нарушения
не считаются, а белый список перебивает всё.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from web.backend.core.config import get_web_settings
from web.backend.main import create_app

VALID_KEY = {"id": 1, "name": "bot", "scopes": ["violations:read"]}
WRONG_SCOPE_KEY = {"id": 2, "name": "limited", "scopes": ["users:read"]}


@pytest.fixture()
def v3_app(monkeypatch):
    monkeypatch.setenv("EXTERNAL_API_ENABLED", "true")
    get_web_settings.cache_clear()
    app = create_app()
    yield app
    app.dependency_overrides.clear()
    get_web_settings.cache_clear()


@pytest_asyncio.fixture()
async def v3_client(v3_app):
    transport = ASGITransport(app=v3_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class _Conn:
    def __init__(self, row: dict | None, whitelisted: bool, notice: dict | None = None):
        self.row = row
        self.whitelisted = whitelisted
        self.notice = notice

    async def fetchrow(self, sql, *args, **kwargs):
        # Запросов два: сводка по нарушениям и последнее предупреждение.
        if "violation_notices" in sql:
            return self.notice
        return self.row

    async def fetchval(self, *args, **kwargs):
        return 1 if self.whitelisted else None


def _db(row: dict | None, whitelisted: bool = False, notice: dict | None = None):
    class _Acquire:
        async def __aenter__(self):
            return _Conn(row, whitelisted, notice)

        async def __aexit__(self, *exc):
            return False

    class _DB:
        is_connected = True

        def acquire(self):
            return _Acquire()

    return _DB()


def _row(**extra) -> dict:
    row = {
        "violations": 2,
        "max_score": 74.0,
        "last_detected_at": datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc),
        "user_uuid": "11111111-2222-3333-4444-555555555555",
        "telegram_id": 366945364,
        "last_action": None,
    }
    row.update(extra)
    return row


@pytest.mark.asyncio
async def test_requires_api_key(v3_client):
    resp = await v3_client.get("/api/v3/violations/summary?telegram_id=1")
    assert resp.status_code == 401


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=WRONG_SCOPE_KEY)
async def test_requires_violations_scope(_key, v3_client):
    resp = await v3_client.get(
        "/api/v3/violations/summary?telegram_id=1", headers={"X-API-Key": "rwa_test"}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
async def test_identifier_is_required(_key, v3_client):
    resp = await v3_client.get("/api/v3/violations/summary", headers={"X-API-Key": "rwa_test"})
    assert resp.status_code == 422


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
async def test_seen_but_not_punished_is_warned(_key, v3_client, monkeypatch):
    monkeypatch.setattr("shared.database.db_service", _db(_row()))

    resp = await v3_client.get(
        "/api/v3/violations/summary?telegram_id=366945364", headers={"X-API-Key": "rwa_test"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["level"] == "warned"
    assert body["violations"] == 2
    assert body["max_score"] == 74.0
    assert body["whitelisted"] is False


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
async def test_blocked_user_is_limited(_key, v3_client, monkeypatch):
    monkeypatch.setattr("shared.database.db_service", _db(_row(last_action="hard_block")))

    resp = await v3_client.get(
        "/api/v3/violations/summary?telegram_id=366945364", headers={"X-API-Key": "rwa_test"}
    )

    assert resp.json()["level"] == "limited"


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
async def test_clean_user_without_violations(_key, v3_client, monkeypatch):
    monkeypatch.setattr(
        "shared.database.db_service",
        _db(_row(violations=0, max_score=None, last_detected_at=None, user_uuid=None, telegram_id=None)),
    )

    resp = await v3_client.get(
        "/api/v3/violations/summary?telegram_id=366945364", headers={"X-API-Key": "rwa_test"}
    )

    body = resp.json()
    assert body["level"] == "clean"
    assert body["violations"] == 0
    assert body["telegram_id"] == 366945364, "id возвращаем даже когда нарушений нет"


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
async def test_whitelist_overrides_everything(_key, v3_client, monkeypatch):
    # Белый список ставят руками, зная про нарушения: интеграция не должна
    # наказывать того, кого оператор уже оправдал.
    monkeypatch.setattr(
        "shared.database.db_service", _db(_row(last_action="hard_block"), whitelisted=True)
    )

    resp = await v3_client.get(
        "/api/v3/violations/summary?telegram_id=366945364", headers={"X-API-Key": "rwa_test"}
    )

    body = resp.json()
    assert body["level"] == "clean"
    assert body["whitelisted"] is True
    assert body["violations"] == 0


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
async def test_summary_carries_the_warning_customer_got(_key, v3_client, monkeypatch):
    """Кабинет рисует плашку по тексту, который человек реально получил."""
    notice = {
        "violation_id": 5,
        "kind": "device",
        "subject": "Устройства на подписке",
        "body": "Текст, который ушёл клиенту",
        "sent_at": datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
    }
    monkeypatch.setattr("shared.database.db_service", _db(_row(), notice=notice))

    resp = await v3_client.get(
        "/api/v3/violations/summary?telegram_id=366945364", headers={"X-API-Key": "rwa_test"}
    )

    body = resp.json()
    assert body["notice"]["body"] == "Текст, который ушёл клиенту"
    assert body["notice"]["violation_id"] == 5


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
async def test_warning_reaches_cabinet_without_telegram_markup(_key, v3_client, monkeypatch):
    """Кабинет показывает текст как есть — теги Telegram ему не нужны, адрес ссылки — нужен."""
    notice = {
        "violation_id": 5,
        "kind": "device",
        "subject": "Устройства на подписке",
        "body": '<b>Внимание</b>: см. <a href="https://stijoin.com/rules">правила</a> &amp; FAQ',
        "sent_at": None,
    }
    monkeypatch.setattr("shared.database.db_service", _db(_row(), notice=notice))

    resp = await v3_client.get(
        "/api/v3/violations/summary?telegram_id=366945364", headers={"X-API-Key": "rwa_test"}
    )

    assert resp.json()["notice"]["body"] == "Внимание: см. правила (https://stijoin.com/rules) & FAQ"


@pytest.mark.asyncio
@patch("web.backend.core.api_key_auth.validate_api_key", new_callable=AsyncMock, return_value=VALID_KEY)
async def test_whitelisted_customer_sees_no_warning(_key, v3_client, monkeypatch):
    """Оправданному оператором человеку плашку не показываем."""
    notice = {"violation_id": 5, "kind": "device", "subject": "s", "body": "b", "sent_at": None}
    monkeypatch.setattr("shared.database.db_service", _db(_row(), whitelisted=True, notice=notice))

    resp = await v3_client.get(
        "/api/v3/violations/summary?telegram_id=366945364", headers={"X-API-Key": "rwa_test"}
    )

    assert resp.json()["notice"] is None

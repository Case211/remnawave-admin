"""Лента активности клиента переживает бота без этой ручки.

Ручка `/users/{id}/activity` появилась в боте недавно (BEDOLAGA-DEV#3266). На
старой версии бот отвечает 404, и раздел должен просто исчезнуть из карточки —
без ошибки на весь экран. Отличать это от «пользователь не найден» приходится по
телу ответа: путь, которого нет, FastAPI отдаёт с detail «Not Found», а наша
ручка — «User not found».
"""
import httpx
import pytest

from web.backend.api.v2.bedolaga import customers


def _response(status_code: int, payload) -> httpx.Response:
    request = httpx.Request("GET", "http://bot/users/1/activity")
    return httpx.Response(status_code, json=payload, request=request)


def _raise(response: httpx.Response):
    async def _call(*args, **kwargs):
        raise httpx.HTTPStatusError("boom", request=response.request, response=response)

    return _call


@pytest.fixture(autouse=True)
def _reset_support(monkeypatch):
    customers._activity_support.update({"supported": True, "checked_at": 0.0})
    monkeypatch.setattr(customers, "ensure_configured", lambda: None)


@pytest.mark.asyncio
async def test_activity_returns_timeline(monkeypatch):
    payload = {
        "items": [{"type": "transaction", "timestamp": "2026-09-20T09:04:00Z", "amount_kopeks": 45000}],
        "total": 1,
        "limit": 50,
        "offset": 0,
    }

    async def fake_get(user_id, limit=50, offset=0, types=None):
        assert (user_id, limit, offset, types) == (7, 50, 0, None)
        return payload

    monkeypatch.setattr(customers.bedolaga_client, "get_user_activity", fake_get)

    result = await customers.user_activity(user_id=7, limit=50, offset=0, types=None, admin=None)

    assert result["available"] is True
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_missing_endpoint_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(
        customers.bedolaga_client, "get_user_activity", _raise(_response(404, {"detail": "Not Found"}))
    )

    result = await customers.user_activity(user_id=7, limit=50, offset=0, types=None, admin=None)

    assert result == {"items": [], "total": 0, "limit": 50, "offset": 0, "available": False}
    assert customers._activity_support["supported"] is False


@pytest.mark.asyncio
async def test_unsupported_flag_stops_further_calls(monkeypatch):
    calls = []

    async def counting(*args, **kwargs):
        calls.append(1)
        raise httpx.HTTPStatusError(
            "boom",
            request=_response(404, {"detail": "Not Found"}).request,
            response=_response(404, {"detail": "Not Found"}),
        )

    monkeypatch.setattr(customers.bedolaga_client, "get_user_activity", counting)

    first = await customers.user_activity(user_id=7, limit=50, offset=0, types=None, admin=None)
    second = await customers.user_activity(user_id=7, limit=50, offset=0, types=None, admin=None)

    assert first["available"] is False and second["available"] is False
    # второй раз бота не трогаем — флаг кэширован
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_missing_user_is_a_real_404(monkeypatch):
    monkeypatch.setattr(
        customers.bedolaga_client, "get_user_activity", _raise(_response(404, {"detail": "User not found"}))
    )

    with pytest.raises(customers.HTTPException) as exc:
        await customers.user_activity(user_id=7, limit=50, offset=0, types=None, admin=None)

    assert exc.value.status_code == 404
    # фича доступна — виноват пользователь, а не версия бота
    assert customers._activity_support["supported"] is True


@pytest.mark.asyncio
async def test_connection_error_becomes_502(monkeypatch):
    async def fail(*args, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(customers.bedolaga_client, "get_user_activity", fail)

    with pytest.raises(customers.HTTPException) as exc:
        await customers.user_activity(user_id=7, limit=50, offset=0, types=None, admin=None)

    assert exc.value.status_code == 502
    assert customers._activity_support["supported"] is True

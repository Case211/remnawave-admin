import pytest

from shared.bedolaga_client import BedolagaClient


@pytest.mark.asyncio
async def test_get_user_by_email_paginates_and_matches_exactly(monkeypatch):
    client = BedolagaClient()
    pages = {
        0: {"items": [{"id": 1, "email": "other@example.com"}], "total": 2},
        1: {"items": [{"id": 2, "email": "Person@Example.com"}], "total": 2},
    }

    async def fake_list_users(limit, offset):
        assert limit == 1
        return pages[offset]

    monkeypatch.setattr(client, "list_users", fake_list_users)

    assert await client.get_user_by_email(" person@example.com ", page_size=1) == pages[1]["items"][0]


@pytest.mark.asyncio
async def test_get_user_by_email_returns_none_after_last_page(monkeypatch):
    client = BedolagaClient()

    async def fake_list_users(limit, offset):
        return {"items": [{"id": 1, "email": "other@example.com"}], "total": 1}

    monkeypatch.setattr(client, "list_users", fake_list_users)

    assert await client.get_user_by_email("missing@example.com") is None


@pytest.mark.asyncio
async def test_get_user_by_email_stops_after_max_pages(monkeypatch):
    """Бот, не учитывающий offset, отдаёт одну и ту же полную страницу — перебор не должен крутиться вечно."""
    client = BedolagaClient()
    calls = []

    async def fake_list_users(limit, offset):
        calls.append(offset)
        return {"items": [{"id": i, "email": f"u{i}@example.com"} for i in range(limit)]}

    monkeypatch.setattr(client, "list_users", fake_list_users)

    assert await client.get_user_by_email("missing@example.com", page_size=2, max_pages=3) is None
    assert len(calls) == 3

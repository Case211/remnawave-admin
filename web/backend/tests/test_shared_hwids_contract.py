"""Контракт выдачи общих HWID: одиночный и батчевый методы обязаны совпадать.

В проекте две независимые реализации одного и того же запроса:

  * ``get_shared_hwids_for_user`` (shared/db/network.py) — одиночная проверка;
  * ``batch_get_shared_hwids`` (shared/db/violations.py) — горячий путь,
    через него идут коллектор и HWID-скан (``check_users_batch``).

HwidCrossAccountAnalyzer читает из выдачи ``email`` (группировка подписок
одного человека без Telegram), ``is_trial`` и ``is_active`` (отсечка апгрейда
«пробная → платная» от абуза параллельных триалов). Если поля появились
только в одном методе, в проде анализатор молча работает вслепую: нарушение
не создаётся и это никак не проявляется в логах.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from shared.database import db_service


FUTURE = datetime.now(timezone.utc) + timedelta(days=10)
PAST = datetime.now(timezone.utc) - timedelta(days=10)

SELF_UUID = "11111111-1111-1111-1111-111111111111"
OTHER_UUID = "22222222-2222-2222-2222-222222222222"


def _row(**overrides):
    """Строка, покрывающая поля обоих SQL-запросов сразу."""
    row = {
        "source_uuid": SELF_UUID,
        "hwid": "HW1",
        "user_uuid": OTHER_UUID,
        "username": "other",
        "status": "ACTIVE",
        "telegram_id": None,
        "email": "shared@example.com",
        "tag": "TRIAL",
        "expire_at": FUTURE,
        "raw_data": None,
        "self_telegram_id": None,
        "self_email": "Shared@Example.com",
        "self_status": "ACTIVE",
        "self_tag": "TRIAL",
        "self_expire_at": FUTURE,
        "self_raw_data": None,
    }
    row.update(overrides)
    return row


def _patch_db(rows):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=rows)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return (
        patch.object(type(db_service), "is_connected", PropertyMock(return_value=True)),
        patch.object(db_service, "acquire", MagicMock(return_value=cm)),
    )


async def _both_methods(rows):
    p1, p2 = _patch_db(rows)
    with p1, p2:
        single = await db_service.get_shared_hwids_for_user(SELF_UUID)
        batch = await db_service.batch_get_shared_hwids([SELF_UUID])
    return single[0], batch[SELF_UUID][0]


@pytest.mark.asyncio
async def test_group_keys_match_between_methods():
    single_group, batch_group = await _both_methods([_row()])
    assert set(single_group) == set(batch_group)
    assert set(single_group["other_users"][0]) == set(batch_group["other_users"][0])


@pytest.mark.asyncio
async def test_both_methods_expose_analyzer_fields():
    """Поля, без которых анализатор не отличит абуз от легального мультитарифа."""
    single_group, batch_group = await _both_methods([_row()])
    for group in (single_group, batch_group):
        assert group["self_email"] == "Shared@Example.com"
        assert group["self_is_trial"] is True
        assert group["self_is_active"] is True
        other = group["other_users"][0]
        assert other["email"] == "shared@example.com"
        assert other["is_trial"] is True
        assert other["is_active"] is True


@pytest.mark.asyncio
async def test_expired_and_disabled_are_not_active_in_both():
    """Истёкшая и отключённая подписки живыми не считаются — иначе апгрейд
    «пробная → платная» выглядел бы как два параллельных триала."""
    rows = [_row(expire_at=PAST), _row(user_uuid=OTHER_UUID, status="DISABLED")]
    single_group, batch_group = await _both_methods(rows)
    for group in (single_group, batch_group):
        assert all(u["is_active"] is False for u in group["other_users"])

"""Tests for the shared counter helpers under the corrected model.

Counter model (corrected):
  traffic_used_bytes = sum of (limit + used) of all quota events to date.

- Create user with limit L: +L (or 0 if L is None / 0 / unlimited)
- User uses X traffic: not tracked (no counter change)
- Reset user (used was U): +U (the consumed U is now on the admin's tab)
- Edit user (L1 → L2, used < L2): ±(L2 - L1) — signed delta
- Delete user (L, U): -(L - U) = -unused. Consumed U stays on the tab.

These tests pin the contract between the bot/web-backend callers and
`increment_usage_counter`. The DB-level safety floor is exercised in
web/backend/tests/test_admins_api.py::TestCounterFloorAtZero.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("BOT_TOKEN", "123456:TEST-FAKE-TOKEN")
os.environ.setdefault("API_BASE_URL", "http://localhost:3000")
os.environ.setdefault("INTERNAL_API_SECRET", "test-secret-123")


def _record_calls(calls):
    """Return an async stub that captures (admin_id, counter, amount) calls."""
    async def stub(admin_id, counter_name, amount=1):
        calls.append((admin_id, counter_name, amount))
        return True
    return stub


def _patched_inc(calls):
    """Patch `increment_usage_counter` at its import site in shared.admin_quota."""
    return patch("shared.admin_quota.increment_usage_counter", new=_record_calls(calls))


# ── Reset: +used_bytes ───────────────────────────────────────────


def test_reset_adds_used_bytes_to_counter():
    """Resetting a user with U used adds +U to the counter."""
    used_bytes = 50 * 1073741824
    calls = []
    with _patched_inc(calls):
        from shared.admin_quota import apply_user_reset_traffic_quotas
        import asyncio
        asyncio.run(apply_user_reset_traffic_quotas(creator_admin_id=1, used_traffic_bytes=used_bytes))
    assert (1, "traffic_used_bytes", used_bytes) in calls, \
        f"Expected +{used_bytes}, got: {calls}"


# ── Edit: signed delta ───────────────────────────────────────────


def test_edit_increase_adds_delta():
    """Editing L1→L2 where L2>L1 passes +delta."""
    delta = 50 * 1073741824
    calls = []
    with _patched_inc(calls):
        from shared.admin_quota import apply_user_limit_edit_quotas
        import asyncio
        asyncio.run(apply_user_limit_edit_quotas(creator_admin_id=1, traffic_delta_bytes=delta))
    assert (1, "traffic_used_bytes", delta) in calls, \
        f"Expected +{delta}, got: {calls}"


def test_edit_decrease_subtracts_delta():
    """Editing L1→L2 where L2<L1 passes a NEGATIVE delta (not zero, not skipped)."""
    delta = -50 * 1073741824
    calls = []
    with _patched_inc(calls):
        from shared.admin_quota import apply_user_limit_edit_quotas
        import asyncio
        asyncio.run(apply_user_limit_edit_quotas(creator_admin_id=1, traffic_delta_bytes=delta))
    assert (1, "traffic_used_bytes", delta) in calls, \
        f"Expected {delta}, got: {calls}"


# ── Delete: -unused per user, aggregated per owner ──────────────


def test_bulk_delete_subtracts_unused_per_user():
    """For 2 users (100GB/30GB, 50GB/0), delete math is: admin 1 -70GB, admin 2 -50GB."""
    calls = []
    users_data = [
        (1, 100 * 1073741824, 30 * 1073741824),  # admin 1, unused=70GB
        (2, 50 * 1073741824, 0),                  # admin 2, unused=50GB
    ]
    with _patched_inc(calls):
        from shared.admin_quota import apply_users_delete_quotas_batch
        import asyncio
        asyncio.run(apply_users_delete_quotas_batch(users_data))
    recorded = {(c[0], c[2]) for c in calls if c[1] == "traffic_used_bytes"}
    assert (1, -70 * 1073741824) in recorded, f"Expected admin 1: -70GB, got: {recorded}"
    assert (2, -50 * 1073741824) in recorded, f"Expected admin 2: -50GB, got: {recorded}"


# ── users_created: удаление слот не возвращает ──────────────────


def test_single_delete_does_not_touch_users_created():
    """Удаление не трогает счётчик созданных.

    Здесь стоял +1: удаление не просто не освобождало слот, а съедало
    ещё один, и админ с лимитом выбирал квоту вдвое быстрее.
    """
    calls = []
    with _patched_inc(calls):
        from shared.admin_quota import apply_user_delete_quotas
        import asyncio
        asyncio.run(apply_user_delete_quotas(1, 100 * 1073741824, 30 * 1073741824))
    assert [c for c in calls if c[1] == "users_created"] == []
    assert (1, "traffic_used_bytes", -70 * 1073741824) in calls


def test_bulk_delete_does_not_touch_users_created():
    calls = []
    users_data = [
        (1, 100 * 1073741824, 30 * 1073741824),
        (1, 50 * 1073741824, 0),
    ]
    with _patched_inc(calls):
        from shared.admin_quota import apply_users_delete_quotas_batch
        import asyncio
        asyncio.run(apply_users_delete_quotas_batch(users_data))
    assert [c for c in calls if c[1] == "users_created"] == []
    # оба юзера одного владельца — освобождённый трафик суммируется
    assert (1, "traffic_used_bytes", -120 * 1073741824) in calls


def test_reassign_still_moves_users_created():
    """Переназначение — другой случай: юзер жив, слот переезжает."""
    calls = []
    with _patched_inc(calls):
        from shared.admin_quota import apply_user_reassign_quotas
        import asyncio
        asyncio.run(apply_user_reassign_quotas(1, 2, 10 * 1073741824, 0))
    moved = {(c[0], c[2]) for c in calls if c[1] == "users_created"}
    assert (1, -1) in moved, f"прежний владелец должен освободить слот: {moved}"
    assert (2, 1) in moved, f"новый владелец должен занять слот: {moved}"

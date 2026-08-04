"""Admin quota counter updates — shared between bot and web backend.

Centralizes the logic for incrementing/decrementing admin usage counters
(users_created, traffic_used_bytes, nodes_created, hosts_created) so
bot and web backend do not duplicate this logic.

Counter model:
- users_created / nodes_created / hosts_created: lifetime change
  counters. Incremented on every create AND on every delete (a tick
  per "change"). The number only ever grows. Useful for tracking
  activity, not for hard limits.
- traffic_used_bytes: the total traffic the admin is responsible for.
  Equals `sum of (limit + used)` across all quota events to date.
  Conceptually: the admin is "charged" for the limits they've
  allocated AND for the traffic their users have consumed. The
  consumed portion is irrecoverable — only the unused portion is
  returned to the admin on delete or on limit-decrease edits.
    * Create user with limit L: +L
    * Reset user traffic (used was U): +U. The U is now on the admin's
      tab because the user got a do-over on their fresh quota.
    * Edit user from L1 to L2 (used < L2): -(L1 - L2). Only the
      decrease is returned. The consumed traffic up to L1 stays on
      the tab.
    * Delete user (limit L, used U): -unused where unused = max(0, L - U).
      The consumed U is NOT returned — it stays on the tab forever.
    * Reassign (with previous owner): old -unused, new +unused
    * Reassign (no previous owner): new +full_limit

All counter updates go through increment_usage_counter (from shared.rbac),
which floors the result at 0 to prevent the negative-value bug from
inconsistent create/edit tracking.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from shared.db_schema import USERS_TABLE
from shared.db_query import select_sql
from shared.database import db_service
from shared.rbac import increment_usage_counter

logger = logging.getLogger(__name__)


# ── User data extraction helpers ─────────────────────────────────

def _extract_user_admin_data(user: Dict[str, Any]) -> Tuple[Optional[int], int, int, int]:
    """Extract (creator_admin_id, traffic_limit_bytes, used_traffic_bytes) from user data.

    Accepts both Panel API response format (top-level fields) and
    snake_case DB format.
    """
    if not user:
        return None, 0, 0, 0
    info = user.get("response", user)
    creator = (
        info.get("createdByAdminId")
        or info.get("created_by_admin_id")
    )
    limit = (
        info.get("trafficLimitBytes")
        or info.get("traffic_limit_bytes")
        or 0
    )
    used = (
        info.get("usedTrafficBytes")
        or info.get("used_traffic_bytes")
        or 0
    )
    return creator, int(limit), int(used), 0  # last value reserved for future use


async def fetch_user_quota_data(user_uuid: str) -> Tuple[Optional[int], int, int]:
    """Fetch (creator_admin_id, traffic_limit_bytes, used_traffic_bytes) from local DB.

    Returns (None, 0, 0) if user not found or DB unavailable.
    """
    if not db_service.is_connected:
        return None, 0, 0
    try:
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(
                    USERS_TABLE,
                    "created_by_admin_id, traffic_limit_bytes, used_traffic_bytes",
                    "WHERE uuid = $1",
                ),
                user_uuid,
            )
            if not row:
                return None, 0, 0
            return (
                row.get("created_by_admin_id"),
                int(row.get("traffic_limit_bytes") or 0),
                int(row.get("used_traffic_bytes") or 0),
            )
    except Exception as e:
        logger.warning("fetch_user_quota_data failed for %s: %s", user_uuid, e)
        return None, 0, 0


async def fetch_users_quota_data_batch(
    user_uuids: List[str],
) -> List[Tuple[Optional[int], int, int]]:
    """Fetch quota data for multiple users in a single query.

    Returns list of (creator_admin_id, traffic_limit_bytes, used_traffic_bytes) in the
    same order as input. Missing users have (None, 0, 0).
    """
    if not user_uuids:
        return []
    if not db_service.is_connected:
        return [(None, 0, 0) for _ in user_uuids]
    try:
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    USERS_TABLE,
                    "uuid::text, created_by_admin_id, traffic_limit_bytes, used_traffic_bytes",
                    "WHERE uuid = ANY($1::uuid[])",
                ),
                user_uuids,
            )
        by_uuid = {
            r["uuid"]: (
                r.get("created_by_admin_id"),
                int(r.get("traffic_limit_bytes") or 0),
                int(r.get("used_traffic_bytes") or 0),
            )
            for r in rows
        }
        return [by_uuid.get(u, (None, 0, 0)) for u in user_uuids]
    except Exception as e:
        logger.warning("fetch_users_quota_data_batch failed: %s", e)
        return [(None, 0, 0) for _ in user_uuids]


# ── User counter update helpers ─────────────────────────────────

async def apply_user_delete_quotas(
    creator_admin_id: Optional[int],
    traffic_limit_bytes: int,
    used_traffic_bytes: int,
) -> None:
    """Apply quota counter changes for a single user deletion.

    - users_created: не меняется. Счётчик считает созданные аккаунты за
      всё время, поэтому удаление не возвращает слот. Раньше здесь стоял
      +1 — удаление не просто не освобождало слот, а съедало ещё один, и
      админ с лимитом выбирал квоту вдвое быстрее.
    - traffic_used_bytes: -unused (free up the user's unused traffic)

    Переназначение владельца — другой случай: там юзер жив и у прежнего
    владельца слот действительно освобождается (apply_user_reassign_quotas).

    If creator_admin_id is None, no counter changes are applied.
    """
    if creator_admin_id is None:
        return
    try:
        unused = max(0, traffic_limit_bytes - used_traffic_bytes)
        if unused > 0:
            await increment_usage_counter(creator_admin_id, "traffic_used_bytes", -unused)
    except Exception as e:
        logger.warning("apply_user_delete_quotas failed: %s", e)


async def apply_users_delete_quotas_batch(
    users_data: List[Tuple[Optional[int], int, int]],
) -> None:
    """Apply quota counter changes for a batch of user deletions.

    Each tuple: (creator_admin_id, traffic_limit_bytes, used_traffic_bytes).
    Aggregates per creator admin and updates in one call each.

    users_created не трогаем — см. apply_user_delete_quotas.
    """
    if not users_data:
        return
    # Aggregate per creator admin
    per_admin: Dict[int, int] = {}
    for creator_id, limit, used in users_data:
        if creator_id is None:
            continue
        unused = max(0, limit - used)
        if unused > 0:
            per_admin[creator_id] = per_admin.get(creator_id, 0) + unused
    try:
        for admin_id, unused_total in per_admin.items():
            if unused_total > 0:
                await increment_usage_counter(admin_id, "traffic_used_bytes", -unused_total)
    except Exception as e:
        logger.warning("apply_users_delete_quotas_batch failed: %s", e)


async def apply_user_reassign_quotas(
    previous_admin_id: Optional[int],
    new_admin_id: int,
    traffic_limit_bytes: int,
    used_traffic_bytes: int,
) -> None:
    """Apply quota counter changes for a user reassignment.

    Cases:
    - Had previous owner: previous loses the user (users_created -1, traffic -unused),
      new gains the user (users_created +1, traffic +unused).
    - No previous owner: new gains the user (users_created +1, traffic +full_limit).
    """
    if previous_admin_id == new_admin_id:
        return
    unused = max(0, traffic_limit_bytes - used_traffic_bytes)
    try:
        if previous_admin_id is not None:
            await increment_usage_counter(previous_admin_id, "users_created", -1)
            if unused > 0:
                await increment_usage_counter(previous_admin_id, "traffic_used_bytes", -unused)
        # New owner always gains the user (+1 users_created)
        await increment_usage_counter(new_admin_id, "users_created", 1)
        if previous_admin_id is None:
            # No previous owner: take the FULL traffic limit (regardless of used amount)
            if traffic_limit_bytes > 0:
                await increment_usage_counter(new_admin_id, "traffic_used_bytes", traffic_limit_bytes)
        else:
            # Had previous owner: transfer the unused amount
            if unused > 0:
                await increment_usage_counter(new_admin_id, "traffic_used_bytes", unused)
    except Exception as e:
        logger.warning("apply_user_reassign_quotas failed: %s", e)


async def apply_users_reassign_quotas_batch(
    users_data: List[Tuple[Optional[int], int, int]],
    new_admin_id: int,
) -> None:
    """Apply quota counter changes for a batch of user reassignments.

    Each tuple: (previous_admin_id, traffic_limit_bytes, used_traffic_bytes).
    Aggregates per admin:
    - Previous owners lose their users' users_created and unused traffic.
    - New admin gains users_created (count of all reassigned).
    - New admin gains unused traffic for users with previous owner.
    - New admin gains FULL traffic limit for users with no previous owner.
    """
    if not users_data:
        return
    # Aggregate per previous admin
    per_previous: Dict[int, Dict[str, int]] = {}
    total_new_count = 0
    total_new_unused_from_transfer = 0
    total_new_full_from_no_owner = 0
    for prev_id, limit, used in users_data:
        if prev_id is None or prev_id == new_admin_id:
            continue
        bucket = per_previous.setdefault(prev_id, {"count": 0, "unused": 0})
        bucket["count"] += 1
        unused = max(0, limit - used)
        if unused > 0:
            bucket["unused"] += unused
    for prev_id, limit, used in users_data:
        if prev_id == new_admin_id:
            continue
        total_new_count += 1
        if prev_id is None:
            if limit > 0:
                total_new_full_from_no_owner += limit
        else:
            unused = max(0, limit - used)
            if unused > 0:
                total_new_unused_from_transfer += unused
    try:
        for admin_id, bucket in per_previous.items():
            if bucket["count"] > 0:
                await increment_usage_counter(admin_id, "users_created", -bucket["count"])
            if bucket["unused"] > 0:
                await increment_usage_counter(admin_id, "traffic_used_bytes", -bucket["unused"])
        if total_new_count > 0:
            await increment_usage_counter(new_admin_id, "users_created", total_new_count)
        if total_new_unused_from_transfer > 0:
            await increment_usage_counter(new_admin_id, "traffic_used_bytes", total_new_unused_from_transfer)
        if total_new_full_from_no_owner > 0:
            await increment_usage_counter(new_admin_id, "traffic_used_bytes", total_new_full_from_no_owner)
    except Exception as e:
        logger.warning("apply_users_reassign_quotas_batch failed: %s", e)


async def apply_user_reset_traffic_quotas(
    creator_admin_id: Optional[int],
    used_traffic_bytes: int,
) -> None:
    """Apply quota counter change for a user traffic reset.

    - traffic_used_bytes: +used_bytes

    `used_traffic_bytes` MUST be the amount the user had used
    immediately before the reset (i.e. a non-negative integer).

    Counter model — `traffic_used_bytes` = sum of (limit + used) of all
    quota events to date, conceptually "the total traffic the admin is
    responsible for":

    - Create user with limit L: the (L, 0) event adds L to the counter.
    - User uses X traffic: we don't update the counter at use time (we
      don't know about it), but the consumed X is implicitly part of
      the limit value L.
    - Reset user (used was U): the (0, U) event is recorded. The user
      now has fresh quota, but the U they had consumed stays on the
      admin's tab — it can't be recovered even by deleting the user.
      This is why reset adds U to the counter.
    - Edit user from L1 to L2 (used < L2): only the decrease
      (L1 - L2) is returned. The consumed traffic up to L1 is still
      on the admin's tab.
    - Delete user (limit L, used U): the unused L - U is returned.
      The consumed U is NOT returned — it stays on the admin's tab
      forever (in this counter model, the admin is "charged" for any
      traffic the user ever consumed).

    For limit edits use `apply_user_limit_edit_quotas` instead — calling
    this helper with a signed delta (which the old bot code did)
    silently does nothing for negative values and over-counts for
    positive values.
    """
    if creator_admin_id is None or used_traffic_bytes <= 0:
        return
    try:
        await increment_usage_counter(creator_admin_id, "traffic_used_bytes", used_traffic_bytes)
    except Exception as e:
        logger.warning("apply_user_reset_traffic_quotas failed: %s", e)


async def apply_user_limit_edit_quotas(
    creator_admin_id: Optional[int],
    traffic_delta_bytes: int,
) -> None:
    """Apply quota counter change for a user limit edit (not a reset).

    The counter tracks the user's currently-allocated quota. Editing the
    limit by ±delta should apply the same delta to the counter so the
    counter stays in sync with the user's actual allocation.

    Unlike `apply_user_reset_traffic_quotas`, this helper accepts a SIGNED
    delta (negative = limit decreased, positive = limit increased) and
    never silently drops a value.
    """
    if creator_admin_id is None or traffic_delta_bytes == 0:
        return
    try:
        await increment_usage_counter(creator_admin_id, "traffic_used_bytes", traffic_delta_bytes)
    except Exception as e:
        logger.warning("apply_user_limit_edit_quotas failed: %s", e)


async def apply_users_reset_traffic_quotas_batch(
    users_data: List[Tuple[Optional[int], int, int]],
) -> None:
    """Apply quota counter changes for a batch of user traffic resets.

    Each tuple: (creator_admin_id, traffic_limit_bytes, used_traffic_bytes).
    Aggregates used_traffic_bytes per creator admin.
    """
    if not users_data:
        return
    per_creator: Dict[int, int] = {}
    for creator_id, _limit, used in users_data:
        if creator_id is None or used <= 0:
            continue
        per_creator[creator_id] = per_creator.get(creator_id, 0) + used
    try:
        for creator_id, total_used in per_creator.items():
            await increment_usage_counter(creator_id, "traffic_used_bytes", total_used)
    except Exception as e:
        logger.warning("apply_users_reset_traffic_quotas_batch failed: %s", e)

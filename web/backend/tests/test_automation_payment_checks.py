"""#308: меру по нарушению не применяют к клиенту, который уже платит.

Сценарий «абуз триала → предупредить → через 12 ч заблокировать»: если за это
время клиент оплатил или у него уже есть платная подписка, мера пропускается
с понятной причиной в журнале. Галочки по умолчанию выключены — старые правила
ведут себя как раньше.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from pydantic import ValidationError

from web.backend.core import automation
from web.backend.core.automation_engine import AutomationEngine, _payment_reason
from web.backend.schemas.automation import AutomationRuleCreate

SINCE = datetime(2026, 10, 3, 20, 0, tzinfo=timezone.utc)


def _checks(paid=None, paid_subscription=False):
    return (
        patch("web.backend.core.automation.paid_since", AsyncMock(return_value=paid)),
        patch("web.backend.core.automation.person_has_paid_subscription",
              AsyncMock(return_value=paid_subscription)),
    )


class TestPaymentReason:
    @pytest.mark.asyncio
    async def test_flags_off_touch_nothing(self):
        paid, person = _checks(paid=True, paid_subscription=True)
        with paid as paid_mock, person as person_mock:
            assert await _payment_reason("block_user", "u-1", {}, since=SINCE) is None
        paid_mock.assert_not_awaited()
        person_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_paid_subscription_spares_client(self):
        paid, person = _checks(paid_subscription=True)
        with paid, person:
            assert await _payment_reason("warn_user", "u-1", {"unless_paid": True}) == "active_paid_subscription"

    @pytest.mark.asyncio
    async def test_trial_client_is_not_spared(self):
        paid, person = _checks(paid_subscription=False)
        with paid, person:
            assert await _payment_reason("block_user", "u-1", {"unless_paid": True}) is None

    @pytest.mark.asyncio
    async def test_payment_after_trigger_from_bedolaga(self):
        paid, person = _checks(paid=True)
        with paid as paid_mock, person:
            reason = await _payment_reason("block_user", "u-1", {"unless_paid_after": True},
                                           since=SINCE, telegram_id=42)
        assert reason == "payment_received"
        paid_mock.assert_awaited_once_with(42, SINCE)

    @pytest.mark.asyncio
    async def test_bedolaga_says_no_payment(self):
        """Ответ «не платил» окончательный: статус подписки без второй галочки не спрашиваем."""
        paid, person = _checks(paid=False, paid_subscription=True)
        with paid, person as person_mock:
            assert await _payment_reason("block_user", "u-1", {"unless_paid_after": True}, since=SINCE) is None
        person_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_without_bedolaga_falls_back_to_subscription(self):
        paid, person = _checks(paid=None, paid_subscription=True)
        with paid, person:
            reason = await _payment_reason("throttle_user", "u-1", {"unless_paid_after": True}, since=SINCE)
        assert reason == "active_paid_subscription"

    @pytest.mark.asyncio
    async def test_paid_after_is_not_asked_at_trigger_time(self):
        paid, person = _checks(paid=True, paid_subscription=True)
        with paid as paid_mock, person:
            assert await _payment_reason("warn_user", "u-1", {"unless_paid_after": True}) is None
        paid_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_other_actions_ignore_flags(self):
        paid, person = _checks(paid_subscription=True)
        with paid, person:
            assert await _payment_reason("notify", "u-1", {"unless_paid": True}) is None


class TestChain:
    @pytest.mark.asyncio
    async def test_skipped_warning_holds_sanction_with_payment_reason(self, monkeypatch):
        """Предупреждение не нужно — клиент платит; отложенная мера не ставится,
        и в журнале это «платит», а не «предупреждение не доставлено»."""
        engine = AutomationEngine()
        single = AsyncMock(return_value=("success", {}))
        monkeypatch.setattr(engine, "_execute_single", single)
        rule = {"id": 7, "name": "Триалы", "action_type": "warn_user", "action_config": {"unless_paid": True},
                "extra_actions": [{"action_type": "block_user", "action_config": {}, "delay_hours": 12}]}
        schedule = AsyncMock(return_value=True)
        paid, person = _checks(paid_subscription=True)
        with paid, person, patch("web.backend.core.automation.schedule_pending_action", schedule):
            result, details = await engine._execute_action(rule, "user", "u-1", {"violation_id": 5})

        assert result == "skipped" and details["reason"] == "active_paid_subscription"
        assert details["then"] == [{"action": "block_user", "result": "skipped",
                                    "details": {"reason": "active_paid_subscription"}}]
        single.assert_not_awaited()
        schedule.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_check_is_an_error_not_a_silent_sanction(self, monkeypatch):
        engine = AutomationEngine()
        single = AsyncMock(return_value=("success", {}))
        monkeypatch.setattr(engine, "_execute_single", single)
        rule = {"id": 7, "action_type": "block_user", "action_config": {"unless_paid": True}}
        with patch("web.backend.core.automation.person_has_paid_subscription",
                   AsyncMock(side_effect=RuntimeError("db down"))):
            result, details = await engine._execute_action(rule, "user", "u-1", {})
        assert result == "error" and "db down" in details["error"]
        single.assert_not_awaited()


class _Conn:
    async def fetchrow(self, sql, *args):
        return {"user_uuid": "u-1", "telegram_id": 42, "action_taken": None}

    async def fetchval(self, sql, *args):
        return None if "user_throttles" in sql else "ACTIVE"


def _db():
    class _Acquire:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *exc):
            return False

    return SimpleNamespace(acquire=_Acquire, is_user_violation_whitelisted=AsyncMock(return_value=(False, None)))


class TestDelayedStep:
    @pytest.mark.asyncio
    async def test_payment_since_trigger_cancels_the_step(self):
        payload = {"unless_support": False, "started_at": SINCE.isoformat(),
                   "action_config": {"unless_paid_after": True}}
        paid, person = _checks(paid=True)
        with patch("shared.database.db_service", _db()), paid as paid_mock, person:
            reason = await AutomationEngine()._step_blocker("block_user", "u-1", payload, {"violation_id": 5})
        assert reason == "payment_received"
        paid_mock.assert_awaited_once_with(42, SINCE)

    @pytest.mark.asyncio
    async def test_step_without_flags_runs(self):
        payload = {"unless_support": False, "started_at": SINCE.isoformat(), "action_config": {}}
        with patch("shared.database.db_service", _db()):
            assert await AutomationEngine()._step_blocker("block_user", "u-1", payload, {"violation_id": 5}) is None


class _Bedolaga:
    is_configured = True

    def __init__(self, customer=None, transactions=None, error=None):
        self.customer = customer
        self.transactions = transactions or []
        self.error = error
        self.list_transactions = AsyncMock(side_effect=self._list)

    async def get_user_by_telegram(self, telegram_id):
        if self.error:
            raise self.error
        if self.customer is None:
            request = httpx.Request("GET", f"http://b/users/by-telegram-id/{telegram_id}")
            raise httpx.HTTPStatusError("404", request=request, response=httpx.Response(404, request=request))
        return self.customer

    async def _list(self, **kwargs):
        return {"items": self.transactions}


class TestPaidSince:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        client = _Bedolaga()
        client.is_configured = False
        with patch("shared.bedolaga_client.bedolaga_client", client):
            assert await automation.paid_since(42, SINCE) is None

    @pytest.mark.asyncio
    async def test_no_telegram_id(self):
        with patch("shared.bedolaga_client.bedolaga_client", _Bedolaga()):
            assert await automation.paid_since(None, SINCE) is None

    @pytest.mark.asyncio
    async def test_unknown_customer_did_not_pay(self):
        with patch("shared.bedolaga_client.bedolaga_client", _Bedolaga(customer=None)):
            assert await automation.paid_since(42, SINCE) is False

    @pytest.mark.asyncio
    async def test_admin_grant_refund_and_bonus_are_not_payments(self):
        client = _Bedolaga(customer={"id": 9}, transactions=[
            {"type": "subscription_payment", "amount_kopeks": 0},
            {"type": "refund", "amount_kopeks": 19900},
            {"type": "referral_reward", "amount_kopeks": 5000},
        ])
        with patch("shared.bedolaga_client.bedolaga_client", client):
            assert await automation.paid_since(42, SINCE) is False

    @pytest.mark.asyncio
    async def test_deposit_is_a_payment(self):
        client = _Bedolaga(customer={"id": 9}, transactions=[{"type": "deposit", "amount_kopeks": 19900}])
        with patch("shared.bedolaga_client.bedolaga_client", client):
            assert await automation.paid_since(42, SINCE) is True
        assert client.list_transactions.await_args.kwargs == {
            "limit": 50, "user_id": 9, "is_completed": True, "date_from": SINCE.isoformat(),
        }

    @pytest.mark.asyncio
    async def test_api_failure_means_unknown(self):
        with patch("shared.bedolaga_client.bedolaga_client", _Bedolaga(error=httpx.ConnectError("down"))):
            assert await automation.paid_since(42, SINCE) is None


def _users_db(me, rows):
    conn = MagicMock(fetchrow=AsyncMock(return_value=me), fetch=AsyncMock(return_value=rows))

    class _Acquire:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *exc):
            return False

    return SimpleNamespace(acquire=_Acquire), conn


def _row(tag, days=30, status="ACTIVE"):
    from datetime import timedelta
    return {"tag": tag, "raw_data": None, "status": status,
            "expire_at": datetime.now(timezone.utc) + timedelta(days=days)}


class TestPersonHasPaidSubscription:
    @staticmethod
    async def _run(me, rows):
        db, conn = _users_db(me, rows)
        with patch("shared.database.db_service", db), \
                patch("shared.db.network._load_trial_settings", return_value=(["trial"], [])):
            return await automation.person_has_paid_subscription("u-1"), conn

    @pytest.mark.asyncio
    async def test_paid_sibling_account_counts(self):
        result, conn = await self._run({"telegram_id": 42, "email": None}, [_row("trial"), _row("VIP")])
        assert result is True
        assert conn.fetch.await_args.args[1:] == ("u-1", 42, None)

    @pytest.mark.asyncio
    async def test_only_trials_are_not_paid(self):
        result, _ = await self._run({"telegram_id": 42, "email": None}, [_row("trial"), _row("TRIAL")])
        assert result is False

    @pytest.mark.asyncio
    async def test_expired_or_disabled_paid_does_not_count(self):
        rows = [_row("VIP", days=-1), _row("VIP", status="DISABLED")]
        result, _ = await self._run({"telegram_id": None, "email": "a@b.c"}, rows)
        assert result is False

    @pytest.mark.asyncio
    async def test_unknown_user(self):
        result, _ = await self._run(None, [])
        assert result is None


class TestSchema:
    BASE = {"name": "Триалы", "category": "violations", "trigger_type": "event",
            "trigger_config": {"event": "violation.detected"}}

    def test_payment_flags_on_sanctions(self):
        rule = AutomationRuleCreate(**{
            **self.BASE, "action_type": "warn_user", "action_config": {"unless_paid": True},
            "extra_actions": [{"action_type": "block_user", "delay_hours": 12,
                               "action_config": {"unless_paid": True, "unless_paid_after": True}}],
        })
        assert rule.extra_actions[0].action_config["unless_paid_after"] is True

    def test_payment_flags_rejected_elsewhere(self):
        with pytest.raises(ValidationError):
            AutomationRuleCreate(**{**self.BASE, "action_type": "notify",
                                    "action_config": {"unless_paid": True}})

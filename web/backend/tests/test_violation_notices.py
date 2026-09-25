"""Предупреждение клиенту: какой текст, кому и когда.

Сообщение уходит живому человеку от имени сервиса и не отзывается, поэтому
сторожим три вещи: правильный ли шаблон выбран, не написали ли дважды об одном
и том же, и не ушло ли предупреждение тому, кого предупреждать не за что.
"""
import pytest

from web.backend.core import violation_notices as notices


# ── Какой текст ──


def test_kind_follows_dominant_analyzer():
    """Сработал HWID — и текст про устройства, а не общий про раздачу доступа."""
    violation = {
        "raw_breakdown": '{"breakdown": {"hwid": {"score": 80}, "geo": {"score": 10}}}',
        "reasons": [],
    }

    assert notices.violation_kind(violation) == "hwid"


def test_kind_falls_back_to_default():
    violation = {"raw_breakdown": None, "reasons": ["что-то непонятное"]}

    assert notices.violation_kind(violation) == "default"


def test_torrents_are_recognised_by_reason():
    # Торрент-события живут мимо анализаторов, у них нет своего скоринга.
    violation = {"raw_breakdown": None, "reasons": ["Торрент-трафик на ноде Germany"]}

    assert notices.violation_kind(violation) == "torrent"


# ── Когда ──


class _Conn:
    def __init__(self, templates: dict, notified: bool = False):
        self.templates = templates
        self.notified = notified
        self.executed: list[str] = []

    async def fetchrow(self, sql, *args):
        if "violation_notice_templates" in sql:
            return self.templates.get(args[0] if args else "default")
        return None

    async def fetchval(self, sql, *args):
        return 1 if self.notified else None

    async def execute(self, sql, *args):
        self.executed.append(sql)
        return "INSERT 1"


def _db(conn):
    class _Acquire:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *exc):
            return False

    class _DB:
        is_connected = True

        def acquire(self):
            return _Acquire()

    return _DB()


def _template(**extra) -> dict:
    row = {
        "kind": "device",
        "enabled": True,
        "min_score": 55.0,
        "send_email": True,
        "subject_ru": "Устройства на подписке",
        "body_ru": "Текст предупреждения",
    }
    row.update(extra)
    return row


@pytest.mark.asyncio
async def test_threshold_holds_back_auto_send(monkeypatch):
    """Порог сдерживает автоматику: слабое срабатывание клиента не тревожит."""
    monkeypatch.setattr("shared.database.db_service", _db(_Conn({"device": _template()})))

    assert await notices.pick_template("device", score=20.0, respect_threshold=True) is None


@pytest.mark.asyncio
async def test_button_ignores_threshold(monkeypatch):
    """Нажатие «Предупредить» — уже решение человека, спорить с ним не надо."""
    monkeypatch.setattr("shared.database.db_service", _db(_Conn({"device": _template()})))

    template = await notices.pick_template("device", score=20.0)

    assert template is not None, "ручная отправка порогом не ограничивается"


@pytest.mark.asyncio
async def test_disabled_kind_falls_back_to_default(monkeypatch):
    conn = _Conn({
        "device": _template(enabled=False),
        "default": _template(kind="default", min_score=0, body_ru="Общий текст"),
    })
    monkeypatch.setattr("shared.database.db_service", _db(conn))

    template = await notices.pick_template("device", score=90.0, respect_threshold=True)

    assert template is not None
    assert template["kind"] == "default"


@pytest.mark.asyncio
async def test_empty_text_means_silence(monkeypatch):
    # Пустой шаблон — это «не писать», а не «отправить пустоту».
    conn = _Conn({"device": _template(body_ru="   "), "default": _template(kind="default", body_ru="")})
    monkeypatch.setattr("shared.database.db_service", _db(conn))

    assert await notices.pick_template("device", score=90.0) is None


# ── Кому ──


@pytest.mark.asyncio
async def test_no_recipient_no_notice(monkeypatch):
    """Без Telegram и почты адресата нет, и это не ошибка доставки."""
    result = await notices.send_notice({"id": 1, "telegram_id": None, "email": None})

    assert result == {"sent": False, "reason": "no_recipient"}


@pytest.mark.asyncio
async def test_email_only_notice_is_delivered_and_recorded(monkeypatch):
    conn = _Conn({"default": _template(kind="default", min_score=0, send_email=False)})
    monkeypatch.setattr("shared.database.db_service", _db(conn))
    monkeypatch.setattr("web.backend.api.v2.bedolaga.ensure_configured", lambda: None)

    async def fake_user(email):
        assert email == "person@example.com"
        return {"id": 7, "telegram_id": None, "email": email}

    async def fake_notify(user_id, **kwargs):
        assert user_id == 7
        assert kwargs["channels"] == ["email"]
        return {"telegram": {"sent": False}, "email": {"sent": True}}

    monkeypatch.setattr("shared.bedolaga_client.bedolaga_client.get_user_by_email", fake_user)
    monkeypatch.setattr("shared.bedolaga_client.bedolaga_client.notify_user", fake_notify)

    result = await notices.send_notice({
        "id": 1,
        "telegram_id": None,
        "email": "person@example.com",
        "user_uuid": "11111111-2222-3333-4444-555555555555",
        "score": 90,
    })

    assert result["sent"] is True
    assert result["email"]["sent"] is True
    assert any("violation_notices" in sql for sql in conn.executed)


@pytest.mark.asyncio
async def test_second_notice_needs_force(monkeypatch):
    conn = _Conn({}, notified=True)
    monkeypatch.setattr("shared.database.db_service", _db(conn))

    result = await notices.send_notice({"id": 1, "telegram_id": 42})

    assert result["reason"] == "already_notified"


@pytest.mark.asyncio
async def test_notice_goes_out_and_is_recorded(monkeypatch):
    conn = _Conn({"default": _template(kind="default", min_score=0)})
    monkeypatch.setattr("shared.database.db_service", _db(conn))
    monkeypatch.setattr("web.backend.api.v2.bedolaga.ensure_configured", lambda: None)

    async def fake_user(telegram_id):
        return {"id": 7, "telegram_id": telegram_id}

    async def fake_notify(user_id, **kwargs):
        fake_notify.seen = kwargs
        return {"telegram": {"sent": True}, "email": {"sent": False, "reason": "no_email"}}

    monkeypatch.setattr("shared.bedolaga_client.bedolaga_client.get_user_by_telegram", fake_user)
    monkeypatch.setattr("shared.bedolaga_client.bedolaga_client.notify_user", fake_notify)

    result = await notices.send_notice(
        {"id": 1, "telegram_id": 42, "user_uuid": "11111111-2222-3333-4444-555555555555", "score": 90},
        sent_by="operator",
    )

    assert result["sent"] is True
    assert result["telegram"]["sent"] is True
    assert "Текст предупреждения" in fake_notify.seen["text"]
    assert any("violation_notices" in sql for sql in conn.executed), "отметку об отправке надо хранить"


@pytest.mark.asyncio
async def test_failed_delivery_leaves_no_mark(monkeypatch):
    """Не дошло — отметки нет, оператор сможет отправить снова без force."""
    conn = _Conn({"default": _template(kind="default", min_score=0)})
    monkeypatch.setattr("shared.database.db_service", _db(conn))
    monkeypatch.setattr("web.backend.api.v2.bedolaga.ensure_configured", lambda: None)

    async def fake_user(telegram_id):
        return {"id": 7}

    async def fake_notify(user_id, **kwargs):
        return {"telegram": {"sent": False, "reason": "blocked_by_user"},
                "email": {"sent": False, "reason": "no_email"}}

    monkeypatch.setattr("shared.bedolaga_client.bedolaga_client.get_user_by_telegram", fake_user)
    monkeypatch.setattr("shared.bedolaga_client.bedolaga_client.notify_user", fake_notify)

    result = await notices.send_notice(
        {"id": 1, "telegram_id": 42, "user_uuid": "11111111-2222-3333-4444-555555555555", "score": 90}
    )

    assert result["sent"] is False
    assert not any("violation_notices" in sql for sql in conn.executed)

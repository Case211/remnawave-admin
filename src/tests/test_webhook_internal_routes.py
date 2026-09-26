"""Колбэки бэкенда (/internal/*) доходят до своих ручек.

run_webhook_server() подключает роутер bot_callbacks к приложению вебхука,
поэтому запросы бэкенда и коллектора проходят через его middleware
catch_invalid_requests. Здесь приложение собирается так же, как в проде:
ручки, вызванные напрямую (test_bot_callbacks.py), фильтр путей не видят.
"""
import sys
import types

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    # Как в test_webhook_torrent.py: пакет хендлеров тянет живой aiogram.
    if "src.handlers.state" not in sys.modules:
        stub = types.ModuleType("src.handlers.state")
        stub.BOT_CREATING_USERS = set()
        sys.modules["src.handlers.state"] = stub

    from src.services.bot_callbacks import app as callbacks_app
    from src.services.webhook import app as webhook_app

    if not any(getattr(r, "path", None) == "/internal/health" for r in webhook_app.routes):
        webhook_app.include_router(callbacks_app.router)
    return TestClient(webhook_app)


def test_internal_health_reaches_route(client):
    resp = client.get("/internal/health")
    assert resp.status_code == 200
    assert resp.json()["service"] == "bot-callbacks"


@pytest.mark.parametrize("path", ["/internal/telegram-send", "/internal/panel-event"])
def test_internal_callback_checks_secret_itself(client, monkeypatch, path):
    """Чужой секрет отбивает сама ручка (401), а не фильтр путей (404)."""
    monkeypatch.setenv("INTERNAL_API_SECRET", "test-secret")
    resp = client.post(path, json={}, headers={"X-Internal-Api-Secret": "wrong"})
    assert resp.status_code == 401


@pytest.mark.parametrize("path", ["/wp-login.php", "/internalx", "/api/internal/health"])
def test_unknown_paths_still_404(client, path):
    assert client.get(path).status_code == 404

"""Периодический синк переживает всё, кроме собственной остановки.

27.09.2026 проход встал во время сетевого сбоя у хостера, и цикл молча
вышел: синк не шёл 12 часов, пока его не запустили руками.
"""
import asyncio

import pytest

from shared import sync as sync_module
from shared.sync import SyncService


def _service(monkeypatch, full_sync):
    svc = SyncService()
    svc._running = True
    monkeypatch.setattr(SyncService, "_get_sync_interval", staticmethod(lambda: 0))
    monkeypatch.setattr(svc, "full_sync", full_sync)
    return svc


@pytest.mark.asyncio
async def test_cancellation_leaking_from_a_pass_does_not_stop_the_loop(monkeypatch):
    calls = 0

    async def full_sync():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise asyncio.CancelledError()  # так её роняет сетевой клиент на обрыве
        if calls == 3:
            svc._running = False
        return {}

    svc = _service(monkeypatch, full_sync)
    await asyncio.wait_for(svc._periodic_sync_loop(), timeout=5)
    assert calls == 3


@pytest.mark.asyncio
async def test_hung_pass_is_cancelled_by_timeout(monkeypatch):
    calls = 0

    async def full_sync():
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(3600)  # проход встал
        svc._running = False
        return {}

    svc = _service(monkeypatch, full_sync)
    monkeypatch.setattr(sync_module, "SYNC_PASS_TIMEOUT_SECONDS", 0.05)
    await asyncio.wait_for(svc._periodic_sync_loop(), timeout=5)
    assert calls == 2


@pytest.mark.asyncio
async def test_stop_still_stops_the_loop(monkeypatch):
    async def full_sync():
        await asyncio.sleep(3600)

    svc = _service(monkeypatch, full_sync)
    svc._sync_task = asyncio.create_task(svc._periodic_sync_loop())
    await asyncio.sleep(0.05)
    await asyncio.wait_for(svc.stop(), timeout=5)
    assert svc._sync_task is None


@pytest.mark.asyncio
async def test_cancelling_the_loop_task_itself_stops_it(monkeypatch):
    """Отмена задачи цикла (остановка приложения) — не «протёкшая», цикл выходит."""
    async def full_sync():
        await asyncio.sleep(3600)

    svc = _service(monkeypatch, full_sync)
    task = asyncio.create_task(svc._periodic_sync_loop())
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.wait({task}, timeout=5)
    assert task.done()

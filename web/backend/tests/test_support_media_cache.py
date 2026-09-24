"""Кэш вложений: помогает, пока свежий, и не растёт бесконечно.

Файлы живут в Telegram, у нас они лежат временно — чтобы не ходить к боту при
каждом открытии переписки. Поэтому уборка обязана быть честной: просроченное
удаляется, переполнение срезается с самых давних, а потеря кэша ничем не
грозит — старый тикет просто скачает вложение заново.
"""
import os
import time

import pytest

from web.backend.core import support_media_cache as cache


@pytest.fixture(autouse=True)
def _cache_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPPORT_MEDIA_CACHE_DIR", str(tmp_path / "media"))
    monkeypatch.setattr(cache, "is_enabled", lambda: True)
    monkeypatch.setattr(cache, "ttl_days", lambda: 14)
    monkeypatch.setattr(cache, "limit_bytes", lambda: 0)
    return tmp_path


def _age(key: str, days: float) -> None:
    path = cache._path_for(key)
    old = time.time() - days * 24 * 60 * 60
    os.utime(path, (old, old))


def test_written_file_is_read_back():
    cache.write("AgACphoto", b"picture-bytes")
    assert cache.read("AgACphoto") == b"picture-bytes"


def test_missing_key_is_a_miss():
    assert cache.read("nothing-here") is None


def test_disabled_cache_never_stores(monkeypatch):
    monkeypatch.setattr(cache, "is_enabled", lambda: False)
    cache.write("AgACphoto", b"picture-bytes")
    assert cache.read("AgACphoto") is None


def test_expired_file_is_removed():
    cache.write("old", b"x" * 10)
    cache.write("fresh", b"y" * 10)
    _age("old", 20)

    result = cache.cleanup()

    assert result["removed"] == 1
    assert cache.read("old") is None
    assert cache.read("fresh") == b"y" * 10


def test_reading_keeps_file_alive():
    """Открыли старый тикет — файл снова считается нужным."""
    cache.write("touched", b"z" * 10)
    _age("touched", 20)

    assert cache.read("touched") == b"z" * 10
    assert cache.cleanup()["removed"] == 0


def test_oversized_cache_drops_oldest(monkeypatch):
    monkeypatch.setattr(cache, "limit_bytes", lambda: 30)
    cache.write("a", b"1" * 20)
    cache.write("b", b"2" * 20)
    cache.write("c", b"3" * 20)
    _age("a", 3)
    _age("b", 2)
    _age("c", 1)

    result = cache.cleanup()

    assert result["removed"] == 2
    assert cache.read("a") is None and cache.read("b") is None
    assert cache.read("c") == b"3" * 20


def test_empty_write_is_ignored():
    cache.write("empty", b"")
    assert cache.read("empty") is None


def test_cleanup_on_empty_dir_is_harmless():
    assert cache.cleanup() == {"removed": 0, "freed_bytes": 0, "kept_bytes": 0}

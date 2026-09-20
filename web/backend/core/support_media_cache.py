"""Кэш вложений поддержки на диске.

Файлы живут в Telegram, и каждый показ переписки означал бы поход за ними к
боту: у активного тикета на десяток скриншотов это десяток запросов при каждом
открытии. Поэтому скачанное кладём рядом с собой.

Кэш намеренно устроен как временный: файлы старше срока (по умолчанию две
недели) уборщик удаляет, и открытый после этого старый тикет просто скачает их
заново. Потерять здесь нечего — источник правды всегда в Telegram.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 6 * 60 * 60
DEFAULT_TTL_DAYS = 14
DEFAULT_LIMIT_MB = 2048


def cache_dir() -> Path:
    return Path(os.environ.get("SUPPORT_MEDIA_CACHE_DIR", "/app/data/support-media"))


def ttl_days() -> int:
    from shared.config_service import config_service

    try:
        return max(1, int(config_service.get("support_media_cache_days", DEFAULT_TTL_DAYS) or DEFAULT_TTL_DAYS))
    except (TypeError, ValueError):
        return DEFAULT_TTL_DAYS


def limit_bytes() -> int:
    from shared.config_service import config_service

    try:
        limit_mb = int(config_service.get("support_media_cache_max_mb", DEFAULT_LIMIT_MB) or DEFAULT_LIMIT_MB)
    except (TypeError, ValueError):
        limit_mb = DEFAULT_LIMIT_MB
    return max(0, limit_mb) * 1024 * 1024


def is_enabled() -> bool:
    from shared.config_service import config_service

    return bool(config_service.get("support_media_cache_enabled", True))


def _path_for(key: str) -> Path:
    # file_id Telegram длинный и содержит символы, неудобные для файловой
    # системы, поэтому имя — его хеш.
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return cache_dir() / digest[:2] / digest


def read(key: str) -> bytes | None:
    """Содержимое из кэша или None. Битый файл кэшем не считается."""
    if not is_enabled():
        return None
    path = _path_for(key)
    try:
        if not path.exists():
            return None
        data = path.read_bytes()
    except OSError as exc:
        logger.debug("Support media: чтение кэша не удалось (%s): %s", key[:12], exc)
        return None

    if not data:
        return None
    # Файл перечитали — двигаем время, чтобы уборщик считал его живым.
    try:
        os.utime(path, None)
    except OSError:
        pass
    return data


def write(key: str, content: bytes) -> None:
    """Положить файл в кэш. Ошибка записи не должна ломать показ вложения."""
    if not is_enabled() or not content:
        return
    path = _path_for(key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Пишем через временный файл: параллельный запрос не должен прочитать
        # половину картинки.
        tmp = path.with_suffix(".part")
        tmp.write_bytes(content)
        tmp.replace(path)
    except OSError as exc:
        logger.warning("Support media: не удалось закэшировать %s: %s", key[:12], exc)


def _iter_files() -> list[tuple[Path, os.stat_result]]:
    root = cache_dir()
    if not root.exists():
        return []
    files: list[tuple[Path, os.stat_result]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            files.append((path, path.stat()))
        except OSError:
            continue
    return files


def cleanup() -> dict:
    """Удалить просроченное, а если кэш всё равно велик — самое старое."""
    if not is_enabled():
        return {"removed": 0, "freed_bytes": 0, "kept_bytes": 0}

    deadline = time.time() - ttl_days() * 24 * 60 * 60
    removed = 0
    freed = 0
    survivors: list[tuple[Path, os.stat_result]] = []

    for path, stat in _iter_files():
        if stat.st_mtime < deadline:
            try:
                path.unlink()
                removed += 1
                freed += stat.st_size
            except OSError:
                continue
        else:
            survivors.append((path, stat))

    limit = limit_bytes()
    total = sum(stat.st_size for _, stat in survivors)
    if limit and total > limit:
        # Переполнение чистим с самых давно не открывавшихся файлов.
        survivors.sort(key=lambda item: item[1].st_mtime)
        for path, stat in survivors:
            if total <= limit:
                break
            try:
                path.unlink()
            except OSError:
                continue
            removed += 1
            freed += stat.st_size
            total -= stat.st_size

    if removed:
        logger.info("Support media: удалено %s файлов, освобождено %.1f МБ", removed, freed / 1024 / 1024)
    return {"removed": removed, "freed_bytes": freed, "kept_bytes": total}


async def cleanup_loop() -> None:
    """Уборка раз в несколько часов; падение круга не убивает цикл."""
    while True:
        try:
            await asyncio.to_thread(cleanup)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Support media: уборка упала: %s", exc, exc_info=True)
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)

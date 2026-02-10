"""
Автоматическое скачивание и обновление баз MaxMind GeoLite2.

Требуется бесплатный лицензионный ключ с maxmind.com.
Базы обновляются каждый вторник, проверка раз в 24 часа.
"""
import asyncio
import gzip
import io
import os
import shutil
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from src.utils.logger import logger

# MaxMind download URL
DOWNLOAD_URL = "https://download.maxmind.com/app/geoip_download"

# Editions to download
EDITIONS = {
    "city": "GeoLite2-City",
    "asn": "GeoLite2-ASN",
}

# Check for updates every 24 hours
UPDATE_CHECK_INTERVAL = timedelta(hours=24)

# Consider DB stale after 8 days (MaxMind updates weekly on Tuesdays)
MAX_DB_AGE = timedelta(days=8)


async def download_database(
    license_key: str,
    edition_id: str,
    output_path: str,
) -> bool:
    """
    Скачивает .mmdb базу с MaxMind.

    Args:
        license_key: Лицензионный ключ MaxMind
        edition_id: ID издания (GeoLite2-City, GeoLite2-ASN)
        output_path: Путь для сохранения .mmdb файла

    Returns:
        True если успешно
    """
    params = {
        "edition_id": edition_id,
        "license_key": license_key,
        "suffix": "tar.gz",
    }

    try:
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            logger.info("Downloading %s from MaxMind...", edition_id)
            resp = await client.get(DOWNLOAD_URL, params=params)

            if resp.status_code == 401:
                logger.error("MaxMind: invalid license key (401)")
                return False
            if resp.status_code != 200:
                logger.error("MaxMind download failed: HTTP %d", resp.status_code)
                return False

            # Распаковываем tar.gz и находим .mmdb файл внутри
            data = resp.content
            mmdb_data = _extract_mmdb_from_targz(data, edition_id)

            if not mmdb_data:
                logger.error("Could not find .mmdb file in %s archive", edition_id)
                return False

            # Записываем файл атомарно (tmp → rename)
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = out.with_suffix(".mmdb.tmp")

            tmp_path.write_bytes(mmdb_data)
            tmp_path.replace(out)

            size_mb = len(mmdb_data) / (1024 * 1024)
            logger.info("Downloaded %s (%.1f MB) → %s", edition_id, size_mb, output_path)
            return True

    except httpx.HTTPError as e:
        logger.error("HTTP error downloading %s: %s", edition_id, e)
        return False
    except Exception as e:
        logger.error("Error downloading %s: %s", edition_id, e, exc_info=True)
        return False


def _extract_mmdb_from_targz(data: bytes, edition_id: str) -> Optional[bytes]:
    """Извлекает .mmdb файл из tar.gz архива MaxMind."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith(".mmdb"):
                    f = tar.extractfile(member)
                    if f:
                        return f.read()
    except Exception as e:
        logger.error("Error extracting %s archive: %s", edition_id, e)
    return None


def _db_needs_update(path: str) -> bool:
    """Проверяет, нужно ли обновить базу."""
    p = Path(path)
    if not p.exists():
        return True
    age = datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)
    return age > MAX_DB_AGE


async def ensure_databases(
    license_key: str,
    city_path: str,
    asn_path: Optional[str] = None,
    force: bool = False,
) -> dict[str, bool]:
    """
    Скачивает базы если они отсутствуют или устарели.

    Args:
        license_key: Лицензионный ключ MaxMind
        city_path: Путь для GeoLite2-City.mmdb
        asn_path: Путь для GeoLite2-ASN.mmdb (опционально)
        force: Принудительно скачать даже если базы свежие

    Returns:
        dict с результатами: {"city": True/False, "asn": True/False}
    """
    results = {}

    # City DB (обязательная)
    if force or _db_needs_update(city_path):
        results["city"] = await download_database(license_key, EDITIONS["city"], city_path)
    else:
        logger.debug("GeoLite2-City is up to date: %s", city_path)
        results["city"] = True

    # ASN DB (опциональная)
    if asn_path:
        if force or _db_needs_update(asn_path):
            results["asn"] = await download_database(license_key, EDITIONS["asn"], asn_path)
        else:
            logger.debug("GeoLite2-ASN is up to date: %s", asn_path)
            results["asn"] = True

    return results


class MaxMindUpdater:
    """Фоновый сервис для периодического обновления баз MaxMind."""

    def __init__(
        self,
        license_key: str,
        city_path: str,
        asn_path: Optional[str] = None,
        check_interval: timedelta = UPDATE_CHECK_INTERVAL,
    ):
        self.license_key = license_key
        self.city_path = city_path
        self.asn_path = asn_path
        self.check_interval = check_interval
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Запускает фоновое обновление."""
        if self.is_running:
            return
        self.is_running = True

        # Первая проверка сразу
        await ensure_databases(self.license_key, self.city_path, self.asn_path)

        # Запускаем периодическую проверку
        self._task = asyncio.create_task(self._run())
        logger.info("MaxMind updater started (check every %s)", self.check_interval)

    async def _run(self):
        """Периодическая проверка обновлений."""
        while self.is_running:
            await asyncio.sleep(self.check_interval.total_seconds())
            if not self.is_running:
                break
            try:
                await ensure_databases(self.license_key, self.city_path, self.asn_path)
            except Exception as e:
                logger.error("MaxMind update check failed: %s", e)

    def stop(self):
        """Останавливает фоновое обновление."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("MaxMind updater stopped")

"""
Автоматическое скачивание и обновление баз MaxMind GeoLite2.

Поддерживает два источника:
1. Официальный MaxMind (требуется лицензионный ключ с maxmind.com)
2. GitHub-зеркала GeoLite2 без ключа — по очереди, см. GITHUB_MIRRORS

Базы обновляются каждый вторник, проверка раз в 24 часа.
"""
import asyncio
import io
import os
import tarfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import httpx
from shared.logger import logger

# ── Download sources ─────────────────────────────────────────────

# Official MaxMind (requires license key)
MAXMIND_DOWNLOAD_URL = "https://download.maxmind.com/app/geoip_download"

# GitHub-зеркала GeoLite2 без ключа, пробуются по очереди. Раздавать GeoLite2
# лицензия MaxMind не разрешает, и зеркала смертны: ltsdev/maxmind удалили в
# октябре 2026, а зарегистрироваться в MaxMind из РФ или через VPN нельзя.
# Поэтому их несколько, а своё ставится вперёд переменной MAXMIND_MIRROR_URL.
# {edition} — GeoLite2-City / GeoLite2-ASN; адрес ведёт на .mmdb или .tar.gz.
GITHUB_MIRRORS = (
    "https://github.com/P3TERX/GeoLite.mmdb/releases/latest/download/{edition}.mmdb",
    "https://raw.githubusercontent.com/GitSquared/node-geolite2-redist/master/redist/{edition}.tar.gz",
)

# Метка секции метаданных MaxMind DB — в конце любой настоящей базы. Без неё
# зеркало отдало что-то другое (HTML-страницу с кодом 200), и сохранять нельзя.
MMDB_MARKER = b"\xab\xcd\xefMaxMind.com"
MMDB_METADATA_WINDOW = 128 * 1024


def mirror_urls() -> list:
    """Шаблоны зеркал по очереди: своё из MAXMIND_MIRROR_URL — первым."""
    custom = (os.environ.get("MAXMIND_MIRROR_URL") or "").strip()
    return ([custom] if custom else []) + list(GITHUB_MIRRORS)

# Editions
EDITIONS = {
    "city": "GeoLite2-City",
    "asn": "GeoLite2-ASN",
}

# Check for updates every 24 hours
UPDATE_CHECK_INTERVAL = timedelta(hours=24)

# Consider DB stale after 8 days (MaxMind updates weekly on Tuesdays)
MAX_DB_AGE = timedelta(days=8)


# ── Download functions ───────────────────────────────────────────

async def download_from_maxmind(
    license_key: str,
    edition_id: str,
    output_path: str,
) -> bool:
    """Скачивает .mmdb базу с официального MaxMind (требуется ключ)."""
    params = {
        "edition_id": edition_id,
        "license_key": license_key,
        "suffix": "tar.gz",
    }

    try:
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            logger.info("Downloading %s from MaxMind (official)...", edition_id)
            resp = await client.get(MAXMIND_DOWNLOAD_URL, params=params)

            if resp.status_code == 401:
                logger.error("MaxMind: invalid license key (401)")
                return False
            if resp.status_code != 200:
                logger.error("MaxMind download failed: HTTP %d", resp.status_code)
                return False

            return _save_mmdb_from_targz(resp.content, edition_id, output_path)

    except httpx.HTTPError as e:
        logger.error("HTTP error downloading %s from MaxMind: %s", edition_id, e)
        return False
    except Exception as e:
        logger.error("Error downloading %s from MaxMind: %s", edition_id, e, exc_info=True)
        return False


async def download_from_github(
    edition_key: str,
    output_path: str,
    mirrors: Optional[list] = None,
) -> bool:
    """Скачивает базу с GitHub-зеркал без ключа — по очереди, до первой удачи."""
    edition = EDITIONS.get(edition_key)
    if not edition:
        logger.error("Unknown edition key for GitHub download: %s", edition_key)
        return False

    for template in (mirror_urls() if mirrors is None else mirrors):
        if await _download_from_mirror(template.format(edition=edition), edition, output_path):
            return True
    logger.error("No GeoLite2 mirror served %s", edition)
    return False


async def _download_from_mirror(url: str, edition: str, output_path: str) -> bool:
    """Одно зеркало: .tar.gz распаковывается, .mmdb сохраняется как есть."""
    try:
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=30.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            logger.info("Downloading %s from %s", edition, url)
            resp = await client.get(url)
        if resp.status_code != 200:
            logger.warning("Mirror failed for %s: HTTP %d (%s)", edition, resp.status_code, url)
            return False
        if url.endswith((".tar.gz", ".tgz")):
            return _save_mmdb_from_targz(resp.content, edition, output_path)
        return _save_mmdb(resp.content, edition, output_path)
    except httpx.HTTPError as e:
        logger.warning("HTTP error downloading %s from %s: %s", edition, url, e)
        return False
    except Exception as e:
        logger.error("Error downloading %s from %s: %s", edition, url, e, exc_info=True)
        return False


# Legacy alias
async def download_database(license_key: str, edition_id: str, output_path: str) -> bool:
    """Скачивает .mmdb базу с MaxMind (обратная совместимость)."""
    return await download_from_maxmind(license_key, edition_id, output_path)


# ── Helpers ──────────────────────────────────────────────────────

def _save_mmdb_from_targz(data: bytes, edition_id: str, output_path: str) -> bool:
    """Извлекает .mmdb из tar.gz и сохраняет атомарно."""
    mmdb_data = _extract_mmdb_from_targz(data, edition_id)
    if not mmdb_data:
        logger.error("Could not find .mmdb file in %s archive", edition_id)
        return False
    return _save_mmdb(mmdb_data, edition_id, output_path)


def _save_mmdb(mmdb_data: bytes, edition_id: str, output_path: str) -> bool:
    """Сохраняет .mmdb атомарно — и только настоящую базу MaxMind DB."""
    if MMDB_MARKER not in mmdb_data[-MMDB_METADATA_WINDOW:]:
        logger.error("Downloaded %s is not a MaxMind DB (%d bytes)", edition_id, len(mmdb_data))
        return False

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out.with_suffix(".mmdb.tmp")

    tmp_path.write_bytes(mmdb_data)
    tmp_path.replace(out)

    size_mb = len(mmdb_data) / (1024 * 1024)
    logger.info("Downloaded %s (%.1f MB) → %s", edition_id, size_mb, output_path)
    return True


def _extract_mmdb_from_targz(data: bytes, edition_id: str) -> Optional[bytes]:
    """Извлекает .mmdb файл из tar.gz архива."""
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


def get_db_status(path: str) -> dict:
    """Возвращает информацию о состоянии базы данных."""
    p = Path(path)
    if not p.exists():
        return {"exists": False, "path": path}
    stat = p.stat()
    age = datetime.now() - datetime.fromtimestamp(stat.st_mtime)
    return {
        "exists": True,
        "path": path,
        "size_mb": round(stat.st_size / (1024 * 1024), 1),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "age_days": round(age.total_seconds() / 86400, 1),
        "needs_update": age > MAX_DB_AGE,
    }


# ── Main ensure function ────────────────────────────────────────

async def ensure_databases(
    license_key: Optional[str] = None,
    city_path: str = "/app/geoip/GeoLite2-City.mmdb",
    asn_path: Optional[str] = "/app/geoip/GeoLite2-ASN.mmdb",
    force: bool = False,
    source: str = "auto",
) -> dict[str, bool]:
    """
    Скачивает базы если они отсутствуют или устарели.

    Args:
        license_key: Лицензионный ключ MaxMind (опционально)
        city_path: Путь для GeoLite2-City.mmdb
        asn_path: Путь для GeoLite2-ASN.mmdb (опционально)
        force: Принудительно скачать
        source: Источник: "auto" (GitHub → MaxMind), "github", "maxmind"

    Returns:
        dict с результатами: {"city": True/False, "asn": True/False}
    """
    results = {}

    async def _download_edition(key: str, path: str) -> bool:
        """Download a single edition using the configured source."""
        if source == "maxmind" and license_key:
            return await download_from_maxmind(license_key, EDITIONS[key], path)
        elif source == "github":
            return await download_from_github(key, path)
        else:
            # Auto: try GitHub first (no key needed), fall back to MaxMind
            ok = await download_from_github(key, path)
            if not ok and license_key:
                logger.info("GitHub download failed, trying official MaxMind...")
                ok = await download_from_maxmind(license_key, EDITIONS[key], path)
            return ok

    # City DB
    if force or _db_needs_update(city_path):
        results["city"] = await _download_edition("city", city_path)
    else:
        logger.debug("GeoLite2-City is up to date: %s", city_path)
        results["city"] = True

    # ASN DB
    if asn_path:
        if force or _db_needs_update(asn_path):
            results["asn"] = await _download_edition("asn", asn_path)
        else:
            logger.debug("GeoLite2-ASN is up to date: %s", asn_path)
            results["asn"] = True

    return results


class MaxMindUpdater:
    """Фоновый сервис для периодического обновления баз MaxMind."""

    def __init__(
        self,
        license_key: Optional[str] = None,
        city_path: str = "/app/geoip/GeoLite2-City.mmdb",
        asn_path: Optional[str] = "/app/geoip/GeoLite2-ASN.mmdb",
        check_interval: timedelta = UPDATE_CHECK_INTERVAL,
        source: str = "auto",
    ):
        self.license_key = license_key
        self.city_path = city_path
        self.asn_path = asn_path
        self.check_interval = check_interval
        self.source = source
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Запускает фоновое обновление."""
        if self.is_running:
            return
        self.is_running = True

        # Первая проверка сразу
        await ensure_databases(
            self.license_key, self.city_path, self.asn_path, source=self.source,
        )

        # Запускаем периодическую проверку
        self._task = asyncio.create_task(self._run())
        logger.info(
            "MaxMind updater started (source=%s, check every %s)",
            self.source, self.check_interval,
        )

    async def _run(self):
        """Периодическая проверка обновлений."""
        while self.is_running:
            await asyncio.sleep(self.check_interval.total_seconds())
            if not self.is_running:
                break
            try:
                await ensure_databases(
                    self.license_key, self.city_path, self.asn_path,
                    source=self.source,
                )
            except Exception as e:
                logger.error("MaxMind update check failed: %s", e)

    def stop(self):
        """Останавливает фоновое обновление."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("MaxMind updater stopped")

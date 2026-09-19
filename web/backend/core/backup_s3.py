"""Выгрузка бэкапов в S3-совместимое хранилище.

Подпись AWS Signature Version 4 своя, как у Route 53 (`core/dns/route53.py`):
boto3 ради четырёх запросов в образ не тянем, а httpx в зависимостях уже есть.

Параметры подключения лежат в обычных настройках категории `backup`, ключи
доступа — отдельно в `backup_s3_creds`, зашифрованные Fernet (тот же приём, что
у DNS-провайдеров): в общий список настроек секрет не попадает и наружу не
отдаётся даже маской.

Совместимость: Amazon S3, MinIO, Selectel, Timeweb Cloud, Backblaze B2 и прочие
S3-совместимые. Для локальных MinIO и большинства российских провайдеров нужен
path-style (`https://endpoint/bucket/key`) — он и стоит по умолчанию.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote, urlsplit

import httpx

from web.backend.core.crypto import decrypt_field, encrypt_field

logger = logging.getLogger(__name__)

CREDS_KEY = "backup_s3_creds"
_SERVICE = "s3"
_CHUNK_BYTES = 1 << 20
_TIMEOUT = httpx.Timeout(connect=15.0, read=300.0, write=300.0, pool=15.0)


class S3Error(Exception):
    """Ошибка обращения к хранилищу с человекочитаемым текстом."""


@dataclass(frozen=True)
class S3Settings:
    endpoint: str
    bucket: str
    region: str
    prefix: str
    path_style: bool
    access_key: str
    secret_key: str
    auto_upload: bool
    keep_count: int

    @property
    def is_ready(self) -> bool:
        return bool(self.endpoint and self.bucket and self.access_key and self.secret_key)


# ── Настройки ────────────────────────────────────────────────────

def get_credentials() -> Tuple[str, str]:
    """Пара (access_key, secret_key); пустые строки — ключи не заведены."""
    from shared.config_service import config_service

    raw = config_service.get(CREDS_KEY, None)
    if not raw:
        return "", ""
    try:
        data = json.loads(decrypt_field(str(raw)))
    except Exception:  # noqa: BLE001 — битый шифртекст = хранилище не настроено
        logger.warning("S3: ключи доступа не расшифровались")
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    return str(data.get("access_key") or ""), str(data.get("secret_key") or "")


async def save_credentials(access_key: str, secret_key: str) -> None:
    """Сохранить ключи доступа в зашифрованном виде."""
    payload = encrypt_field(json.dumps({"access_key": access_key, "secret_key": secret_key}))
    await _write_creds(payload)


async def clear_credentials() -> None:
    await _write_creds("")


async def _write_creds(value: str) -> None:
    from shared.config_service import config_service

    if not await config_service.set(CREDS_KEY, value):
        raise S3Error("Не удалось сохранить ключи доступа")


def load_settings() -> S3Settings:
    from shared.config_service import config_service

    access_key, secret_key = get_credentials()
    prefix = str(config_service.get("backup_s3_prefix", "") or "").strip().strip("/")
    return S3Settings(
        endpoint=str(config_service.get("backup_s3_endpoint", "") or "").strip().rstrip("/"),
        bucket=str(config_service.get("backup_s3_bucket", "") or "").strip().strip("/"),
        region=str(config_service.get("backup_s3_region", "us-east-1") or "us-east-1").strip(),
        prefix=prefix,
        path_style=bool(config_service.get("backup_s3_path_style", True)),
        access_key=access_key,
        secret_key=secret_key,
        auto_upload=bool(config_service.get("backup_s3_auto_upload", False)),
        keep_count=int(config_service.get("backup_s3_keep_count", 0) or 0),
    )


def is_configured() -> bool:
    return load_settings().is_ready


def object_key(settings: S3Settings, filename: str) -> str:
    return f"{settings.prefix}/{filename}" if settings.prefix else filename


# ── SigV4 ────────────────────────────────────────────────────────

def _sign(
    settings: S3Settings,
    method: str,
    host: str,
    path: str,
    canonical_qs: str,
    payload_hash: str,
    now: Optional[datetime] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Заголовки запроса с подписью AWS Signature Version 4."""
    t = now or datetime.now(timezone.utc)
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")

    headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    for key, value in (extra_headers or {}).items():
        headers[key.lower()] = value

    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
    canonical_request = "\n".join([
        method.upper(), path, canonical_qs, canonical_headers, signed_headers, payload_hash,
    ])
    scope = f"{date_stamp}/{settings.region}/{_SERVICE}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    signing_key = _hmac(_hmac(_hmac(_hmac(("AWS4" + settings.secret_key).encode(), date_stamp),
                                    settings.region), _SERVICE), "aws4_request")
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()

    result = {
        "X-Amz-Date": amz_date,
        "X-Amz-Content-Sha256": payload_hash,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={settings.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }
    for key, value in (extra_headers or {}).items():
        result[key] = value
    return result


def _canonical_query(query: Optional[Dict[str, str]]) -> str:
    if not query:
        return ""
    return "&".join(
        f"{quote(k, safe='-_.~')}={quote(str(v), safe='-_.~')}" for k, v in sorted(query.items())
    )


def _target(settings: S3Settings, key: str = "") -> Tuple[str, str, str]:
    """(base_url, host, canonical_path) для запроса к бакету или объекту.

    Ключ объекта в canonical path кодируется как путь: слэши остаются
    разделителями, остальное экранируется — иначе подпись не сойдётся с тем,
    что провайдер посчитает на своей стороне.
    """
    if not settings.endpoint:
        raise S3Error("Не задан адрес хранилища (endpoint)")
    split = urlsplit(settings.endpoint if "//" in settings.endpoint else f"https://{settings.endpoint}")
    scheme = split.scheme or "https"
    host = split.netloc
    if not host:
        raise S3Error(f"Некорректный адрес хранилища: {settings.endpoint}")

    encoded_key = quote(key, safe="/-_.~") if key else ""
    if settings.path_style:
        path = f"/{settings.bucket}" + (f"/{encoded_key}" if encoded_key else "/")
        return f"{scheme}://{host}", host, path

    host = f"{settings.bucket}.{host}"
    path = f"/{encoded_key}" if encoded_key else "/"
    return f"{scheme}://{host}", host, path


def _explain_error(status: int, body: bytes) -> str:
    """Короткое объяснение ответа хранилища вместо голого XML."""
    code = ""
    message = ""
    try:
        root = ET.fromstring(body.decode("utf-8", "replace"))
        for child in root.iter():
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "Code" and child.text:
                code = child.text.strip()
            elif tag == "Message" and child.text:
                message = child.text.strip()
    except ET.ParseError:
        pass

    hints = {
        "SignatureDoesNotMatch": "не совпала подпись — проверьте секретный ключ и регион",
        "InvalidAccessKeyId": "хранилище не знает такой Access Key",
        "AccessDenied": "у ключа нет прав на этот бакет",
        "NoSuchBucket": "бакет не найден",
        "PermanentRedirect": "бакет живёт в другом регионе или нужен path-style",
    }
    hint = hints.get(code, "")
    parts = [p for p in (code, message, hint) if p]
    return f"HTTP {status}: " + (" — ".join(parts) if parts else body[:200].decode("utf-8", "replace"))


async def _send(
    settings: S3Settings,
    method: str,
    key: str = "",
    *,
    query: Optional[Dict[str, str]] = None,
    payload_hash: str = hashlib.sha256(b"").hexdigest(),
    content=None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> httpx.Response:
    base_url, host, path = _target(settings, key)
    canonical_qs = _canonical_query(query)
    headers = _sign(settings, method, host, path, canonical_qs, payload_hash,
                    extra_headers=extra_headers)

    url = f"{base_url}{path}" + (f"?{canonical_qs}" if canonical_qs else "")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.request(method, url, headers=headers, content=content)
    except httpx.HTTPError as exc:
        raise S3Error(f"Хранилище недоступно: {exc}") from exc

    if response.status_code >= 400:
        raise S3Error(_explain_error(response.status_code, response.content))
    return response


# ── Операции ─────────────────────────────────────────────────────

def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_chunks(path: Path) -> Iterator[bytes]:
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_CHUNK_BYTES)
            if not chunk:
                return
            yield chunk


async def test_connection(settings: Optional[S3Settings] = None) -> dict:
    """Листинг одного объекта — проверяет и доступ, и существование бакета."""
    settings = settings or load_settings()
    if not settings.is_ready:
        raise S3Error("Хранилище не настроено: нужны endpoint, бакет и ключи доступа")
    await _send(settings, "GET", query={"list-type": "2", "max-keys": "1"})
    return {"success": True, "bucket": settings.bucket, "endpoint": settings.endpoint}


async def upload_backup(filename: str, settings: Optional[S3Settings] = None) -> dict:
    """Залить готовый файл бэкапа из локального каталога в бакет."""
    from web.backend.core.backup_service import get_backup_filepath

    settings = settings or load_settings()
    if not settings.is_ready:
        raise S3Error("Хранилище не настроено: нужны endpoint, бакет и ключи доступа")

    filepath = get_backup_filepath(filename)
    if not filepath:
        raise S3Error(f"Файл не найден: {filename}")

    path = Path(filepath)
    size = path.stat().st_size
    key = object_key(settings, filename)
    # Content-Length задаём сами: с ним httpx не переключится на chunked,
    # которого S3 без отдельной схемы подписи не понимает, и файл уходит
    # потоком, не считываясь в память целиком.
    await _send(
        settings, "PUT", key,
        payload_hash=_file_sha256(path),
        content=_file_chunks(path),
        extra_headers={
            "Content-Length": str(size),
            "Content-Type": "application/octet-stream",
        },
    )
    logger.info("S3: бэкап %s выгружен (%s байт)", key, size)
    return {"success": True, "key": key, "size": size}


async def list_objects(settings: Optional[S3Settings] = None) -> List[dict]:
    """Объекты бакета под нашим префиксом, новые сверху."""
    settings = settings or load_settings()
    if not settings.is_ready:
        raise S3Error("Хранилище не настроено: нужны endpoint, бакет и ключи доступа")

    query = {"list-type": "2", "max-keys": "1000"}
    if settings.prefix:
        query["prefix"] = f"{settings.prefix}/"

    response = await _send(settings, "GET", query=query)
    items: List[dict] = []
    try:
        root = ET.fromstring(response.content.decode("utf-8", "replace"))
    except ET.ParseError as exc:
        raise S3Error(f"Хранилище вернуло неразборчивый ответ: {exc}") from exc

    for node in root.iter():
        if node.tag.rsplit("}", 1)[-1] != "Contents":
            continue
        entry: Dict[str, str] = {}
        for child in node:
            entry[child.tag.rsplit("}", 1)[-1]] = (child.text or "").strip()
        if not entry.get("Key"):
            continue
        items.append({
            "key": entry["Key"],
            "filename": entry["Key"].rsplit("/", 1)[-1],
            "size": int(entry.get("Size") or 0),
            "last_modified": entry.get("LastModified", ""),
        })

    items.sort(key=lambda item: item["last_modified"], reverse=True)
    return items


async def delete_object(key: str, settings: Optional[S3Settings] = None) -> dict:
    settings = settings or load_settings()
    if not settings.is_ready:
        raise S3Error("Хранилище не настроено: нужны endpoint, бакет и ключи доступа")
    await _send(settings, "DELETE", key)
    logger.info("S3: объект %s удалён", key)
    return {"success": True, "key": key}


async def rotate(settings: Optional[S3Settings] = None) -> int:
    """Оставить в бакете последние `backup_s3_keep_count` файлов. 0 — не чистить."""
    settings = settings or load_settings()
    if settings.keep_count <= 0:
        return 0

    items = await list_objects(settings)
    removed = 0
    for item in items[settings.keep_count:]:
        try:
            await delete_object(item["key"], settings)
            removed += 1
        except S3Error as exc:
            logger.warning("S3: не удалось удалить %s: %s", item["key"], exc)
    return removed


async def upload_if_enabled(filename: str) -> None:
    """Автовыгрузка после планового бэкапа: молча пропускаем, если выключена."""
    settings = load_settings()
    if not settings.auto_upload or not settings.is_ready:
        return
    try:
        await upload_backup(filename, settings)
        await rotate(settings)
    except S3Error as exc:
        logger.warning("S3: автовыгрузка %s не удалась: %s", filename, exc)
        from web.backend.core.backup_service import _notify_backup_failed

        await _notify_backup_failed(
            "Бэкап не ушёл в S3",
            f"Файл {filename} создан, но выгрузка в хранилище не удалась: {exc}",
            group_key="backup_s3_failed",
        )

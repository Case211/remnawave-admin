"""Тесты выгрузки бэкапов в S3-совместимое хранилище."""
import hashlib
from datetime import datetime, timezone

import httpx
import pytest

from web.backend.core import backup_s3
from web.backend.core.backup_s3 import S3Error, S3Settings


def _settings(**overrides) -> S3Settings:
    base = dict(
        endpoint="https://s3.example.com",
        bucket="backups",
        region="ru-1",
        prefix="admin",
        path_style=True,
        access_key="AKIAEXAMPLE0001",
        secret_key="secret-key-value",
        auto_upload=False,
        keep_count=0,
    )
    base.update(overrides)
    return S3Settings(**base)


# ── Адресация и ключи ───────────────────────────────────────────

def test_object_key_respects_prefix():
    assert backup_s3.object_key(_settings(), "dump.sql.gz") == "admin/dump.sql.gz"
    assert backup_s3.object_key(_settings(prefix=""), "dump.sql.gz") == "dump.sql.gz"


def test_target_path_style_keeps_bucket_in_path():
    base_url, host, path = backup_s3._target(_settings(), "admin/dump.sql.gz")
    assert base_url == "https://s3.example.com"
    assert host == "s3.example.com"
    assert path == "/backups/admin/dump.sql.gz"


def test_target_virtual_host_moves_bucket_into_host():
    base_url, host, path = backup_s3._target(_settings(path_style=False), "dump.sql.gz")
    assert base_url == "https://backups.s3.example.com"
    assert host == "backups.s3.example.com"
    assert path == "/dump.sql.gz"


def test_target_accepts_endpoint_without_scheme():
    _, host, _ = backup_s3._target(_settings(endpoint="s3.example.com"))
    assert host == "s3.example.com"


def test_target_rejects_empty_endpoint():
    with pytest.raises(S3Error):
        backup_s3._target(_settings(endpoint=""))


# ── Подпись ─────────────────────────────────────────────────────

def test_sign_is_deterministic_and_well_formed():
    now = datetime(2026, 9, 20, 12, 30, 0, tzinfo=timezone.utc)
    payload_hash = hashlib.sha256(b"").hexdigest()
    args = ("GET", "s3.example.com", "/backups/", "list-type=2", payload_hash)

    first = backup_s3._sign(_settings(), *args, now=now)
    second = backup_s3._sign(_settings(), *args, now=now)
    assert first == second

    assert first["X-Amz-Date"] == "20260920T123000Z"
    assert first["X-Amz-Content-Sha256"] == payload_hash
    auth = first["Authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKIAEXAMPLE0001/20260920/ru-1/s3/aws4_request")
    assert "SignedHeaders=host;x-amz-content-sha256;x-amz-date" in auth
    signature = auth.rsplit("Signature=", 1)[1]
    assert len(signature) == 64 and all(c in "0123456789abcdef" for c in signature)


def test_sign_changes_with_secret_key():
    now = datetime(2026, 9, 20, 12, 30, 0, tzinfo=timezone.utc)
    payload_hash = hashlib.sha256(b"").hexdigest()
    args = ("GET", "s3.example.com", "/backups/", "", payload_hash)

    one = backup_s3._sign(_settings(), *args, now=now)["Authorization"]
    two = backup_s3._sign(_settings(secret_key="another"), *args, now=now)["Authorization"]
    assert one != two


def test_sign_includes_extra_headers_in_signature():
    now = datetime(2026, 9, 20, 12, 30, 0, tzinfo=timezone.utc)
    payload_hash = hashlib.sha256(b"x").hexdigest()
    headers = backup_s3._sign(
        _settings(), "PUT", "s3.example.com", "/backups/a", "", payload_hash,
        now=now, extra_headers={"Content-Length": "1"},
    )
    assert headers["Content-Length"] == "1"
    assert "content-length" in headers["Authorization"]


# ── Ошибки хранилища ────────────────────────────────────────────

def test_explain_error_extracts_code_and_hint():
    body = (b"<?xml version='1.0'?><Error><Code>SignatureDoesNotMatch</Code>"
            b"<Message>The request signature we calculated does not match</Message></Error>")
    text = backup_s3._explain_error(403, body)
    assert "HTTP 403" in text
    assert "SignatureDoesNotMatch" in text
    assert "секретный ключ" in text


def test_explain_error_survives_non_xml_body():
    text = backup_s3._explain_error(500, b"gateway exploded")
    assert "HTTP 500" in text
    assert "gateway exploded" in text


# ── Загрузка файла ──────────────────────────────────────────────

class _FakeClient:
    """Подменяет httpx.AsyncClient и запоминает единственный запрос."""

    captured: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def request(self, method, url, headers=None, content=None):
        body = b""
        if content is not None:
            body = b"".join(content) if hasattr(content, "__iter__") and not isinstance(content, bytes) else content
        _FakeClient.captured = {
            "method": method, "url": url, "headers": dict(headers or {}), "body": body,
        }
        return httpx.Response(200, content=b"", request=httpx.Request(method, url))


@pytest.mark.asyncio
async def test_upload_streams_file_with_content_length(monkeypatch, tmp_path):
    payload = b"dump-content" * 1000
    backup_file = tmp_path / "backup_20260920.sql.gz"
    backup_file.write_bytes(payload)

    monkeypatch.setattr("web.backend.core.backup_service.get_backup_filepath",
                        lambda name: backup_file)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    result = await backup_s3.upload_backup("backup_20260920.sql.gz", _settings())

    assert result == {"success": True, "key": "admin/backup_20260920.sql.gz", "size": len(payload)}
    captured = _FakeClient.captured
    assert captured["method"] == "PUT"
    assert captured["url"] == "https://s3.example.com/backups/admin/backup_20260920.sql.gz"
    assert captured["headers"]["Content-Length"] == str(len(payload))
    assert captured["headers"]["X-Amz-Content-Sha256"] == hashlib.sha256(payload).hexdigest()
    assert captured["body"] == payload


@pytest.mark.asyncio
async def test_upload_rejects_unconfigured_storage():
    with pytest.raises(S3Error, match="не настроено"):
        await backup_s3.upload_backup("x.sql.gz", _settings(bucket=""))


@pytest.mark.asyncio
async def test_upload_reports_missing_file(monkeypatch):
    monkeypatch.setattr("web.backend.core.backup_service.get_backup_filepath", lambda name: None)
    with pytest.raises(S3Error, match="Файл не найден"):
        await backup_s3.upload_backup("ghost.sql.gz", _settings())


# ── Ротация ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rotate_deletes_only_surplus(monkeypatch):
    objects = [
        {"key": f"admin/b{i}.sql.gz", "filename": f"b{i}.sql.gz", "size": 1,
         "last_modified": f"2026-09-2{i}T00:00:00Z"}
        for i in range(5, 0, -1)
    ]
    deleted = []

    async def fake_list(settings=None):
        return objects

    async def fake_delete(key, settings=None):
        deleted.append(key)
        return {"success": True, "key": key}

    monkeypatch.setattr(backup_s3, "list_objects", fake_list)
    monkeypatch.setattr(backup_s3, "delete_object", fake_delete)

    removed = await backup_s3.rotate(_settings(keep_count=2))

    assert removed == 3
    assert deleted == ["admin/b3.sql.gz", "admin/b2.sql.gz", "admin/b1.sql.gz"]


@pytest.mark.asyncio
async def test_rotate_disabled_by_zero_keep_count(monkeypatch):
    async def fail(*args, **kwargs):
        raise AssertionError("хранилище не должно опрашиваться при keep_count=0")

    monkeypatch.setattr(backup_s3, "list_objects", fail)
    assert await backup_s3.rotate(_settings(keep_count=0)) == 0


# ── Автовыгрузка ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_if_enabled_skips_when_auto_upload_off(monkeypatch):
    monkeypatch.setattr(backup_s3, "load_settings", lambda: _settings(auto_upload=False))

    async def fail(*args, **kwargs):
        raise AssertionError("выгрузка не должна запускаться")

    monkeypatch.setattr(backup_s3, "upload_backup", fail)
    await backup_s3.upload_if_enabled("backup.sql.gz")


@pytest.mark.asyncio
async def test_upload_if_enabled_uploads_and_rotates(monkeypatch):
    calls = []
    monkeypatch.setattr(backup_s3, "load_settings",
                        lambda: _settings(auto_upload=True, keep_count=3))

    async def fake_upload(filename, settings=None):
        calls.append(("upload", filename))
        return {"success": True, "key": filename, "size": 1}

    async def fake_rotate(settings=None):
        calls.append(("rotate", None))
        return 0

    monkeypatch.setattr(backup_s3, "upload_backup", fake_upload)
    monkeypatch.setattr(backup_s3, "rotate", fake_rotate)

    await backup_s3.upload_if_enabled("backup.sql.gz")
    assert calls == [("upload", "backup.sql.gz"), ("rotate", None)]


@pytest.mark.asyncio
async def test_upload_if_enabled_alerts_on_failure(monkeypatch):
    monkeypatch.setattr(backup_s3, "load_settings", lambda: _settings(auto_upload=True))
    alerts = []

    async def fake_upload(filename, settings=None):
        raise S3Error("бакет не найден")

    async def fake_notify(title, body, group_key="backup_failed"):
        alerts.append((title, group_key))

    monkeypatch.setattr(backup_s3, "upload_backup", fake_upload)
    monkeypatch.setattr("web.backend.core.backup_service._notify_backup_failed", fake_notify)

    await backup_s3.upload_if_enabled("backup.sql.gz")
    assert alerts == [("Бэкап не ушёл в S3", "backup_s3_failed")]

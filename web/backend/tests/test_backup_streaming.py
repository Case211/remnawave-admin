"""Бэкап не проходит через память процесса.

Регрессия: на базе в 750 МБ плановый бэкап поднимал RSS backend до гигабайта —
весь plain-дамп лежал в памяти до сжатия. Теперь pg_dump пишет сжатый файл
сам, части для Telegram читаются с диска по одной, загрузка копируется кусками.
"""
import asyncio
import gzip
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core import backup_service


def _pg_dump_fake(returncode: int = 0, stderr: bytes = b""):
    """Подменяет pg_dump: пишет сжатый дамп в файл из --file и запоминает вызов."""
    calls = {}

    async def _spawn(*args, **kwargs):
        calls["args"] = args
        calls["kwargs"] = kwargs
        target = next(a for a in args if a.startswith("--file=")).split("=", 1)[1]
        with gzip.open(target, "wb") as fh:
            fh.write(b"-- dump\nSELECT 1;\n" if returncode == 0 else b"")
        proc = MagicMock()
        proc.returncode = returncode
        proc.communicate = AsyncMock(return_value=(b"", stderr))
        return proc

    return _spawn, calls


class TestCreateDatabaseBackup:
    @pytest.mark.asyncio
    async def test_pg_dump_writes_compressed_file_itself(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
        spawn, calls = _pg_dump_fake()
        with patch("asyncio.create_subprocess_exec", side_effect=spawn), \
                patch("web.backend.core.webhook_security.fire_event"):
            result = await backup_service.create_database_backup("postgresql://x")

        args = calls["args"]
        assert args[0] == "pg_dump"
        assert "--compress=6" in args
        assert calls["kwargs"]["stdout"] is asyncio.subprocess.DEVNULL
        final = tmp_path / result["filename"]
        assert final.name.startswith("db_backup_") and final.name.endswith(".sql.gz")
        with gzip.open(final, "rb") as fh:
            assert fh.read() == b"-- dump\nSELECT 1;\n"
        assert result["size_bytes"] == final.stat().st_size
        assert [p.name for p in tmp_path.iterdir()] == [final.name]

    @pytest.mark.asyncio
    async def test_failed_dump_leaves_no_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
        spawn, _ = _pg_dump_fake(returncode=1, stderr=b"connection refused")
        with patch("asyncio.create_subprocess_exec", side_effect=spawn):
            with pytest.raises(RuntimeError, match="connection refused"):
                await backup_service.create_database_backup("postgresql://x")
        assert list(tmp_path.iterdir()) == []


class TestTelegramParts:
    @pytest.mark.asyncio
    async def test_parts_are_read_from_disk_one_at_a_time(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
        monkeypatch.setattr(backup_service, "TELEGRAM_MAX_PART", 4)
        (tmp_path / "db_backup_z.sql.gz").write_bytes(b"0123456789")
        sent = []

        class _Resp:
            status_code = 200
            text = ""

        class _Client:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, data=None, files=None):
                name, payload = files["document"]
                sent.append((name, payload))
                return _Resp()

        with patch("httpx.AsyncClient", _Client):
            result = await backup_service.send_backup_to_telegram(
                "db_backup_z.sql.gz", chat_id="1", bot_token="t",
            )

        assert result["parts_sent"] == 3
        assert [name for name, _ in sent] == [f"db_backup_z.sql.gz.part{i}of3" for i in (1, 2, 3)]
        assert b"".join(payload for _, payload in sent) == b"0123456789"
        assert max(len(payload) for _, payload in sent) <= 4


class TestUploadStreaming:
    @pytest.mark.asyncio
    async def test_copies_in_chunks_and_reports_size(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
        monkeypatch.setattr(backup_service, "_CHUNK_BYTES", 3)
        result = await backup_service.save_uploaded_file(
            "my dump.sql.gz", io.BytesIO(b"abcdefgh"), max_bytes=100,
        )
        assert result["filename"] == "my_dump.sql.gz"
        assert result["size_bytes"] == 8
        assert (tmp_path / "my_dump.sql.gz").read_bytes() == b"abcdefgh"

    @pytest.mark.asyncio
    async def test_over_limit_is_rejected_and_cleaned_up(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
        monkeypatch.setattr(backup_service, "_CHUNK_BYTES", 3)
        with pytest.raises(backup_service.BackupTooLarge):
            await backup_service.save_uploaded_file("big.sql.gz", io.BytesIO(b"x" * 10), max_bytes=5)
        assert not (tmp_path / "big.sql.gz").exists()

    @pytest.mark.asyncio
    async def test_wrong_extension_rejected_before_writing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
        with pytest.raises(ValueError):
            await backup_service.save_uploaded_file("evil.sh", io.BytesIO(b"x"), max_bytes=5)
        assert list(tmp_path.iterdir()) == []

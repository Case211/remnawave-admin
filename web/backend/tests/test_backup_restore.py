"""Unit tests for restore_database_backup safety flags and error propagation.

These guard against silent partial restores: psql must run with ON_ERROR_STOP=1
and --single-transaction so a failed statement aborts and rolls back instead of
reporting success on a half-restored database.

Дамп подаётся в psql потоком, а не одним буфером — проверяем, что в stdin
ушёл ровно распакованный SQL и что stdin закрыт, иначе psql не завершится.
"""
import gzip
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core import backup_service


def _make_proc(returncode: int, stderr: bytes = b""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdin.written = []
    proc.stdin.write = proc.stdin.written.append
    proc.stdin.drain = AsyncMock()
    proc.stderr.read = AsyncMock(return_value=stderr)
    proc.wait = AsyncMock(return_value=returncode)
    return proc


@pytest.mark.asyncio
async def test_restore_passes_safety_flags(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
    backup_file = tmp_path / "db_backup_x.sql.gz"
    with gzip.open(backup_file, "wb") as fh:
        fh.write(b"SELECT 1;")

    proc = _make_proc(0)
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as m:
        m.return_value = proc
        await backup_service.restore_database_backup("postgresql://x", "db_backup_x.sql.gz")

    args = m.call_args.args
    assert args[0] == "psql"
    assert "ON_ERROR_STOP=1" in args
    assert "--single-transaction" in args
    # Decompressed SQL must be fed to psql via stdin, then stdin closed.
    assert b"".join(proc.stdin.written) == b"SELECT 1;"
    proc.stdin.close.assert_called_once()


@pytest.mark.asyncio
async def test_restore_streams_in_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(backup_service, "_CHUNK_BYTES", 4)
    backup_file = tmp_path / "db_backup_s.sql.gz"
    with gzip.open(backup_file, "wb") as fh:
        fh.write(b"SELECT 1; SELECT 2;")

    proc = _make_proc(0)
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as m:
        m.return_value = proc
        await backup_service.restore_database_backup("postgresql://x", "db_backup_s.sql.gz")

    assert len(proc.stdin.written) > 1
    assert max(len(c) for c in proc.stdin.written) <= 4
    assert b"".join(proc.stdin.written) == b"SELECT 1; SELECT 2;"
    assert proc.stdin.drain.await_count == len(proc.stdin.written)


@pytest.mark.asyncio
async def test_restore_raises_on_psql_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
    backup_file = tmp_path / "db_backup_y.sql.gz"
    with gzip.open(backup_file, "wb") as fh:
        fh.write(b"BAD SQL")

    proc = _make_proc(3, stderr=b"ERROR: syntax error")
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as m:
        m.return_value = proc
        with pytest.raises(RuntimeError, match="psql restore failed"):
            await backup_service.restore_database_backup("postgresql://x", "db_backup_y.sql.gz")


@pytest.mark.asyncio
async def test_restore_missing_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        await backup_service.restore_database_backup("postgresql://x", "does_not_exist.sql.gz")

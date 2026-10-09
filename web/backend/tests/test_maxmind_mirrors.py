"""GeoIP-базы с зеркал без ключа: по очереди, до первой удачи, и только настоящая MaxMind DB.

Зеркало ltsdev/maxmind удалили в октябре 2026, а зарегистрироваться в MaxMind
из РФ или через VPN нельзя — без запасных зеркал новые установки оставались
вовсе без географии.
"""
import io
import tarfile

import httpx
import pytest

from shared import maxmind_updater as mu

MMDB = b"\x00" * 64 + mu.MMDB_MARKER + b"\x00" * 16


def _targz(name: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _serve(monkeypatch, routes: dict):
    """httpx-клиент обновлятора отвечает по таблице адресов; остальное — 404."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        body = routes.get(str(request.url))
        return httpx.Response(200, content=body) if body is not None else httpx.Response(404)

    real = httpx.AsyncClient
    monkeypatch.setattr(mu.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return seen


@pytest.mark.asyncio
async def test_falls_back_to_the_next_mirror(monkeypatch, tmp_path):
    first = "https://dead.example/{edition}.mmdb"
    second = "https://alive.example/{edition}.tar.gz"
    seen = _serve(monkeypatch, {"https://alive.example/GeoLite2-ASN.tar.gz": _targz("x/GeoLite2-ASN.mmdb", MMDB)})
    out = tmp_path / "GeoLite2-ASN.mmdb"

    assert await mu.download_from_github("asn", str(out), mirrors=[first, second])
    assert out.read_bytes() == MMDB
    assert seen == ["https://dead.example/GeoLite2-ASN.mmdb", "https://alive.example/GeoLite2-ASN.tar.gz"]


@pytest.mark.asyncio
async def test_html_with_200_is_not_saved(monkeypatch, tmp_path):
    """Зеркало вместо базы отдало страницу — старый файл не затирается."""
    _serve(monkeypatch, {"https://mirror.example/GeoLite2-City.mmdb": b"<html>gone</html>"})
    out = tmp_path / "GeoLite2-City.mmdb"
    out.write_bytes(MMDB)

    assert not await mu.download_from_github("city", str(out), mirrors=["https://mirror.example/{edition}.mmdb"])
    assert out.read_bytes() == MMDB


def test_own_mirror_goes_first(monkeypatch):
    monkeypatch.setenv("MAXMIND_MIRROR_URL", "https://geo.example/{edition}.mmdb")
    assert mu.mirror_urls() == ["https://geo.example/{edition}.mmdb", *mu.GITHUB_MIRRORS]
    monkeypatch.delenv("MAXMIND_MIRROR_URL")
    assert mu.mirror_urls() == list(mu.GITHUB_MIRRORS)


def test_default_mirrors_are_alive_ones():
    assert not any("ltsdev" in url for url in mu.GITHUB_MIRRORS)
    assert all("{edition}" in url for url in mu.GITHUB_MIRRORS)

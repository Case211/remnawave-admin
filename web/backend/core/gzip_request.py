"""Приём сжатых тел запросов.

Батч подключений от агента — это одни и те же ключи, соседние адреса и
близкие отметки времени: gzip снимает с него примерно 11-кратный объём. На
ноде с большим онлайном это разница между забитым каналом и незаметным
фоном, поэтому агент 1.6.0+ шлёт тело с ``Content-Encoding: gzip``.

Starlette такие тела сам не разворачивает, а обработчику нужен уже
разобранный JSON — поэтому распаковка живёт в ASGI-слое, до маршрутизации:
эндпоинты о сжатии не знают и остаются прежними.
"""
import zlib

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class GzipRequestMiddleware:
    """Разворачивает тело запроса, присланное с ``Content-Encoding: gzip``."""

    def __init__(self, app: ASGIApp, max_decompressed_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_decompressed_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if headers.get("content-encoding", "").lower() != "gzip":
            await self.app(scope, receive, send)
            return

        # Сжатое тело крупнее лимита разворачивать незачем — оно и в
        # распакованном виде его не пройдёт.
        declared = headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send, 413, "Request body too large", "BODY_TOO_LARGE")
            return

        body = bytearray()
        while True:
            message: Message = await receive()
            if message["type"] != "http.request":
                break
            body += message.get("body", b"")
            if len(body) > self.max_bytes:
                await self._reject(send, 413, "Request body too large", "BODY_TOO_LARGE")
                return
            if not message.get("more_body", False):
                break

        # Распаковываем с потолком: сжатие скрывает настоящий размер, и без
        # ограничения десяток килобайт мог бы развернуться в гигабайты.
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            raw = decompressor.decompress(bytes(body), self.max_bytes)
        except zlib.error:
            await self._reject(send, 400, "Malformed gzip body", "BAD_ENCODING")
            return
        if decompressor.unconsumed_tail:
            await self._reject(send, 413, "Request body too large", "BODY_TOO_LARGE")
            return

        scope = dict(scope)
        scope["headers"] = self._rewrite_headers(scope["headers"], len(raw))
        await self.app(scope, self._replay(raw), send)

    @staticmethod
    def _rewrite_headers(raw_headers: list, length: int) -> list:
        """Снимает content-encoding и выставляет длину распакованного тела."""
        rewritten = [
            (name, value)
            for name, value in raw_headers
            if name.lower() not in (b"content-encoding", b"content-length")
        ]
        rewritten.append((b"content-length", str(length).encode("latin-1")))
        return rewritten

    @staticmethod
    def _replay(raw: bytes) -> Receive:
        """Отдаёт распакованное тело так, будто оно таким и пришло."""
        sent = False

        async def receive() -> Message:
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": raw, "more_body": False}

        return receive

    @staticmethod
    async def _reject(send: Send, status: int, detail: str, code: str) -> None:
        response = JSONResponse({"detail": detail, "code": code}, status_code=status)
        await response({"type": "http"}, None, send)

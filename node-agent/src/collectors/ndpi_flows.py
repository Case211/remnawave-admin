"""Вердикты nDPI: второй источник правды про торренты.

Xray опознаёт BitTorrent по началу соединения — открытому рукопожатию
``\\x13BitTorrent protocol``. Современные клиенты по умолчанию шифруют
поток (MSE/PE), работают через DHT и uTP поверх UDP, и до этого
рукопожатия дело просто не доходит. Поэтому тег ``TORRENT`` в роутинге
ловит в основном тех, кто качает старым клиентом с выключенным
шифрованием.

nDPI смотрит глубже: у него есть эвристики на зашифрованный BitTorrent,
на DHT-пакеты и на uTP. Демон ``nDPId`` гоняет эту библиотеку по трафику
интерфейса и раздаёт вердикты JSON-строками через UNIX-сокет; агент их
читает и складывает в короткое окно.

Связка с пользователем делается снаружи (см. ``XrayLogCollector``): сам
nDPI видит трафик уже после NAT, то есть от имени ноды, и о том, чей это
клиент, не знает ничего. Зато адрес назначения у него и у Xray один и тот
же — по нему потоки и сходятся.

Формат сокета (nDPIsrvd): каждое сообщение предваряется пятизначным
десятичным числом — длиной самого сообщения вместе с завершающим
переводом строки.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any, Deque, Iterator, Optional, Tuple

logger = logging.getLogger("collector")

#: Длина префикса с размером сообщения.
HEADER_LEN = 5

#: События, в которых вердикт уже осмысленный. «new» пропускаем: на первом
#: пакете протокол ещё не определён.
MEANINGFUL_EVENTS = frozenset({"detected", "detection-update", "update", "guessed", "end", "idle"})

#: Как называется наша добыча в терминах nDPI. Проверяем вхождением: у
#: составных протоколов имя выглядит как «master.app», и BitTorrent может
#: оказаться любой из половин.
TORRENT_MARKERS = ("bittorrent", "torrent")


def iter_messages(buffer: bytes) -> Tuple[Iterator[dict], bytes]:
    """Разобрать буфер на сообщения; вернуть (события, остаток).

    Остаток — незавершённое сообщение, которое дочитается следующей
    порцией. Сообщение с битым префиксом отбрасывать нельзя: поток после
    него уже не разобрать, поэтому такой буфер обнуляется целиком.
    """
    events = []
    rest = buffer
    while len(rest) >= HEADER_LEN:
        header = rest[:HEADER_LEN]
        try:
            size = int(header.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            logger.warning("nDPI: сломанный префикс длины, сбрасываю буфер")
            return iter(events), b""
        if len(rest) < HEADER_LEN + size:
            break
        payload = rest[HEADER_LEN:HEADER_LEN + size]
        rest = rest[HEADER_LEN + size:]
        try:
            events.append(json.loads(payload.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            # Одно нечитаемое сообщение не повод рвать поток: рамки
            # известны, следующее прочитается нормально.
            logger.debug("nDPI: сообщение не разобралось, пропускаю")
    return iter(events), rest


def protocol_of(event: dict) -> str:
    """Имя протокола из события — плоским ключом или вложенным объектом."""
    flat = event.get("ndpi.proto")
    if isinstance(flat, str):
        return flat
    nested = event.get("ndpi")
    if isinstance(nested, dict):
        value = nested.get("proto")
        if isinstance(value, str):
            return value
    return ""


def is_torrent(event: dict) -> bool:
    """Вердикт про BitTorrent — по протоколу или категории обмена файлами."""
    if event.get("flow_event_name") not in MEANINGFUL_EVENTS:
        return False
    proto = protocol_of(event).lower()
    return any(marker in proto for marker in TORRENT_MARKERS)


def destination_of(event: dict) -> Optional[str]:
    """``ip:port`` назначения — в том же виде, в каком его пишет Xray."""
    ip = event.get("dst_ip")
    port = event.get("dst_port")
    if not ip or port in (None, ""):
        return None
    return f"{ip}:{port}"


class NdpiTorrentWatcher:
    """Окно свежих торрент-вердиктов nDPI по адресам назначения.

    Живёт фоновой задачей: держит подключение к сокету, переподключается
    при обрыве и складывает вердикты в окно. Ответ на вопрос «этот адрес
    сейчас торрент?» должен быть мгновенным — разбор лога Xray не может
    ждать сеть.
    """

    def __init__(self, socket_path: str, window_seconds: int = 120) -> None:
        self._socket_path = socket_path
        self._window = max(10, window_seconds)
        self._seen: dict[str, float] = {}
        self._order: Deque[Tuple[float, str]] = deque()
        self._task: Optional[asyncio.Task] = None
        self._stopping = False
        self.connected = False
        self.verdicts_total = 0

    # ── работа с окном ────────────────────────────────────────────

    def remember(self, destination: str, at: Optional[float] = None) -> None:
        now = at if at is not None else time.monotonic()
        self._seen[destination] = now
        self._order.append((now, destination))
        self.verdicts_total += 1
        self._forget_old(now)

    def _forget_old(self, now: float) -> None:
        deadline = now - self._window
        while self._order and self._order[0][0] < deadline:
            _, destination = self._order.popleft()
            # Адрес мог засветиться снова и быть моложе своей первой записи.
            if self._seen.get(destination, 0.0) < deadline:
                self._seen.pop(destination, None)

    def is_torrent(self, destination: str, at: Optional[float] = None) -> bool:
        """Был ли по этому адресу торрент-вердикт в пределах окна."""
        if not destination:
            return False
        now = at if at is not None else time.monotonic()
        self._forget_old(now)
        seen_at = self._seen.get(destination)
        return seen_at is not None and (now - seen_at) <= self._window

    # ── чтение сокета ─────────────────────────────────────────────

    async def _read_forever(self) -> None:
        backoff = 1.0
        while not self._stopping:
            try:
                reader, writer = await asyncio.open_unix_connection(self._socket_path)
            except (OSError, asyncio.CancelledError) as e:
                if self._stopping:
                    return
                self.connected = False
                logger.warning("nDPI: сокет %s недоступен (%s), повтор через %.0fs",
                               self._socket_path, e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
                continue

            self.connected = True
            backoff = 1.0
            logger.info("nDPI: подключён к %s", self._socket_path)
            buffer = b""
            try:
                while not self._stopping:
                    chunk = await reader.read(65536)
                    if not chunk:
                        break  # демон закрыл соединение
                    buffer += chunk
                    events, buffer = iter_messages(buffer)
                    for event in events:
                        if not is_torrent(event):
                            continue
                        destination = destination_of(event)
                        if destination:
                            self.remember(destination)
            except (OSError, asyncio.IncompleteReadError) as e:
                logger.warning("nDPI: соединение прервано (%s)", e)
            finally:
                self.connected = False
                writer.close()
                try:
                    await writer.wait_closed()
                except (OSError, asyncio.CancelledError):
                    pass

    async def start(self) -> None:
        if self._task is None:
            self._stopping = False
            self._task = asyncio.create_task(self._read_forever())

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    def stats(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "verdicts_total": self.verdicts_total,
            "window_size": len(self._seen),
        }

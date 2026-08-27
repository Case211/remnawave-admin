"""Запуск nDPId прямо из агента.

Демон едет внутри образа, поэтому «установка» сводится к запуску пары
процессов: оператору достаточно тумблера в панели, а сборка на ноде
руками не нужна вовсе. Слушать интерфейс агент может, потому что живёт в
сети хоста с privileged — иначе не собирались бы и сетевые метрики.

Процессов два, как того требует сам nDPId:

* ``nDPId`` разбирает трафик интерфейса и пишет вердикты в свой сокет;
* ``nDPIsrvd`` читает его и раздаёт потребителям — к этому сокету и
  подключается агент.

Если бинарников в образе нет (агент старой сборки), поднимать нечего:
честно говорим об этом, а не делаем вид, что всё включилось.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger("collector")

NDPID_BIN = "nDPId"
NDPISRVD_BIN = "nDPIsrvd"

#: Сокет между самим nDPId и раздатчиком — внутренняя кухня, наружу не идёт.
COLLECTOR_SOCKET = "/tmp/ndpid-collector.sock"

#: Имя экземпляра в каждом JSON-сообщении.
DAEMON_ALIAS = "remnawave-node-agent"

#: Что не отдаём в разбор вообще. Вердикты с этих портов детектор всё равно
#: выбрасывает (ndpi_flows.IMPLAUSIBLE_PEER_PORTS), а на VPN-ноде именно они
#: и составляют почти весь поток: клиентский трафик идёт на 443. Отсеивать
#: их до разбора дешевле, чем разбирать и выкидывать — это снимает основную
#: часть нагрузки, не трогая ни DHT, ни uTP на случайных высоких портах.
BPF_FILTER = "not (port 80 or port 443 or port 8443 or port 5222)"

#: Потолок потоков разбора. Дефолт nDPId — 10, и на двухъядерной ноде они
#: дают под половину CPU: десять reader-тредов при двух ядрах только делят
#: между собой одну и ту же работу. С включённым BPF-фильтром потока
#: остаётся столько, что хватает пары.
MAX_READER_THREADS = 4

#: Сколько держать мёртвый TCP-поток в таблице. Дефолт — 7440 секунд, то
#: есть больше двух часов: таблица растёт весь uptime, память вслед за ней.
#: Торрент опознаётся в первые секунды обмена, ждать дольше незачем.
TCP_IDLE_US = 300_000_000        # 5 минут
UDP_IDLE_US = 120_000_000        # 2 минуты — DHT живёт короткими всплесками
GENERIC_IDLE_US = 300_000_000

#: Чаще подметать таблицу: дефолтные 10 секунд при коротких таймаутах
#: означают, что истёкшие потоки всё равно ждут своей очереди.
FLOW_SCAN_US = 5_000_000

#: Потолок таблицы на поток разбора. При четырёх тредах это 8192 потока —
#: с запасом на пиковую ноду, но без неограниченного роста.
MAX_FLOWS_PER_THREAD = 2048


async def socket_alive(path: str) -> bool:
    """Отвечает ли кто-нибудь на этом сокете.

    Файл сокета переживает смерть процесса, поэтому его наличие ничего не
    доказывает: после падения демона остаётся мёртвый путь, к которому
    невозможно подключиться. Спрашиваем подключением.
    """
    try:
        _, writer = await asyncio.open_unix_connection(path)
    except (OSError, asyncio.CancelledError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return True


def binaries_available() -> bool:
    return bool(shutil.which(NDPID_BIN) and shutil.which(NDPISRVD_BIN))


def default_interface() -> Optional[str]:
    """Интерфейс маршрута по умолчанию — тот, через который ходит трафик нод.

    Читаем /proc/net/route: «any» у nDPId ловит и loopback, а разбирать
    собственный трафик агента незачем.
    """
    try:
        lines = Path("/proc/net/route").read_text(encoding="utf-8").splitlines()[1:]
    except OSError:
        return None
    for line in lines:
        parts = line.split()
        # destination == 00000000 → маршрут по умолчанию
        if len(parts) >= 2 and parts[1] == "00000000":
            return parts[0]
    return None


class NdpiDaemon:
    """Пара процессов nDPId + nDPIsrvd под присмотром агента."""

    def __init__(
        self,
        distributor_socket: str,
        interface: Optional[str] = None,
        collector_socket: str = COLLECTOR_SOCKET,
    ) -> None:
        self.distributor_socket = distributor_socket
        self.collector_socket = collector_socket
        self.interface = interface or default_interface()
        self._ndpid: Optional[asyncio.subprocess.Process] = None
        self._srvd: Optional[asyncio.subprocess.Process] = None

    @property
    def running(self) -> bool:
        return bool(
            self._ndpid and self._ndpid.returncode is None
            and self._srvd and self._srvd.returncode is None
        )

    async def start(self) -> dict:
        """Поднять демоны; вернуть состояние для панели."""
        if not binaries_available():
            return {
                "started": False,
                "reason": "nDPId не собран в этом образе агента — обновите агента",
            }
        if self.running:
            return {"started": True, "interface": self.interface, "already_running": True}
        if not self.interface:
            return {"started": False, "reason": "не удалось определить сетевой интерфейс"}

        # Осиротевший сокет от прежнего запуска не даст демону встать
        # («address already in use»), а живой означает, что демон уже поднят.
        for path in (self.collector_socket, self.distributor_socket):
            if Path(path).exists() and not await socket_alive(path):
                try:
                    Path(path).unlink()
                except OSError:
                    logger.warning("nDPI: не удалось убрать мёртвый сокет %s", path)

        # Раздатчик поднимается первым: nDPId при старте стучится в его
        # сокет, и обратный порядок дал бы гонку на пустом месте.
        # Без «-d»: этот флаг уводит процесс в фон, родитель выходит с
        # кодом 0, и агент теряет управление — остановить такой демон он уже
        # не может, а по коду возврата решает, что запуск провалился.
        self._srvd = await asyncio.create_subprocess_exec(
            NDPISRVD_BIN, "-c", self.collector_socket, "-s", self.distributor_socket,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.sleep(0.3)
        # Alias обязателен: без него nDPId ругается в stderr и берёт
        # hostname, а он у контейнера случайный и меняется при каждом
        # пересоздании — в вердиктах это выглядело бы новым источником.
        self._ndpid = await asyncio.create_subprocess_exec(
            NDPID_BIN, "-i", self.interface, "-c", self.collector_socket,
            "-a", DAEMON_ALIAS,
            # Отсекаем до разбора то, что детектор всё равно выбросит:
            # на ноде это почти весь клиентский поток.
            "-B", BPF_FILTER,
            # Пакетные события — две трети потока в сокет, и ни одно из них
            # не несёт вердикта: агент их отбрасывает. На живой ноде это
            # была даром потраченная сериализация на каждый поток.
            "-o", "max-packets-per-flow-to-send=0",
            # Тредов по дефолту десять — на ноде они делят одну работу и
            # съедают CPU; таблицы по дефолту живут часами и растут весь
            # uptime. Обе ручки прижимаем, детект от этого не страдает.
            "-o", f"max-reader-threads={MAX_READER_THREADS}",
            "-o", f"max-flows-per-thread={MAX_FLOWS_PER_THREAD}",
            "-o", f"flow-scan-interval={FLOW_SCAN_US}",
            "-o", f"tcp-max-idle-time={TCP_IDLE_US}",
            "-o", f"udp-max-idle-time={UDP_IDLE_US}",
            "-o", f"generic-max-idle-time={GENERIC_IDLE_US}",
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.sleep(0.5)

        if not self.running:
            reason = await self._failure_reason()
            await self.stop()
            return {"started": False, "reason": reason}

        logger.info("nDPId запущен на интерфейсе %s", self.interface)
        return {
            "started": True,
            "interface": self.interface,
            "pids": {"nDPId": self._ndpid.pid, "nDPIsrvd": self._srvd.pid},
        }

    async def _failure_reason(self) -> str:
        """Что именно сказал упавший процесс — иначе отладка вслепую."""
        for name, proc in (("nDPId", self._ndpid), ("nDPIsrvd", self._srvd)):
            if proc is None or proc.returncode is None:
                continue
            try:
                _, err = await asyncio.wait_for(proc.communicate(), timeout=2)
            except (asyncio.TimeoutError, ValueError):
                err = b""
            message = (err or b"").decode("utf-8", errors="replace").strip()
            return f"{name} завершился с кодом {proc.returncode}: {message[:200]}"
        return "процесс не поднялся"

    async def stop(self) -> None:
        for proc in (self._ndpid, self._srvd):
            if proc is None or proc.returncode is not None:
                continue
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
        self._ndpid = None
        self._srvd = None

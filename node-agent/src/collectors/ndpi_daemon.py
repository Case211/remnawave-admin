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
            # Пакетные события — две трети потока в сокет, и ни одно из них
            # не несёт вердикта: агент их отбрасывает. На живой ноде это
            # была даром потраченная сериализация на каждый поток.
            "-o", "max-packets-per-flow-to-send=0",
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

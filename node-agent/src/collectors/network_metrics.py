"""
Коллектор сетевых метрик ноды: трафик интерфейсов, conntrack, давление на TCP.

Читает network namespace ХОСТА. Агент обычно живёт в контейнере без
network_mode: host, и собственный /proc/net показал бы трафик бриджа, а не
ноды. Спасает pid: "host" из docker-compose: через /proc/1/net виден netns
хостового init.

Если хостовый netns недоступен, коллектор молчит (None) — ноль вместо данных
читался бы как «на ноде тишина», а это ровно противоположный вывод.
"""
import logging
import os
import time
from pathlib import Path
from typing import Callable

from ..models import NetworkMetrics

logger = logging.getLogger(__name__)

# Виртуальные интерфейсы: петля, бриджи докера и туннели. Их трафик — это либо
# тот же самый трафик, уже посчитанный на физическом интерфейсе, либо локальный.
_VIRTUAL_PREFIXES = (
    "lo", "docker", "br-", "veth", "virbr", "vmbr", "tun", "tap",
    "wg", "dummy", "sit", "gre", "ip6tnl", "ifb", "teql", "warp", "nebula",
)

# Что берём из /proc/net/netstat и /proc/net/snmp
_TCPEXT_FIELDS = {"SyncookiesSent": "syncookies", "ListenDrops": "listen_drops"}
_TCP_FIELDS = {"CurrEstab": "tcp_established"}

# Счётчики, которые растут монотонно — из них считаем скорость в секунду
_RATE_FIELDS = (
    "rx_bytes", "tx_bytes", "rx_packets", "tx_packets",
    "rx_drop", "tx_drop", "syncookies", "listen_drops",
)


def _is_virtual(iface: str) -> bool:
    # Точка в имени — VLAN поверх физического интерфейса (eth0.100). Тот же
    # пакет считается и там, и на носителе, так что цифры удвоились бы.
    return "." in iface or iface.startswith(_VIRTUAL_PREFIXES)


def _in_container() -> bool:
    """Агент запущен в контейнере?"""
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/self/cgroup").read_text()
    except OSError:
        return False
    return any(marker in cgroup for marker in ("docker", "containerd", "kubepods"))


def _foreign_netns() -> bool:
    """netns процесса 1 отличается от нашего — значит pid: host и это netns хоста."""
    try:
        return os.readlink("/proc/1/ns/net") != os.readlink("/proc/self/ns/net")
    except OSError:
        return False


def _shares_host_netns() -> bool:
    """Контейнер поднят с network_mode: host — свой /proc/net уже хостовый.

    Отличаем по интерфейсам докера: в собственной сети контейнера их не видно,
    а на ноде докер есть заведомо — в нём крутится сам агент.
    """
    try:
        text = Path("/proc/net/dev").read_text()
    except OSError:
        return False
    return any(marker in text for marker in ("docker0", "veth", "br-"))


def _resolve_net_root() -> Path | None:
    """Найти /proc/net хоста. None — если виден только собственный контейнер."""
    if not _in_container():
        return Path("/proc/net")

    host = Path("/proc/1/net")
    if _foreign_netns() and (host / "dev").exists():
        return host

    if _shares_host_netns():
        return Path("/proc/net")

    return None


def _read_int(path: Path) -> int | None:
    """Прочитать файл с единственным числом (sysctl)."""
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _read_kv_table(path: Path, section: str, wanted: dict[str, str]) -> dict[str, int]:
    """Разобрать /proc/net/{snmp,netstat}: пары строк «заголовок / значения».

    Формат — две строки с одним префиксом подряд: сначала имена колонок,
    следом их значения.
    """
    out: dict[str, int] = {}
    lines = path.read_text().splitlines()
    prefix = f"{section}:"
    for header, values in zip(lines, lines[1:]):
        if not header.startswith(prefix) or not values.startswith(prefix):
            continue
        for key, raw in zip(header.split()[1:], values.split()[1:]):
            field = wanted.get(key)
            if field is not None:
                try:
                    out[field] = int(raw)
                except ValueError:
                    pass
    return out


class NetworkMetricsCollector:
    """Собирает сетевые метрики хоста из procfs."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._net_root = _resolve_net_root()
        # Свой netns или чужой (хостовый, прочитанный через /proc/1/net) —
        # от этого зависит, можно ли верить sysctl: он всегда про наш namespace
        self._own_netns = self._net_root == Path("/proc/net")
        self._clock = clock
        self._prev: dict[str, int] = {}
        self._prev_ts: float | None = None
        self._conntrack_warned = False

        if self._net_root is None:
            logger.warning(
                "Сетевые метрики недоступны: агент не видит network namespace хоста. "
                'Проверьте, что в docker-compose.yml агента задан pid: "host".'
            )
        else:
            logger.info("Сетевые метрики: источник %s", self._net_root)

    @property
    def available(self) -> bool:
        return self._net_root is not None

    async def collect(self) -> NetworkMetrics | None:
        """Собрать сетевые метрики. None — источник недоступен."""
        if self._net_root is None:
            return None

        counters: dict[str, int] = {}

        try:
            counters.update(self._read_dev())
        except Exception as e:
            logger.debug("Failed to read %s/dev: %s", self._net_root, e)

        try:
            counters.update(
                _read_kv_table(self._net_root / "netstat", "TcpExt", _TCPEXT_FIELDS)
            )
        except Exception as e:
            logger.debug("Failed to read netstat: %s", e)

        established = 0
        try:
            snmp = _read_kv_table(self._net_root / "snmp", "Tcp", _TCP_FIELDS)
            established = snmp.get("tcp_established", 0)
        except Exception as e:
            logger.debug("Failed to read snmp: %s", e)

        conntrack_count, conntrack_max = self._read_conntrack()
        rates = self._rates(counters)

        return NetworkMetrics(
            rx_bps=rates.get("rx_bytes", 0),
            tx_bps=rates.get("tx_bytes", 0),
            rx_pps=rates.get("rx_packets", 0),
            tx_pps=rates.get("tx_packets", 0),
            rx_drop_ps=rates.get("rx_drop", 0),
            tx_drop_ps=rates.get("tx_drop", 0),
            conntrack_count=conntrack_count,
            conntrack_max=conntrack_max,
            tcp_established=established,
            tcp_syncookies_ps=rates.get("syncookies", 0),
            tcp_listen_drop_ps=rates.get("listen_drops", 0),
        )

    def _rates(self, counters: dict[str, int]) -> dict[str, int]:
        """Перевести монотонные счётчики в «за секунду» по дельте с прошлого раза.

        Первый вызов даёт нули: не с чем сравнивать. Отрицательная дельта
        означает перезапуск счётчика (ребут ноды) — отдаём ноль, а не мусор.
        """
        now = self._clock()
        prev, prev_ts = self._prev, self._prev_ts

        self._prev = counters
        self._prev_ts = now

        if prev_ts is None:
            return {}

        elapsed = now - prev_ts
        if elapsed <= 0:
            return {}

        rates: dict[str, int] = {}
        for field in _RATE_FIELDS:
            if field not in counters or field not in prev:
                continue
            rates[field] = max(0, int((counters[field] - prev[field]) / elapsed))
        return rates

    def _read_dev(self) -> dict[str, int]:
        """Суммарные счётчики физических интерфейсов из <net>/dev."""
        totals = dict.fromkeys(
            ("rx_bytes", "rx_packets", "rx_drop", "tx_bytes", "tx_packets", "tx_drop"), 0
        )

        assert self._net_root is not None
        for line in (self._net_root / "dev").read_text().splitlines():
            name, sep, rest = line.partition(":")
            if not sep:
                continue  # шапка таблицы
            name = name.strip()
            if _is_virtual(name):
                continue

            parts = rest.split()
            if len(parts) < 12:
                continue
            try:
                totals["rx_bytes"] += int(parts[0])
                totals["rx_packets"] += int(parts[1])
                totals["rx_drop"] += int(parts[3])
                totals["tx_bytes"] += int(parts[8])
                totals["tx_packets"] += int(parts[9])
                totals["tx_drop"] += int(parts[11])
            except ValueError:
                continue

        return totals

    def _read_conntrack(self) -> tuple[int | None, int | None]:
        """Заполнение таблицы conntrack: (занято, потолок).

        Таблица своя у каждого network namespace, а sysctl отдаёт значения того
        namespace, где выполняется процесс. Из сети контейнера цифры были бы про
        сам контейнер: на проде это 8 записей против 178 у хоста.

        Когда namespace хоста нам чужой, занятое место остаётся только в
        <net>/stat/nf_conntrack — а этот файл существует лишь при
        CONFIG_NF_CONNTRACK_PROCFS, которого в типовых ядрах Ubuntu нет. Тогда
        метрику не отдаём совсем: потолок без занятого места читался бы как
        «таблица пуста», то есть как отсутствие проблемы.
        """
        limit = _read_int(Path("/proc/sys/net/netfilter/nf_conntrack_max"))

        if self._own_netns:
            count = _read_int(Path("/proc/sys/net/netfilter/nf_conntrack_count"))
        else:
            count = self._read_conntrack_entries()

        if count is None:
            self._warn_conntrack_once()
            return (None, None)

        return (count, limit)

    def _read_conntrack_entries(self) -> int | None:
        """Занятые записи из <net>/stat/nf_conntrack: первая колонка, в hex."""
        assert self._net_root is not None
        try:
            rows = (self._net_root / "stat" / "nf_conntrack").read_text().splitlines()
            return int(rows[1].split()[0], 16)
        except (OSError, ValueError, IndexError):
            return None

    def _warn_conntrack_once(self) -> None:
        if self._conntrack_warned:
            return
        self._conntrack_warned = True
        logger.info(
            "conntrack не собирается: таблица хоста не видна из сети контейнера "
            "(ядро без CONFIG_NF_CONNTRACK_PROCFS). Поможет network_mode: host "
            "в docker-compose агента. Остальные метрики не затронуты."
        )

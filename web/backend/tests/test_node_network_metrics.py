"""Тесты коллектора сетевых метрик node-agent.

Коллектор разбирает procfs руками, поэтому проверяем именно разбор: форматы
/proc/net/* отличаются друг от друга (hex в conntrack, парные строки в snmp),
а поверх них считаются дельты, где легко получить мусор при перезапуске ноды.
"""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_AGENT_SRC = Path(__file__).resolve().parents[3] / "node-agent" / "src"
_PACKAGE = "node_agent_src"


def _load_collector() -> ModuleType:
    """Загрузить модуль агента.

    node-agent не устанавливается как пакет, а его каталог `src` совпадает по
    имени с пакетом бота в корне репозитория — поэтому собираем пространство
    имён вручную, вместо того чтобы добавлять путь в sys.path.
    """
    full = f"{_PACKAGE}.collectors.network_metrics"
    if full in sys.modules:
        return sys.modules[full]

    for name, path in ((_PACKAGE, _AGENT_SRC), (f"{_PACKAGE}.collectors", _AGENT_SRC / "collectors")):
        if name not in sys.modules:
            pkg = ModuleType(name)
            pkg.__path__ = [str(path)]
            sys.modules[name] = pkg

    spec = importlib.util.spec_from_file_location(
        full, _AGENT_SRC / "collectors" / "network_metrics.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


net_metrics = _load_collector()


PROC_NET_DEV = """\
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 1000 10 0 0 0 0 0 0 1000 10 0 0 0 0 0 0
  eth0: 2000 20 1 3 0 0 0 0 4000 40 2 5 0 0 0 0
  ens3: 500 5 0 1 0 0 0 0 700 7 0 2 0 0 0 0
eth0.100: 1500 15 0 0 0 0 0 0 3000 30 0 0 0 0 0 0
docker0: 999999 9999 0 0 0 0 0 0 999999 9999 0 0 0 0 0 0
veth9a1b2: 888 88 0 0 0 0 0 0 888 88 0 0 0 0 0 0
"""

PROC_NET_NETSTAT = """\
TcpExt: SyncookiesSent SyncookiesRecv ListenOverflows ListenDrops
TcpExt: 12 4 3 7
IpExt: InNoRoutes InTruncatedPkts
IpExt: 0 0
"""

PROC_NET_SNMP = """\
Tcp: RtoAlgorithm RtoMin CurrEstab InSegs OutSegs
Tcp: 1 200 4231 100 90
Udp: InDatagrams NoPorts
Udp: 5 0
"""

PROC_NET_CONNTRACK_STAT = """\
entries  searched found new invalid ignore delete delete_list insert insert_failed drop early_drop icmp_error
0000012c  00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000
0000012c  00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000 00000000
"""


@pytest.fixture
def net_root(tmp_path: Path) -> Path:
    """Заготовка хостового /proc/net."""
    (tmp_path / "dev").write_text(PROC_NET_DEV)
    (tmp_path / "netstat").write_text(PROC_NET_NETSTAT)
    (tmp_path / "snmp").write_text(PROC_NET_SNMP)
    (tmp_path / "stat").mkdir()
    (tmp_path / "stat" / "nf_conntrack").write_text(PROC_NET_CONNTRACK_STAT)
    return tmp_path


class FakeClock:
    """Часы под управлением теста: реальный monotonic дал бы дельту в микросекунды."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def collector(net_root: Path, clock: FakeClock, monkeypatch: pytest.MonkeyPatch):
    """Коллектор, приколоченный к подставному procfs."""
    monkeypatch.setattr(net_metrics, "_resolve_net_root", lambda: net_root)
    return net_metrics.NetworkMetricsCollector(clock=clock)


def test_dev_sums_physical_interfaces_only(collector):
    """Бридж докера, veth и VLAN — это уже посчитанный трафик, их считать нельзя."""
    totals = collector._read_dev()

    assert totals["rx_bytes"] == 2500      # eth0 + ens3, без lo/docker0/veth/eth0.100
    assert totals["rx_packets"] == 25
    assert totals["rx_drop"] == 4
    assert totals["tx_bytes"] == 4700
    assert totals["tx_packets"] == 47
    assert totals["tx_drop"] == 7


def test_netstat_and_snmp_are_read_by_section(net_root: Path):
    """У snmp и netstat один формат — парные строки, но разные секции."""
    tcpext = net_metrics._read_kv_table(
        net_root / "netstat", "TcpExt", {"SyncookiesSent": "syncookies", "ListenDrops": "listen_drops"}
    )
    assert tcpext == {"syncookies": 12, "listen_drops": 7}

    # "Tcp:" не должен цепляться к секции "TcpExt:"
    tcp = net_metrics._read_kv_table(net_root / "snmp", "Tcp", {"CurrEstab": "tcp_established"})
    assert tcp == {"tcp_established": 4231}


def test_conntrack_entries_are_hex(collector):
    """entries в /proc/net/stat/nf_conntrack — шестнадцатеричные."""
    count, _ = collector._read_conntrack()
    assert count == 300  # 0x12c


def test_conntrack_skipped_when_host_table_unreachable(collector, monkeypatch: pytest.MonkeyPatch):
    """Потолок без занятого места не отдаём: это читалось бы как «таблица пуста».

    Боевой случай: ядро без CONFIG_NF_CONNTRACK_PROCFS (типовое Ubuntu 5.15) —
    файла со статистикой нет, а nf_conntrack_max контейнер наследует от хоста
    и прочитал бы успешно.
    """
    (collector._net_root / "stat" / "nf_conntrack").unlink()
    monkeypatch.setattr(net_metrics, "_read_int", lambda path: 262144)

    assert collector._read_conntrack() == (None, None)


def test_conntrack_from_sysctl_in_host_netns(collector, monkeypatch: pytest.MonkeyPatch):
    """В сети хоста sysctl честный — берём занятое и потолок оттуда."""
    collector._own_netns = True
    sysctl = {"nf_conntrack_count": 178, "nf_conntrack_max": 262144}
    monkeypatch.setattr(net_metrics, "_read_int", lambda path: sysctl[path.name])

    assert collector._read_conntrack() == (178, 262144)


def test_first_collect_reports_zero_rates(collector):
    """Первый замер сравнивать не с чем — отдаём нули, а не мгновенный счётчик."""
    rates = collector._rates({"rx_bytes": 1000})
    assert rates == {}


def test_rates_are_per_second(collector, clock: FakeClock):
    """Скорость — дельта счётчика, делённая на прошедшее время."""
    collector._rates({"rx_bytes": 1_000, "rx_packets": 50})
    clock.advance(10)
    rates = collector._rates({"rx_bytes": 6_000, "rx_packets": 150})

    assert rates["rx_bytes"] == 500  # 5000 байт за 10 секунд
    assert rates["rx_packets"] == 10


def test_counter_reset_does_not_produce_garbage(collector, clock: FakeClock):
    """После ребута ноды счётчики начинаются заново — отрицательной скорости быть не должно."""
    collector._rates({"rx_bytes": 10_000_000})
    clock.advance(30)
    rates = collector._rates({"rx_bytes": 1_000})

    assert rates["rx_bytes"] == 0


@pytest.mark.asyncio
async def test_collect_returns_metrics(collector, clock: FakeClock):
    assert await collector.collect() is not None  # прогрев: снимаем базу счётчиков
    clock.advance(1)

    (collector._net_root / "dev").write_text(
        PROC_NET_DEV.replace("  eth0: 2000 20", "  eth0: 12000 120")
    )
    metrics = await collector.collect()

    assert metrics.rx_bps == 10_000        # +10 КБ за секунду
    assert metrics.rx_pps == 100
    assert metrics.tcp_established == 4231
    assert metrics.conntrack_count == 300


@pytest.mark.asyncio
async def test_no_host_netns_means_no_metrics(monkeypatch: pytest.MonkeyPatch):
    """Без доступа к netns хоста метрик нет.

    Ноли здесь читались бы как «на ноде тишина» — вывод, обратный правде.
    """
    monkeypatch.setattr(net_metrics, "_resolve_net_root", lambda: None)
    collector = net_metrics.NetworkMetricsCollector()

    assert collector.available is False
    assert await collector.collect() is None


def test_container_without_pid_host_is_detected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Контейнер в своей сети: свой /proc/net покажет бридж, а не ноду."""
    monkeypatch.setattr(net_metrics, "_in_container", lambda: True)
    monkeypatch.setattr(net_metrics, "_foreign_netns", lambda: False)
    monkeypatch.setattr(net_metrics, "_shares_host_netns", lambda: False)

    assert net_metrics._resolve_net_root() is None


def test_host_netns_via_pid_host(monkeypatch: pytest.MonkeyPatch):
    """pid: host — netns хоста виден через /proc/1/net."""
    monkeypatch.setattr(net_metrics, "_in_container", lambda: True)
    monkeypatch.setattr(net_metrics, "_foreign_netns", lambda: True)
    monkeypatch.setattr(net_metrics.Path, "exists", lambda self: True)

    assert net_metrics._resolve_net_root() == Path("/proc/1/net")

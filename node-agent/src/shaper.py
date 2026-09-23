"""Шейпер ноды: общий потолок на каждого клиента и персональные лимиты юзеров.

Программа eBPF (bpf/shaper.bpf.c) едет в образе агента и вешается на вход
и выход основного интерфейса. Скачивание режется по EDT — пакету
назначается время отправки, а выдерживает его fq в корне. Отдача режется
полисером.

Лимитов два уровня, и действует меньший из них:
- общий — настройка шейпера ноды (команда set_shaper): потолок на каждого
  клиента на портах inbound'ов и режим штрафа для качальщиков;
- персональный — мягкая блокировка юзера (команда sync_throttled_ips):
  потолок на адрес клиента, от портов не зависит и работает на любой ноде.
0 на любом уровне — «без лимита».

Всё, что агент ставит на ноду, помечено, и снимается только помеченное:
- фильтры на приоритете SHAPER_PREF с программой rws_egress / rws_ingress;
- fq в корне — с handle 7277: и только если до нас там стояла дефолтная
  дисциплина ядра. Чужой корень не трогаем: скачивание тогда режется
  грубее, отбрасыванием, о чём агент и сообщает панели.

Скрипты выполняются в сети хоста, но с файловой системой контейнера:
объектник eBPF, bpftool и tc — из образа агента.
"""
from __future__ import annotations

import ipaddress
import struct
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

# Объектник собирается в Dockerfile (стадия bpf-builder)
BPF_OBJECT = "/app/bpf/shaper.bpf.o"
# Своя bpffs вне /sys: ``ip netns exec`` и подобные перемонтируют /sys, и
# пины оттуда пропадают. Здесь их видит только контейнер агента.
PIN_DIR = "/run/rwshaper"
# Меньше 49152: с этого номера ядро раздаёт приоритеты фильтрам без явного,
# и чужая eBPF-программа на нём может закончить проверку раньше нас.
SHAPER_PREF = 29304
# Метка своего fq в корне: по ней при выключении понятно, что снимать его — нам
ROOT_HANDLE = "7277:"

# Прежние раскладки мягкой блокировки, которые агент убирает при встрече:
# prio в корне с нашим HTB 40: (агенты до 1.8.x) и ifb (сборки 1.9.0 до шейпера)
LEGACY_IFB = "rwthrottle0"
LEGACY_IFB_PREF = 29303

# Дальше этого срока пакет скачивания не откладываем, а отбрасываем
HORIZON_NS = 2_000_000_000
# Запас полисера отдачи: столько времени при потолке можно «занять вперёд»
BURST_NS = 200_000_000

MAX_PORTS = 64            # размер карты rws_ports
MAX_PERSONAL = 16384      # размер карты rws_personal
MAX_KBIT = 100_000_000    # 100 Гбит/с — всё, что выше, опечатка
MIN_PENALTY_KBIT = 64

#: Код выхода «пинов нет — нужна полная установка»
RELOAD_EXIT = 3


@dataclass(frozen=True)
class ShaperConfig:
    """Общий шейпер ноды."""
    enabled: bool
    ports: tuple = ()
    down_kbit: int = 0
    up_kbit: int = 0
    penalty_mb: int = 0          # 0 — штраф выключен
    penalty_window_sec: int = 0
    penalty_kbit: int = 0
    penalty_minutes: int = 0


DISABLED = ShaperConfig(enabled=False)


def _int(value, name: str, low: int, high: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name}: expected a number")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: expected a number") from None
    if not low <= number <= high:
        raise ValueError(f"{name}: must be between {low} and {high}")
    return number


def parse_config(msg: dict) -> ShaperConfig:
    """Разобрать команду панели. В скрипт попадают только проверенные числа."""
    if not msg.get("enabled"):
        return DISABLED

    raw_ports = msg.get("ports") or []
    if not isinstance(raw_ports, list):
        raise ValueError("ports: expected a list")
    ports = sorted({_int(p, "ports", 1, 65535) for p in raw_ports})
    if not ports:
        # Без списка портов под потолок попали бы и собственные соединения
        # ноды в интернет — а там адрес получателя уже не клиент, а сайт
        raise ValueError("ports: at least one inbound port is required")
    if len(ports) > MAX_PORTS:
        raise ValueError(f"ports: at most {MAX_PORTS}")

    down = _int(msg.get("down_kbit", 0), "down_kbit", 0, MAX_KBIT)
    up = _int(msg.get("up_kbit", 0), "up_kbit", 0, MAX_KBIT)

    penalty = msg.get("penalty") or {}
    if not isinstance(penalty, dict):
        raise ValueError("penalty: expected an object")
    if penalty.get("enabled"):
        mb = _int(penalty.get("mb"), "penalty.mb", 1, 10_000_000)
        window = _int(penalty.get("window_sec"), "penalty.window_sec", 10, 86_400)
        kbit = _int(penalty.get("kbit"), "penalty.kbit", MIN_PENALTY_KBIT, MAX_KBIT)
        minutes = _int(penalty.get("minutes"), "penalty.minutes", 1, 10_080)
    else:
        mb = window = kbit = minutes = 0

    if not down and not up and not mb:
        raise ValueError("nothing to shape: set a speed cap or the penalty mode")

    return ShaperConfig(
        enabled=True, ports=tuple(ports), down_kbit=down, up_kbit=up,
        penalty_mb=mb, penalty_window_sec=window,
        penalty_kbit=kbit, penalty_minutes=minutes,
    )


def parse_personal(raw_rules: Iterable) -> tuple:
    """Правила мягкой блокировки → ({адрес: кбит/с}, пропущено).

    Адрес нормализуется, скорость — целое больше нуля: 0 значит «без лимита»,
    и такой адрес в карту не попадает. Два правила на один адрес — берём
    меньшую скорость.
    """
    personal: Dict[str, int] = {}
    skipped = 0
    for item in raw_rules or []:
        try:
            addr = ipaddress.ip_address(str(item.get("ip", "")).strip())
            rate = int(item.get("rate_kbit"))
        except (AttributeError, TypeError, ValueError):
            skipped += 1
            continue
        if rate <= 0 or rate > MAX_KBIT:
            skipped += 1
            continue
        ip = str(addr)
        personal[ip] = min(rate, personal.get(ip, rate))
    if len(personal) > MAX_PERSONAL:
        skipped += len(personal) - MAX_PERSONAL
        personal = dict(sorted(personal.items())[:MAX_PERSONAL])
    return personal, skipped


def _bytes_per_sec(kbit: int) -> int:
    return kbit * 1000 // 8


def encode_cfg(cfg: ShaperConfig, l2_len: int) -> bytes:
    """Значение карты rws_cfg — порядок полей как в struct shaper_cfg."""
    return struct.pack(
        "<9Q",
        l2_len,
        _bytes_per_sec(cfg.down_kbit),
        _bytes_per_sec(cfg.up_kbit),
        HORIZON_NS,
        BURST_NS,
        cfg.penalty_mb * 1024 * 1024,
        cfg.penalty_window_sec * 1_000_000_000,
        _bytes_per_sec(cfg.penalty_kbit),
        cfg.penalty_minutes * 60 * 1_000_000_000,
    )


def client_key(ip: str) -> bytes:
    """Ключ карт по адресу клиента: IPv6 как есть, IPv4 как ::ffff:a.b.c.d."""
    addr = ipaddress.ip_address(ip)
    if addr.version == 4:
        addr = ipaddress.IPv6Address(f"::ffff:{addr}")
    return addr.packed


def encode_personal(kbit: int) -> bytes:
    """Значение карты rws_personal: одна скорость на обе стороны."""
    rate = _bytes_per_sec(kbit)
    return struct.pack("<2Q", rate, rate)


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data)


_IFACE = [
    'IFACE=$(ip route show default 2>/dev/null | awk \'/default/ {print $5; exit}\')',
    '[ -n "$IFACE" ] || { echo "ERROR=no default route interface"; exit 1; }',
    'echo "IFACE=$IFACE"',
]

_HAD = ['HAD=""']

# Прежние раскладки мягкой блокировки. Узнаются по своим меткам и снимаются
# один раз; идёт до решения про корень — старый prio иначе сочли бы чужим.
_LEGACY = [
    "if tc qdisc show dev \"$IFACE\" | grep -q '^qdisc htb 40: parent 1:4 '; then",
    '  tc qdisc del dev "$IFACE" root',
    '  echo "LEGACY=prio"',
    "fi",
    f'OLD=$(tc filter show dev "$IFACE" egress pref {LEGACY_IFB_PREF} 2>/dev/null || true)',
    'case "$OLD" in',
    f'  *"{LEGACY_IFB}"*) tc filter del dev "$IFACE" egress pref {LEGACY_IFB_PREF} protocol ip; '
    'HAD=1; echo "LEGACY=ifb" ;;',
    "esac",
    f"ip link del {LEGACY_IFB} 2>/dev/null || true",
]


def _remove_filters(strict: bool) -> List[str]:
    """Снять свои фильтры с обоих хуков. Своё — наш приоритет и имя программы."""
    foreign = (
        f'      *) echo "ERROR=$HOOK pref {SHAPER_PREF} on $IFACE is taken by another tool"; exit 1 ;;'
        if strict else
        '      *) echo "FOREIGN=$HOOK" ;;'
    )
    return [
        "for HOOK in egress ingress; do",
        f'  OURS=$(tc filter show dev "$IFACE" $HOOK pref {SHAPER_PREF} 2>/dev/null || true)',
        '  if [ -n "$OURS" ]; then',
        '    case "$OURS" in',
        f'      *rws_*) tc filter del dev "$IFACE" $HOOK pref {SHAPER_PREF}; HAD=1 ;;',
        foreign,
        "    esac",
        "  fi",
        "done",
    ]


def _personal_updates(personal: Dict[str, int]) -> List[str]:
    return [
        f"bpftool map update pinned {PIN_DIR}/maps/rws_personal "
        f"key hex {_hex(client_key(ip))} value hex {_hex(encode_personal(kbit))}"
        for ip, kbit in sorted(personal.items())
    ]


def build_apply_script(cfg: ShaperConfig, personal: Optional[Dict[str, int]] = None) -> str:
    """Поставить программу заново: общий шейпер (может быть выключен) и
    персональные лимиты. Прежняя установка снимается целиком."""
    personal = personal or {}
    ports = [
        f"bpftool map update pinned {PIN_DIR}/maps/rws_ports "
        f"key hex {_hex(struct.pack('<H', port))} value hex 01"
        for port in (cfg.ports if cfg.enabled else ())
    ]
    lines = ["set -e", *_IFACE, *_HAD, *_LEGACY, *_remove_filters(strict=True)]
    lines += [
        # Своя bpffs: смонтирована — чистим прошлые пины, нет — монтируем
        f"if mountpoint -q {PIN_DIR}; then rm -rf {PIN_DIR}/progs {PIN_DIR}/maps; "
        f"else mkdir -p {PIN_DIR} && mount -t bpf bpf {PIN_DIR}; fi",
        # Корень: время отправки выдерживает только fq. Дефолтную дисциплину
        # ядра меняем на свою fq с меткой, чужую не трогаем.
        "ROOT=$(tc qdisc show dev \"$IFACE\" | awk '$4 == \"root\" {print $2, $3; exit}')",
        'KIND=${ROOT%% *}; HANDLE=${ROOT#* }',
        "NONFQ=$(tc qdisc show dev \"$IFACE\" | awk '$4 == \"parent\" && $5 != \"ffff:fff1\" "
        "&& $2 != \"fq\" {n++} END {print n+0}')",
        'if [ "$KIND" = fq ] || { [ "$KIND" = mq ] && [ "$NONFQ" = 0 ]; }; then',
        '  echo "ROOT=kept:$KIND"',
        'elif [ "$HANDLE" = "0:" ]; then',
        '  if [ "$KIND" = mq ]; then',
        f'    tc qdisc replace dev "$IFACE" root handle {ROOT_HANDLE} mq',
        "    for Q in $(tc qdisc show dev \"$IFACE\" | awk '$4 == \"parent\" && "
        f"$5 ~ /^{ROOT_HANDLE}/ {{print $5}}'); do",
        '      tc qdisc replace dev "$IFACE" parent "$Q" fq',
        "    done",
        "  else",
        f'    tc qdisc replace dev "$IFACE" root handle {ROOT_HANDLE} fq',
        "  fi",
        '  echo "ROOT=installed:$KIND"',
        "else",
        '  echo "ROOT=foreign:$KIND"',
        "fi",
        f"bpftool prog loadall {BPF_OBJECT} {PIN_DIR}/progs type classifier pinmaps {PIN_DIR}/maps",
        # Заголовок канального уровня есть не у всех интерфейсов
        "if ip -o link show dev \"$IFACE\" | grep -q 'link/ether'; then",
        f'  CFG="{_hex(encode_cfg(cfg if cfg.enabled else DISABLED, 14))}"',
        "else",
        f'  CFG="{_hex(encode_cfg(cfg if cfg.enabled else DISABLED, 0))}"',
        "fi",
        f"bpftool map update pinned {PIN_DIR}/maps/rws_cfg key hex 00 00 00 00 value hex $CFG",
        *ports,
        *_personal_updates(personal),
        # Чужой clsact годится как есть: пересоздание снесло бы его фильтры
        "if ! tc qdisc show dev \"$IFACE\" | grep -q '^qdisc clsact '; then",
        "  if tc qdisc show dev \"$IFACE\" | grep -q '^qdisc ingress '; then",
        '    echo "ERROR=$IFACE has an ingress qdisc, clsact cannot be added"; exit 1',
        "  fi",
        '  tc qdisc add dev "$IFACE" clsact',
        "fi",
        f'tc filter add dev "$IFACE" egress pref {SHAPER_PREF} bpf da pinned {PIN_DIR}/progs/rws_egress',
        f'tc filter add dev "$IFACE" ingress pref {SHAPER_PREF} bpf da pinned {PIN_DIR}/progs/rws_ingress',
        f'echo "PERSONAL={len(personal)}"',
        'echo "ACTIVE=1"',
    ]
    return "\n".join(lines)


def build_personal_update_script(to_set: Dict[str, int], to_delete: Iterable[str]) -> str:
    """Поменять персональные лимиты, не перезагружая программу.

    Перезагрузка обнулила бы состояние клиентов — и штраф качальщика вместе
    с ним, а адреса урезанных меняются по нескольку раз в сутки. Пинов нет
    (агент перезапускался) — выходим с RELOAD_EXIT, нужна полная установка.
    """
    lines = [
        "set -e",
        f'[ -e {PIN_DIR}/maps/rws_personal ] || {{ echo "RELOAD=1"; exit {RELOAD_EXIT}; }}',
        *_personal_updates(to_set),
    ]
    lines += [
        f"bpftool map delete pinned {PIN_DIR}/maps/rws_personal "
        f"key hex {_hex(client_key(ip))} 2>/dev/null || true"
        for ip in sorted(to_delete)
    ]
    lines.append('echo "UPDATED=1"')
    return "\n".join(lines)


def build_disable_script() -> str:
    """Снять шейпер и вернуть ноду как было. Чужое не трогается."""
    lines = ["set -e", *_IFACE, *_HAD, *_LEGACY, *_remove_filters(strict=False)]
    lines += [
        # Корень снимаем, только если fq ставили мы: ядро вернёт дефолтную
        "if [ \"$(tc qdisc show dev \"$IFACE\" | awk '$4 == \"root\" {print $3; exit}')\" "
        f'= "{ROOT_HANDLE}" ]; then',
        '  tc qdisc del dev "$IFACE" root',
        '  echo "ROOT=restored"',
        "fi",
        # clsact мог быть нашим. Если после нас на нём пусто — убираем
        'if [ -n "$HAD" ] && [ -z "$(tc filter show dev "$IFACE" egress 2>/dev/null)" ] '
        '&& [ -z "$(tc filter show dev "$IFACE" ingress 2>/dev/null)" ]; then',
        '  tc qdisc del dev "$IFACE" clsact 2>/dev/null || true',
        "fi",
        f"if mountpoint -q {PIN_DIR}; then umount {PIN_DIR}; fi",
        'echo "ACTIVE=0"',
    ]
    return "\n".join(lines)


#: Дамп карты штрафов; своя bpffs видна только контейнеру агента
PENALTIES_DUMP = f"bpftool -j map dump pinned {PIN_DIR}/maps/rws_penalties"


def _raw_bytes(value) -> bytes:
    """bpftool -j печатает байты списком строк «0x..»."""
    return bytes(int(str(b), 16) for b in value)


def _key_to_ip(key: bytes) -> str:
    addr = ipaddress.IPv6Address(key)
    return str(addr.ipv4_mapped or addr)


def parse_penalties(output: str, now_mono_ns: int, now_wall: float) -> List[dict]:
    """События штрафов из дампа карты rws_penalties.

    Программа пишет время по CLOCK_MONOTONIC (bpf_ktime_get_ns); в стенное
    его переводим через текущие показания обоих часов.
    """
    import json

    try:
        items = json.loads(output or "[]")
    except ValueError:
        return []
    events = []
    for item in items if isinstance(items, list) else []:
        try:
            key = _raw_bytes(item["key"])
            start_ns, until_ns, total = struct.unpack("<3Q", _raw_bytes(item["value"])[:24])
            ip = _key_to_ip(key)
        except (KeyError, TypeError, ValueError, struct.error):
            continue
        events.append({
            "ip": ip,
            "start_ns": start_ns,
            "started_at": now_wall - (now_mono_ns - start_ns) / 1e9,
            "until": now_wall - (now_mono_ns - until_ns) / 1e9,
            "bytes": total,
        })
    return events


def parse_report(output: str) -> Dict[str, str]:
    """Строки KEY=VALUE из вывода скрипта; прочее — диагностика tc и bpftool."""
    report: Dict[str, str] = {}
    for line in output.splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key.isupper() and key.isalpha():
            report[key] = value
    return report


def summarize(cfg: ShaperConfig, output: str, exit_code: int, personal: int = 0) -> dict:
    """Ответ панели: работает ли общий шейпер и что стало с корнем."""
    report = parse_report(output)
    root: Optional[str] = report.get("ROOT")
    error = report.get("ERROR")
    if exit_code != 0 and not error:
        tail = [line for line in output.strip().splitlines() if line.strip()]
        error = tail[-1] if tail else f"exit code {exit_code}"
    loaded = exit_code == 0 and report.get("ACTIVE") == "1"
    return {
        "enabled": cfg.enabled,
        # Программа может стоять ради персональных лимитов при выключенном общем
        "active": loaded and cfg.enabled,
        "loaded": loaded,
        "personal": personal,
        "interface": report.get("IFACE"),
        "root": root,
        # Без fq в корне время отправки никто не выдерживает — скачивание
        # режется отбрасыванием, грубее и с потерями
        "download_exact": bool(root) and not root.startswith("foreign:"),
        "error": error,
    }

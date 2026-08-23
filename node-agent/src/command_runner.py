"""
Agent Command Runner — routes and executes commands from the backend.

Handles command types: exec_script, shell_session, pty_input, service_status.
Includes HMAC signature verification and forbidden pattern blocking.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import re
import time
from typing import Any, Callable, Awaitable, Dict, Optional

from .config import Settings

logger = logging.getLogger(__name__)

# ── Security: Forbidden Patterns ──────────────────────────────────

FORBIDDEN_PATTERNS = [
    re.compile(r'rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\s*$', re.IGNORECASE),     # rm -rf /
    re.compile(r'rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+)?/\*', re.IGNORECASE),        # rm -rf /*
    re.compile(r'mkfs\b', re.IGNORECASE),                                       # mkfs
    re.compile(r'dd\s+if=', re.IGNORECASE),                                     # dd if=
    re.compile(r':\(\)\s*\{\s*:\|\s*:\s*&\s*\}\s*;', re.IGNORECASE),          # fork bomb
    re.compile(r'shutdown\s+(-[hPr]\s+)?now', re.IGNORECASE),                  # shutdown
    re.compile(r'init\s+0', re.IGNORECASE),                                     # init 0
    re.compile(r'halt\b', re.IGNORECASE),                                       # halt
    re.compile(r'poweroff\b', re.IGNORECASE),                                   # poweroff
    re.compile(r'>\s*/dev/sd[a-z]', re.IGNORECASE),                            # write to disk device
    re.compile(r'chmod\s+-R\s+777\s+/', re.IGNORECASE),                         # chmod -R 777 /
]

ALLOWED_COMMAND_TYPES = {
    "exec_script",
    "shell_session",
    "pty_input",
    "pty_resize",
    "service_status",
    "sync_blocked_ips",
    "sync_throttled_ips",
    "set_ndpi",
    "ping",
}


def _is_forbidden(command_text: str) -> bool:
    """Check if a command matches any forbidden pattern."""
    for pattern in FORBIDDEN_PATTERNS:
        if pattern.search(command_text):
            return True
    return False


# ── HMAC Verification ────────────────────────────────────────────

def _derive_key(secret_key: str, agent_token: str) -> bytes:
    """Derive HMAC key from secret + agent token."""
    return hashlib.sha256(f"{secret_key}:{agent_token}".encode()).digest()


def verify_signature(
    payload: Dict[str, Any],
    signature: str,
    secret_key: str,
    agent_token: str,
    max_age_seconds: int = 60,
) -> bool:
    """Verify HMAC-SHA256 signature and timestamp freshness."""
    ts = payload.get("_ts")
    if ts is None:
        return False

    now = int(time.time())
    if abs(now - ts) > max_age_seconds:
        return False

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    key = _derive_key(secret_key, agent_token)
    expected = hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── Command Runner ───────────────────────────────────────────────

class CommandRunner:
    """Routes and executes commands received via Agent v2 WebSocket."""

    def __init__(
        self,
        settings: Settings,
        send_fn: Callable[[dict], Awaitable[bool]],
        ndpi_control: Optional[Callable[..., Awaitable[dict]]] = None,
    ):
        self._settings = settings
        self._send = send_fn
        # Включение nDPI приходит командой из панели, чтобы оператору не
        # пришлось лезть в .env на каждой ноде. Сам агент решать за панель
        # ничего не должен, поэтому здесь только вызов контроллера.
        self._ndpi_control = ndpi_control

    async def handle(self, msg: dict) -> None:
        """Route an incoming command message."""
        msg_type = msg.get("type")
        if not msg_type:
            return

        if msg_type not in ALLOWED_COMMAND_TYPES:
            logger.warning("Unknown command type: %s", msg_type)
            return

        # Verify HMAC signature (skip for ping)
        if msg_type != "ping":
            signature = msg.get("_sig")
            payload = {k: v for k, v in msg.items() if k != "_sig"}

            if not signature or not verify_signature(
                payload,
                signature,
                self._settings.ws_secret_key,
                self._settings.auth_token,
            ):
                logger.warning("HMAC verification failed for %s", msg_type)
                await self._send({
                    "type": "command_result",
                    "command_id": msg.get("command_id"),
                    "status": "error",
                    "output": "HMAC signature verification failed",
                    "exit_code": -1,
                })
                return

        # Dispatch
        if msg_type == "exec_script":
            await self._exec_script(msg)
        elif msg_type == "shell_session":
            await self._shell_session(msg)
        elif msg_type == "pty_input":
            await self._pty_input(msg)
        elif msg_type == "pty_resize":
            await self._pty_resize(msg)
        elif msg_type == "service_status":
            await self._service_status(msg)
        elif msg_type == "sync_blocked_ips":
            await self._sync_blocked_ips(msg)
        elif msg_type == "sync_throttled_ips":
            await self._sync_throttled_ips(msg)
        elif msg_type == "set_ndpi":
            await self._set_ndpi(msg)

    async def _run_shell(self, script: str, timeout: int) -> tuple:
        """Run a shell script (on the HOST via nsenter when host_mode).

        Returns (output, exit_code); exit_code -1 on timeout.
        """
        if self._settings.host_mode:
            import shlex
            shell_cmd = (
                "nsenter --target 1 --mount --uts --ipc --net --pid -- "
                f"/bin/sh -c {shlex.quote(script)}"
            )
        else:
            shell_cmd = script

        proc = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            return output, proc.returncode or 0
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "Command timed out", -1

    async def _exec_script(self, msg: dict) -> None:
        """Execute a script on this node."""
        script_content = msg.get("script_content", "")
        command_id = msg.get("command_id")
        timeout = msg.get("timeout", 60)

        # Security check
        if _is_forbidden(script_content):
            logger.warning("Blocked forbidden script (cmd_id=%s)", command_id)
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "blocked",
                "output": "Command blocked by security policy",
                "exit_code": -1,
            })
            return

        # Аудит: фиксируем, ЧТО именно выполняется (первая строка + хэш) —
        # раньше в логах был только cmd_id, восстановить команду было нельзя
        import hashlib
        first_line = next(
            (ln.strip() for ln in script_content.splitlines()
             if ln.strip() and not ln.strip().startswith("#")), "")
        script_hash = hashlib.sha256(script_content.encode()).hexdigest()[:12]
        logger.info(
            "Executing script (cmd_id=%s, timeout=%ds, host_mode=%s, "
            "sha256=%s, %d bytes): %.120s",
            command_id, timeout, self._settings.host_mode,
            script_hash, len(script_content), first_line,
        )

        try:
            output, exit_code = await self._run_shell(script_content, timeout)

            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "completed" if exit_code == 0 else "error",
                "output": output[-50000:],  # Limit output size
                "exit_code": exit_code,
            })

        except Exception as e:
            logger.exception("Script execution error (cmd_id=%s): %s", command_id, e)
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "error",
                "output": str(e),
                "exit_code": -1,
            })

    async def _sync_blocked_ips(self, msg: dict) -> None:
        """Apply the backend's IP blocklist on this node (ipset or iptables chain).

        Payload: {"ips": ["1.2.3.4/32", ...], "mode": "replace"}.
        The full list replaces the previous one atomically (ipset swap /
        chain flush), so an empty list clears all blocks.
        """
        import ipaddress

        command_id = msg.get("command_id")
        raw_ips = msg.get("ips") or []

        # Validate every entry — only clean CIDR strings reach the shell
        v4, v6, skipped = [], [], 0
        for item in raw_ips:
            try:
                net = ipaddress.ip_network(str(item), strict=False)
                (v4 if net.version == 4 else v6).append(str(net))
            except ValueError:
                skipped += 1
        if skipped:
            logger.warning("sync_blocked_ips: skipped %d invalid entries", skipped)

        script = self._build_blocklist_script(v4, v6)
        output, exit_code = await self._run_shell(script, timeout=120)

        if exit_code == 0:
            logger.info("Blocklist applied: %d IPv4, %d IPv6", len(v4), len(v6))
        else:
            logger.error(
                "Blocklist apply failed (exit=%d): %.500s", exit_code, output
            )

        if command_id:
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "completed" if exit_code == 0 else "error",
                "output": output[-10000:],
                "exit_code": exit_code,
            })

    async def _sync_throttled_ips(self, msg: dict) -> None:
        """Ограничить скорость к указанным адресам на этой ноде (tc HTB).

        Payload: {"rules": [{"ip": "1.2.3.4", "rate_kbit": 1024}, ...]}.

        Список заменяет прежний целиком, поэтому пустой снимает все
        ограничения. Режется исходящий трафик ноды к адресу — то есть
        скачивание у клиента; отдача идёт входящей стороной, её tc без
        отдельного ifb-интерфейса не шейпит.

        Ограничение вешается на адрес, а не на порт или пользователя: так
        не нужно ни трогать конфиг Xray, ни переносить человека между
        сквадами, и мера применяется мгновенно.
        """
        import ipaddress

        command_id = msg.get("command_id")
        raw_rules = msg.get("rules") or []

        # До шелла доходят только разобранный адрес и целое число — оба
        # приходят снаружи, и подставлять их в скрипт как есть нельзя.
        rules, skipped = [], 0
        for item in raw_rules:
            try:
                addr = ipaddress.ip_address(str(item.get("ip", "")).strip())
                rate = int(item.get("rate_kbit"))
            except (AttributeError, TypeError, ValueError):
                skipped += 1
                continue
            if addr.version != 4 or rate <= 0:
                # IPv6 в подключениях пока не встречается, а фильтр под него
                # нужен отдельный — молча резать не тот трафик хуже, чем не резать.
                skipped += 1
                continue
            rules.append((str(addr), rate))

        if skipped:
            logger.warning("sync_throttled_ips: skipped %d invalid entries", skipped)

        script = self._build_throttle_script(rules)
        output, exit_code = await self._run_shell(script, timeout=60)

        if exit_code == 0:
            logger.info("Throttling applied: %d addresses", len(rules))
        else:
            logger.error("Throttling failed (exit=%d): %.500s", exit_code, output)

        if command_id:
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "completed" if exit_code == 0 else "error",
                "output": output[-10000:],
                "exit_code": exit_code,
            })

    @staticmethod
    def _build_throttle_script(rules: list) -> str:
        """Собрать POSIX-скрипт, целиком заменяющий текущую раскладку tc.

        Корнем стоит prio с priomap из одних нулей: весь неразмеченный
        трафик уходит в первую полосу, где никакого ограничителя нет. HTB
        висит только на отдельной полосе, куда фильтры заводят наказанные
        адреса.

        Так сделано ради безопасности. Если завернуть в HTB весь трафик,
        дисциплине придётся сообщить ширину канала — и ошибка в этом числе
        придушит всех пользователей ноды разом. Здесь знать ширину не нужно
        вовсе: обычный трафик ограничителя просто не касается.

        Режется исходящий трафик ноды к адресу, то есть скачивание у
        клиента; отдача идёт входящей стороной, её tc без отдельного
        ifb-интерфейса не шейпит.
        """
        lines = [
            "set -e",
            'IFACE=$(ip route show default 2>/dev/null | awk \'/default/ {print $5; exit}\')',
            '[ -n "$IFACE" ] || { echo "no default route interface"; exit 1; }',
            # Прежняя раскладка снимается всегда: список приходит целиком,
            # и разбирать разницу дороже, чем собрать заново.
            'tc qdisc del dev "$IFACE" root 2>/dev/null || true',
        ]

        if not rules:
            lines.append('echo "throttling cleared on $IFACE"')
            return "\n".join(lines)

        lines += [
            # priomap из нулей: без явного фильтра пакет всегда идёт в 1:1.
            'tc qdisc add dev "$IFACE" root handle 1: prio bands 4 '
            'priomap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0',
            # Ограничитель — только на четвёртой полосе, отдельно от всех.
            'tc qdisc add dev "$IFACE" parent 1:4 handle 40: htb',
        ]

        for index, (ip, rate_kbit) in enumerate(rules, start=10):
            lines += [
                f'tc class add dev "$IFACE" parent 40: classid 40:{index} '
                f'htb rate {rate_kbit}kbit ceil {rate_kbit}kbit burst 32k',
                # Первый фильтр уводит адрес на полосу ограничителя,
                # второй — в его личный класс с нужной скоростью.
                f'tc filter add dev "$IFACE" protocol ip parent 1:0 prio 1 u32 '
                f'match ip dst {ip}/32 flowid 1:4',
                f'tc filter add dev "$IFACE" protocol ip parent 40: prio 1 u32 '
                f'match ip dst {ip}/32 flowid 40:{index}',
            ]

        lines.append(f'echo "throttled {len(rules)} addresses on $IFACE"')
        return "\n".join(lines)

    @staticmethod
    def _build_blocklist_script(v4: list, v6: list) -> str:
        """Build a POSIX script that atomically replaces the node blocklist."""
        lines = ["set -e"]

        # IPv4: ipset (atomic swap) with plain iptables-chain fallback
        lines.append("if command -v ipset >/dev/null 2>&1; then")
        lines.append("  ipset create remnawave-block hash:net -exist")
        lines.append("  ipset create remnawave-block-tmp hash:net -exist")
        lines.append("  ipset flush remnawave-block-tmp")
        for ip in v4:
            lines.append(f"  ipset add remnawave-block-tmp {ip} -exist")
        lines.append("  ipset swap remnawave-block-tmp remnawave-block")
        lines.append("  ipset destroy remnawave-block-tmp")
        lines.append(
            "  iptables -C INPUT -m set --match-set remnawave-block src -j DROP 2>/dev/null"
            " || iptables -I INPUT 1 -m set --match-set remnawave-block src -j DROP"
        )
        lines.append(
            "  iptables -C FORWARD -m set --match-set remnawave-block src -j DROP 2>/dev/null"
            " || iptables -I FORWARD 1 -m set --match-set remnawave-block src -j DROP"
        )
        lines.append("else")
        lines.append("  iptables -N REMNAWAVE-BLOCK 2>/dev/null || true")
        lines.append("  iptables -F REMNAWAVE-BLOCK")
        for ip in v4:
            lines.append(f"  iptables -A REMNAWAVE-BLOCK -s {ip} -j DROP")
        lines.append(
            "  iptables -C INPUT -j REMNAWAVE-BLOCK 2>/dev/null"
            " || iptables -I INPUT 1 -j REMNAWAVE-BLOCK"
        )
        lines.append(
            "  iptables -C FORWARD -j REMNAWAVE-BLOCK 2>/dev/null"
            " || iptables -I FORWARD 1 -j REMNAWAVE-BLOCK"
        )
        lines.append("fi")

        # IPv6: only when ip6tables is present (skip silently otherwise)
        lines.append("if command -v ip6tables >/dev/null 2>&1; then")
        lines.append("  ip6tables -N REMNAWAVE-BLOCK 2>/dev/null || true")
        lines.append("  ip6tables -F REMNAWAVE-BLOCK")
        for ip in v6:
            lines.append(f"  ip6tables -A REMNAWAVE-BLOCK -s {ip} -j DROP")
        lines.append(
            "  ip6tables -C INPUT -j REMNAWAVE-BLOCK 2>/dev/null"
            " || ip6tables -I INPUT 1 -j REMNAWAVE-BLOCK"
        )
        lines.append(
            "  ip6tables -C FORWARD -j REMNAWAVE-BLOCK 2>/dev/null"
            " || ip6tables -I FORWARD 1 -j REMNAWAVE-BLOCK"
        )
        lines.append("fi")
        return "\n".join(lines)

    async def _shell_session(self, msg: dict) -> None:
        """Start or close a shell session."""
        from .pty_provider import pty_manager

        session_id = msg.get("session_id", "")
        action = msg.get("action", "open")
        command_id = msg.get("command_id")

        if action == "close":
            await pty_manager.close_session(session_id)
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "completed",
                "output": "Session closed",
                "exit_code": 0,
            })
            return

        # Open new PTY session
        cols = msg.get("cols", 80)
        rows = msg.get("rows", 24)

        async def on_pty_output(sid: str, data: bytes) -> None:
            """Forward PTY output to backend via WS."""
            import base64
            await self._send({
                "type": "pty_output",
                "session_id": sid,
                "data": base64.b64encode(data).decode("ascii"),
            })

        try:
            await pty_manager.create_session(
                session_id, on_pty_output, cols, rows,
                host_mode=self._settings.host_mode,
            )
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "completed",
                "output": "Session opened",
                "exit_code": 0,
            })
        except Exception as e:
            logger.exception("Failed to start PTY session: %s", e)
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "error",
                "output": str(e),
                "exit_code": -1,
            })

    async def _pty_input(self, msg: dict) -> None:
        """Forward keyboard input to PTY."""
        import base64
        from .pty_provider import pty_manager

        session_id = msg.get("session_id", "")
        data_b64 = msg.get("data", "")

        session = pty_manager.get_session(session_id)
        if not session:
            return

        try:
            data = base64.b64decode(data_b64)
            await session.write(data)
        except Exception as e:
            logger.debug("PTY input error: %s", e)

    async def _pty_resize(self, msg: dict) -> None:
        """Resize terminal."""
        from .pty_provider import pty_manager

        session_id = msg.get("session_id", "")
        cols = msg.get("cols", 80)
        rows = msg.get("rows", 24)

        session = pty_manager.get_session(session_id)
        if session:
            session.resize(cols, rows)

    async def _set_ndpi(self, msg: dict) -> None:
        """Включить или выключить чтение вердиктов nDPI.

        Отвечаем честно: включить чтение можно всегда, а вот демона на ноде
        может не быть вовсе. Панель должна видеть разницу между «включено и
        работает» и «включено, но сокета нет» — иначе тумблер врёт.
        """
        command_id = msg.get("command_id")
        if self._ndpi_control is None:
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "error",
                "output": "nDPI control is not available in this agent build",
                "exit_code": 1,
            })
            return

        try:
            state = await self._ndpi_control(
                enabled=bool(msg.get("enabled")),
                socket_path=msg.get("socket_path") or None,
                window_seconds=msg.get("window_seconds") or None,
            )
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "completed",
                "output": json.dumps(state, ensure_ascii=False),
                "exit_code": 0,
            })
        except Exception as e:
            logger.error("set_ndpi failed: %s", e, exc_info=True)
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "error",
                "output": str(e),
                "exit_code": 1,
            })

    async def _service_status(self, msg: dict) -> None:
        """Get service status information."""
        command_id = msg.get("command_id")
        try:
            proc = await asyncio.create_subprocess_shell(
                "systemctl is-active xray remnanode docker 2>/dev/null || true",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode("utf-8", errors="replace") if stdout else ""

            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "completed",
                "output": output.strip(),
                "exit_code": proc.returncode or 0,
            })
        except Exception as e:
            await self._send({
                "type": "command_result",
                "command_id": command_id,
                "status": "error",
                "output": str(e),
                "exit_code": -1,
            })

"""Seed built-in scripts for the script catalog.

Revision ID: 0027
Revises: 0026
Create Date: 2026-02-15

Seeds ~20 built-in scripts across 4 categories:
security, network, system, monitoring.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0027'
down_revision: Union[str, None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUILTIN_SCRIPTS = [
    # ── Security ──
    {
        "name": "security_updates",
        "display_name": "Install Security Updates",
        "description": "Install only security-related package updates (unattended-upgrades)",
        "category": "security",
        "script_content": "#!/bin/bash\nset -e\napt-get update -qq\napt-get upgrade -y -o Dpkg::Options::='--force-confold' --only-upgrade\necho 'Security updates installed.'",
        "timeout_seconds": 300,
        "requires_root": True,
    },
    {
        "name": "fail2ban_status",
        "display_name": "Fail2ban Status",
        "description": "Show fail2ban jail status and banned IPs",
        "category": "security",
        "script_content": "#!/bin/bash\nif command -v fail2ban-client &>/dev/null; then\n  fail2ban-client status\n  echo '---'\n  fail2ban-client status sshd 2>/dev/null || echo 'sshd jail not found'\nelse\n  echo 'fail2ban not installed'\nfi",
        "timeout_seconds": 15,
        "requires_root": True,
    },
    {
        "name": "install_fail2ban",
        "display_name": "Install Fail2ban",
        "description": "Install and enable fail2ban with default SSH jail",
        "category": "security",
        "script_content": "#!/bin/bash\nset -e\napt-get update -qq\napt-get install -y fail2ban\nsystemctl enable fail2ban\nsystemctl start fail2ban\nfail2ban-client status\necho 'fail2ban installed and running.'",
        "timeout_seconds": 120,
        "requires_root": True,
    },
    {
        "name": "ssh_auth_log",
        "display_name": "SSH Auth Log (last 50)",
        "description": "Show last 50 SSH authentication attempts",
        "category": "security",
        "script_content": "#!/bin/bash\ngrep -i 'sshd' /var/log/auth.log 2>/dev/null | tail -50 || journalctl -u sshd --no-pager -n 50 2>/dev/null || echo 'No SSH logs found'",
        "timeout_seconds": 10,
        "requires_root": True,
    },
    {
        "name": "open_ports",
        "display_name": "List Open Ports",
        "description": "Show all listening TCP/UDP ports",
        "category": "security",
        "script_content": "#!/bin/bash\nss -tulnp 2>/dev/null || netstat -tulnp 2>/dev/null || echo 'Neither ss nor netstat available'",
        "timeout_seconds": 10,
        "requires_root": False,
    },
    # ── Network ──
    {
        "name": "enable_bbr",
        "display_name": "Enable BBR",
        "description": "Enable TCP BBR congestion control for improved throughput",
        "category": "network",
        "script_content": "#!/bin/bash\nset -e\nif sysctl net.ipv4.tcp_congestion_control | grep -q bbr; then\n  echo 'BBR is already enabled'\nelse\n  echo 'net.core.default_qdisc=fq' >> /etc/sysctl.conf\n  echo 'net.ipv4.tcp_congestion_control=bbr' >> /etc/sysctl.conf\n  sysctl -p\n  echo 'BBR enabled.'\nfi\nsysctl net.ipv4.tcp_congestion_control\nsysctl net.core.default_qdisc",
        "timeout_seconds": 15,
        "requires_root": True,
    },
    {
        "name": "network_interfaces",
        "display_name": "Network Interfaces",
        "description": "Show network interfaces and their IP addresses",
        "category": "network",
        "script_content": "#!/bin/bash\nip -br addr show 2>/dev/null || ifconfig 2>/dev/null || echo 'Cannot determine network interfaces'",
        "timeout_seconds": 10,
        "requires_root": False,
    },
    {
        "name": "speed_test",
        "display_name": "Network Speed Test",
        "description": "Run a quick bandwidth test using curl",
        "category": "network",
        "script_content": "#!/bin/bash\necho 'Download speed test (100MB file)...'\ncurl -o /dev/null -w 'Speed: %{speed_download} bytes/sec\\nTime: %{time_total}s\\n' -s 'http://speedtest.tele2.net/100MB.zip' 2>&1 | head -5\necho 'Done.'",
        "timeout_seconds": 120,
        "requires_root": False,
    },
    {
        "name": "dns_check",
        "display_name": "DNS Resolution Check",
        "description": "Test DNS resolution for common domains",
        "category": "network",
        "script_content": "#!/bin/bash\nfor domain in google.com cloudflare.com github.com; do\n  echo -n \"$domain: \"\n  dig +short $domain 2>/dev/null | head -1 || nslookup $domain 2>/dev/null | grep 'Address:' | tail -1 || echo 'FAIL'\ndone",
        "timeout_seconds": 15,
        "requires_root": False,
    },
    {
        "name": "ping_test",
        "display_name": "Ping Test",
        "description": "Ping common endpoints to check connectivity",
        "category": "network",
        "script_content": "#!/bin/bash\nfor host in 1.1.1.1 8.8.8.8 google.com; do\n  echo -n \"$host: \"\n  ping -c 3 -W 2 $host 2>/dev/null | tail -1 || echo 'FAIL'\ndone",
        "timeout_seconds": 30,
        "requires_root": False,
    },
    # ── System ──
    {
        "name": "system_info",
        "display_name": "System Information",
        "description": "Show OS, kernel, CPU, RAM, disk summary",
        "category": "system",
        "script_content": "#!/bin/bash\necho '=== OS ==='\ncat /etc/os-release 2>/dev/null | head -4\necho '\\n=== Kernel ==='\nuname -a\necho '\\n=== CPU ==='\nlscpu | grep -E 'Model name|CPU\\(s\\)|Thread' 2>/dev/null || cat /proc/cpuinfo | head -5\necho '\\n=== Memory ==='\nfree -h\necho '\\n=== Disk ==='\ndf -h / | tail -1",
        "timeout_seconds": 10,
        "requires_root": False,
    },
    {
        "name": "update_system",
        "display_name": "Full System Update",
        "description": "Run apt update && apt upgrade (non-interactive)",
        "category": "system",
        "script_content": "#!/bin/bash\nset -e\nexport DEBIAN_FRONTEND=noninteractive\napt-get update -qq\napt-get upgrade -y -o Dpkg::Options::='--force-confold'\napt-get autoremove -y\necho 'System updated.'",
        "timeout_seconds": 600,
        "requires_root": True,
    },
    {
        "name": "reboot_node",
        "display_name": "Reboot Server",
        "description": "Gracefully reboot the server (1 minute delay)",
        "category": "system",
        "script_content": "#!/bin/bash\necho 'Scheduling reboot in 1 minute...'\nshutdown -r +1 'Scheduled reboot from Remnawave Admin'\necho 'Reboot scheduled. Server will restart in 1 minute.'",
        "timeout_seconds": 10,
        "requires_root": True,
    },
    {
        "name": "docker_status",
        "display_name": "Docker Status",
        "description": "Show running Docker containers and resource usage",
        "category": "system",
        "script_content": "#!/bin/bash\nif command -v docker &>/dev/null; then\n  echo '=== Running Containers ==='\n  docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' 2>/dev/null\n  echo '\\n=== Docker Disk Usage ==='\n  docker system df 2>/dev/null\nelse\n  echo 'Docker not installed'\nfi",
        "timeout_seconds": 15,
        "requires_root": False,
    },
    {
        "name": "cleanup_docker",
        "display_name": "Docker Cleanup",
        "description": "Remove unused Docker images, containers and volumes",
        "category": "system",
        "script_content": "#!/bin/bash\nset -e\nif command -v docker &>/dev/null; then\n  echo 'Before:'\n  docker system df\n  echo '\\nCleaning...'\n  docker system prune -af --volumes 2>&1\n  echo '\\nAfter:'\n  docker system df\nelse\n  echo 'Docker not installed'\nfi",
        "timeout_seconds": 120,
        "requires_root": True,
    },
    {
        "name": "xray_update",
        "display_name": "Update Xray",
        "description": "Update Xray-core to the latest version",
        "category": "system",
        "script_content": "#!/bin/bash\nset -e\necho 'Current Xray version:'\nxray version 2>/dev/null || echo 'Xray not found in PATH'\necho '\\nDownloading latest Xray...'\nbash -c \"$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)\" @ install\necho '\\nNew Xray version:'\nxray version 2>/dev/null || echo 'Check installation'",
        "timeout_seconds": 120,
        "requires_root": True,
    },
    # ── Monitoring ──
    {
        "name": "top_processes",
        "display_name": "Top Processes (CPU)",
        "description": "Show top 15 processes by CPU usage",
        "category": "monitoring",
        "script_content": "#!/bin/bash\nps aux --sort=-%cpu | head -16",
        "timeout_seconds": 10,
        "requires_root": False,
    },
    {
        "name": "top_memory",
        "display_name": "Top Processes (Memory)",
        "description": "Show top 15 processes by memory usage",
        "category": "monitoring",
        "script_content": "#!/bin/bash\nps aux --sort=-%mem | head -16",
        "timeout_seconds": 10,
        "requires_root": False,
    },
    {
        "name": "disk_usage",
        "display_name": "Disk Usage",
        "description": "Show disk usage for all filesystems and top 10 largest directories",
        "category": "monitoring",
        "script_content": "#!/bin/bash\necho '=== Filesystems ==='\ndf -h\necho '\\n=== Top 10 directories in / ==='\ndu -h --max-depth=1 / 2>/dev/null | sort -rh | head -10",
        "timeout_seconds": 30,
        "requires_root": False,
    },
    {
        "name": "journal_errors",
        "display_name": "Recent Errors (journalctl)",
        "description": "Show last 50 error/critical log entries from systemd journal",
        "category": "monitoring",
        "script_content": "#!/bin/bash\njournalctl -p err --no-pager -n 50 2>/dev/null || echo 'journalctl not available'",
        "timeout_seconds": 10,
        "requires_root": True,
    },
    {
        "name": "xray_logs",
        "display_name": "Xray Logs (last 100)",
        "description": "Show last 100 lines of Xray access and error logs",
        "category": "monitoring",
        "script_content": "#!/bin/bash\necho '=== Xray Access Log ==='\ntail -50 /var/log/remnanode/access.log 2>/dev/null || echo 'No access log found'\necho '\\n=== Xray Error Log ==='\ntail -50 /var/log/remnanode/error.log 2>/dev/null || echo 'No error log found'",
        "timeout_seconds": 10,
        "requires_root": False,
    },
]


def upgrade() -> None:
    conn = op.get_bind()

    for script in BUILTIN_SCRIPTS:
        conn.execute(
            sa.text(
                """
                INSERT INTO node_scripts
                    (name, display_name, description, category, script_content,
                     timeout_seconds, requires_root, is_builtin)
                VALUES
                    (:name, :display_name, :description, :category, :script_content,
                     :timeout_seconds, :requires_root, true)
                ON CONFLICT (name) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    description = EXCLUDED.description,
                    category = EXCLUDED.category,
                    script_content = EXCLUDED.script_content,
                    timeout_seconds = EXCLUDED.timeout_seconds,
                    requires_root = EXCLUDED.requires_root
                """
            ),
            script,
        )


def downgrade() -> None:
    op.execute("DELETE FROM node_scripts WHERE is_builtin = true")

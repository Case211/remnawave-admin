"""
Парсер access.log Xray для получения активных подключений.

Формат лога Xray (реальный пример):
  2026/01/28 11:23:18.306521 from 188.170.87.33:20129 accepted tcp:accounts.google.com:443 [Sweden1 >> DIRECT] email: 154

Примечание: по логам видим только connect (accepted). Disconnect и длительность
при необходимости можно выводить из других строк или считать по таймауту на стороне Collector.
"""
import asyncio
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..config import Settings
from ..models import ConnectionReport, TorrentEvent
from .base import BaseCollector

logger = logging.getLogger(__name__)

# Расширенный формат: захватывает destination + routing tags
# 2026/01/28 11:23:18 from 188.170.87.33:20129 accepted tcp:accounts.google.com:443 [Sweden1 >> DIRECT] email: 154
# Группы: timestamp, client_ip, client_port, destination, inbound_tag, outbound_tag, user_id
LOG_PATTERN_EXTENDED = re.compile(
    r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+from\s+"
    r"(?:\[?([0-9a-fA-F:\.]+)\]?)"       # IPv4 или IPv6
    r":(\d+)\s+accepted\s+"
    r"(?:tcp|udp):(\S+)\s+"               # destination (e.g. tracker.example.com:6881)
    r"\[([^\]]*?)\s*>>\s*([^\]]*?)\]\s+"  # [inbound_tag >> outbound_tag]
    r"email:\s*(\d+)",
    re.IGNORECASE,
)

# Fallback: базовый паттерн для нестандартных строк (без routing brackets и т.п.)
LOG_PATTERN_BASIC = re.compile(
    r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+from\s+"
    r"(?:\[?([0-9a-fA-F:\.]+)\]?)"  # IPv4 или IPv6
    r":(\d+)\s+accepted.*?email:\s*(\d+)",
    re.IGNORECASE,
)


def _parse_timestamp(s: str) -> datetime:
    """Парсит Xray timestamp: 2026/01/28 11:23:18.306521 или 2026/01/28 11:23:18 -> datetime UTC."""
    try:
        s = s.strip()
        # Пробуем парсить с микросекундами
        if '.' in s:
            try:
                # Формат: 2026/01/28 11:23:18.306521
                date_part, time_part = s.split(' ', 1)
                time_base, microseconds = time_part.split('.', 1)
                # Ограничиваем микросекунды до 6 цифр
                microseconds = microseconds[:6].ljust(6, '0')
                dt = datetime.strptime(f"{date_part} {time_base}.{microseconds}", "%Y/%m/%d %H:%M:%S.%f")
                return dt
            except ValueError:
                pass

        # Если не получилось с микросекундами, парсим без них
        return datetime.strptime(s.split('.')[0], "%Y/%m/%d %H:%M:%S")
    except ValueError:
        return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_lines(
    lines: list[str],
    node_uuid: str,
    torrent_tag: str = "TORRENT",
) -> tuple[list[ConnectionReport], list[TorrentEvent], int, int, int]:
    """
    Парсит строки лога Xray и возвращает подключения + торрент-события.

    Общая логика парсинга для polling и realtime режимов.
    Подключения группируются по (user_email, ip); торрент-события сохраняются все.

    Returns:
        (connections, torrent_events, lines_count, accepted_lines, matched_lines)
    """
    connections_map: dict[tuple[str, str], tuple[datetime, str]] = {}
    torrent_events: list[TorrentEvent] = []

    lines_count = 0
    accepted_lines = 0
    matched_lines = 0

    for line in lines:
        lines_count += 1
        line = line.strip()
        if not line:
            continue
        if "accepted" not in line.lower():
            continue
        accepted_lines += 1

        # Сначала пробуем расширенный regex (7 групп: с destination и routing tags)
        match = LOG_PATTERN_EXTENDED.search(line)
        if match:
            matched_lines += 1
            ts_str, client_ip, client_port, destination, inbound_tag, outbound_tag, user_id = match.groups()
            user_identifier = f"user_{user_id}"

            try:
                detected_at = _parse_timestamp(ts_str)
            except Exception:
                detected_at = datetime.now(timezone.utc).replace(tzinfo=None)

            # Проверяем торрент-тег
            if outbound_tag.strip().upper() == torrent_tag.upper():
                torrent_events.append(TorrentEvent(
                    user_email=user_identifier,
                    ip_address=client_ip,
                    destination=destination,
                    inbound_tag=inbound_tag.strip(),
                    outbound_tag=outbound_tag.strip(),
                    node_uuid=node_uuid,
                    detected_at=detected_at,
                ))
                continue  # Торрент-подключения не добавляем в обычные connections

            # Обычное подключение
            key = (user_identifier, client_ip)
            if key not in connections_map:
                connections_map[key] = (detected_at, user_identifier)
            else:
                existing_time, _ = connections_map[key]
                if detected_at > existing_time:
                    connections_map[key] = (detected_at, user_identifier)
            continue

        # Fallback: базовый regex (4 группы, без destination/tags)
        match = LOG_PATTERN_BASIC.search(line)
        if not match:
            logger.debug("Line matched 'accepted' but regex failed: %s", line[:100] if len(line) > 100 else line)
            continue
        matched_lines += 1
        ts_str, client_ip, client_port, user_id = match.groups()
        user_identifier = f"user_{user_id}"
        key = (user_identifier, client_ip)

        try:
            connected_at = _parse_timestamp(ts_str)
        except Exception:
            connected_at = datetime.now(timezone.utc).replace(tzinfo=None)

        if key not in connections_map:
            connections_map[key] = (connected_at, user_identifier)
        else:
            existing_time, _ = connections_map[key]
            if connected_at > existing_time:
                connections_map[key] = (connected_at, user_identifier)

    # Преобразуем в список ConnectionReport
    connections = [
        ConnectionReport(
            user_email=user_identifier,
            ip_address=client_ip,
            node_uuid=node_uuid,
            connected_at=connected_at,
            disconnected_at=None,
            bytes_sent=0,
            bytes_received=0,
        )
        for (user_identifier, client_ip), (connected_at, _) in connections_map.items()
    ]

    return connections, torrent_events, lines_count, accepted_lines, matched_lines


class XrayLogCollector(BaseCollector):
    """Читает access.log Xray и возвращает список подключений (accepted)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._log_path = Path(settings.xray_log_path)
        self._buffer_size = settings.log_read_buffer_bytes
        self._node_uuid = settings.node_uuid
        self._torrent_tag = settings.torrent_outbound_tag
        self._torrent_enabled = settings.torrent_detection_enabled
        self._last_torrent_events: list[TorrentEvent] = []

    @property
    def last_torrent_events(self) -> list[TorrentEvent]:
        """Торрент-события из последнего вызова collect()."""
        return self._last_torrent_events

    async def collect(self) -> list[ConnectionReport]:
        """Читает конец лог-файла и парсит строки с 'accepted'."""
        self._last_torrent_events = []

        if not self._log_path.exists():
            logger.warning("Log file does not exist: %s", self._log_path)
            return []

        try:
            # Проверяем размер файла
            stat = await asyncio.to_thread(self._log_path.stat)
            file_size = stat.st_size
            logger.debug("Log file exists, size: %d bytes", file_size)

            if file_size == 0:
                logger.debug("Log file is empty")
                return []

            content = await asyncio.to_thread(
                _read_tail,
                self._log_path,
                self._buffer_size,
            )
            logger.debug("Read %d bytes from log file (last %d bytes)", len(content), min(self._buffer_size, file_size))
        except OSError as e:
            logger.warning("Cannot read log file %s: %s", self._log_path, e)
            return []

        tag = self._torrent_tag if self._torrent_enabled else "__DISABLED__"
        connections, torrent_events, lines_count, accepted_lines, matched_lines = _parse_lines(
            content.splitlines(), self._node_uuid, torrent_tag=tag
        )
        self._last_torrent_events = torrent_events

        torrent_info = f" torrent_events={len(torrent_events)}" if torrent_events else ""
        logger.info(
            "Log parsing: total_lines=%d accepted_lines=%d matched_lines=%d connections=%d%s",
            lines_count,
            accepted_lines,
            matched_lines,
            len(connections),
            torrent_info,
        )
        return connections


def _read_tail(path: Path, size: int) -> str:
    """Читает последние `size` байт файла."""
    with path.open("rb") as f:
        f.seek(0, 2)
        total = f.tell()
        start = max(0, total - size)
        f.seek(start)
        return f.read().decode("utf-8", errors="replace")


class XrayLogRealtimeCollector(BaseCollector):
    """
    Real-time парсер access.log Xray.
    
    Отслеживает позицию в файле и читает только новые строки (как tail -f).
    При старте читает последние N байт для инициализации, затем отслеживает только новые данные.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self._log_path = Path(settings.xray_log_path)
        self._buffer_size = settings.log_read_buffer_bytes
        self._node_uuid = settings.node_uuid
        self._torrent_tag = settings.torrent_outbound_tag
        self._torrent_enabled = settings.torrent_detection_enabled
        self._file_position: int = 0  # Текущая позиция в файле
        self._file_inode: Optional[int] = None  # Inode файла для отслеживания ротации
        self._initialized: bool = False
        self._last_torrent_events: list[TorrentEvent] = []

    @property
    def last_torrent_events(self) -> list[TorrentEvent]:
        """Торрент-события из последнего вызова collect()."""
        return self._last_torrent_events
    
    async def _initialize_position(self) -> None:
        """Инициализирует позицию чтения: читает последние N байт и устанавливает позицию в конец."""
        if not self._log_path.exists():
            logger.warning("Log file does not exist: %s", self._log_path)
            self._file_position = 0
            self._file_inode = None
            return
        
        try:
            stat = await asyncio.to_thread(self._log_path.stat)
            file_size = stat.st_size
            self._file_inode = stat.st_ino
            
            if file_size == 0:
                self._file_position = 0
                logger.debug("Log file is empty, position set to 0")
                return
            
            # Читаем последние N байт для инициализации
            start_pos = max(0, file_size - self._buffer_size)
            self._file_position = start_pos
            
            logger.info(
                "Initialized real-time collector: file_size=%d, start_position=%d, inode=%d",
                file_size, start_pos, self._file_inode
            )
        except OSError as e:
            logger.warning("Cannot initialize log file position %s: %s", self._log_path, e)
            self._file_position = 0
            self._file_inode = None
    
    async def _check_file_rotation(self) -> bool:
        """
        Проверяет, был ли файл ротирован (перезаписан или удалён и создан заново).
        
        Returns:
            True если файл был ротирован, False если всё в порядке
        """
        if not self._log_path.exists():
            logger.warning("Log file disappeared, resetting position")
            self._file_position = 0
            self._file_inode = None
            return True
        
        try:
            stat = await asyncio.to_thread(self._log_path.stat)
            current_inode = stat.st_ino
            current_size = stat.st_size
            
            # Если inode изменился или размер файла меньше нашей позиции - файл ротирован
            if self._file_inode is not None and current_inode != self._file_inode:
                logger.info("Log file rotated (inode changed: %d -> %d), resetting position", 
                           self._file_inode, current_inode)
                self._file_position = 0
                self._file_inode = current_inode
                return True
            
            if current_size < self._file_position:
                logger.info("Log file rotated (size decreased: %d -> %d), resetting position",
                           self._file_position, current_size)
                self._file_position = 0
                self._file_inode = current_inode
                return True
            
            # Обновляем inode если он был None
            if self._file_inode is None:
                self._file_inode = current_inode
            
            return False
        except OSError as e:
            logger.warning("Cannot check file rotation: %s", e)
            return False
    
    async def _read_new_lines(self) -> list[str]:
        """
        Читает новые строки из файла начиная с текущей позиции.
        
        Returns:
            Список новых строк (может быть пустым)
        """
        if not self._log_path.exists():
            return []
        
        try:
            # Проверяем ротацию файла
            await self._check_file_rotation()
            
            # Читаем новые данные
            def _read_from_position(path: Path, position: int) -> tuple[str, int]:
                """Читает данные с указанной позиции, возвращает (content, new_position)."""
                with path.open("rb") as f:
                    f.seek(0, 2)  # Переходим в конец файла
                    file_size = f.tell()
                    
                    if position >= file_size:
                        # Нет новых данных
                        return "", file_size
                    
                    f.seek(position)
                    content = f.read().decode("utf-8", errors="replace")
                    return content, file_size
            
            content, new_position = await asyncio.to_thread(
                _read_from_position,
                self._log_path,
                self._file_position
            )
            
            # Обновляем позицию
            old_position = self._file_position
            self._file_position = new_position
            
            if content:
                lines = content.splitlines(keepends=False)
                logger.debug(
                    "Read %d new lines from position %d to %d (%d bytes)",
                    len(lines), old_position, new_position, len(content)
                )
                return lines
            
            return []
            
        except OSError as e:
            logger.warning("Cannot read new lines from log file %s: %s", self._log_path, e)
            return []
    
    async def collect(self) -> list[ConnectionReport]:
        """
        Читает новые строки из лог-файла и парсит подключения.

        При первом вызове инициализирует позицию (читает последние N байт).
        При последующих вызовах читает только новые данные.
        """
        self._last_torrent_events = []

        # Инициализация при первом вызове
        if not self._initialized:
            await self._initialize_position()
            self._initialized = True

        # Читаем новые строки
        new_lines = await self._read_new_lines()

        if not new_lines:
            return []

        tag = self._torrent_tag if self._torrent_enabled else "__DISABLED__"
        connections, torrent_events, lines_count, accepted_lines, matched_lines = _parse_lines(
            new_lines, self._node_uuid, torrent_tag=tag
        )
        self._last_torrent_events = torrent_events

        if connections or torrent_events:
            torrent_info = f" torrent_events={len(torrent_events)}" if torrent_events else ""
            logger.info(
                "Real-time parsing: new_lines=%d accepted_lines=%d matched_lines=%d connections=%d%s",
                lines_count,
                accepted_lines,
                matched_lines,
                len(connections),
                torrent_info,
            )

        return connections

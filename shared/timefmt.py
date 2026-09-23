"""Время для людей.

В базе и в API время хранится и ходит в UTC. Всё, что читает человек —
уведомления, карточки бота, выгрузки, веб-админка, — показывается в одной
зоне из настройки ``display_timezone`` (IANA, по умолчанию Europe/Moscow)
и подписывается, чтобы не гадать, какое это время.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Optional, Union

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "Europe/Moscow"
SETTING_KEY = "display_timezone"

#: Подписи для зон, которые у нас в ходу; прочие — смещением «UTC+5»
_LABELS = {"Europe/Moscow": "МСК", "UTC": "UTC", "Etc/UTC": "UTC"}

_warned: set = set()

DateLike = Union[datetime, date, str, None]


def zone(name: Optional[str]) -> tzinfo:
    """Зона по имени IANA. Пусто или неизвестная — UTC, с одним предупреждением в лог."""
    name = str(name or "").strip()
    if not name or name.upper() == "UTC":
        return timezone.utc
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except Exception as exc:  # noqa: BLE001 — нет такой зоны или базы tzdata
        if name not in _warned:
            _warned.add(name)
            logger.warning("Часовой пояс «%s» не найден (%s), показываю время в UTC", name, exc)
        return timezone.utc


def zone_name() -> str:
    """Имя зоны из настройки; настройки недоступны — зона по умолчанию."""
    try:
        from shared.config_service import config_service

        return str(config_service.get(SETTING_KEY, DEFAULT_TIMEZONE) or "").strip() or "UTC"
    except Exception:  # noqa: BLE001 — сервис настроек ещё не поднят
        return DEFAULT_TIMEZONE


def display_tz() -> tzinfo:
    return zone(zone_name())


def parse(value: DateLike) -> Optional[datetime]:
    """datetime или ISO-строка → aware datetime в UTC. Время без зоны считается UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    return None


def to_display(value: DateLike) -> Optional[datetime]:
    """Момент времени в зоне отображения."""
    dt = parse(value)
    return dt.astimezone(display_tz()) if dt else None


def now() -> datetime:
    """Текущее время в зоне отображения."""
    return datetime.now(timezone.utc).astimezone(display_tz())


def label(dt: Optional[datetime] = None) -> str:
    """Подпись зоны: «МСК», «UTC» или «UTC+5»."""
    name = zone_name()
    # Зона не нашлась — время показано в UTC, так и подписываем
    if name in _LABELS and (_LABELS[name] == "UTC" or zone(name) is not timezone.utc):
        return _LABELS[name]
    dt = dt or now()
    offset = dt.utcoffset() or timedelta(0)
    if not offset:
        return "UTC"
    total = int(offset.total_seconds() // 60)
    sign = "+" if total > 0 else "-"
    hours, minutes = divmod(abs(total), 60)
    return f"UTC{sign}{hours}" + (f":{minutes:02d}" if minutes else "")


def fmt(value: DateLike, pattern: str = "%d.%m.%Y %H:%M", with_label: bool = True,
        empty: str = "") -> str:
    """Отформатировать момент в зоне отображения, по умолчанию с подписью зоны."""
    dt = to_display(value)
    if dt is None:
        return empty if value in (None, "") else str(value)
    text = dt.strftime(pattern)
    return f"{text} {label(dt)}" if with_label else text


def fmt_date(value: DateLike, pattern: str = "%d.%m.%Y", empty: str = "") -> str:
    """Дата без времени. Чистая дата (без часов) не сдвигается зоной."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.strftime(pattern)
    return fmt(value, pattern, with_label=False, empty=empty)


def parse_filter(value: Optional[str], end: bool = False) -> Optional[datetime]:
    """Граница фильтра по времени из запроса → aware datetime в UTC.

    - «2026-09-23» — сутки в зоне отображения: начало суток, а для конца
      диапазона (end=True) — начало следующих суток, чтобы выбранный день
      попал в выборку целиком;
    - время без пояса — на часах зоны отображения;
    - время с поясом или «Z» — как есть.

    Пусто — None, мусор — ValueError.
    """
    if value is None or not str(value).strip():
        return None
    raw = str(value).strip()
    if len(raw) == 10:
        day = date.fromisoformat(raw)
        start = datetime(day.year, day.month, day.day, tzinfo=display_tz())
        if end:
            start = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=display_tz())
        return start.astimezone(timezone.utc)
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=display_tz())
    return dt.astimezone(timezone.utc)


def sql_zone() -> str:
    """Зона отображения SQL-литералом для «ts AT TIME ZONE …» — чтобы сутки и
    недели в отчётах резались по часам панели, а не по UTC. Имя проверено
    (есть в базе зон и без посторонних символов), иначе — 'UTC'."""
    import re

    name = zone_name()
    if name != "UTC" and re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", name) and zone(name) is not timezone.utc:
        return f"'{name}'"
    return "'UTC'"


def filter_bounds(date_from: Optional[str], date_to: Optional[str]) -> tuple:
    """Пара границ фильтра «с … по …» для запроса «>= since AND < until».

    Кривая граница не валит запрос, а отбрасывается с записью в лог: список
    без фильтра лучше ошибки на всю страницу.
    """
    bounds = []
    for value, end in ((date_from, False), (date_to, True)):
        try:
            bounds.append(parse_filter(value, end=end))
        except ValueError:
            logger.warning("Фильтр по времени отброшен: %r", value)
            bounds.append(None)
    return bounds[0], bounds[1]

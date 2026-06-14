"""Auto-extracted from shared/violation_detector.py."""
import asyncio
import json
import re
import time
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as tz
from itertools import combinations
from math import radians, sin, cos, sqrt, atan2
from typing import List, Dict, Any, Optional, Set
from enum import Enum

from shared.analyzers.models import (
    ViolationAction, TemporalScore, GeoScore, ASNScore, ProfileScore,
    DeviceScore, HwidScore, UserAgentClassification, SuspiciousAgent,
    UserAgentScore, ViolationScore,
)
from shared.connection_monitor import ConnectionMonitor, ActiveConnection, ConnectionStats
from shared.logger import logger

class UserAgentAnalyzer:
    """
    Анализ User-Agent подписочных запросов для детекции двойных туннелей и ботов.

    Классификация:
    - VALID — whitelist известных клиентов (FlClash, Happ, v2rayN и т.д.)
    - LINK_IN_UA — подписочная ссылка (vless://) вставлена в клиент как UA = двойной туннель
    - BOT_LIBRARY — curl, Go-http-client, python-requests = скрипт
    - STUB — обрезанный "Mozilla/5.0" без продолжения
    - EMPTY — UA не передан
    - UNKNOWN — не matched, возможно новый клиент
    """

    WHITELIST_PATTERNS = [
        # iOS/macOS
        r"^Happ/", r"^Stash/", r"^Streisand/", r"^V2Box/", r"^Karing/",
        r"^ShadowRocket/", r"^FoXray/", r"^Loon/", r"^Wings\s?X/",
        # Android
        r"^v2rayNG/", r"^v2raytun/", r"^NekoBox/", r"^Exclave/", r"^Matsuri/", r"^SagerNet/",
        r"^Hiddify/", r"^HiddifyNext/",
        # Clash/Mihomo family (cross-platform)
        r"^FlClash(?:\s?X)?/", r"^ClashX(?:\s?Pro)?/",
        r"^Clash[-\s]?(?:Verge)?(?:[-\s]?Rev)?/", r"^ClashMeta(?:ForAndroid)?/",
        r"^Mihomo(?:\s?Party)?/", r"^koala[-\s]?clash/", r"^Throne/",
        r"^prizrak[-\s]?box/",
        # v2ray core-based
        r"^v2rayN/", r"^Nekoray(?:NG)?/",
        # Core engines
        r"^sing-?box/", r"^Xray/",
    ]

    # Ссылка подписки вставлена вместо UA → гарантированный двойной туннель
    BLACKLIST_LINK_PATTERNS = [
        r"^(?:vless|vmess|trojan|ss|hysteria2?|tuic|socks5?|shadowsocks|wireguard)://",
        r"^https?://",
    ]

    # HTTP-библиотеки / скрипты / инструменты разработки
    BLACKLIST_BOT_PATTERNS = [
        r"^Go-http-client/", r"^curl/", r"^Wget/",
        r"^python-(?:requests|urllib|httpx)/", r"^Java/",
        r"^node(?:-fetch|-superagent)?/", r"^axios/", r"^undici",
        r"^got\s?\(", r"^PostmanRuntime/", r"^Insomnia/", r"^HTTPie/",
    ]

    # "Mozilla/5.0" без продолжения — голый префикс
    STUB_PATTERNS = [
        r"^Mozilla/5\.0\s*$",
    ]

    def __init__(self):
        self._compiled_whitelist = [re.compile(p, re.IGNORECASE) for p in self.WHITELIST_PATTERNS]
        self._compiled_blacklist_link = [re.compile(p, re.IGNORECASE) for p in self.BLACKLIST_LINK_PATTERNS]
        self._compiled_blacklist_bot = [re.compile(p, re.IGNORECASE) for p in self.BLACKLIST_BOT_PATTERNS]
        self._compiled_stub = [re.compile(p, re.IGNORECASE) for p in self.STUB_PATTERNS]
        self._extra_whitelist: List[re.Pattern] = []
        self._extra_blacklist: List[re.Pattern] = []

    def set_extra_patterns(self, whitelist_extra: List[str], blacklist_extra: List[str]) -> None:
        """Установить пользовательские regex-паттерны из настроек."""
        self._extra_whitelist = self._safe_compile(whitelist_extra)
        self._extra_blacklist = self._safe_compile(blacklist_extra)

    @staticmethod
    def _safe_compile(patterns: List[str]) -> List[re.Pattern]:
        compiled = []
        for p in patterns or []:
            try:
                compiled.append(re.compile(p, re.IGNORECASE))
            except re.error as e:
                logger.warning("Invalid UA regex skipped: %r (%s)", p, e)
        return compiled

    def classify(self, user_agent: Optional[str]) -> UserAgentClassification:
        """Определить класс одного UA."""
        if not user_agent or not user_agent.strip():
            return UserAgentClassification.EMPTY

        ua = user_agent.strip()

        # Whitelist (в т.ч. пользовательский) имеет приоритет над blacklist
        for p in self._compiled_whitelist + self._extra_whitelist:
            if p.search(ua):
                return UserAgentClassification.VALID

        # Extra blacklist (пользовательский) — до встроенного, чтобы админ мог переопределить
        for p in self._extra_blacklist:
            if p.search(ua):
                return UserAgentClassification.BOT_LIBRARY

        for p in self._compiled_blacklist_link:
            if p.search(ua):
                return UserAgentClassification.LINK_IN_UA

        for p in self._compiled_blacklist_bot:
            if p.search(ua):
                return UserAgentClassification.BOT_LIBRARY

        for p in self._compiled_stub:
            if p.search(ua):
                return UserAgentClassification.STUB

        return UserAgentClassification.UNKNOWN

    def analyze(
        self,
        srh_records: List[Dict[str, Any]],
        max_age_days: int = 0,
    ) -> UserAgentScore:
        """
        Проанализировать User-Agent в Subscription Request History.

        Каждая запись SRH — отдельный HTTP-запрос подписки. Клиенты могут посылать
        множество запросов с разными UA (например Happ и следом vless:// от другого клиента),
        поэтому анализируется вся доступная история.

        Args:
            srh_records: список записей SRH с полями {user_agent, request_id, request_ip, request_at}
                         (поля snake_case; вызывающий код нормализует camelCase из Panel API)
            max_age_days: игнорировать записи старше указанного количества дней (0 = без ограничения)

        Returns:
            UserAgentScore — агрегированный результат по всем запросам подписки
        """
        if not srh_records:
            return UserAgentScore(score=0.0, reasons=[])

        cutoff = None
        if max_age_days > 0:
            cutoff = datetime.now(tz.utc) - timedelta(days=max_age_days)

        suspicious: List[SuspiciousAgent] = []
        valid_count = 0
        analyzed = 0
        has_link = False
        has_bot = False
        has_stub = False
        has_empty = False
        has_unknown = False

        # Дедуп по UA — не засоряем список одинаковыми записями если юзер каждые 30с дёргает подписку
        seen_ua_keys: Set[str] = set()

        for record in srh_records:
            request_at = record.get("request_at")
            if cutoff and request_at:
                if isinstance(request_at, datetime):
                    ra = request_at
                    if ra.tzinfo is None:
                        ra = ra.replace(tzinfo=tz.utc)
                    if ra < cutoff:
                        continue

            ua = record.get("user_agent")
            classification = self.classify(ua)
            analyzed += 1

            if classification == UserAgentClassification.VALID:
                valid_count += 1
                continue

            # Дедуп: один UA на один IP — не добавляем повторно
            dedup_key = f"{classification.value}|{(ua or '')[:200]}|{record.get('request_ip') or ''}"
            if dedup_key in seen_ua_keys:
                # Всё равно помечаем класс (чтобы set'ы has_* были корректны), но не дублируем entry
                pass
            else:
                seen_ua_keys.add(dedup_key)
                request_at_str = request_at.isoformat() if isinstance(request_at, datetime) else (str(request_at) if request_at else None)
                entry = SuspiciousAgent(
                    request_id=record.get("request_id"),
                    user_agent=(ua or "")[:200],
                    request_ip=record.get("request_ip"),
                    request_at=request_at_str,
                    classification=classification.value,
                )
                suspicious.append(entry)

            if classification == UserAgentClassification.LINK_IN_UA:
                has_link = True
            elif classification == UserAgentClassification.BOT_LIBRARY:
                has_bot = True
            elif classification == UserAgentClassification.STUB:
                has_stub = True
            elif classification == UserAgentClassification.EMPTY:
                has_empty = True
            elif classification == UserAgentClassification.UNKNOWN:
                has_unknown = True

        if analyzed == 0:
            return UserAgentScore(score=0.0, reasons=[])

        # Score по приоритету: link > bot > stub > empty > unknown
        # Score тут информативный (для breakdown), реальные hard floors применяются в IntelligentViolationDetector
        if has_link:
            score = 90.0
        elif has_bot:
            score = 70.0
        elif has_stub:
            score = 55.0
        elif has_empty:
            score = 40.0
        elif has_unknown:
            score = 25.0
        else:
            score = 0.0

        reasons: List[str] = []
        if has_link:
            link_agents = [s for s in suspicious if s.classification == UserAgentClassification.LINK_IN_UA.value]
            sample = link_agents[0].user_agent[:80]
            reasons.append(
                f"Подписочная ссылка в User-Agent ({len(link_agents)} запр.): \"{sample}\" — двойной туннель"
            )
        if has_bot:
            bot_agents = [s for s in suspicious if s.classification == UserAgentClassification.BOT_LIBRARY.value]
            sample = bot_agents[0].user_agent[:80]
            reasons.append(
                f"HTTP-библиотека/скрипт в User-Agent ({len(bot_agents)} запр.): \"{sample}\""
            )
        if has_stub:
            reasons.append(f"Обрезанный User-Agent \"Mozilla/5.0\" ({sum(1 for s in suspicious if s.classification == UserAgentClassification.STUB.value)} запр.)")
        if has_empty and not (has_link or has_bot):
            reasons.append(f"Пустой User-Agent ({sum(1 for s in suspicious if s.classification == UserAgentClassification.EMPTY.value)} запр.)")
        if has_unknown and not (has_link or has_bot or has_stub or has_empty):
            unknown_count = sum(1 for s in suspicious if s.classification == UserAgentClassification.UNKNOWN.value)
            reasons.append(f"Неизвестный User-Agent ({unknown_count} запр.) — возможно новый клиент, требует ручной проверки")

        # Mixed pattern: в истории запросов есть и валидные клиенты, и подозрительные — классика «двойного туннеля»
        if valid_count > 0 and (has_link or has_bot):
            reasons.append(
                f"Смешанные клиенты: {valid_count} легитимных запросов + {len(suspicious)} подозрительных — вероятно второй клиент/туннель"
            )

        return UserAgentScore(
            score=score,
            reasons=reasons,
            suspicious_agents=suspicious[:20],
            has_link_in_ua=has_link,
            has_bot_library=has_bot,
            valid_count=valid_count,
            total_analyzed=analyzed,
        )



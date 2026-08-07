"""Проверка подлинности входящего письма: SPF, DKIM, DMARC.

Приёмник до сих пор верил письму на слово: раз домен получателя наш —
складываем в ящик. Кто угодно мог представиться нашим же noreply@ и попасть
в тот же список, что и настоящая почта. Здесь письмо получает три ответа
на три разных вопроса:

* SPF  — имел ли право этот IP отправлять почту от имени домена конверта;
* DKIM — не изменилось ли письмо в пути и кто за него подписался;
* DMARC — совпадает ли домен, за который отвечает подпись, с тем, что
  видит человек в поле «От», и что владелец домена велел делать с непрошедшими.

SPF считается своей реализацией на dnspython, а не готовой библиотекой:
единственная зрелая (pyspf) синхронная, а тут асинхронный сервер, и её
блокирующие DNS-запросы вешали бы приём почты целиком.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# RFC 7208 §4.6.4: не больше десяти обращений к DNS на проверку. Ограничение
# не про производительность, а про защиту от усиления: цепочка include может
# быть закольцована злонамеренно.
_MAX_DNS_LOOKUPS = 10
_DNS_TIMEOUT = 5.0

# Суффиксы, где организации живут на третьем уровне. Полный список публичных
# суффиксов тянуть в проект ради выравнивания DMARC незачем — а без этих
# нескольких sub.example.co.uk и evil.co.uk посчитались бы роднёй.
_MULTI_LABEL_SUFFIXES = frozenset({
    "co.uk", "org.uk", "me.uk", "ltd.uk", "plc.uk", "net.uk", "sch.uk", "ac.uk", "gov.uk",
    "com.au", "net.au", "org.au", "edu.au", "gov.au",
    "co.jp", "or.jp", "ne.jp", "ac.jp", "go.jp",
    "com.br", "net.br", "org.br", "gov.br",
    "com.cn", "net.cn", "org.cn", "gov.cn",
    "co.kr", "or.kr", "com.tr", "com.mx", "com.ar", "com.sg", "com.hk",
    "co.za", "co.nz", "co.il", "co.in", "com.ua", "net.ua", "org.ua",
    "com.pl", "com.tw", "co.th", "com.my", "com.ph", "com.vn",
})


def organizational_domain(domain: str) -> str:
    """Домен организации: то, что осталось от имени после отсечения зоны.

    Нужен для «мягкого» выравнивания DMARC, где mail.example.com и
    example.com считаются одним владельцем, а example.com и example.net — нет.
    """
    parts = (domain or "").strip(".").lower().split(".")
    if len(parts) <= 2:
        return ".".join(parts)
    if ".".join(parts[-2:]) in _MULTI_LABEL_SUFFIXES:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


# ── DNS ───────────────────────────────────────────────────────────

async def _resolve(name: str, rtype: str) -> List[Any]:
    """Асинхронный DNS-запрос. Пустой список — и «нет записи», и сбой:
    вызывающий различает их по исключению, а здесь нужен только результат."""
    try:
        import dns.asyncresolver
        resolver = dns.asyncresolver.Resolver()
        resolver.lifetime = _DNS_TIMEOUT
        resolver.timeout = _DNS_TIMEOUT
        answer = await resolver.resolve(name, rtype)
        return list(answer)
    except Exception:
        return []


async def _resolve_txt(name: str) -> List[str]:
    out = []
    for rdata in await _resolve(name, "TXT"):
        # Длинные TXT нарезаны на куски по 255 байт — DNS склеивает их
        # обратно только логически, а физически они приезжают отдельно.
        try:
            joined = b"".join(rdata.strings).decode("utf-8", errors="replace")
        except Exception:
            joined = str(rdata).strip('"')
        out.append(joined)
    return out


# ── SPF ───────────────────────────────────────────────────────────

@dataclass
class SpfResult:
    result: str = "none"          # pass|fail|softfail|neutral|none|temperror|permerror
    domain: str = ""
    explanation: str = ""


class _LookupBudget:
    """Счётчик обращений к DNS, общий на всю проверку — включая вложенные
    include и redirect, иначе лимит обходится вложенностью."""

    def __init__(self, limit: int = _MAX_DNS_LOOKUPS):
        self.left = limit

    def spend(self) -> bool:
        self.left -= 1
        return self.left >= 0


_QUALIFIERS = {"+": "pass", "-": "fail", "~": "softfail", "?": "neutral"}


def _expand_macros(value: str, ip: str, sender: str, domain: str, helo: str) -> str:
    """Подстановка макросов SPF (%{d}, %{i}, %{s}, %{o}, %{h}).

    Полная грамматика с обрезкой и разворотом меток встречается у единиц
    доменов; поддержаны только простые формы, остальное остаётся как есть —
    лучше не подставить, чем подставить неверно.
    """
    if "%" not in value:
        return value
    local, _, sender_domain = sender.partition("@")
    replacements = {
        "%{d}": domain,
        "%{i}": ip,
        "%{s}": sender or f"postmaster@{helo}",
        "%{o}": sender_domain or helo,
        "%{l}": local or "postmaster",
        "%{h}": helo,
        "%%": "%",
        "%_": " ",
    }
    for macro, repl in replacements.items():
        value = value.replace(macro, repl)
    return value


async def _spf_check(
    ip: str, domain: str, sender: str, helo: str, budget: _LookupBudget, depth: int = 0,
) -> SpfResult:
    if depth > 5:
        return SpfResult("permerror", domain, "too many redirects")

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return SpfResult("permerror", domain, f"bad ip {ip}")

    records = [r for r in await _resolve_txt(domain) if r.lower().startswith("v=spf1")]
    if not records:
        return SpfResult("none", domain, "no SPF record")
    if len(records) > 1:
        # Две политики — это не «строже», а неопределённость: чью выполнять,
        # стандарт не решает и требует признать домен сломанным.
        return SpfResult("permerror", domain, "multiple SPF records")

    terms = records[0].split()[1:]
    redirect: Optional[str] = None

    for term in terms:
        qualifier = "+"
        if term[:1] in _QUALIFIERS:
            qualifier, term = term[0], term[1:]
        lowered = term.lower()

        if lowered.startswith("redirect="):
            redirect = _expand_macros(term[9:], ip, sender, domain, helo)
            continue
        if lowered.startswith("exp="):
            continue

        matched = False

        if lowered == "all":
            matched = True

        elif lowered.startswith("ip4:") or lowered.startswith("ip6:"):
            try:
                network = ipaddress.ip_network(term.split(":", 1)[1], strict=False)
                matched = addr in network
            except ValueError:
                return SpfResult("permerror", domain, f"bad network in {term}")

        elif lowered.startswith("a") or lowered.startswith("mx"):
            mechanism, _, arg = term.partition(":")
            target, prefix = _split_cidr(arg or domain, mechanism)
            target = _expand_macros(target, ip, sender, domain, helo)
            if not budget.spend():
                return SpfResult("permerror", domain, "DNS lookup limit exceeded")
            hosts = [target]
            if mechanism.lower().startswith("mx"):
                hosts = [str(r.exchange).rstrip(".") for r in await _resolve(target, "MX")]
            matched = await _any_host_matches(hosts, addr, prefix)

        elif lowered.startswith("include:"):
            if not budget.spend():
                return SpfResult("permerror", domain, "DNS lookup limit exceeded")
            included = _expand_macros(term[8:], ip, sender, domain, helo)
            nested = await _spf_check(ip, included, sender, helo, budget, depth + 1)
            # include — это вопрос «а у них проходит?». Их отказ не наш отказ:
            # механизм просто не сработал, и проверка идёт дальше по списку.
            if nested.result == "pass":
                matched = True
            elif nested.result in ("temperror", "permerror"):
                return SpfResult(nested.result, domain, nested.explanation)

        elif lowered.startswith("exists:"):
            if not budget.spend():
                return SpfResult("permerror", domain, "DNS lookup limit exceeded")
            target = _expand_macros(term[7:], ip, sender, domain, helo)
            matched = bool(await _resolve(target, "A"))

        elif lowered.startswith("ptr"):
            # PTR объявлен устаревшим (RFC 7208 §5.5) и на практике его либо
            # нет, либо он подделан — считаем механизм несработавшим.
            if not budget.spend():
                return SpfResult("permerror", domain, "DNS lookup limit exceeded")
            matched = False

        if matched:
            return SpfResult(_QUALIFIERS[qualifier], domain, f"matched {term}")

    if redirect:
        return await _spf_check(ip, redirect, sender, helo, budget, depth + 1)

    return SpfResult("neutral", domain, "no mechanism matched")


def _split_cidr(arg: str, mechanism: str) -> Tuple[str, Optional[int]]:
    """Разделить «host/24» на имя и длину префикса."""
    if "/" in arg:
        host, _, prefix = arg.partition("/")
        try:
            return (host or "", int(prefix))
        except ValueError:
            return (host or "", None)
    return (arg, None)


async def _any_host_matches(hosts: List[str], addr, prefix: Optional[int]) -> bool:
    version = addr.version
    rtype = "A" if version == 4 else "AAAA"
    for host in hosts[:10]:
        for rdata in await _resolve(host, rtype):
            try:
                candidate = ipaddress.ip_address(str(rdata))
            except ValueError:
                continue
            if prefix is None:
                if candidate == addr:
                    return True
            else:
                network = ipaddress.ip_network(f"{candidate}/{prefix}", strict=False)
                if addr in network:
                    return True
    return False


async def check_spf(ip: str, mail_from: str, helo: str) -> SpfResult:
    """Проверить SPF для конверта.

    При пустом обратном адресе (так приходят отчёты о недоставке) стандарт
    велит проверять домен из HELO — иначе отказы никогда бы не проходили.
    """
    sender = mail_from or f"postmaster@{helo}"
    domain = sender.rpartition("@")[2] or helo
    if not domain:
        return SpfResult("none", "", "no domain to check")
    try:
        return await _spf_check(ip, domain.lower(), sender, helo or domain, _LookupBudget())
    except Exception as e:  # noqa: BLE001
        logger.warning("SPF check failed for %s: %s", domain, e)
        return SpfResult("temperror", domain, str(e)[:200])


# ── DKIM ──────────────────────────────────────────────────────────

@dataclass
class DkimResult:
    result: str = "none"          # pass|fail|none|temperror
    domains: List[str] = field(default_factory=list)   # домены прошедших подписей
    detail: str = ""


def _signature_domains(raw: bytes) -> List[str]:
    """Домены из всех заголовков DKIM-Signature, по порядку следования."""
    domains = []
    for match in re.finditer(rb"^DKIM-Signature:(.*?)(?=^\S|\Z)", raw[:200_000],
                             re.MULTILINE | re.DOTALL | re.IGNORECASE):
        block = match.group(1).replace(b"\r\n", b" ").replace(b"\n", b" ")
        d = re.search(rb"[;\s]d=([^;\s]+)", b" " + block)
        domains.append(d.group(1).decode("ascii", "replace").strip().lower() if d else "")
    return domains


def _verify_dkim_blocking(raw: bytes) -> DkimResult:
    """Синхронная проверка подписей — вызывается только из потока."""
    try:
        import dkim
    except ImportError:
        return DkimResult("none", [], "dkimpy not installed")

    domains = _signature_domains(raw)
    if not domains:
        return DkimResult("none", [], "no DKIM-Signature header")

    passed: List[str] = []
    errors: List[str] = []
    for idx, domain in enumerate(domains):
        try:
            if dkim.DKIM(raw).verify(idx):
                passed.append(domain)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{domain or '?'}: {str(e)[:80]}")

    if passed:
        return DkimResult("pass", passed, "")
    # Ключ мог не отдаться из-за сбоя DNS — это не подделка, и жёстко
    # штрафовать за это письмо нельзя.
    if errors and any("dns" in e.lower() or "timeout" in e.lower() for e in errors):
        return DkimResult("temperror", [], "; ".join(errors)[:400])
    return DkimResult("fail", [], "; ".join(errors)[:400] or "signature did not verify")


async def check_dkim(raw: bytes) -> DkimResult:
    """Проверка подписей письма.

    Криптография и обращения к DNS внутри dkimpy блокирующие, поэтому
    уезжают в отдельный поток: иначе одно письмо с медленным DNS
    останавливает приём всей остальной почты.
    """
    try:
        return await asyncio.to_thread(_verify_dkim_blocking, raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("DKIM verification failed: %s", e)
        return DkimResult("temperror", [], str(e)[:200])


# ── DMARC ─────────────────────────────────────────────────────────

@dataclass
class DmarcResult:
    result: str = "none"          # pass|fail|none
    policy: str = "none"          # none|quarantine|reject
    aligned_by: str = ""          # spf|dkim
    detail: str = ""


async def _dmarc_policy(from_domain: str) -> Optional[Dict[str, str]]:
    """Политика домена или его организации — как предписывает RFC 7489."""
    for candidate in (from_domain, organizational_domain(from_domain)):
        if not candidate:
            continue
        for record in await _resolve_txt(f"_dmarc.{candidate}"):
            if record.lower().startswith("v=dmarc1"):
                tags = {}
                for part in record.split(";"):
                    key, _, value = part.partition("=")
                    if key.strip():
                        tags[key.strip().lower()] = value.strip()
                return tags
    return None


def _aligned(child: str, parent: str, strict: bool) -> bool:
    if not child or not parent:
        return False
    child, parent = child.lower(), parent.lower()
    if strict:
        return child == parent
    return organizational_domain(child) == organizational_domain(parent)


async def check_dmarc(from_domain: str, spf: SpfResult, dkim_res: DkimResult,
                      envelope_domain: str) -> DmarcResult:
    """Свести SPF и DKIM к вердикту DMARC.

    Ключевая часть — выравнивание. Письмо может иметь безупречный SPF для
    домена отправителя-посредника и при этом показывать в поле «От» чужой
    адрес; именно на этот случай DMARC и требует, чтобы прошедший механизм
    относился к тому же домену, который видит человек.
    """
    if not from_domain:
        return DmarcResult("none", "none", "", "no From domain")

    tags = await _dmarc_policy(from_domain)
    if not tags:
        return DmarcResult("none", "none", "", "no DMARC record")

    policy = (tags.get("p") or "none").lower()
    strict_spf = (tags.get("aspf") or "r").lower() == "s"
    strict_dkim = (tags.get("adkim") or "r").lower() == "s"

    if dkim_res.result == "pass":
        for signed_domain in dkim_res.domains:
            if _aligned(signed_domain, from_domain, strict_dkim):
                return DmarcResult("pass", policy, "dkim", f"signed by {signed_domain}")

    if spf.result == "pass" and _aligned(envelope_domain, from_domain, strict_spf):
        return DmarcResult("pass", policy, "spf", f"envelope {envelope_domain}")

    return DmarcResult("fail", policy, "", "no aligned identifier")


# ── Итоговая оценка ───────────────────────────────────────────────

@dataclass
class AuthVerdict:
    spf: str = "none"
    dkim: str = "none"
    dmarc: str = "none"
    spam_score: float = 0.0
    is_spam: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


# Порог, после которого письмо помечается подозрительным. Пять баллов —
# это ровно «домен объявил политику и письмо её не прошло»: одного этого
# достаточно, остальные признаки лишь добавляют уверенности.
SPAM_THRESHOLD = 5.0


async def authenticate(raw: bytes, remote_ip: str, mail_from: str, helo: str,
                       from_header: str, threshold: float = SPAM_THRESHOLD) -> AuthVerdict:
    """Проверить письмо целиком и выставить оценку.

    Ошибка любой из проверок не должна мешать письму дойти: почта важнее
    метки, поэтому наверху стоит широкий перехват, а не проброс исключения.
    """
    from email.utils import parseaddr

    verdict = AuthVerdict()
    try:
        from_addr = parseaddr(from_header or "")[1]
        from_domain = from_addr.rpartition("@")[2].lower()
        envelope_domain = (mail_from or "").rpartition("@")[2].lower()

        spf, dkim_res = await asyncio.gather(
            check_spf(remote_ip, mail_from, helo),
            check_dkim(raw),
        )
        dmarc = await check_dmarc(from_domain, spf, dkim_res, envelope_domain or helo)

        verdict.spf = spf.result
        verdict.dkim = dkim_res.result
        verdict.dmarc = dmarc.result
        verdict.details = {
            "spf": {"result": spf.result, "domain": spf.domain, "detail": spf.explanation},
            "dkim": {"result": dkim_res.result, "domains": dkim_res.domains,
                     "detail": dkim_res.detail},
            "dmarc": {"result": dmarc.result, "policy": dmarc.policy,
                      "aligned_by": dmarc.aligned_by, "detail": dmarc.detail},
            "from_domain": from_domain,
            "envelope_domain": envelope_domain,
            "helo": helo,
        }

        score = 0.0
        if dmarc.result == "fail":
            # Владелец домена сам сказал, что делать с такими письмами.
            score += 5.0 if dmarc.policy in ("reject", "quarantine") else 2.0
        if spf.result == "fail":
            score += 3.0
        elif spf.result == "softfail":
            score += 1.0
        if dkim_res.result == "fail":
            score += 2.0
        if spf.result == "none" and dkim_res.result == "none":
            # Ни одной проверяемой подписи: так выглядит либо очень старый
            # сервер, либо тот, кому нечего предъявить.
            score += 2.0

        verdict.spam_score = round(score, 1)
        verdict.is_spam = score >= threshold
    except Exception as e:  # noqa: BLE001
        logger.warning("Authentication checks failed: %s", e)
        verdict.details = {"error": str(e)[:200]}

    return verdict


def authentication_results_header(hostname: str, verdict: AuthVerdict) -> str:
    """Строка Authentication-Results — то, что почтовые клиенты умеют читать."""
    parts = [hostname or "localhost"]
    details = verdict.details or {}
    spf_domain = (details.get("spf") or {}).get("domain", "")
    parts.append(f"spf={verdict.spf}" + (f" smtp.mailfrom={spf_domain}" if spf_domain else ""))
    dkim_domains = (details.get("dkim") or {}).get("domains") or []
    parts.append(f"dkim={verdict.dkim}" + (f" header.d={dkim_domains[0]}" if dkim_domains else ""))
    from_domain = details.get("from_domain", "")
    parts.append(f"dmarc={verdict.dmarc}" + (f" header.from={from_domain}" if from_domain else ""))
    return "; ".join(parts)

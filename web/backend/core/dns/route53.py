"""Amazon Route 53 — DNS-провайдер (Access Key + Secret, подпись AWS SigV4 без boto3).

Особенности API: записи сгруппированы в наборы (name, type) с общим TTL и
списком значений, своих id у записей нет — идентифицируем синтетикой
name|type|value (как у reg.ru). Создание, правка и удаление одного значения —
это чтение набора и UPSERT/DELETE всего набора целиком. Alias-записи (на
ресурсы AWS) показываем, но не редактируем: у них нет ни TTL, ни значений.
"""
import base64
import hashlib
import hmac
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote
from xml.sax.saxutils import escape as _xml_escape

import httpx

from web.backend.core.dns.base import (
    DEFAULT_TIMEOUT, DnsField, DnsProvider, DnsProviderError, DnsRecord, DnsZone,
    register_provider,
)

logger = logging.getLogger(__name__)

R53_HOST = "route53.amazonaws.com"
R53_BASE = f"https://{R53_HOST}"
R53_API = "/2013-04-01"
R53_NS = "https://route53.amazonaws.com/doc/2013-04-01/"
# Route 53 — глобальный сервис, подписывается регионом us-east-1.
_REGION = "us-east-1"
_SERVICE = "route53"
_ALIAS_PREFIX = "alias|"
_DEFAULT_TTL = 300
_MAX_PAGES = 20


@register_provider
class Route53Provider(DnsProvider):
    slug = "route53"
    title = "Amazon Route 53"
    fields = [
        DnsField("access_key_id", "Access Key ID",
                 help="IAM-пользователь с правами route53:ListHostedZones, "
                      "route53:GetHostedZone, route53:ListResourceRecordSets, "
                      "route53:ChangeResourceRecordSets."),
        DnsField("secret_access_key", "Secret Access Key", type="password"),
    ]
    record_types = ["A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA"]
    proxyable = []
    supports_ttl = True

    # ── HTTP ─────────────────────────────────────────────────────

    async def _req(self, creds: Dict[str, str], method: str, path: str,
                   query: Optional[Dict[str, str]] = None, body: bytes = b"") -> ET.Element:
        access_key = (creds.get("access_key_id") or "").strip()
        secret_key = (creds.get("secret_access_key") or "").strip()
        if not access_key or not secret_key:
            raise DnsProviderError("Route 53: не заданы Access Key ID и Secret Access Key")
        query = query or {}
        canonical_qs = _canonical_query(query)
        headers = _sign(method, path, canonical_qs, body, access_key, secret_key)
        if body:
            headers["Content-Type"] = "application/xml"
        url = f"{R53_BASE}{path}" + (f"?{canonical_qs}" if canonical_qs else "")
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.request(method, url, content=body or None, headers=headers)
        except httpx.HTTPError as e:
            raise DnsProviderError(f"Сеть/HTTP: {e}")

        root: Optional[ET.Element] = None
        text = resp.text or ""
        if text.strip():
            try:
                root = ET.fromstring(text)
            except ET.ParseError:
                raise DnsProviderError(f"Некорректный ответ Route 53 (HTTP {resp.status_code})")
        if resp.status_code in (401, 403):
            detail = _text(root, "Message") if root is not None else ""
            raise DnsProviderError(
                "Ключи отклонены или без прав (нужны route53:List*/Get*/ChangeResourceRecordSets)"
                + (f": {detail}" if detail else "")
            )
        if resp.status_code >= 400:
            detail = (_text(root, "Message") if root is not None else "") or f"HTTP {resp.status_code}"
            raise DnsProviderError(f"Route 53: {detail}")
        if root is None:
            raise DnsProviderError(f"Пустой ответ Route 53 (HTTP {resp.status_code})")
        return root

    # ── Контракт провайдера ──────────────────────────────────────

    async def verify(self, creds: Dict[str, str]) -> bool:
        try:
            await self._req(creds, "GET", f"{R53_API}/hostedzone", {"maxitems": "1"})
        except DnsProviderError:
            return False
        return True

    async def list_zones(self, creds: Dict[str, str]) -> List[DnsZone]:
        out: List[DnsZone] = []
        marker: Optional[str] = None
        for _ in range(_MAX_PAGES):
            query = {"maxitems": "100"}
            if marker:
                query["marker"] = marker
            root = await self._req(creds, "GET", f"{R53_API}/hostedzone", query)
            for zone in _iter(root, "HostedZone"):
                zid = _zone_id(_text(zone, "Id"))
                name = _norm_name(_text(zone, "Name"))
                if zid and name:
                    out.append(DnsZone(id=zid, name=name))
            if _text(root, "IsTruncated") != "true":
                break
            marker = _text(root, "NextMarker") or None
            if not marker:
                break
        return out

    async def list_records(self, creds: Dict[str, str], zone_id: str) -> List[DnsRecord]:
        out: List[DnsRecord] = []
        query: Dict[str, str] = {"maxitems": "300"}
        for _ in range(_MAX_PAGES):
            root = await self._req(creds, "GET", f"{R53_API}/hostedzone/{zone_id}/rrset", query)
            for rrset in _iter(root, "ResourceRecordSet"):
                out.extend(_flatten(rrset))
            if _text(root, "IsTruncated") != "true":
                break
            query = {"maxitems": "300"}
            for src, dst in (("NextRecordName", "name"), ("NextRecordType", "type"),
                             ("NextRecordIdentifier", "identifier")):
                value = _text(root, src)
                if value:
                    query[dst] = value
            if "name" not in query:
                break
        return out

    async def create_record(self, creds, zone_id, rec) -> DnsRecord:
        zone_name = await self._zone_name(creds, zone_id)
        rtype = str(rec.get("type") or "").upper()
        name = _fqdn(str(rec.get("name") or ""), zone_name)
        value = _wire_value(rtype, str(rec.get("content") or ""), rec.get("priority"))
        ttl = _int(rec.get("ttl"))
        existing = await self._get_set(creds, zone_id, name, rtype)
        values = list(existing[1]) if existing else []
        if value not in values:
            values.append(value)
        ttl = ttl or (existing[0] if existing and existing[0] else None) or _DEFAULT_TTL
        await self._change(creds, zone_id, "UPSERT", name, rtype, ttl, values)
        return _record(_norm_name(name), rtype, value, ttl)

    async def update_record(self, creds, zone_id, record_id, rec) -> DnsRecord:
        _forbid_alias(record_id)
        old_name, old_type, old_value = _unid(record_id)
        zone_name = await self._zone_name(creds, zone_id)
        rtype = str(rec.get("type") or old_type).upper()
        name = _fqdn(str(rec.get("name") or old_name), zone_name)
        value = _wire_value(rtype, str(rec.get("content") or ""), rec.get("priority"))
        ttl = _int(rec.get("ttl"))

        if _norm_name(name) == _norm_name(old_name) and rtype == old_type:
            current = await self._get_set(creds, zone_id, name, rtype)
            values = list(current[1]) if current else []
            values = [value if v == old_value else v for v in values]
            if value not in values:
                values.append(value)
            ttl = ttl or (current[0] if current and current[0] else None) or _DEFAULT_TTL
            await self._change(creds, zone_id, "UPSERT", name, rtype, ttl, values)
        else:
            # Имя или тип сменились: значение уходит из старого набора и встаёт в новый.
            await self._remove_value(creds, zone_id, _fqdn(old_name, zone_name), old_type, old_value)
            target = await self._get_set(creds, zone_id, name, rtype)
            values = list(target[1]) if target else []
            if value not in values:
                values.append(value)
            ttl = ttl or (target[0] if target and target[0] else None) or _DEFAULT_TTL
            await self._change(creds, zone_id, "UPSERT", name, rtype, ttl, values)
        return _record(_norm_name(name), rtype, value, ttl)

    async def delete_record(self, creds, zone_id, record_id) -> None:
        _forbid_alias(record_id)
        name, rtype, value = _unid(record_id)
        zone_name = await self._zone_name(creds, zone_id)
        await self._remove_value(creds, zone_id, _fqdn(name, zone_name), rtype, value)

    # ── Наборы записей ───────────────────────────────────────────

    async def _zone_name(self, creds: Dict[str, str], zone_id: str) -> str:
        root = await self._req(creds, "GET", f"{R53_API}/hostedzone/{zone_id}")
        name = _norm_name(_text(root, "Name"))
        if not name:
            raise DnsProviderError("Route 53: зона не найдена")
        return name

    async def _get_set(self, creds: Dict[str, str], zone_id: str, name: str,
                       rtype: str) -> Optional[Tuple[Optional[int], List[str]]]:
        """(TTL, значения) набора name/type или None. Листинг с name/type начинает
        с этой позиции по алфавиту, поэтому первый элемент сверяем явно."""
        root = await self._req(creds, "GET", f"{R53_API}/hostedzone/{zone_id}/rrset",
                               {"name": name, "type": rtype, "maxitems": "1"})
        for rrset in _iter(root, "ResourceRecordSet"):
            if (_norm_name(_text(rrset, "Name")) == _norm_name(name)
                    and _text(rrset, "Type") == rtype and _child(rrset, "AliasTarget") is None):
                values = [_text(rr, "Value") for rr in _iter(rrset, "ResourceRecord")]
                return _int(_text(rrset, "TTL")), [v for v in values if v]
        return None

    async def _remove_value(self, creds: Dict[str, str], zone_id: str, name: str,
                            rtype: str, value: str) -> None:
        current = await self._get_set(creds, zone_id, name, rtype)
        if not current:
            return
        ttl, values = current
        remaining = [v for v in values if v != value]
        if len(remaining) == len(values):
            return
        if remaining:
            await self._change(creds, zone_id, "UPSERT", name, rtype, ttl or _DEFAULT_TTL, remaining)
        else:
            # DELETE в Route 53 принимает только точную копию набора.
            await self._change(creds, zone_id, "DELETE", name, rtype, ttl or _DEFAULT_TTL, values)

    async def _change(self, creds: Dict[str, str], zone_id: str, action: str, name: str,
                      rtype: str, ttl: int, values: List[str]) -> None:
        body = _change_xml(action, name, rtype, ttl, values)
        await self._req(creds, "POST", f"{R53_API}/hostedzone/{zone_id}/rrset/", body=body)


# ── SigV4 ────────────────────────────────────────────────────────

def _canonical_query(query: Dict[str, str]) -> str:
    return "&".join(
        f"{quote(k, safe='-_.~')}={quote(str(v), safe='-_.~')}" for k, v in sorted(query.items())
    )


def _sign(method: str, path: str, canonical_qs: str, body: bytes, access_key: str,
          secret_key: str, now: Optional[datetime] = None) -> Dict[str, str]:
    """Заголовки запроса с подписью AWS Signature Version 4."""
    t = now or datetime.now(timezone.utc)
    amz_date = t.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = t.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(body or b"").hexdigest()
    headers = {"host": R53_HOST, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    signed_headers = ";".join(sorted(headers))
    canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
    canonical_request = "\n".join([
        method.upper(), quote(path, safe="/-_.~"), canonical_qs,
        canonical_headers, signed_headers, payload_hash,
    ])
    scope = f"{date_stamp}/{_REGION}/{_SERVICE}/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope,
        hashlib.sha256(canonical_request.encode()).hexdigest(),
    ])

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    signing_key = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret_key).encode(), date_stamp),
                                    _REGION), _SERVICE), "aws4_request")
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "Host": R53_HOST,
        "X-Amz-Date": amz_date,
        "X-Amz-Content-Sha256": payload_hash,
        "Authorization": (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        ),
    }


# ── XML ──────────────────────────────────────────────────────────

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iter(el: Optional[ET.Element], tag: str) -> Iterable[ET.Element]:
    if el is None:
        return []
    return [child for child in el.iter() if _local(child.tag) == tag]


def _child(el: ET.Element, tag: str) -> Optional[ET.Element]:
    for child in el:
        if _local(child.tag) == tag:
            return child
    return None


def _text(el: Optional[ET.Element], tag: str) -> str:
    if el is None:
        return ""
    if _local(el.tag) == tag:
        return (el.text or "").strip()
    for child in el.iter():
        if _local(child.tag) == tag:
            return (child.text or "").strip()
    return ""


def _change_xml(action: str, name: str, rtype: str, ttl: int, values: List[str]) -> bytes:
    records = "".join(
        f"<ResourceRecord><Value>{_xml_escape(v)}</Value></ResourceRecord>" for v in values
    )
    return (
        f'<ChangeResourceRecordSetsRequest xmlns="{R53_NS}"><ChangeBatch><Changes><Change>'
        f"<Action>{action}</Action><ResourceRecordSet><Name>{_xml_escape(name)}</Name>"
        f"<Type>{_xml_escape(rtype)}</Type><TTL>{int(ttl)}</TTL>"
        f"<ResourceRecords>{records}</ResourceRecords></ResourceRecordSet>"
        "</Change></Changes></ChangeBatch></ChangeResourceRecordSetsRequest>"
    ).encode()


# ── Имена, значения, идентификаторы ──────────────────────────────

def _zone_id(raw: str) -> str:
    return raw.rsplit("/", 1)[-1].strip()


def _norm_name(name: str) -> str:
    """Имя из API → без завершающей точки и без восьмеричных экранов (\\052 = *)."""
    name = re.sub(r"\\(\d{3})", lambda m: chr(int(m.group(1), 8)), name or "")
    return name.strip().rstrip(".").lower()


def _fqdn(name: str, zone: str) -> str:
    name = (name or "").strip().rstrip(".")
    zone = zone.strip().rstrip(".")
    if name in ("", "@"):
        return f"{zone}."
    if name.lower() == zone.lower() or name.lower().endswith(f".{zone.lower()}"):
        return f"{name}."
    return f"{name}.{zone}."


def _wire_value(rtype: str, content: str, priority: Any) -> str:
    content = content.strip()
    if rtype == "TXT":
        if content.startswith('"') and content.endswith('"') and len(content) >= 2:
            return content
        return '"' + content.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if rtype in ("MX", "SRV"):
        prio = _int(priority)
        if prio is None:
            # Приоритет уже в начале значения — оставляем как есть.
            head = content.split(" ", 1)[0]
            if head.isdigit():
                return content
            prio = 10 if rtype == "MX" else 0
        return f"{prio} {content}"
    return content


def _display_value(rtype: str, value: str) -> Tuple[str, Optional[int]]:
    """Значение из API → (content для UI, priority)."""
    if rtype == "TXT":
        chunks = re.findall(r'"((?:[^"\\]|\\.)*)"', value)
        if chunks:
            return "".join(chunks).replace('\\"', '"').replace("\\\\", "\\"), None
        return value, None
    if rtype in ("MX", "SRV"):
        head, _, rest = value.partition(" ")
        if head.isdigit() and rest:
            return rest, int(head)
    return value, None


def _flatten(rrset: ET.Element) -> List[DnsRecord]:
    name = _norm_name(_text(rrset, "Name"))
    rtype = _text(rrset, "Type")
    alias = _child(rrset, "AliasTarget")
    if alias is not None:
        target = _norm_name(_text(alias, "DNSName"))
        return [DnsRecord(id=f"{_ALIAS_PREFIX}{name}|{rtype}", type=rtype, name=name,
                          content=f"ALIAS {target}", ttl=None)]
    ttl = _int(_text(rrset, "TTL"))
    out: List[DnsRecord] = []
    for rr in _iter(rrset, "ResourceRecord"):
        value = _text(rr, "Value")
        if value:
            out.append(_record(name, rtype, value, ttl))
    return out


def _record(name: str, rtype: str, value: str, ttl: Optional[int]) -> DnsRecord:
    content, priority = _display_value(rtype, value)
    return DnsRecord(id=_mkid(name, rtype, value), type=rtype, name=name,
                     content=content, ttl=ttl, priority=priority)


def _mkid(name: str, rtype: str, value: str) -> str:
    raw = f"{name}|{rtype}|{value}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unid(record_id: str) -> Tuple[str, str, str]:
    try:
        padded = record_id + "=" * (-len(record_id) % 4)
        name, rtype, value = base64.urlsafe_b64decode(padded).decode().split("|", 2)
        return name, rtype, value
    except Exception:  # noqa: BLE001 — чужой/битый id
        raise DnsProviderError("Route 53: некорректный идентификатор записи")


def _forbid_alias(record_id: str) -> None:
    if record_id.startswith(_ALIAS_PREFIX):
        raise DnsProviderError("Alias-записи Route 53 из админки не редактируются")


def _int(value: Any) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None

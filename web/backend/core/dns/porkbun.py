"""Porkbun — DNS-провайдер (API Key + Secret API Key, JSON API v3).

Особенности API: ключи передаются в теле каждого POST-запроса; у домена в
кабинете Porkbun должен быть включён «API Access», иначе приходит ошибка
«Domain is not opted in to API access». Имена в ответах — полные (FQDN), а на
запись принимаются относительно зоны (пусто — сама зона). Минимальный TTL — 600.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.dns.base import (
    DEFAULT_TIMEOUT, DnsField, DnsProvider, DnsProviderError, DnsRecord, DnsZone,
    register_provider,
)

logger = logging.getLogger(__name__)

PB_BASE = "https://api.porkbun.com/api/json/v3"
_MIN_TTL = 600


@register_provider
class PorkbunProvider(DnsProvider):
    slug = "porkbun"
    title = "Porkbun"
    fields = [
        DnsField("apikey", "API Key",
                 help="Account → API Access. У каждого домена включить «API Access» "
                      "в его настройках (Domain Management → Details)."),
        DnsField("secretapikey", "Secret API Key", type="password"),
    ]
    record_types = ["A", "AAAA", "CNAME", "TXT", "MX", "NS", "SRV", "CAA"]
    proxyable = []
    supports_ttl = True

    async def _call(self, creds: Dict[str, str], path: str,
                    payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        apikey = (creds.get("apikey") or "").strip()
        secret = (creds.get("secretapikey") or "").strip()
        if not apikey or not secret:
            raise DnsProviderError("Porkbun: не заданы API Key и Secret API Key")
        body: Dict[str, Any] = {"apikey": apikey, "secretapikey": secret}
        body.update(payload or {})
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                resp = await client.post(f"{PB_BASE}{path}", json=body)
        except httpx.HTTPError as e:
            raise DnsProviderError(f"Сеть/HTTP: {e}")
        try:
            data = resp.json()
        except ValueError:
            raise DnsProviderError(f"Некорректный ответ Porkbun (HTTP {resp.status_code})")
        if not isinstance(data, dict):
            raise DnsProviderError(f"Некорректный ответ Porkbun (HTTP {resp.status_code})")
        if resp.status_code in (401, 403) or (data.get("status") != "SUCCESS" and resp.status_code >= 400):
            msg = data.get("message") or f"HTTP {resp.status_code}"
            if resp.status_code in (401, 403) and "message" not in data:
                msg = "Ключи отклонены (проверьте API Key / Secret API Key и «API Access» у домена)"
            raise DnsProviderError(f"Porkbun: {msg}")
        if data.get("status") != "SUCCESS":
            raise DnsProviderError(f"Porkbun: {data.get('message') or 'запрос отклонён'}")
        return data

    async def verify(self, creds: Dict[str, str]) -> bool:
        try:
            await self._call(creds, "/ping")
        except DnsProviderError:
            return False
        return True

    async def list_zones(self, creds: Dict[str, str]) -> List[DnsZone]:
        data = await self._call(creds, "/domain/listAll", {"includeLabels": "no"})
        out: List[DnsZone] = []
        for d in data.get("domains") or []:
            name = str((d or {}).get("domain") or "").strip().lower() if isinstance(d, dict) else ""
            if name:
                out.append(DnsZone(id=name, name=name))
        return out

    async def list_records(self, creds: Dict[str, str], zone_id: str) -> List[DnsRecord]:
        data = await self._call(creds, f"/dns/retrieve/{zone_id}")
        return [_record(r) for r in (data.get("records") or []) if isinstance(r, dict) and r.get("id")]

    async def create_record(self, creds, zone_id, rec) -> DnsRecord:
        payload = _payload(rec, zone_id)
        data = await self._call(creds, f"/dns/create/{zone_id}", payload)
        return DnsRecord(
            id=str(data.get("id") or ""), type=payload["type"],
            name=_fqdn(payload["name"], zone_id), content=payload["content"],
            ttl=_num(payload["ttl"]), priority=_num(payload.get("prio")),
        )

    async def update_record(self, creds, zone_id, record_id, rec) -> DnsRecord:
        payload = _payload(rec, zone_id)
        await self._call(creds, f"/dns/edit/{zone_id}/{record_id}", payload)
        return DnsRecord(
            id=str(record_id), type=payload["type"],
            name=_fqdn(payload["name"], zone_id), content=payload["content"],
            ttl=_num(payload["ttl"]), priority=_num(payload.get("prio")),
        )

    async def delete_record(self, creds, zone_id, record_id) -> None:
        await self._call(creds, f"/dns/delete/{zone_id}/{record_id}")


def _sub(name: str, zone: str) -> str:
    """FQDN или короткое имя → относительное имя для API (пусто — сама зона)."""
    name = (name or "").strip().rstrip(".")
    zone = zone.strip().rstrip(".").lower()
    if name in ("", "@") or name.lower() == zone:
        return ""
    if name.lower().endswith(f".{zone}"):
        return name[: -len(zone) - 1]
    return name


def _fqdn(sub: str, zone: str) -> str:
    return zone if not sub else f"{sub}.{zone}"


def _payload(rec: Dict[str, Any], zone: str) -> Dict[str, Any]:
    rtype = str(rec.get("type") or "").upper()
    ttl = _num(rec.get("ttl")) or _MIN_TTL
    body: Dict[str, Any] = {
        "name": _sub(str(rec.get("name") or ""), zone),
        "type": rtype,
        "content": str(rec.get("content") or "").strip(),
        "ttl": str(max(ttl, _MIN_TTL)),
    }
    if rtype in ("MX", "SRV") and rec.get("priority") is not None:
        body["prio"] = str(int(rec["priority"]))
    return body


def _record(r: Dict[str, Any]) -> DnsRecord:
    rtype = str(r.get("type") or "").upper()
    prio = _num(r.get("prio"))
    return DnsRecord(
        id=str(r.get("id")), type=rtype, name=str(r.get("name") or ""),
        content=str(r.get("content") or ""), ttl=_num(r.get("ttl")),
        priority=prio if rtype in ("MX", "SRV") else None,
    )


def _num(v: Any) -> Optional[int]:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None

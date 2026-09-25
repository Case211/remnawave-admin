"""reg.ru — DNS-провайдер (логин + пароль API).

Особенности API reg.ru: у записей НЕТ id (идентифицируем синтетикой
subdomain|type|content, base64), нет проксирования и TTL, править запись
нельзя — правка делается как delete + create. Домены/операции идут через
input_data (JSON). Пароль — отдельный API-пароль (Настройки → Управление доступом).
"""
import base64
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import httpx

from web.backend.core.dns.base import (
    DEFAULT_TIMEOUT, DnsField, DnsProvider, DnsProviderError, DnsRecord, DnsZone,
    register_provider,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.reg.ru/api/regru2"
_SEP = "\x1f"


@register_provider
class RegruProvider(DnsProvider):
    slug = "regru"
    title = "reg.ru"
    fields = [
        DnsField("username", "Логин reg.ru"),
        DnsField("password", "Пароль API", type="password",
                 help="Настройки → Управление доступом → пароль для API (лучше отдельный)."),
    ]
    record_types = ["A", "AAAA", "CNAME", "TXT", "MX"]
    proxyable = []
    supports_ttl = False

    async def _call(self, creds: Dict[str, str], path: str, input_data: Dict[str, Any]) -> Any:
        params = {
            "username": (creds.get("username") or "").strip(),
            "password": (creds.get("password") or "").strip(),
            "output_format": "json", "input_format": "json", "io_encoding": "utf8",
            "input_data": json.dumps(input_data, ensure_ascii=True),
        }
        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
                # reg.ru принимает только POST (на GET отвечает ONLY_POST_ALLOWED);
                # логин и пароль уходят формой в теле, а не в строке URL
                resp = await client.post(f"{_BASE}{path}", data=params)
            data = resp.json()
        except httpx.HTTPError as e:
            raise DnsProviderError(f"Сеть/HTTP ({path}): {e}")
        except ValueError:
            raise DnsProviderError(f"Некорректный ответ reg.ru ({path})")
        if isinstance(data, dict) and str(data.get("result")).lower() == "error":
            raise DnsProviderError(
                f"reg.ru: {data.get('error_text') or data.get('error_code') or 'ошибка'}")
        answer = data.get("answer") if isinstance(data, dict) else None
        # Операции над списком доменов отвечают общим result=success,
        # а ошибка конкретного домена лежит в нём самом
        for dom in (answer.get("domains") if isinstance(answer, dict) else None) or []:
            if isinstance(dom, dict) and str(dom.get("result")).lower() == "error":
                raise DnsProviderError(
                    f"reg.ru ({dom.get('dname') or path}): "
                    f"{dom.get('error_text') or dom.get('error_code') or 'ошибка'}")
        return answer

    async def verify(self, creds: Dict[str, str]) -> bool:
        try:
            await self._call(creds, "/domain/get_list", {})
        except DnsProviderError:
            return False
        return True

    async def list_zones(self, creds: Dict[str, str]) -> List[DnsZone]:
        ans = await self._call(creds, "/domain/get_list", {})
        domains = (ans.get("domains") if isinstance(ans, dict) else None) or []
        out: List[DnsZone] = []
        for d in domains:
            if isinstance(d, dict) and d.get("dname"):
                out.append(DnsZone(id=str(d["dname"]), name=str(d["dname"])))
        return out

    async def list_records(self, creds: Dict[str, str], zone_id: str) -> List[DnsRecord]:
        ans = await self._call(creds, "/zone/get_resource_records", {"domains": [{"dname": zone_id}]})
        domains = (ans.get("domains") if isinstance(ans, dict) else None) or []
        out: List[DnsRecord] = []
        for dom in domains:
            if not isinstance(dom, dict):
                continue
            for rr in (dom.get("rrs") or dom.get("resource_records") or []):
                if not isinstance(rr, dict):
                    continue
                rtype = str(rr.get("rectype") or rr.get("record_type") or "").upper()
                if not rtype:
                    continue
                sub = str(rr.get("subname") or rr.get("subdomain") or "@")
                content = str(rr.get("content") or rr.get("data") or "")
                out.append(DnsRecord(
                    id=_mkid(sub, rtype, content), type=rtype, name=sub, content=content,
                    ttl=None, proxied=None, priority=_num(rr.get("prio")),
                ))
        return out

    async def create_record(self, creds, zone_id, rec) -> DnsRecord:
        rtype = str(rec.get("type") or "").upper()
        sub = (str(rec.get("name") or "@").strip() or "@")
        content = str(rec.get("content") or "").strip()
        if rtype == "A":
            await self._call(creds, "/zone/add_alias",
                             {"domain_name": zone_id, "subdomain": sub, "ipaddr": content})
        elif rtype == "AAAA":
            await self._call(creds, "/zone/add_aaaa",
                             {"domain_name": zone_id, "subdomain": sub, "ipaddr": content})
        elif rtype == "CNAME":
            await self._call(creds, "/zone/add_cname",
                             {"domain_name": zone_id, "subdomain": sub, "canonical_name": content})
        elif rtype == "TXT":
            await self._call(creds, "/zone/add_txt",
                             {"domain_name": zone_id, "subdomain": sub, "text": content})
        elif rtype == "MX":
            prio = rec.get("priority") if rec.get("priority") is not None else 10
            await self._call(creds, "/zone/add_mx",
                             {"domains": [{"dname": zone_id}], "subdomain": sub,
                              "priority": str(prio), "mail_server": content})
        else:
            raise DnsProviderError(f"reg.ru не поддерживает тип {rtype}")
        return DnsRecord(id=_mkid(sub, rtype, content), type=rtype, name=sub,
                         content=content, priority=_num(rec.get("priority")))

    async def update_record(self, creds, zone_id, record_id, rec) -> DnsRecord:
        # reg.ru не умеет править запись — удаляем старую и создаём новую
        await self.delete_record(creds, zone_id, record_id)
        return await self.create_record(creds, zone_id, rec)

    async def delete_record(self, creds, zone_id, record_id) -> None:
        sub, rtype, content = _unid(record_id)
        await self._call(creds, "/zone/remove_record",
                         {"domains": [{"dname": zone_id}], "subdomain": sub,
                          "record_type": rtype, "content": content})


def _mkid(sub: str, rtype: str, content: str) -> str:
    raw = f"{sub}{_SEP}{rtype}{_SEP}{content}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _unid(record_id: str) -> Tuple[str, str, str]:
    try:
        raw = base64.urlsafe_b64decode(record_id.encode()).decode()
        parts = raw.split(_SEP)
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
    except Exception:  # noqa: BLE001
        pass
    raise DnsProviderError("Некорректный идентификатор записи reg.ru")


def _num(v: Any) -> Optional[int]:
    if v in (None, ""):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None

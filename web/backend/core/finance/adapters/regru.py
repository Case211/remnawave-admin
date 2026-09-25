"""reg.ru — регистратор доменов и услуги (логин + пароль API).

База: https://api.reg.ru/api/regru2
- услуги: POST /service/get_list -> answer.services[] (домены/VPS с датой продления);
  API принимает только POST (на GET — ONLY_POST_ALLOWED), параметры — формой в теле
Ответ: {result: "success"|"error", answer|error_text}. Цена/срок из услуги.
Пароль — рекомендуется отдельный API-пароль (Настройки → Управление доступом).
Баланс через API нестабилен — не запрашиваем (домены/даты — главное).
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

from web.backend.core.finance.adapters.base import (
    DEFAULT_TIMEOUT, AdapterError, AdapterField, HosterAdapter, Service, SyncResult,
    register_adapter,
)

logger = logging.getLogger(__name__)

_BASE = "https://api.reg.ru/api/regru2"


@register_adapter
class RegruAdapter(HosterAdapter):
    slug = "regru"
    title = "reg.ru"
    description = "reg.ru: домены/услуги и даты продления. Пароль — отдельный API-пароль (рекомендуется)."
    needs_base_url = False
    fields = [
        AdapterField("username", "Логин reg.ru", help="Логин аккаунта reg.ru."),
        AdapterField("password", "Пароль API", type="password",
                     help="Настройки → Управление доступом → пароль для API (лучше отдельный)."),
    ]

    async def fetch(self, base_url: Optional[str], credentials: Dict[str, str]) -> SyncResult:
        user = (credentials.get("username") or "").strip()
        pwd = (credentials.get("password") or "").strip()
        if not (user and pwd):
            raise AdapterError("Заполни логин и пароль API")
        params = {"username": user, "password": pwd, "output_format": "json", "io_encoding": "utf8"}
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            services = await self._services(client, params)
        return SyncResult(balance=None, currency="RUB", services=services)

    async def _call(self, client: httpx.AsyncClient, path: str, params: Dict[str, str]) -> Any:
        try:
            resp = await client.post(f"{_BASE}{path}", data=params)
        except httpx.HTTPError as e:
            raise AdapterError(f"Сеть/HTTP ({path}): {e}")
        try:
            data = resp.json()
        except ValueError:
            raise AdapterError(f"Некорректный ответ reg.ru ({path})")
        if isinstance(data, dict) and str(data.get("result")).lower() == "error":
            raise AdapterError(f"reg.ru: {data.get('error_text') or data.get('error_code') or 'ошибка'}")
        return data.get("answer") if isinstance(data, dict) else None

    async def _services(self, client: httpx.AsyncClient, params: Dict[str, str]) -> List[Service]:
        answer = await self._call(client, "/service/get_list", params)
        rows = (answer.get("services") if isinstance(answer, dict) else None) or []
        out: List[Service] = []
        for s in rows[:200]:
            if not isinstance(s, dict):
                continue
            out.append(Service(
                name=str(s.get("servname") or s.get("dname") or f"#{s.get('service_id')}"),
                status=str(s.get("state") or "").lower() or None,
                price=_num(s.get("cost")),
                currency="RUB",
                period="yearly",
                next_due_at=_date(s.get("expiration_date")),
                external_id=str(s.get("service_id") or ""),
                specs=str(s.get("servtype") or "") or None,
                ips=None,
            ))
        return out


def _num(v: Any) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _date(v: Any) -> Optional[str]:
    if not v:
        return None
    head = str(v).strip()[:10]
    return head if len(head) == 10 and head[4:5] == "-" and head[7:8] == "-" else None

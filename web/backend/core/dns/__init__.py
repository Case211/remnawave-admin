"""DNS-провайдеры для управления записями зон из админки.

Каждый провайдер знает CRUD над DNS-записями своего хостинга. Реестр отдаёт
метаданные (поля подключения, типы записей, поддержка proxied/ttl) — фронт
рисует форму и адаптирует UI. Импорт модуля = регистрация провайдера.
"""
from web.backend.core.dns.base import (
    DnsField,
    DnsProvider,
    DnsProviderError,
    DnsRecord,
    DnsZone,
    clear_creds,
    get_creds,
    get_provider,
    is_configured,
    list_providers,
    register_provider,
    save_creds,
)

from web.backend.core.dns import cloudflare  # noqa: F401
from web.backend.core.dns import timeweb  # noqa: F401
from web.backend.core.dns import regru  # noqa: F401
from web.backend.core.dns import selectel  # noqa: F401
from web.backend.core.dns import aeza  # noqa: F401
from web.backend.core.dns import route53  # noqa: F401
from web.backend.core.dns import porkbun  # noqa: F401

__all__ = [
    "DnsField", "DnsProvider", "DnsProviderError", "DnsRecord", "DnsZone",
    "clear_creds", "get_creds", "get_provider", "is_configured",
    "list_providers", "register_provider", "save_creds",
]

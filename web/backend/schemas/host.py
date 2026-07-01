"""Host schemas for web panel API."""
from typing import Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, field_validator


def _normalize_str_list(v: Any) -> Optional[List[str]]:
    """Accept a single string or a list; normalize to list[str] (or None).

    Keeps backward compatibility with Remnawave < 2.8.0, which returned single
    scalar values (``tag``, ``alpn``) where 2.8.0 returns arrays.
    """
    if v is None:
        return None
    if isinstance(v, str):
        return [v] if v else None
    return v


class HostBase(BaseModel):
    """Базовые поля хоста."""
    remark: str
    address: str
    port: int = 443


class HostListItem(HostBase):
    """Элемент списка хостов."""
    uuid: str
    is_disabled: bool = False
    view_position: int = 0
    inbound_uuid: Optional[str] = None
    sni: Optional[str] = None
    host: Optional[str] = None
    path: Optional[str] = None
    security: Optional[str] = None
    security_layer: Optional[str] = None
    alpn: Optional[List[str]] = None
    fingerprint: Optional[str] = None
    # 2.8.0: единичный `tag` заменён массивом `tags[]` (до 10, ^[A-Z0-9_:]+$)
    tags: Optional[List[str]] = None
    # 2.8.0: версия IP для Mihomo (dual / ipv4 / ipv6 / ipv4-prefer / ipv6-prefer)
    mihomo_ip_version: Optional[str] = None
    # 2.8.0: вместо булева allowInsecure — пиннинг сертификата
    pinned_peer_cert_sha256: Optional[str] = None
    verify_peer_cert_by_name: bool = False
    server_description: Optional[str] = None
    is_hidden: bool = False
    shuffle_host: bool = False
    mihomo_x25519: bool = False
    # Inbound nested object
    inbound: Optional[dict] = None
    # Node associations
    nodes: Optional[list] = None
    excluded_internal_squads: Optional[list] = None
    # Access-policy scope for the current admin
    allowed_actions: Optional[List[str]] = None

    @field_validator('alpn', mode='before')
    @classmethod
    def parse_alpn(cls, v):
        return _normalize_str_list(v)

    @field_validator('tags', mode='before')
    @classmethod
    def parse_tags(cls, v):
        # 2.8.0 отдаёт tags[]; Remnawave < 2.8.0 — единичный tag-строкой.
        return _normalize_str_list(v)

    @field_validator(
        'is_disabled', 'is_hidden', 'shuffle_host', 'mihomo_x25519', 'verify_peer_cert_by_name',
        mode='before',
    )
    @classmethod
    def _bool_none_to_false(cls, v):
        # Remnawave 2.8.0 может присылать null для булевых полей (напр. verifyPeerCertByName,
        # когда пиннинг сертификата не настроен) — трактуем None как False, иначе pydantic
        # роняет валидацию и вместе с ней весь список хостов.
        return False if v is None else v

    class Config:
        from_attributes = True


class HostDetail(HostListItem):
    """Детальная информация о хосте."""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Дополнительные настройки
    override_sni_from_address: bool = False
    keep_sni_blank: bool = False
    vless_route_id: Optional[int] = None
    x_http_extra_params: Optional[Any] = None
    mux_params: Optional[Any] = None
    sockopt_params: Optional[Any] = None
    xray_json_template_uuid: Optional[str] = None

    @field_validator('override_sni_from_address', 'keep_sni_blank', mode='before')
    @classmethod
    def _detail_bool_none_to_false(cls, v):
        # 2.8.0 может присылать null и для этих булевых полей детального ответа.
        return False if v is None else v


class HostCreate(BaseModel):
    """Создание хоста."""
    remark: str
    address: str
    port: int = 443
    inbound: Optional[dict] = None
    # Legacy field for backward compat
    inbound_uuid: Optional[str] = None
    sni: Optional[str] = None
    host: Optional[str] = None
    path: Optional[str] = None
    security: Optional[str] = None
    security_layer: Optional[str] = None
    alpn: Optional[str] = None
    fingerprint: Optional[str] = None
    tags: Optional[List[str]] = None
    mihomo_ip_version: Optional[str] = None
    is_disabled: bool = False
    is_hidden: bool = False
    server_description: Optional[str] = None
    override_sni_from_address: bool = False
    keep_sni_blank: bool = False
    pinned_peer_cert_sha256: Optional[str] = None
    verify_peer_cert_by_name: bool = False
    vless_route_id: Optional[int] = None
    shuffle_host: bool = False
    mihomo_x25519: bool = False
    nodes: Optional[List[str]] = None
    xray_json_template_uuid: Optional[str] = None
    excluded_internal_squads: Optional[List[str]] = None
    x_http_extra_params: Optional[Any] = None
    mux_params: Optional[Any] = None
    sockopt_params: Optional[Any] = None


class HostUpdate(BaseModel):
    """Обновление хоста."""
    remark: Optional[str] = None
    address: Optional[str] = None
    port: Optional[int] = None
    is_disabled: Optional[bool] = None
    inbound: Optional[dict] = None
    sni: Optional[str] = None
    host: Optional[str] = None
    path: Optional[str] = None
    security: Optional[str] = None
    security_layer: Optional[str] = None
    alpn: Optional[str] = None
    fingerprint: Optional[str] = None
    tags: Optional[List[str]] = None
    mihomo_ip_version: Optional[str] = None
    is_hidden: Optional[bool] = None
    server_description: Optional[str] = None
    override_sni_from_address: Optional[bool] = None
    keep_sni_blank: Optional[bool] = None
    pinned_peer_cert_sha256: Optional[str] = None
    verify_peer_cert_by_name: Optional[bool] = None
    vless_route_id: Optional[int] = None
    shuffle_host: Optional[bool] = None
    mihomo_x25519: Optional[bool] = None
    nodes: Optional[List[str]] = None
    xray_json_template_uuid: Optional[str] = None
    excluded_internal_squads: Optional[List[str]] = None
    x_http_extra_params: Optional[Any] = None
    mux_params: Optional[Any] = None
    sockopt_params: Optional[Any] = None


class HostListResponse(BaseModel):
    """Ответ списка хостов."""
    items: List[HostListItem]
    total: int

"""Host schemas for web panel API."""
from typing import Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, field_validator


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
    tag: Optional[str] = None
    server_description: Optional[str] = None
    is_hidden: bool = False
    shuffle_host: bool = False
    mihomo_x25519: bool = False
    # Inbound nested object
    inbound: Optional[dict] = None
    # Node associations
    nodes: Optional[List[str]] = None
    excluded_internal_squads: Optional[List[str]] = None

    @field_validator('alpn', mode='before')
    @classmethod
    def parse_alpn(cls, v):
        if isinstance(v, str):
            return [v] if v else None
        return v

    class Config:
        from_attributes = True


class HostDetail(HostListItem):
    """Детальная информация о хосте."""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Дополнительные настройки
    allow_insecure: bool = False
    override_sni_from_address: bool = False
    keep_sni_blank: bool = False
    vless_route_id: Optional[int] = None
    x_http_extra_params: Optional[Any] = None
    mux_params: Optional[Any] = None
    sockopt_params: Optional[Any] = None
    xray_json_template_uuid: Optional[str] = None


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
    tag: Optional[str] = None
    is_disabled: bool = False
    is_hidden: bool = False
    server_description: Optional[str] = None
    override_sni_from_address: bool = False
    keep_sni_blank: bool = False
    allow_insecure: bool = False
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
    tag: Optional[str] = None
    is_hidden: Optional[bool] = None
    server_description: Optional[str] = None
    override_sni_from_address: Optional[bool] = None
    keep_sni_blank: Optional[bool] = None
    allow_insecure: Optional[bool] = None
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

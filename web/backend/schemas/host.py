"""Host schemas for web panel API."""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class HostBase(BaseModel):
    """Базовые поля хоста."""
    remark: str
    address: str
    port: int = 443


class HostListItem(HostBase):
    """Элемент списка хостов."""
    uuid: str
    is_disabled: bool = False
    inbound_uuid: Optional[str] = None
    sni: Optional[str] = None
    host: Optional[str] = None
    path: Optional[str] = None
    security: Optional[str] = None
    alpn: Optional[List[str]] = None
    fingerprint: Optional[str] = None

    class Config:
        from_attributes = True


class HostDetail(HostListItem):
    """Детальная информация о хосте."""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Дополнительные настройки
    allow_insecure: bool = False
    reality_public_key: Optional[str] = None
    reality_short_id: Optional[str] = None


class HostCreate(BaseModel):
    """Создание хоста."""
    remark: str
    address: str
    port: int = 443
    inbound_uuid: Optional[str] = None
    sni: Optional[str] = None
    host: Optional[str] = None
    path: Optional[str] = None
    security: Optional[str] = None
    alpn: Optional[List[str]] = None
    fingerprint: Optional[str] = None


class HostUpdate(BaseModel):
    """Обновление хоста."""
    remark: Optional[str] = None
    address: Optional[str] = None
    port: Optional[int] = None
    is_disabled: Optional[bool] = None
    sni: Optional[str] = None
    host: Optional[str] = None
    path: Optional[str] = None
    security: Optional[str] = None
    alpn: Optional[List[str]] = None
    fingerprint: Optional[str] = None


class HostListResponse(BaseModel):
    """Ответ списка хостов."""
    items: List[HostListItem]
    total: int

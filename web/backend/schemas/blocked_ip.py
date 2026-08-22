"""Pydantic schemas for blocked IPs."""
import ipaddress
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class BlockedIPCreate(BaseModel):
    ip_cidr: str
    reason: Optional[str] = None
    expires_in_hours: Optional[int] = Field(None, gt=0)

    @field_validator("ip_cidr")
    @classmethod
    def validate_cidr(cls, v: str) -> str:
        v = v.strip()
        try:
            net = ipaddress.ip_network(v, strict=False)
        except ValueError:
            raise ValueError(f"Invalid IP or CIDR: {v}")
        if net.version == 4 and net.prefixlen < 16:
            raise ValueError("IPv4 subnets wider than /16 are not allowed")
        if net.version == 6 and net.prefixlen < 48:
            raise ValueError("IPv6 subnets wider than /48 are not allowed")
        return str(net)


class BlockedIPBulkCreate(BaseModel):
    ips: List[str]
    reason: Optional[str] = None
    expires_in_hours: Optional[int] = Field(None, gt=0)

    @field_validator("ips")
    @classmethod
    def validate_ips(cls, v: List[str]) -> List[str]:
        if len(v) > 100:
            raise ValueError("Maximum 100 IPs per bulk request")
        result = []
        for ip in v:
            ip = ip.strip()
            if not ip:
                continue
            try:
                net = ipaddress.ip_network(ip, strict=False)
            except ValueError:
                raise ValueError(f"Invalid IP or CIDR: {ip}")
            if net.version == 4 and net.prefixlen < 16:
                raise ValueError(f"IPv4 subnets wider than /16 are not allowed: {ip}")
            if net.version == 6 and net.prefixlen < 48:
                raise ValueError(f"IPv6 subnets wider than /48 are not allowed: {ip}")
            result.append(str(net))
        return result


class BlockedIPItem(BaseModel):
    id: int
    ip_cidr: str
    reason: Optional[str] = None
    added_by_admin_id: Optional[int] = None
    added_by_username: Optional[str] = None
    country_code: Optional[str] = None
    asn_org: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # Кого запись задевает по истории подключений: без этого из списка не
    # понять, отрезан один абузер или подсеть с живыми абонентами
    accounts: Optional[int] = None
    trial_accounts: Optional[int] = None
    last_seen: Optional[datetime] = None


class BlockedIPListResponse(BaseModel):
    items: List[BlockedIPItem]
    total: int


class BlockedIPUser(BaseModel):
    """Аккаунт, заходивший с заблокированного адреса."""
    user_uuid: str
    username: Optional[str] = None
    status: Optional[str] = None
    telegram_id: Optional[int] = None
    email: Optional[str] = None
    expire_at: Optional[datetime] = None
    conns: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    sample_ip: Optional[str] = None
    is_trial: bool = False
    is_active: bool = False


class BlockedIPUsersResponse(BaseModel):
    ip_cidr: str
    users: List[BlockedIPUser]
    total: int

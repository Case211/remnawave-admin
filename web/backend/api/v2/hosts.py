"""Hosts API endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from typing import List

from web.backend.api.deps import get_current_admin, get_api_client, AdminUser
from web.backend.schemas.host import (
    HostListItem,
    HostListResponse,
    HostDetail,
    HostCreate,
    HostUpdate,
)

router = APIRouter()


@router.get("", response_model=HostListResponse)
async def list_hosts(
    admin: AdminUser = Depends(get_current_admin),
    api_client=Depends(get_api_client),
):
    """Список всех хостов."""
    data = await api_client.get_hosts()
    hosts = data.get('response', []) if isinstance(data, dict) else data

    items = []
    for h in hosts:
        items.append(HostListItem(
            uuid=h.get('uuid'),
            remark=h.get('remark', ''),
            address=h.get('address', ''),
            port=h.get('port', 443),
            is_disabled=h.get('isDisabled', False),
            inbound_uuid=h.get('inboundUuid'),
            sni=h.get('sni'),
            host=h.get('host'),
            path=h.get('path'),
            security=h.get('security'),
            alpn=h.get('alpn'),
            fingerprint=h.get('fingerprint'),
        ))

    return HostListResponse(
        items=items,
        total=len(items),
    )


@router.get("/{host_uuid}", response_model=HostDetail)
async def get_host(
    host_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
    api_client=Depends(get_api_client),
):
    """Получить информацию о хосте."""
    data = await api_client.get_host(host_uuid)

    if not data:
        raise HTTPException(status_code=404, detail="Host not found")

    h = data.get('response', data) if isinstance(data, dict) else data

    return HostDetail(
        uuid=h.get('uuid'),
        remark=h.get('remark', ''),
        address=h.get('address', ''),
        port=h.get('port', 443),
        is_disabled=h.get('isDisabled', False),
        inbound_uuid=h.get('inboundUuid'),
        sni=h.get('sni'),
        host=h.get('host'),
        path=h.get('path'),
        security=h.get('security'),
        alpn=h.get('alpn'),
        fingerprint=h.get('fingerprint'),
        allow_insecure=h.get('allowInsecure', False),
        reality_public_key=h.get('realityPublicKey'),
        reality_short_id=h.get('realityShortId'),
        created_at=h.get('createdAt'),
        updated_at=h.get('updatedAt'),
    )


@router.post("", response_model=HostDetail)
async def create_host(
    data: HostCreate,
    admin: AdminUser = Depends(get_current_admin),
    api_client=Depends(get_api_client),
):
    """Создать новый хост."""
    payload = {
        'remark': data.remark,
        'address': data.address,
        'port': data.port,
    }

    if data.inbound_uuid:
        payload['inboundUuid'] = data.inbound_uuid
    if data.sni:
        payload['sni'] = data.sni
    if data.host:
        payload['host'] = data.host
    if data.path:
        payload['path'] = data.path
    if data.security:
        payload['security'] = data.security
    if data.alpn:
        payload['alpn'] = data.alpn
    if data.fingerprint:
        payload['fingerprint'] = data.fingerprint

    result = await api_client.create_host(payload)

    if not result:
        raise HTTPException(status_code=400, detail="Failed to create host")

    h = result.get('response', result) if isinstance(result, dict) else result

    return HostDetail(
        uuid=h.get('uuid'),
        remark=h.get('remark', ''),
        address=h.get('address', ''),
        port=h.get('port', 443),
        is_disabled=h.get('isDisabled', False),
        inbound_uuid=h.get('inboundUuid'),
        sni=h.get('sni'),
        host=h.get('host'),
        path=h.get('path'),
        security=h.get('security'),
        alpn=h.get('alpn'),
        fingerprint=h.get('fingerprint'),
    )


@router.patch("/{host_uuid}", response_model=HostDetail)
async def update_host(
    host_uuid: str,
    data: HostUpdate,
    admin: AdminUser = Depends(get_current_admin),
    api_client=Depends(get_api_client),
):
    """Обновить хост."""
    payload = {}

    if data.remark is not None:
        payload['remark'] = data.remark
    if data.address is not None:
        payload['address'] = data.address
    if data.port is not None:
        payload['port'] = data.port
    if data.is_disabled is not None:
        payload['isDisabled'] = data.is_disabled
    if data.sni is not None:
        payload['sni'] = data.sni
    if data.host is not None:
        payload['host'] = data.host
    if data.path is not None:
        payload['path'] = data.path
    if data.security is not None:
        payload['security'] = data.security
    if data.alpn is not None:
        payload['alpn'] = data.alpn
    if data.fingerprint is not None:
        payload['fingerprint'] = data.fingerprint

    result = await api_client.update_host(host_uuid, payload)

    if not result:
        raise HTTPException(status_code=404, detail="Host not found or update failed")

    h = result.get('response', result) if isinstance(result, dict) else result

    return HostDetail(
        uuid=h.get('uuid'),
        remark=h.get('remark', ''),
        address=h.get('address', ''),
        port=h.get('port', 443),
        is_disabled=h.get('isDisabled', False),
        inbound_uuid=h.get('inboundUuid'),
        sni=h.get('sni'),
        host=h.get('host'),
        path=h.get('path'),
        security=h.get('security'),
        alpn=h.get('alpn'),
        fingerprint=h.get('fingerprint'),
    )


@router.delete("/{host_uuid}")
async def delete_host(
    host_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
    api_client=Depends(get_api_client),
):
    """Удалить хост."""
    result = await api_client.delete_host(host_uuid)

    if not result:
        raise HTTPException(status_code=404, detail="Host not found or delete failed")

    return {"status": "ok"}


@router.post("/{host_uuid}/enable")
async def enable_host(
    host_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
    api_client=Depends(get_api_client),
):
    """Включить хост."""
    result = await api_client.enable_hosts([host_uuid])

    if not result:
        raise HTTPException(status_code=400, detail="Failed to enable host")

    return {"status": "ok"}


@router.post("/{host_uuid}/disable")
async def disable_host(
    host_uuid: str,
    admin: AdminUser = Depends(get_current_admin),
    api_client=Depends(get_api_client),
):
    """Отключить хост."""
    result = await api_client.disable_hosts([host_uuid])

    if not result:
        raise HTTPException(status_code=400, detail="Failed to disable host")

    return {"status": "ok"}

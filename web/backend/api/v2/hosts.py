"""Hosts API endpoints."""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List

from web.backend.api.deps import get_current_admin, get_api_client, AdminUser, require_permission, require_quota, get_client_ip
from web.backend.core.rbac import write_audit_log
from web.backend.schemas.host import (
    HostListItem,
    HostListResponse,
    HostDetail,
    HostCreate,
    HostUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _map_host(h: dict) -> dict:
    """Маппинг полей хоста из camelCase API ответа."""
    inbound = h.get('inbound', {})
    return dict(
        uuid=h.get('uuid'),
        remark=h.get('remark', ''),
        address=h.get('address', ''),
        port=h.get('port', 443),
        is_disabled=h.get('isDisabled', False),
        view_position=h.get('viewPosition', 0),
        inbound_uuid=inbound.get('configProfileInboundUuid') if isinstance(inbound, dict) else h.get('inboundUuid'),
        inbound=inbound if isinstance(inbound, dict) else None,
        sni=h.get('sni'),
        host=h.get('host'),
        path=h.get('path'),
        security=h.get('security'),
        security_layer=h.get('securityLayer'),
        alpn=h.get('alpn'),
        fingerprint=h.get('fingerprint'),
        tag=h.get('tag'),
        server_description=h.get('serverDescription'),
        is_hidden=h.get('isHidden', False),
        shuffle_host=h.get('shuffleHost', False),
        mihomo_x25519=h.get('mihomoX25519', False),
        nodes=h.get('nodes'),
        excluded_internal_squads=h.get('excludedInternalSquads'),
    )


def _map_host_detail(h: dict) -> dict:
    """Маппинг полей детальной информации о хосте."""
    base = _map_host(h)
    base.update(
        created_at=h.get('createdAt'),
        updated_at=h.get('updatedAt'),
        allow_insecure=h.get('allowInsecure', False),
        override_sni_from_address=h.get('overrideSniFromAddress', False),
        keep_sni_blank=h.get('keepSniBlank', False),
        vless_route_id=h.get('vlessRouteId'),
        x_http_extra_params=h.get('xHttpExtraParams'),
        mux_params=h.get('muxParams'),
        sockopt_params=h.get('sockoptParams'),
        xray_json_template_uuid=h.get('xrayJsonTemplateUuid'),
    )
    return base


async def _get_hosts_list() -> List[dict]:
    """Get hosts from DB first, fall back to API."""
    try:
        from shared.database import db_service
        if db_service.is_connected:
            hosts = await db_service.get_all_hosts()
            if hosts:
                logger.debug("Loaded %d hosts from database", len(hosts))
                return hosts
    except Exception as e:
        logger.debug("DB hosts fetch failed: %s", e)

    from web.backend.core.api_helper import fetch_hosts_from_api
    return await fetch_hosts_from_api()


@router.get("", response_model=HostListResponse)
async def list_hosts(
    admin: AdminUser = Depends(require_permission("hosts", "view")),
):
    """Список всех хостов."""
    hosts = await _get_hosts_list()

    items = [HostListItem(**_map_host(h)) for h in hosts]

    return HostListResponse(
        items=items,
        total=len(items),
    )


@router.get("/{host_uuid}", response_model=HostDetail)
async def get_host(
    host_uuid: str,
    admin: AdminUser = Depends(require_permission("hosts", "view")),
    api_client=Depends(get_api_client),
):
    """Получить информацию о хосте."""
    data = await api_client.get_host(host_uuid)

    if not data:
        raise HTTPException(status_code=404, detail="Host not found")

    h = data.get('response', data) if isinstance(data, dict) else data

    return HostDetail(**_map_host_detail(h))


@router.post("", response_model=HostDetail)
async def create_host(
    data: HostCreate,
    request: Request,
    admin: AdminUser = Depends(require_permission("hosts", "create")),
    _quota: None = Depends(require_quota("hosts")),
    api_client=Depends(get_api_client),
):
    """Создать новый хост."""
    # Формируем payload в формате Remnawave API
    payload = {
        'remark': data.remark,
        'address': data.address,
        'port': data.port,
    }

    # Inbound object
    if data.inbound:
        payload['inbound'] = data.inbound
    elif data.inbound_uuid:
        payload['inboundUuid'] = data.inbound_uuid

    # Все опциональные поля
    if data.sni is not None:
        payload['sni'] = data.sni
    if data.host is not None:
        payload['host'] = data.host
    if data.path is not None:
        payload['path'] = data.path
    if data.alpn is not None:
        payload['alpn'] = data.alpn
    if data.fingerprint is not None:
        payload['fingerprint'] = data.fingerprint
    if data.tag is not None:
        payload['tag'] = data.tag
    if data.security_layer is not None:
        payload['securityLayer'] = data.security_layer
    elif data.security is not None:
        payload['securityLayer'] = data.security
    if data.is_disabled:
        payload['isDisabled'] = data.is_disabled
    if data.is_hidden:
        payload['isHidden'] = data.is_hidden
    if data.server_description is not None:
        payload['serverDescription'] = data.server_description
    if data.override_sni_from_address:
        payload['overrideSniFromAddress'] = data.override_sni_from_address
    if data.keep_sni_blank:
        payload['keepSniBlank'] = data.keep_sni_blank
    if data.allow_insecure:
        payload['allowInsecure'] = data.allow_insecure
    if data.vless_route_id is not None:
        payload['vlessRouteId'] = data.vless_route_id
    if data.shuffle_host:
        payload['shuffleHost'] = data.shuffle_host
    if data.mihomo_x25519:
        payload['mihomoX25519'] = data.mihomo_x25519
    if data.nodes is not None:
        payload['nodes'] = data.nodes
    if data.xray_json_template_uuid is not None:
        payload['xrayJsonTemplateUuid'] = data.xray_json_template_uuid
    if data.excluded_internal_squads is not None:
        payload['excludedInternalSquads'] = data.excluded_internal_squads
    if data.x_http_extra_params is not None:
        payload['xHttpExtraParams'] = data.x_http_extra_params
    if data.mux_params is not None:
        payload['muxParams'] = data.mux_params
    if data.sockopt_params is not None:
        payload['sockoptParams'] = data.sockopt_params

    result = await api_client.create_host_raw(payload)

    if not result:
        raise HTTPException(status_code=400, detail="Failed to create host")

    h = result.get('response', result) if isinstance(result, dict) else result

    # Increment quota usage counter
    if admin.account_id is not None:
        from web.backend.core.rbac import increment_usage_counter
        await increment_usage_counter(admin.account_id, "hosts_created")

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="host.create",
        resource="hosts",
        resource_id=h.get('uuid', ''),
        details=json.dumps({"remark": data.remark}),
        ip_address=get_client_ip(request),
    )

    return HostDetail(**_map_host_detail(h))


@router.patch("/{host_uuid}", response_model=HostDetail)
async def update_host(
    host_uuid: str,
    data: HostUpdate,
    request: Request,
    admin: AdminUser = Depends(require_permission("hosts", "edit")),
    api_client=Depends(get_api_client),
):
    """Обновить хост."""
    payload = {'uuid': host_uuid}

    if data.remark is not None:
        payload['remark'] = data.remark
    if data.address is not None:
        payload['address'] = data.address
    if data.port is not None:
        payload['port'] = data.port
    if data.is_disabled is not None:
        payload['isDisabled'] = data.is_disabled
    if data.inbound is not None:
        payload['inbound'] = data.inbound
    if data.sni is not None:
        payload['sni'] = data.sni
    if data.host is not None:
        payload['host'] = data.host
    if data.path is not None:
        payload['path'] = data.path
    if data.alpn is not None:
        payload['alpn'] = data.alpn
    if data.fingerprint is not None:
        payload['fingerprint'] = data.fingerprint
    if data.tag is not None:
        payload['tag'] = data.tag
    if data.security_layer is not None:
        payload['securityLayer'] = data.security_layer
    elif data.security is not None:
        payload['securityLayer'] = data.security
    if data.is_hidden is not None:
        payload['isHidden'] = data.is_hidden
    if data.server_description is not None:
        payload['serverDescription'] = data.server_description
    if data.override_sni_from_address is not None:
        payload['overrideSniFromAddress'] = data.override_sni_from_address
    if data.keep_sni_blank is not None:
        payload['keepSniBlank'] = data.keep_sni_blank
    if data.allow_insecure is not None:
        payload['allowInsecure'] = data.allow_insecure
    if data.vless_route_id is not None:
        payload['vlessRouteId'] = data.vless_route_id
    if data.shuffle_host is not None:
        payload['shuffleHost'] = data.shuffle_host
    if data.mihomo_x25519 is not None:
        payload['mihomoX25519'] = data.mihomo_x25519
    if data.nodes is not None:
        payload['nodes'] = data.nodes
    if data.xray_json_template_uuid is not None:
        payload['xrayJsonTemplateUuid'] = data.xray_json_template_uuid
    if data.excluded_internal_squads is not None:
        payload['excludedInternalSquads'] = data.excluded_internal_squads
    if data.x_http_extra_params is not None:
        payload['xHttpExtraParams'] = data.x_http_extra_params
    if data.mux_params is not None:
        payload['muxParams'] = data.mux_params
    if data.sockopt_params is not None:
        payload['sockoptParams'] = data.sockopt_params

    result = await api_client.update_host_raw(payload)

    if not result:
        raise HTTPException(status_code=404, detail="Host not found or update failed")

    h = result.get('response', result) if isinstance(result, dict) else result

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="host.update",
        resource="hosts",
        resource_id=host_uuid,
        details=json.dumps({"remark": data.remark}),
        ip_address=get_client_ip(request),
    )

    return HostDetail(**_map_host_detail(h))


@router.delete("/{host_uuid}")
async def delete_host(
    host_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("hosts", "delete")),
    api_client=Depends(get_api_client),
):
    """Удалить хост."""
    result = await api_client.delete_host(host_uuid)

    if not result:
        raise HTTPException(status_code=404, detail="Host not found or delete failed")

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="host.delete",
        resource="hosts",
        resource_id=host_uuid,
        details=json.dumps({"host_uuid": host_uuid}),
        ip_address=get_client_ip(request),
    )

    return {"status": "ok"}


@router.post("/{host_uuid}/enable")
async def enable_host(
    host_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("hosts", "edit")),
    api_client=Depends(get_api_client),
):
    """Включить хост."""
    result = await api_client.enable_hosts([host_uuid])

    if not result:
        raise HTTPException(status_code=400, detail="Failed to enable host")

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="host.enable",
        resource="hosts",
        resource_id=host_uuid,
        details=json.dumps({"host_uuid": host_uuid}),
        ip_address=get_client_ip(request),
    )

    return {"status": "ok"}


@router.post("/{host_uuid}/disable")
async def disable_host(
    host_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("hosts", "edit")),
    api_client=Depends(get_api_client),
):
    """Отключить хост."""
    result = await api_client.disable_hosts([host_uuid])

    if not result:
        raise HTTPException(status_code=400, detail="Failed to disable host")

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="host.disable",
        resource="hosts",
        resource_id=host_uuid,
        details=json.dumps({"host_uuid": host_uuid}),
        ip_address=get_client_ip(request),
    )

    return {"status": "ok"}

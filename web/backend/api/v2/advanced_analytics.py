"""Advanced Analytics API — geo map, top users, trends, node metrics history."""
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from web.backend.api.deps import require_permission, AdminUser
from web.backend.core.cache import cached, CACHE_TTL_LONG
from web.backend.core.errors import api_error, E
from web.backend.core.rate_limit import limiter, RATE_ANALYTICS

from shared import timefmt
from shared.db_schema import (
    USERS_TABLE, NODES_TABLE, HOSTS_TABLE, USER_CONNECTIONS_TABLE,
    IP_METADATA_TABLE, VIOLATIONS_TABLE, NODE_METRICS_SNAPSHOTS_TABLE,
    USER_NODE_TRAFFIC_TABLE,
)
from shared.db_query import select_sql

logger = logging.getLogger(__name__)

NODE_TRAFFIC_SNAPSHOTS_TABLE = "node_traffic_snapshots"
router = APIRouter()


_PERIOD_DAYS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90, "all": 3650}


def _bounds(period: str, date_from: Optional[str] = None, date_to: Optional[str] = None,
            default: str = "7d") -> tuple:
    """Окно отчёта [since, until): свои даты (день «по» — включительно, сутки —
    по часам панели) или последние N дней периода."""
    now = datetime.now(timezone.utc)
    since, until = timefmt.filter_bounds(date_from, date_to)
    if since is None:
        since = now - timedelta(days=_PERIOD_DAYS.get(period, _PERIOD_DAYS[default]))
    until = min(until, now) if until else now
    return since, until


async def _user_scope(admin) -> Optional[List[str]]:
    """Видимые админу юзеры списком для ``$n::uuid[]``; None — видит всех."""
    from web.backend.core.rbac import get_visible_user_uuids
    visible = await get_visible_user_uuids(admin)
    return None if visible is None else sorted(visible)


async def _node_scope(admin) -> Optional[List[str]]:
    """Видимые админу ноды списком для ``$n::uuid[]``; None — видит все."""
    from web.backend.core.rbac import get_scope
    scope = await get_scope(admin, "node", "view")
    return None if scope is None else sorted(scope)


def _db():
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)
    return db_service


def _failed(what: str, exc: Exception) -> HTTPException:
    """Сбой отчёта — ошибкой, а не пустым списком: «данных нет» и «сломалось»
    админ должен различать."""
    if isinstance(exc, HTTPException):
        return exc
    logger.error("analytics %s failed: %s", what, exc, exc_info=True)
    return api_error(500, E.INTERNAL_ERROR, f"analytics {what} failed")


def _usage_item(uuid: str, username: str, status: Optional[str], used: int,
                limit_bytes: Optional[int], online_at: Optional[str]) -> Dict[str, Any]:
    pct = round(used / limit_bytes * 100, 1) if limit_bytes and limit_bytes > 0 else None
    return {
        "uuid": uuid,
        "username": username,
        "status": status or "unknown",
        "used_traffic_bytes": used,
        "traffic_limit_bytes": limit_bytes,
        "usage_percent": pct,
        "online_at": online_at,
    }


_city_aliases: Optional[Dict[str, str]] = None


def _get_city_aliases() -> Dict[str, str]:
    """Lazy-load city name aliases from GeoAnalyzer."""
    global _city_aliases
    if _city_aliases is None:
        from shared.violation_detector import GeoAnalyzer
        _city_aliases = GeoAnalyzer.CITY_NAME_ALIASES
    return _city_aliases


def _normalize_city_name(city: str) -> str:
    """Normalize city name for deduplication (e.g. 'Москва' -> 'moscow')."""
    if not city:
        return ""
    normalized = city.lower().strip()
    for suffix in [' city', ' gorod', ' oblast', ' region']:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].strip()
    return _get_city_aliases().get(normalized, normalized)


# Стили растровых тайлов CARTO под тему интерфейса
_CARTO_STYLES = {"dark": "dark_all", "light": "light_all"}


def _map_tile_urls(api_key: str) -> Dict[str, Any]:
    """URL тайлов карты для аналитики по теме.

    CARTO с августа 2026 без ключа рисует на тайлах водяной знак «API key
    required» (карта работает). С ключом — новый эндпоинт rastertiles, ключ
    передаётся параметром ``key``. Без ключа остаётся старый адрес, чтобы
    карта не пропадала.
    """
    key = (api_key or "").strip()
    if key:
        encoded = quote(key, safe="")
        urls = {
            theme: f"https://basemaps.cartocdn.com/rastertiles/{style}/{{z}}/{{x}}/{{y}}.png?key={encoded}"
            for theme, style in _CARTO_STYLES.items()
        }
    else:
        urls = {
            theme: f"https://{{s}}.basemaps.cartocdn.com/{style}/{{z}}/{{x}}/{{y}}{{r}}.png"
            for theme, style in _CARTO_STYLES.items()
        }
    return {**urls, "has_key": bool(key)}


@router.get("/map-tiles")
@limiter.limit(RATE_ANALYTICS)
async def get_map_tiles(
    request: Request,
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Tile URL templates for the analytics map (dark/light) and whether a CARTO key is set."""
    from shared.config_service import config_service
    return _map_tile_urls(config_service.get("map_tiles_api_key") or "")


@router.get("/geo")
@limiter.limit(RATE_ANALYTICS)
async def get_geo_connections(
    request: Request,
    period: str = Query("7d", description="Period: 24h, 7d, 30d"),
    date_from: Optional[str] = Query(None, description="Custom start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="Custom end date (ISO 8601)"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """География за период: уникальные юзеры и адреса по странам и городам."""
    scope = await _user_scope(admin)
    if scope is None:
        return await _compute_geo(period=period, date_from=date_from, date_to=date_to)
    return await _geo(period, date_from, date_to, scope)


@cached("analytics:geo", ttl=CACHE_TTL_LONG, key_args=("period", "date_from", "date_to"))
async def _compute_geo(period: str = "7d", date_from: Optional[str] = None, date_to: Optional[str] = None):
    return await _geo(period, date_from, date_to, None)


_GEO_CITY_USERS_LIMIT = 100


async def _geo(period: str, date_from: Optional[str], date_to: Optional[str],
               scope: Optional[List[str]]) -> Dict[str, Any]:
    db_service = _db()
    since, until = _bounds(period, date_from, date_to)
    try:
        async with db_service.acquire() as conn:
            # Кто откуда подключался за период: адрес подключения → геоданные.
            # Строка — юзер в городе, так что их порядка числа активных юзеров.
            rows = await conn.fetch(
                f"""
                WITH pairs AS (
                    SELECT user_uuid, SPLIT_PART(ip_address, '/', 1) AS ip, COUNT(*) AS connections
                    FROM {USER_CONNECTIONS_TABLE}
                    WHERE connected_at >= $1 AND connected_at < $2
                      AND ($3::uuid[] IS NULL OR user_uuid = ANY($3::uuid[]))
                    GROUP BY user_uuid, ip
                )
                SELECT p.user_uuid::text AS uuid, u.username, u.status,
                       im.city, im.country_name, im.country_code,
                       AVG(im.latitude) AS latitude, AVG(im.longitude) AS longitude,
                       SUM(p.connections) AS connections,
                       array_agg(p.ip) AS ips
                FROM pairs p
                JOIN {IP_METADATA_TABLE} im ON im.ip_address = p.ip
                LEFT JOIN {USERS_TABLE} u ON u.uuid = p.user_uuid
                WHERE im.country_name IS NOT NULL
                GROUP BY p.user_uuid, u.username, u.status, im.city, im.country_name, im.country_code
                """,
                since, until, scope,
            )
    except Exception as e:
        raise _failed("geo", e)

    countries: Dict[str, Dict[str, Any]] = {}
    cities: Dict[tuple, Dict[str, Any]] = {}
    for r in rows:
        ips = [str(ip) for ip in (r["ips"] or [])]
        c = countries.setdefault(r["country_name"], {
            "country": r["country_name"], "country_code": r["country_code"],
            "users": set(), "ips": set(),
        })
        c["users"].add(r["uuid"])
        c["ips"].update(ips)

        if not r["city"] or r["latitude"] is None or r["longitude"] is None:
            continue
        key = (_normalize_city_name(r["city"]), r["country_name"])
        city = cities.get(key)
        if city is None:
            city = cities[key] = {
                "city": r["city"], "country": r["country_name"],
                "lat_sum": 0.0, "lon_sum": 0.0, "weight": 0,
                "ips": set(), "users": {},
            }
        # Координаты — среднее по адресам: у одного города их бывает несколько
        city["lat_sum"] += float(r["latitude"]) * len(ips)
        city["lon_sum"] += float(r["longitude"]) * len(ips)
        city["weight"] += len(ips)
        city["ips"].update(ips)
        user = city["users"].get(r["uuid"])
        if user is None:
            city["users"][r["uuid"]] = {
                "uuid": r["uuid"], "username": r["username"] or r["uuid"][:8],
                "status": r["status"] or "unknown",
                "connections": int(r["connections"] or 0), "ips": ips,
            }
        else:
            user["connections"] += int(r["connections"] or 0)
            user["ips"] = sorted(set(user["ips"]) | set(ips))

    country_list = sorted(
        ({"country": c["country"], "country_code": c["country_code"],
          "count": len(c["users"]), "unique_ips": len(c["ips"])} for c in countries.values()),
        key=lambda c: c["count"], reverse=True,
    )[:50]

    city_list = []
    for city in cities.values():
        users = sorted(city["users"].values(), key=lambda u: u["connections"], reverse=True)
        weight = city["weight"] or 1
        city_list.append({
            "city": city["city"],
            "country": city["country"],
            "lat": city["lat_sum"] / weight,
            "lon": city["lon_sum"] / weight,
            "count": len(users),
            "unique_users": len(users),
            "unique_ips": len(city["ips"]),
            "users": users[:_GEO_CITY_USERS_LIMIT],
        })
    city_list.sort(key=lambda c: c["count"], reverse=True)

    return {"countries": country_list, "cities": city_list[:100]}


@router.get("/top-users")
@limiter.limit(RATE_ANALYTICS)
async def get_top_users_by_traffic(
    request: Request,
    limit: int = Query(20, ge=5, le=100),
    date_from: Optional[str] = Query(None, description="Start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="End date (ISO 8601)"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get top users by traffic consumption, optionally for a date range."""
    scope = await _user_scope(admin)
    if date_from and date_to:
        return await _top_users_range(date_from[:10], date_to[:10], limit, scope)
    if scope is None:
        return await _compute_top_users(limit=limit)
    return await _top_users(limit, scope)


@cached("analytics:top-users", ttl=CACHE_TTL_LONG, key_args=("limit",))
async def _compute_top_users(limit: int = 20):
    return await _top_users(limit, None)


_ONLINE_AT_SQL = "COALESCE(raw_data->'userTraffic'->>'onlineAt', raw_data->>'onlineAt') AS online_at"


async def _top_users(limit: int, scope: Optional[List[str]]) -> Dict[str, Any]:
    """Топ по счётчику панели (used_traffic_bytes — с последнего сброса)."""
    db_service = _db()
    try:
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    USERS_TABLE,
                    f"uuid::text AS uuid, username, status, used_traffic_bytes, traffic_limit_bytes, {_ONLINE_AT_SQL}",
                    "WHERE used_traffic_bytes > 0 AND ($2::uuid[] IS NULL OR uuid = ANY($2::uuid[])) "
                    "ORDER BY used_traffic_bytes DESC LIMIT $1",
                ),
                limit, scope,
            )
    except Exception as e:
        raise _failed("top-users", e)
    return {"items": [
        _usage_item(r["uuid"], r["username"], r["status"], int(r["used_traffic_bytes"] or 0),
                    r["traffic_limit_bytes"], r["online_at"])
        for r in rows
    ]}


async def _top_users_range(date_from: str, date_to: str, limit: int,
                           scope: Optional[List[str]]) -> Dict[str, Any]:
    """Топ за даты — по статистике панели, одним запросом по всем нодам.

    Панель отдаёт юзеров по имени; uuid, статус и онлайн берём из нашей базы.
    Ограниченному админу часть топа отсеется по видимости, поэтому у панели
    просим с запасом.
    """
    from shared.api_client import api_client

    db_service = _db()
    period = {"from": date_from, "to": date_to}
    try:
        async with db_service.acquire() as conn:
            node_rows = await conn.fetch(select_sql(NODES_TABLE, "uuid::text AS uuid", "WHERE NOT is_external"))
        node_uuids = [r["uuid"] for r in node_rows]
        if not node_uuids:
            return {"items": [], "period": period}

        fetch_limit = limit if scope is None else max(limit * 10, 500)
        resp = await api_client.get_nodes_users_usage(node_uuids, date_from, date_to, fetch_limit)
        payload = resp.get("response", resp) if isinstance(resp, dict) else {}
        traffic: Dict[str, int] = {}
        for u in payload.get("topUsers") or []:
            name = u.get("username") or ""
            total = int(u.get("total") or 0)
            if name and total > 0:
                traffic[name] = traffic.get(name, 0) + total

        users: Dict[str, Any] = {}
        if traffic:
            async with db_service.acquire() as conn:
                rows = await conn.fetch(
                    select_sql(
                        USERS_TABLE,
                        f"uuid::text AS uuid, username, status, traffic_limit_bytes, {_ONLINE_AT_SQL}",
                        "WHERE username = ANY($1::text[]) AND ($2::uuid[] IS NULL OR uuid = ANY($2::uuid[]))",
                    ),
                    list(traffic), scope,
                )
            users = {r["username"]: r for r in rows}
    except Exception as e:
        raise _failed("top-users range", e)

    items = []
    for name, used in sorted(traffic.items(), key=lambda kv: kv[1], reverse=True):
        r = users.get(name)
        if r is None:
            # Юзера нет в базе (удалён) — ограниченному админу его не видно
            if scope is not None:
                continue
            items.append(_usage_item("", name, None, used, None, None))
        else:
            items.append(_usage_item(r["uuid"], name, r["status"], used,
                                     r["traffic_limit_bytes"], r["online_at"]))
        # Доля лимита — про счётчик с последнего сброса, к трафику за даты не относится
        items[-1]["usage_percent"] = None
        if len(items) >= limit:
            break
    return {"items": items, "period": period}


@router.get("/nodes-traffic")
@limiter.limit(RATE_ANALYTICS)
async def get_nodes_traffic(
    request: Request,
    date_from: str = Query(..., description="Start date (ISO 8601)"),
    date_to: str = Query(..., description="End date (ISO 8601)"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Per-node traffic breakdown for a date range."""
    # Panel API expects YYYY-MM-DD, not full ISO 8601
    date_from = date_from[:10]
    date_to = date_to[:10]
    try:
        from web.backend.core.api_helper import fetch_nodes_usage_by_range
        resp = await fetch_nodes_usage_by_range(date_from, date_to, top_nodes_limit=100)
        logger.debug("nodes-traffic response keys: %s", list(resp.keys()) if isinstance(resp, dict) else type(resp))
        if not resp:
            return {"items": [], "total_bytes": 0, "period": {"from": date_from, "to": date_to}}

        nodes_data = resp.get("topNodes") or resp.get("nodes") or []
        if not nodes_data and isinstance(resp, dict):
            logger.debug("nodes-traffic full resp sample: %s", str(resp)[:500])

        # Enrich with node names from DB
        from shared.database import db_service
        node_names = {}
        if db_service.is_connected:
            try:
                async with db_service.acquire() as conn:
                    rows = await conn.fetch(select_sql(NODES_TABLE, "uuid, name"))
                    node_names = {str(r["uuid"]): r["name"] for r in rows}
            except Exception:
                pass

        # Access-policy: filter nodes by admin's scope
        from web.backend.core.rbac import get_scope
        node_scope = await get_scope(admin, "node", "view")

        items = []
        total = 0
        for n in nodes_data:
            uid = n.get("uuid", "")
            if node_scope is not None and uid.lower() not in node_scope:
                continue
            traffic = int(n.get("total", 0) or 0)
            total += traffic
            items.append({
                "uuid": uid,
                "name": node_names.get(uid, uid[:8]),
                "traffic_bytes": traffic,
            })

        # Add percentage
        for item in items:
            item["percent"] = round((item["traffic_bytes"] / total) * 100, 1) if total > 0 else 0

        return {"items": items, "total_bytes": total, "period": {"from": date_from, "to": date_to}}
    except Exception as e:
        raise _failed("nodes-traffic", e)


@router.get("/trends")
@limiter.limit(RATE_ANALYTICS)
async def get_trends(
    request: Request,
    metric: str = Query("users", pattern="^(users|traffic|violations)$"),
    period: str = Query("30d", description="Period: 7d, 30d, 90d, all"),
    date_from: Optional[str] = Query(None, description="Custom start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="Custom end date (ISO 8601)"),
    previous: bool = Query(False, description="Предыдущее окно той же длины — для сравнения"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Динамика по дням: новые юзеры, нарушения или трафик."""
    scope = await (_node_scope(admin) if metric == "traffic" else _user_scope(admin))
    if scope is None:
        return await _compute_trends(metric=metric, period=period, date_from=date_from,
                                     date_to=date_to, previous=previous)
    return await _trends(metric, period, date_from, date_to, previous, scope)


@cached("analytics:trends", ttl=CACHE_TTL_LONG, key_args=("metric", "period", "date_from", "date_to", "previous"))
async def _compute_trends(metric: str = "users", period: str = "30d", date_from: Optional[str] = None,
                          date_to: Optional[str] = None, previous: bool = False):
    return await _trends(metric, period, date_from, date_to, previous, None)


async def _trends(metric: str, period: str, date_from: Optional[str], date_to: Optional[str],
                  previous: bool, scope: Optional[List[str]]) -> Dict[str, Any]:
    """``scope`` — юзеры (users/violations) или ноды (traffic); None — все."""
    since, until = _bounds(period, date_from, date_to, default="30d")
    if previous:
        since, until = since - (until - since), since

    if metric == "traffic":
        series = await _traffic_series(since, until, scope)
    else:
        table, col, who = {
            "users": (USERS_TABLE, "created_at", "uuid"),
            "violations": (VIOLATIONS_TABLE, "detected_at", "user_uuid"),
        }[metric]
        tz = timefmt.sql_zone()
        db_service = _db()
        try:
            async with db_service.acquire() as conn:
                rows = await conn.fetch(
                    select_sql(
                        table,
                        f"DATE({col} AT TIME ZONE {tz}) AS day, COUNT(*) AS count",
                        f"WHERE {col} >= $1 AND {col} < $2 AND ($3::uuid[] IS NULL OR {who} = ANY($3::uuid[])) "
                        "GROUP BY day ORDER BY day",
                    ),
                    since, until, scope,
                )
        except Exception as e:
            raise _failed(f"trends {metric}", e)
        series = [{"date": str(r["day"]), "value": int(r["count"])} for r in rows]

    return {
        "series": series,
        "metric": metric,
        "period": period,
        "total_growth": sum(p["value"] for p in series),
        "since": since.isoformat(),
        "until": until.isoformat(),
    }


async def _traffic_series(since: datetime, until: datetime,
                          node_scope: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Трафик по дням из статистики панели — у неё вся история, а не 31 день
    наших снимков. Сутки панель режет по UTC, «по» у неё включительно."""
    from web.backend.core.api_helper import fetch_nodes_usage_by_range, parse_nodes_usage_series

    start = since.astimezone(timezone.utc).date()
    end = (until - timedelta(microseconds=1)).astimezone(timezone.utc).date()
    try:
        resp = await fetch_nodes_usage_by_range(start.isoformat(), end.isoformat(), top_nodes_limit=500)
    except Exception as e:
        raise _failed("trends traffic", e)
    if resp is None:
        raise api_error(502, E.API_SERVICE_UNAVAILABLE, "Panel bandwidth stats unavailable")
    allowed = None if node_scope is None else {u.lower() for u in node_scope}
    return [
        {"date": day, "value": sum(v for uid, v in per_node.items() if allowed is None or uid.lower() in allowed)}
        for day, per_node in parse_nodes_usage_series(resp)
    ]


@router.get("/shared-hwids")
@limiter.limit(RATE_ANALYTICS)
async def get_shared_hwids(
    request: Request,
    min_users: int = Query(2, ge=2, le=10),
    limit: int = Query(50, ge=5, le=200),
    admin: AdminUser = Depends(require_permission("violations", "view")),
):
    """Get HWIDs shared across multiple user accounts."""
    data = await _compute_shared_hwids(min_users=min_users, limit=limit)
    # Пороги блокировки — вне кэша, чтобы UI видел смену настройки сразу
    from shared.config_service import config_service
    try:
        threshold = int(config_service.get("violations_hard_block_hwid_accounts", 5) or 0)
    except (TypeError, ValueError):
        threshold = 0
    try:
        trials_threshold = int(config_service.get("violations_hwid_max_active_trials", 1) or 0)
    except (TypeError, ValueError):
        trials_threshold = 0
    return {
        **data,
        "hard_block_accounts_threshold": threshold,
        "active_trials_threshold": trials_threshold,
    }


@cached("analytics:shared-hwids", ttl=CACHE_TTL_LONG, key_args=("min_users", "limit"))
async def _compute_shared_hwids(min_users: int = 2, limit: int = 50):
    """Compute shared HWIDs (cacheable)."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"items": [], "total_shared_hwids": 0}

        items = await db_service.get_shared_hwids(min_users=min_users, limit=limit)
        return {"items": items, "total_shared_hwids": len(items)}

    except Exception as e:
        logger.error("get_shared_hwids failed: %s", e)
        return {"items": [], "total_shared_hwids": 0}


@router.get("/providers")
@limiter.limit(RATE_ANALYTICS)
async def get_providers(
    request: Request,
    period: str = Query("7d", description="Period: 24h, 7d, 30d, all"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Провайдеры за период: типы подключений, ASN и доля VPN/прокси/Tor/хостинга
    среди адресов, с которых подключались."""
    groups = await _provider_groups_for(admin, period)
    total = sum(g["count"] for g in groups)
    by_type: Dict[str, int] = defaultdict(int)
    flags = {f: 0 for f in _PROVIDER_FLAGS}
    for g in groups:
        by_type[g["type"]] += g["count"]
        for f in _PROVIDER_FLAGS:
            if g[f]:
                flags[f] += g["count"]
    return {
        "connection_types": [
            {"type": k, "count": v, "percent": _pct(v, total)}
            for k, v in sorted(by_type.items(), key=lambda kv: kv[1], reverse=True)
        ],
        "top_asn": _asn_list(groups, total)[:10],
        "flags": {f: {"count": n, "percent": _pct(n, total)} for f, n in flags.items()},
        "total": total,
    }


@router.get("/providers/asn-all")
@limiter.limit(RATE_ANALYTICS)
async def get_providers_asn_all(
    request: Request,
    period: str = Query("7d", description="Period: 24h, 7d, 30d, all"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get full ASN list (not just top 10) for export."""
    groups = [g for g in await _provider_groups_for(admin, period) if g["asn"] is not None]
    total = sum(g["count"] for g in groups)
    return {"asn_list": _asn_list(groups, total), "total": total}


@router.get("/providers/flag-asn")
@limiter.limit(RATE_ANALYTICS)
async def get_providers_flag_asn(
    request: Request,
    flag: str = Query(..., description="Flag: vpn, proxy, tor, hosting"),
    period: str = Query("7d", description="Period: 24h, 7d, 30d, all"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get ASN breakdown for a specific flag (VPN/Proxy/Tor/Hosting)."""
    if flag not in _PROVIDER_FLAGS:
        raise api_error(400, E.INVALID_INPUT, f"Invalid flag: {flag}")
    groups = [g for g in await _provider_groups_for(admin, period) if g[flag]]
    total = sum(g["count"] for g in groups)
    return {"flag": flag, "asn_list": _asn_list(groups, total)[:20], "total": total}


_PROVIDER_FLAGS = ("vpn", "proxy", "tor", "hosting")


def _pct(part: int, total: int) -> float:
    return round(part / total * 100, 1) if total else 0


def _asn_list(groups: List[Dict[str, Any]], total: int) -> List[Dict[str, Any]]:
    counts: Dict[int, int] = defaultdict(int)
    orgs: Dict[int, str] = {}
    for g in groups:
        if g["asn"] is not None:
            counts[g["asn"]] += g["count"]
            if g["org"]:
                orgs.setdefault(g["asn"], g["org"])
    return [
        {"asn": asn, "org": orgs.get(asn) or f"AS{asn}", "count": n, "percent": _pct(n, total)}
        for asn, n in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]


async def _provider_groups_for(admin, period: str) -> List[Dict[str, Any]]:
    scope = await _user_scope(admin)
    if scope is None:
        return await _compute_provider_groups(period=period)
    return await _provider_groups(period, scope)


@cached("analytics:provider-groups", ttl=CACHE_TTL_LONG, key_args=("period",))
async def _compute_provider_groups(period: str = "7d"):
    return await _provider_groups(period, None)


async def _provider_groups(period: str, scope: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Уникальные адреса подключений за период, сгруппированные по типу, ASN и
    флагам. Одна выборка на все три отчёта о провайдерах."""
    db_service = _db()
    since, until = _bounds(period)
    try:
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                f"""
                WITH ips AS (
                    SELECT DISTINCT SPLIT_PART(ip_address, '/', 1) AS ip
                    FROM {USER_CONNECTIONS_TABLE}
                    WHERE connected_at >= $1 AND connected_at < $2
                      AND ($3::uuid[] IS NULL OR user_uuid = ANY($3::uuid[]))
                )
                SELECT COALESCE(im.connection_type, 'unknown') AS type, im.asn, im.asn_org,
                       im.is_vpn, im.is_proxy, im.is_tor, im.is_hosting, COUNT(*) AS count
                FROM ips JOIN {IP_METADATA_TABLE} im ON im.ip_address = ips.ip
                GROUP BY 1, 2, 3, 4, 5, 6, 7
                """,
                since, until, scope,
            )
    except Exception as e:
        raise _failed("providers", e)
    return [
        {"type": r["type"], "asn": r["asn"], "org": r["asn_org"], "count": int(r["count"]),
         "vpn": bool(r["is_vpn"]), "proxy": bool(r["is_proxy"]),
         "tor": bool(r["is_tor"]), "hosting": bool(r["is_hosting"])}
        for r in rows
    ]


@router.get("/retention")
@limiter.limit(RATE_ANALYTICS)
async def get_retention(
    request: Request,
    weeks: int = Query(12, ge=4, le=52, description="Number of weeks to analyze"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get cohort retention analysis."""
    scope = await _user_scope(admin)
    if scope is None:
        return await _compute_retention(weeks=weeks)
    return await _retention(weeks, scope)


@cached("analytics:retention", ttl=CACHE_TTL_LONG, key_args=("weeks",))
async def _compute_retention(weeks: int = 12):
    return await _retention(weeks, None)


async def _retention(weeks: int, scope: Optional[List[str]]) -> Dict[str, Any]:
    """Когорты по неделе регистрации: сколько сейчас активны, пользовались ли
    вообще (трафик за всё время, а не с последнего сброса) и с живой подпиской."""
    db_service = _db()
    since = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    try:
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                f"""
                WITH cohorts AS (
                    SELECT
                        DATE_TRUNC('week', created_at AT TIME ZONE {timefmt.sql_zone()})::date AS cohort_week,
                        status,
                        GREATEST(
                            COALESCE(NULLIF(raw_data->'userTraffic'->>'lifetimeUsedTrafficBytes', '')::numeric, 0),
                            COALESCE(used_traffic_bytes, 0)
                        ) AS lifetime_bytes,
                        expire_at
                    FROM {USERS_TABLE}
                    WHERE created_at >= $1 AND ($2::uuid[] IS NULL OR uuid = ANY($2::uuid[]))
                )
                SELECT
                    cohort_week,
                    COUNT(*) AS total_users,
                    COUNT(*) FILTER (WHERE UPPER(status) = 'ACTIVE') AS active_users,
                    COUNT(*) FILTER (WHERE lifetime_bytes > 0) AS with_traffic,
                    COUNT(*) FILTER (WHERE expire_at IS NOT NULL AND expire_at > NOW()) AS with_active_sub
                FROM cohorts
                GROUP BY cohort_week
                ORDER BY cohort_week
                """,
                since, scope,
            )
    except Exception as e:
        raise _failed("retention", e)

    cohorts = []
    total_registered = 0
    total_retained = 0
    for r in rows:
        total = r["total_users"]
        active = r["active_users"]
        total_registered += total
        total_retained += active
        cohorts.append({
            "week": str(r["cohort_week"]),
            "total_users": total,
            "active_users": active,
            "retention_percent": _pct(active, total),
            "with_traffic_percent": _pct(r["with_traffic"], total),
            "with_active_sub_percent": _pct(r["with_active_sub"], total),
        })

    return {
        "cohorts": cohorts,
        "overall_retention": _pct(total_retained, total_registered),
        "total_registered": total_registered,
        "total_retained": total_retained,
    }


# ── Node Metrics History ────────────────────────────────────────

@router.get("/node-metrics-history")
@limiter.limit(RATE_ANALYTICS)
async def get_node_metrics_history(
    request: Request,
    period: str = Query("24h", description="Period: 24h, 7d, 30d"),
    node_uuid: Optional[str] = Query(None, description="Filter by node UUID"),
    admin: AdminUser = Depends(require_permission("fleet", "view")),
):
    """Get historical node metrics averages for the given period."""
    scope = await _node_scope(admin)
    if scope is None:
        return await _compute_node_metrics_history(period=period, node_uuid=node_uuid)
    if node_uuid and node_uuid.lower() not in scope:
        return {"nodes": [], "timeseries": [], "node_names": {}}
    return await _node_metrics_history(period, node_uuid, scope)


@cached("analytics:node-metrics-history", ttl=300, key_args=("period", "node_uuid"))
async def _compute_node_metrics_history(period: str = "24h", node_uuid: Optional[str] = None):
    return await _node_metrics_history(period, node_uuid, None)


def _num(v) -> Optional[float]:
    return float(v) if v is not None else None


async def _node_metrics_history(period: str, node_uuid: Optional[str],
                                scope: Optional[List[str]]) -> Dict[str, Any]:
    db_service = _db()
    try:
        nodes = await db_service.get_node_metrics_history(period=period, node_uuid=node_uuid)
        timeseries = await db_service.get_node_metrics_timeseries(
            period=period, node_uuid=node_uuid, node_uuids=scope,
        )
    except Exception as e:
        raise _failed("node-metrics-history", e)
    allowed = None if scope is None else set(scope)

    buckets: dict = defaultdict(dict)
    node_names: dict = {}
    for row in timeseries:
        b = row.get("bucket")
        # Момент в UTC с поясом — фронт покажет его на часах панели
        bucket_str = b.astimezone(timezone.utc).isoformat() if hasattr(b, "astimezone") else str(b)
        uid = str(row["node_uuid"])
        node_names[uid] = row.get("node_name", uid[:8])
        buckets[bucket_str][uid] = {
            "cpu": _num(row.get("avg_cpu")),
            "memory": _num(row.get("avg_memory")),
            "disk": _num(row.get("avg_disk")),
        }

    return {
        "nodes": [
            {
                "node_uuid": str(n["node_uuid"]),
                "node_name": n.get("node_name", ""),
                "avg_cpu": _num(n.get("avg_cpu")),
                "avg_memory": _num(n.get("avg_memory")),
                "avg_disk": _num(n.get("avg_disk")),
                "max_cpu": _num(n.get("max_cpu")),
                "max_memory": _num(n.get("max_memory")),
                "max_disk": _num(n.get("max_disk")),
                "samples_count": n.get("samples_count", 0),
            }
            for n in nodes
            if allowed is None or str(n["node_uuid"]).lower() in allowed
        ],
        "timeseries": [{"timestamp": k, "nodes": v} for k, v in sorted(buckets.items())],
        "node_names": node_names,
    }


# ── Torrent / P2P Analytics ────────────────────────────────────────

@router.get("/torrent-stats")
@limiter.limit(RATE_ANALYTICS)
async def get_torrent_stats(
    request: Request,
    days: int = Query(7, ge=1, le=3650, description="Days to look back"),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Торренты: события агента за период и отдельно — сводка плагина панели
    (у неё только «за всё время», поэтому с периодом их не складываем)."""
    scope = await _user_scope(admin)
    if scope is None:
        return await _compute_torrent_stats(days=days)
    return await _torrent_stats(days, scope)


@cached("analytics:torrent-stats", ttl=300, key_args=("days",))
async def _compute_torrent_stats(days: int = 7):
    return await _torrent_stats(days, None)


async def _torrent_stats(days: int, scope: Optional[List[str]]) -> Dict[str, Any]:
    db_service = _db()
    try:
        stats = await db_service.get_torrent_stats(days=days, user_uuids=scope)
        timeseries = await db_service.get_torrent_timeseries(days=days, user_uuids=scope)
        top_destinations = await db_service.get_torrent_top_destinations(days=days, user_uuids=scope)
    except Exception as e:
        raise _failed("torrent-stats", e)

    # Сводка плагина панели — общая на всех, ограниченному админу её не показываем
    panel = await _fetch_panel_torrent_stats() if scope is None else None
    return {
        "summary": {
            "total_events": stats.get("total_events", 0),
            "unique_users": stats.get("unique_users", 0),
            "unique_destinations": stats.get("unique_destinations", 0),
            "affected_nodes": stats.get("affected_nodes", 0),
        },
        "timeseries": timeseries,
        "top_users": stats.get("top_users", []),
        "top_destinations": top_destinations,
        "panel": panel,
    }


async def _fetch_panel_torrent_stats() -> Optional[Dict[str, Any]]:
    """Сводка плагина torrent-blocker панели (за всё время); None — плагина нет."""
    try:
        from shared.api_client import api_client
        result = await api_client.get_torrent_blocker_stats()
        resp = result.get("response", {})
        stats = resp.get("stats", {})
        return {
            "summary": {
                "total_events": stats.get("totalReports", 0),
                "unique_users": stats.get("distinctUsers", 0),
                "affected_nodes": stats.get("distinctNodes", 0),
                "reports_last_24h": stats.get("reportsLast24Hours", 0),
            },
            "top_users": [
                {"user_uuid": u.get("uuid", ""), "username": u.get("username", ""), "event_count": u.get("total", 0)}
                for u in resp.get("topUsers", [])
            ],
            "top_nodes": [
                {"name": n.get("name", ""), "uuid": n.get("uuid", ""),
                 "country_code": n.get("countryCode", ""), "total": n.get("total", 0)}
                for n in resp.get("topNodes", [])
            ],
        }
    except Exception as e:
        logger.debug("Panel torrent-blocker stats unavailable: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════
# Cohort Analysis — Retention Matrix & Churn
# ══════════════════════════════════════════════════════════════════


@router.get("/cohort-matrix")
@limiter.limit(RATE_ANALYTICS)
async def get_cohort_matrix(
    request: Request,
    granularity: str = Query("week", pattern="^(week|month)$"),
    months: int = Query(3, ge=1, le=12),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get cohort retention matrix — shows activity by cohort over time."""
    scope = await _user_scope(admin)
    if scope is None:
        return await _compute_cohort_matrix(granularity=granularity, months=months)
    return await _cohort_matrix(granularity, months, scope)


@cached("analytics:cohort-matrix", ttl=CACHE_TTL_LONG, key_args=("granularity", "months"))
async def _compute_cohort_matrix(granularity: str = "week", months: int = 3):
    return await _cohort_matrix(granularity, months, None)


async def _cohort_matrix(granularity: str, months: int, scope: Optional[List[str]]) -> Dict[str, Any]:
    db_service = _db()
    trunc = "week" if granularity == "week" else "month"
    tz = timefmt.sql_zone()
    since = datetime.now(timezone.utc) - timedelta(days=months * 30)
    try:
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                f"""
                WITH cohorts AS (
                    SELECT uuid, DATE_TRUNC('{trunc}', created_at AT TIME ZONE {tz})::date AS cohort
                    FROM {USERS_TABLE}
                    WHERE created_at >= $1 AND ($2::uuid[] IS NULL OR uuid = ANY($2::uuid[]))
                ),
                activity AS (
                    SELECT
                        c.cohort,
                        DATE_TRUNC('{trunc}', uc.connected_at AT TIME ZONE {tz})::date AS activity_period,
                        COUNT(DISTINCT c.uuid) AS active_users
                    FROM cohorts c
                    JOIN {USER_CONNECTIONS_TABLE} uc ON uc.user_uuid = c.uuid
                    WHERE uc.connected_at >= $1
                    GROUP BY c.cohort, activity_period
                ),
                cohort_sizes AS (
                    SELECT cohort, COUNT(*) AS total_users FROM cohorts GROUP BY cohort
                )
                SELECT
                    cs.cohort,
                    cs.total_users,
                    a.activity_period,
                    COALESCE(a.active_users, 0) AS active_users
                FROM cohort_sizes cs
                LEFT JOIN activity a ON a.cohort = cs.cohort
                ORDER BY cs.cohort, a.activity_period
                """,
                since, scope,
            )
    except Exception as e:
        raise _failed("cohort-matrix", e)

    cohort_data: Dict[str, Dict[str, Any]] = {}
    periods_set = set()
    for r in rows:
        cohort = str(r["cohort"])
        total = r["total_users"]
        if cohort not in cohort_data:
            cohort_data[cohort] = {"cohort": cohort, "total_users": total, "periods": {}}
        if r["activity_period"]:
            period = str(r["activity_period"])
            periods_set.add(period)
            cohort_data[cohort]["periods"][period] = {
                "active_users": r["active_users"],
                "retention_percent": _pct(r["active_users"], total),
            }

    return {
        "cohorts": sorted(cohort_data.values(), key=lambda x: x["cohort"]),
        "periods": sorted(periods_set),
        "granularity": granularity,
        "connections_retention_days": _connections_retention_days(),
    }


def _connections_retention_days() -> int:
    """Сколько дней хранятся подключения: активность старше не видна."""
    from shared.config_service import config_service
    try:
        return int(config_service.get("connections_retention_days", 30) or 30)
    except (TypeError, ValueError):
        return 30


@router.get("/churn")
@limiter.limit(RATE_ANALYTICS)
async def get_churn_rate(
    request: Request,
    period: str = Query("month", pattern="^(week|month)$"),
    months: int = Query(6, ge=1, le=24),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Get churn rate over time — users who stopped being active."""
    scope = await _user_scope(admin)
    if scope is None:
        return await _compute_churn(period=period, months=months)
    return await _churn(period, months, scope)


@cached("analytics:churn", ttl=CACHE_TTL_LONG, key_args=("period", "months"))
async def _compute_churn(period: str = "month", months: int = 6):
    return await _churn(period, months, None)


async def _churn(period: str, months: int, scope: Optional[List[str]]) -> Dict[str, Any]:
    db_service = _db()
    trunc = "week" if period == "week" else "month"
    tz = timefmt.sql_zone()
    since = datetime.now(timezone.utc) - timedelta(days=months * 30)
    try:
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                f"""
                WITH periods AS (
                    SELECT
                        DATE_TRUNC('{trunc}', connected_at AT TIME ZONE {tz})::date AS p,
                        COUNT(DISTINCT user_uuid) AS active_users
                    FROM {USER_CONNECTIONS_TABLE}
                    WHERE connected_at >= $1 AND ($2::uuid[] IS NULL OR user_uuid = ANY($2::uuid[]))
                    GROUP BY p
                ),
                total_by_period AS (
                    SELECT
                        DATE_TRUNC('{trunc}', created_at AT TIME ZONE {tz})::date AS p,
                        COUNT(*) AS new_users
                    FROM {USERS_TABLE}
                    WHERE created_at >= $1 AND ($2::uuid[] IS NULL OR uuid = ANY($2::uuid[]))
                    GROUP BY p
                )
                SELECT
                    p.p AS period,
                    p.active_users,
                    COALESCE(t.new_users, 0) AS new_users,
                    LAG(p.active_users) OVER (ORDER BY p.p) AS prev_active
                FROM periods p
                LEFT JOIN total_by_period t ON t.p = p.p
                ORDER BY p.p
                """,
                since, scope,
            )
    except Exception as e:
        raise _failed("churn", e)

    series = []
    rates = []
    for r in rows:
        active, prev, new = r["active_users"], r["prev_active"], r["new_users"]
        churned = 0
        churn_rate = 0
        if prev and prev > 0:
            # Ушедшие = активные в прошлом периоде + новые − активные сейчас
            churned = max(0, prev + new - active)
            churn_rate = round(churned / prev * 100, 1)
            rates.append(churn_rate)
        series.append({
            "period": str(r["period"]),
            "active_users": active,
            "new_users": new,
            "churned_users": churned,
            "churn_rate": churn_rate,
        })

    return {
        "series": series,
        "avg_churn": round(sum(rates) / len(rates), 1) if rates else 0,
        "period": period,
        "connections_retention_days": _connections_retention_days(),
    }


@router.get("/ltv")
@limiter.limit(RATE_ANALYTICS)
async def get_ltv_estimate(
    request: Request,
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Оценка LTV в рублях: ARPU × средний срок жизни юзера.

    ARPU — пополнения Bedolaga за 30 дней (их пишет в финансы ежедневный
    рекордер) на число платных подписок из Bedolaga. Рядом — во что обходится
    один активный юзер в месяц по регулярным расходам.
    """
    return await _compute_ltv()


@cached("analytics:ltv", ttl=CACHE_TTL_LONG)
async def _compute_ltv() -> Dict[str, Any]:
    from shared.db_schema import FINANCE_PAYMENTS_TABLE
    from web.backend.core.finance.bedolaga_income import DEPOSIT_SOURCE

    db_service = _db()
    try:
        async with db_service.acquire() as conn:
            # Срок жизни — от регистрации до последнего онлайна по данным панели
            # (вся история, а не только хранимые подключения)
            lifetime_row = await conn.fetchrow(
                f"""
                SELECT AVG(EXTRACT(EPOCH FROM (last_seen - created_at)) / 86400) AS avg_days,
                       COUNT(*) AS sample_size
                FROM (
                    SELECT created_at,
                           NULLIF(COALESCE(raw_data->'userTraffic'->>'onlineAt', raw_data->>'onlineAt'), '')::timestamptz
                               AS last_seen
                    FROM {USERS_TABLE}
                    WHERE created_at >= NOW() - INTERVAL '12 months'
                ) s
                WHERE last_seen > created_at
                """
            )
            revenue_30d = await conn.fetchval(
                f"""SELECT COALESCE(SUM(amount * COALESCE(rate_rub, 1)), 0)
                    FROM {FINANCE_PAYMENTS_TABLE}
                    WHERE kind = 'income' AND source = $1 AND paid_at >= CURRENT_DATE - 30""",
                DEPOSIT_SOURCE,
            )
        summary = await db_service.finance_summary(months=1)
        counts = await db_service.get_users_count_by_status()
    except Exception as e:
        raise _failed("ltv", e)

    avg_days = float(lifetime_row["avg_days"] or 0)
    avg_months = avg_days / 30
    active = int(counts.get("active") or 0)
    monthly_cost = float((summary.get("recurring") or {}).get("expense_rub", 0) or 0)
    cost_per_user = round(monthly_cost / active, 2) if active else None

    paying, bedolaga = await _bedolaga_paid_subscriptions()
    revenue = round(float(revenue_30d or 0), 2)
    arpu = round(revenue / paying, 2) if paying else None
    ltv = round(arpu * avg_months, 2) if arpu is not None else None

    return {
        "currency": "RUB",
        "avg_lifetime_days": round(avg_days, 1),
        "sample_size": lifetime_row["sample_size"] or 0,
        # bedolaga: ok | not_configured | unavailable
        "revenue_source": bedolaga,
        "revenue_30d": revenue,
        "paying_users": paying,
        "arpu_month": arpu,
        "ltv": ltv,
        "cost_per_user_month": cost_per_user,
        "active_users": active,
    }


async def _bedolaga_paid_subscriptions() -> tuple:
    """Число платных подписок сейчас из Bedolaga и статус источника."""
    from shared.bedolaga_client import bedolaga_client
    from web.backend.api.v2.bedolaga import proxy_request

    try:
        full = await proxy_request(bedolaga_client.get_full_stats)
    except HTTPException as e:
        return None, "not_configured" if e.status_code == 503 else "unavailable"
    except Exception as e:
        logger.warning("Bedolaga stats for LTV unavailable: %s", e)
        return None, "unavailable"
    subs = (full or {}).get("subscriptions") or {}
    try:
        return int(subs.get("paid_subscriptions") or 0), "ok"
    except (TypeError, ValueError):
        return None, "unavailable"


# ══════════════════════════════════════════════════════════════════
# Geo-Balancing Recommendations
# ══════════════════════════════════════════════════════════════════


@router.get("/geo-balance")
@limiter.limit(RATE_ANALYTICS)
async def get_geo_balance(
    request: Request,
    days: int = Query(7, ge=1, le=90),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Geo-balancing analysis: node load distribution and recommendations."""
    scope = await _node_scope(admin)
    if scope is None:
        return await _compute_geo_balance(days=days)
    return await _geo_balance(days, scope)


@cached("analytics:geo-balance", ttl=900, key_args=("days",))
async def _compute_geo_balance(days: int = 7):
    return await _geo_balance(days, None)


async def _geo_balance(days: int, scope: Optional[List[str]]) -> Dict[str, Any]:
    """Нагрузка нод панели и откуда к ним ходят. Свои серверы без панели
    (is_external) не в счёт: юзеров на них нет. Рекомендации — кодами с
    параметрами, текст собирает фронт на языке админа."""
    db_service = _db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        async with db_service.acquire() as conn:
            node_rows = await conn.fetch(
                select_sql(
                    NODES_TABLE,
                    "uuid::text, name, is_connected, is_disabled, cpu_usage, memory_usage, disk_usage, "
                    "COALESCE((raw_data->>'usersOnline')::int, 0) AS users_online",
                    "WHERE NOT is_external AND ($1::uuid[] IS NULL OR uuid = ANY($1::uuid[])) ORDER BY name",
                ),
                scope,
            )
            geo_rows = await conn.fetch(
                f"""
                SELECT
                    uc.node_uuid::text AS node_uuid,
                    COALESCE(im.country_code, '??') AS country_code,
                    COALESCE(im.country_name, 'Unknown') AS country_name,
                    COUNT(DISTINCT uc.user_uuid) AS user_count,
                    COUNT(*) AS connection_count
                FROM {USER_CONNECTIONS_TABLE} uc
                LEFT JOIN {IP_METADATA_TABLE} im ON im.ip_address = SPLIT_PART(uc.ip_address, '/', 1)
                WHERE uc.connected_at >= $1 AND ($2::uuid[] IS NULL OR uc.node_uuid = ANY($2::uuid[]))
                GROUP BY uc.node_uuid, im.country_code, im.country_name
                ORDER BY user_count DESC
                """,
                since, scope,
            )
            country_totals = await conn.fetch(
                f"""
                SELECT
                    COALESCE(im.country_code, '??') AS country_code,
                    COALESCE(im.country_name, 'Unknown') AS country_name,
                    COUNT(DISTINCT uc.user_uuid) AS user_count
                FROM {USER_CONNECTIONS_TABLE} uc
                LEFT JOIN {IP_METADATA_TABLE} im ON im.ip_address = SPLIT_PART(uc.ip_address, '/', 1)
                WHERE uc.connected_at >= $1 AND ($2::uuid[] IS NULL OR uc.node_uuid = ANY($2::uuid[]))
                GROUP BY im.country_code, im.country_name
                ORDER BY user_count DESC
                LIMIT 30
                """,
                since, scope,
            )
    except Exception as e:
        raise _failed("geo-balance", e)

    node_geo: Dict[str, List] = defaultdict(list)
    for r in geo_rows:
        node_geo[r["node_uuid"]].append({
            "country_code": r["country_code"],
            "country_name": r["country_name"],
            "user_count": r["user_count"],
            "connection_count": r["connection_count"],
        })

    nodes = []
    for n in node_rows:
        cpu = n["cpu_usage"] or 0
        mem = n["memory_usage"] or 0
        disk = n["disk_usage"] or 0
        nodes.append({
            "uuid": n["uuid"],
            "name": n["name"],
            "is_connected": n["is_connected"],
            "is_disabled": n["is_disabled"],
            "cpu_usage": round(cpu, 1),
            "memory_usage": round(mem, 1),
            "disk_usage": round(disk, 1),
            "users_online": n["users_online"] or 0,
            "is_overloaded": cpu > 80 or mem > 85 or disk > 90,
            "top_countries": node_geo.get(n["uuid"], [])[:5],
        })

    live = [n for n in nodes if n["is_connected"] and not n["is_disabled"]]
    online_values = sorted(n["users_online"] for n in live)
    median_online = online_values[len(online_values) // 2] if online_values else 0

    recommendations = []
    overloaded = [n for n in live if n["is_overloaded"]]
    for n in overloaded:
        reasons = [
            {"metric": metric, "value": n[f"{metric}_usage"]}
            for metric, limit in (("cpu", 80), ("memory", 85), ("disk", 90))
            if n[f"{metric}_usage"] > limit
        ]
        recommendations.append({
            "type": "overloaded",
            "severity": "critical" if n["cpu_usage"] > 90 or n["memory_usage"] > 90 else "warning",
            "node": n["name"],
            "node_uuid": n["uuid"],
            "reasons": reasons,
        })
    for n in live:
        if median_online > 0 and n["users_online"] > median_online * 2.5 and n["users_online"] > 50:
            recommendations.append({
                "type": "unbalanced",
                "severity": "warning",
                "node": n["name"],
                "node_uuid": n["uuid"],
                "users_online": n["users_online"],
                "median": median_online,
            })

    return {
        "nodes": nodes,
        "recommendations": recommendations,
        "regions": [
            {"country_code": r["country_code"], "country_name": r["country_name"], "user_count": r["user_count"]}
            for r in country_totals
        ],
        "median_users_online": median_online,
        "overloaded_count": len(overloaded),
    }


# ══════════════════════════════════════════════════════════════════
# IP Export
# ══════════════════════════════════════════════════════════════════

_EXPORT_IPS_LIMIT = 50_000


@router.get("/export-ips")
@limiter.limit(RATE_ANALYTICS)
async def export_ips(
    request: Request,
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
    node_uuids: Optional[str] = Query(None, description="Comma-separated node UUIDs"),
    username: Optional[str] = Query(None),
    active_only: bool = Query(False),
    admin: AdminUser = Depends(require_permission("analytics", "view")),
):
    """Выгрузка адресов за период: по адресу — кто с него ходил, на какие ноды
    и геоданные. Только в пределах видимых админу юзеров и нод; пишется в аудит."""
    try:
        since = timefmt.parse_filter(date_from)
        until = timefmt.parse_filter(date_to, end=True)
    except ValueError:
        raise api_error(400, E.INVALID_INPUT, "Invalid date format")
    if since is None or until is None or since >= until:
        raise api_error(400, E.INVALID_INPUT, "Invalid date range")

    requested_nodes = [u.strip().lower() for u in (node_uuids or "").split(",") if u.strip()]
    node_scope = await _node_scope(admin)
    if node_scope is not None:
        allowed = set(node_scope)
        requested_nodes = [u for u in requested_nodes if u in allowed] if requested_nodes else sorted(allowed)
        if not requested_nodes:
            return {"items": [], "total": 0, "truncated": False}

    result = await _export_ips(
        since, until, requested_nodes or None, username, active_only, await _user_scope(admin),
    )

    import json
    from web.backend.api.deps import get_client_ip
    from web.backend.core.audit import write_audit_log
    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="analytics.export_ips",
        resource="analytics",
        details=json.dumps({
            "date_from": date_from, "date_to": date_to, "node_uuids": node_uuids,
            "username": username, "active_only": active_only, "total": result["total"],
        }, ensure_ascii=False),
        ip_address=get_client_ip(request),
    )
    return result


async def _export_ips(since: datetime, until: datetime, node_uuids: Optional[List[str]],
                      username: Optional[str], active_only: bool,
                      scope: Optional[List[str]]) -> Dict[str, Any]:
    db_service = _db()
    try:
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT s.*, im.country_code, im.country_name, im.city, im.asn, im.asn_org,
                       im.connection_type, im.is_vpn, im.is_proxy, im.is_tor, im.is_hosting
                FROM (
                    SELECT SPLIT_PART(uc.ip_address, '/', 1) AS ip,
                           array_agg(DISTINCT u.username) FILTER (WHERE u.username IS NOT NULL) AS usernames,
                           array_agg(DISTINCT n.name) FILTER (WHERE n.name IS NOT NULL) AS node_names,
                           MAX(uc.connected_at) AS connected_at,
                           COUNT(*) AS connections
                    FROM {USER_CONNECTIONS_TABLE} uc
                    LEFT JOIN {USERS_TABLE} u ON u.uuid = uc.user_uuid
                    LEFT JOIN {NODES_TABLE} n ON n.uuid = uc.node_uuid
                    WHERE uc.connected_at >= $1 AND uc.connected_at < $2
                      AND ($3::uuid[] IS NULL OR uc.node_uuid = ANY($3::uuid[]))
                      AND ($4::text IS NULL OR LOWER(u.username) = LOWER($4::text))
                      AND (NOT $5 OR uc.disconnected_at IS NULL)
                      AND ($6::uuid[] IS NULL OR uc.user_uuid = ANY($6::uuid[]))
                    GROUP BY 1
                    ORDER BY MAX(uc.connected_at) DESC
                    LIMIT $7
                ) s
                LEFT JOIN {IP_METADATA_TABLE} im ON im.ip_address = s.ip
                ORDER BY s.connected_at DESC
                """,
                since, until, node_uuids, (username or "").strip() or None, active_only, scope,
                _EXPORT_IPS_LIMIT + 1,
            )
    except Exception as e:
        raise _failed("export-ips", e)

    truncated = len(rows) > _EXPORT_IPS_LIMIT
    items = []
    for r in rows[:_EXPORT_IPS_LIMIT]:
        item = dict(r)
        usernames = sorted(item.pop("usernames") or [])
        node_names = sorted(item.pop("node_names") or [])
        item["usernames"] = usernames
        item["username"] = ", ".join(usernames)
        item["node_names"] = node_names
        item["node_name"] = ", ".join(node_names)
        if item.get("connected_at"):
            item["connected_at"] = item["connected_at"].isoformat()
        items.append(item)
    return {"items": items, "total": len(items), "truncated": truncated}

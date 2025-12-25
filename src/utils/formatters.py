from datetime import datetime
from typing import Any, Callable
import html


NA = "n/a"
def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def escape_markdown(text: str) -> str:
    """Экранирует специальные символы Markdown для Telegram."""
    if not text:
        return ""
    # Экранируем только основные специальные символы Markdown для Telegram
    # Не экранируем символы, которые используются в шаблонах или не вызывают проблем
    special_chars = ['*', '_', '`', '[', ']', '(', ')', '~']
    result = str(text)
    for char in special_chars:
        result = result.replace(char, f'\\{char}')
    return result


def format_bytes(value: float | int | None) -> str:
    if value is None:
        return NA
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if abs(size) < 1024.0:
            return f"{size:3.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_datetime(dt_str: str | None) -> str:
    if not dt_str:
        return NA
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return dt_str


def format_uptime(seconds: float | int | None) -> str:
    if seconds is None:
        return NA
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    return " ".join(parts) or "0m"


def build_user_summary(user: dict, t: Callable[[str], str]) -> str:
    info = user.get("response", user)
    status = info.get("status", "UNKNOWN")
    expire_at = format_datetime(info.get("expireAt"))
    used = info.get("userTraffic", {}).get("usedTrafficBytes", 0)
    limit = info.get("trafficLimitBytes")
    hwid_limit = info.get("hwidDeviceLimit", NA)
    last_online = format_datetime(info.get("userTraffic", {}).get("onlineAt"))
    created_at = format_datetime(info.get("createdAt"))
    subscription_url = info.get("subscriptionUrl") or NA
    status_emoji = {
        "ACTIVE": "🟢",
        "DISABLED": "⚪",
        "LIMITED": "🟠",
        "EXPIRED": "🔴",
    }.get(status, "⚙️")

    return t("user.summary").format(
        username=_esc(info.get("username", NA)),
        status=_esc(status),
        statusEmoji=status_emoji,
        uuid=_esc(info.get("uuid", NA)),
        shortUuid=_esc(info.get("shortUuid", NA)),
        telegramId=_esc(info.get("telegramId", NA)),
        subscriptionUrl=_esc(subscription_url),
        used=_esc(format_bytes(used)),
        limit=_esc(format_bytes(limit)),
        hwid=_esc(hwid_limit),
        expire=_esc(expire_at),
        online=_esc(last_online),
        created=_esc(created_at),
    )


def build_created_user(user: dict, t: Callable[[str], str]) -> str:
    info = user.get("response", user)
    expire_at = format_datetime(info.get("expireAt"))
    telegram_id = info.get("telegramId", NA)

    return t("user.created").format(
        username=info.get("username", "n/a"),
        status=info.get("status", "UNKNOWN"),
        uuid=info.get("uuid", "n/a"),
        shortUuid=info.get("shortUuid", "n/a"),
        telegramId=telegram_id if telegram_id is not None else NA,
        expire=expire_at,
        subscriptionUrl=info.get("subscriptionUrl", NA),
    )


def build_node_summary(node: dict, t: Callable[[str], str]) -> str:
    info = node.get("response", node)
    status = "DISABLED" if info.get("isDisabled") else ("ONLINE" if info.get("isConnected") else "OFFLINE")
    status_emoji = "✅" if status == "ONLINE" else ("⚠️" if status == "DISABLED" else "❌")
    traffic_used = info.get("trafficUsedBytes")
    traffic_limit = info.get("trafficLimitBytes")
    users_online = info.get("usersOnline", 0)
    last_change = format_datetime(info.get("lastStatusChange"))
    tags = ", ".join(info.get("tags", [])) if info.get("tags") else NA

    return t("node.summary").format(
        statusEmoji=status_emoji,
        name=info.get("name", "n/a"),
        status=status,
        address=info.get("address", "n/a"),
        port=info.get("port", NA),
        users=users_online if users_online is not None else NA,
        trafficUsed=format_bytes(traffic_used),
        trafficLimit=format_bytes(traffic_limit),
        lastChange=last_change,
        tags=tags,
        uuid=info.get("uuid", "n/a"),
    )


def build_nodes_realtime_usage(usages: list[dict], t: Callable[[str], str]) -> str:
    if not usages:
        return t("node.realtime_empty")
    lines = [t("node.realtime_title")]
    for item in usages[:10]:
        lines.append(
            t("node.realtime_item").format(
                name=item.get("nodeName", "n/a"),
                country=item.get("countryCode", "n/a"),
                down=format_bytes(item.get("downloadBytes")),
                up=format_bytes(item.get("uploadBytes")),
                speed_down=format_bytes(item.get("downloadSpeedBps")) + "/s",
                speed_up=format_bytes(item.get("uploadSpeedBps")) + "/s",
            )
        )
    if len(usages) > 10:
        lines.append(t("node.list_more").format(count=len(usages) - 10))
    return "\n".join(lines)


def build_nodes_usage_range(usages: list[dict], t: Callable[[str], str]) -> str:
    if not usages:
        return t("node.range_empty")
    lines = [t("node.range_title")]
    for item in usages[:10]:
        lines.append(
            t("node.range_item").format(
                date=item.get("date", "n/a"),
                name=item.get("nodeName", "n/a"),
                country=item.get("nodeCountryCode", "n/a"),
                total=item.get("humanReadableTotal", "n/a"),
                down=item.get("humanReadableTotalDownload", "n/a"),
                up=item.get("humanReadableTotalUpload", "n/a"),
            )
        )
    if len(usages) > 10:
        lines.append(t("node.list_more").format(count=len(usages) - 10))
    return "\n".join(lines)


def build_bandwidth_stats(stats: dict, t: Callable[[str], str]) -> str:
    resp = stats.get("response", stats) or {}

    def row(key: str, label: str) -> str:
        item = resp.get(key, {})
        current = item.get("current", NA)
        previous = item.get("previous", NA)
        diff = item.get("difference", NA)
        return t("bandwidth.row").format(
            label=f"*{label}*",
            current=f"`{current}`",
            previous=f"`{previous}`",
            diff=f"`{diff}`",
        )

    lines = [
        f"*{t('bandwidth.title')}*",
        "",
        row("bandwidthLastTwoDays", t("bandwidth.last_two_days")),
        row("bandwidthLastSevenDays", t("bandwidth.last_seven_days")),
        row("bandwidthLast30Days", t("bandwidth.last_30_days")),
        row("bandwidthCalendarMonth", t("bandwidth.calendar_month")),
        row("bandwidthCurrentYear", t("bandwidth.current_year")),
    ]
    return "\n".join(lines)


def build_host_summary(host: dict, t: Callable[[str], str]) -> str:
    info = host.get("response", host)
    status = "DISABLED" if info.get("isDisabled") else "ENABLED"
    status_emoji = "⚠️" if status == "DISABLED" else "✅"
    address = f"{info.get('address', 'n/a')}:{info.get('port', 'n/a')}"
    remark = info.get("remark") or "n/a"
    tag = info.get("tag") or "n/a"
    return t("host.summary").format(
        statusEmoji=status_emoji,
        remark=remark,
        address=address,
        tag=tag,
        uuid=info.get("uuid", "n/a"),
    )


def _safe_int(val: Any) -> int | None:
    try:
        return int(val)
    except Exception:
        return None


def build_subscription_summary(sub: dict, t: Callable[[str], str]) -> str:
    info = sub.get("response", sub)
    user = info.get("user", {})
    short_uuid = user.get("shortUuid", "n/a")
    username = user.get("username", "n/a")
    status = user.get("userStatus", "UNKNOWN")
    days_left = user.get("daysLeft")
    expires_at = format_datetime(user.get("expiresAt"))

    used_bytes = _safe_int(user.get("trafficUsedBytes") or user.get("trafficUsed"))
    limit_bytes = _safe_int(user.get("trafficLimitBytes") or user.get("trafficLimit"))
    lifetime_bytes = _safe_int(user.get("lifetimeTrafficUsedBytes") or user.get("lifetimeTrafficUsed"))

    used = format_bytes(used_bytes)
    limit = format_bytes(limit_bytes)
    lifetime = format_bytes(lifetime_bytes)

    subscription_url = info.get("subscriptionUrl", "n/a")

    return t("sub.summary").format(
        shortUuid=short_uuid,
        username=username,
        status=status,
        daysLeft=days_left if days_left is not None else "n/a",
        used=used,
        limit=limit,
        lifetime=lifetime,
        expires=expires_at,
        url=subscription_url,
    )


def _mask_token(token: str) -> str:
    if not token:
        return NA
    if len(token) <= 8:
        return token
    return f"{token[:4]}...{token[-4:]}"


def build_tokens_list(tokens: list[dict], t: Callable[[str], str]) -> str:
    if not tokens:
        return t("token.list_empty")
    lines = [t("token.list_title").format(total=len(tokens))]
    for item in tokens[:10]:
        token = item.get("token", "")
        token_name = item.get("tokenName", "n/a")
        uuid = item.get("uuid", "n/a")
        masked = _mask_token(token)
        lines.append(t("token.list_item").format(name=token_name, token=masked, uuid=uuid))
    if len(tokens) > 10:
        lines.append(t("token.list_more").format(count=len(tokens) - 10))
    lines.append(t("token.list_hint"))
    return "\n".join(lines)


def build_created_token(token: dict, t: Callable[[str], str]) -> str:
    info = token.get("response", token)
    return t("token.created").format(token=info.get("token", "n/a"), uuid=info.get("uuid", "n/a"))


def build_token_line(token: dict, t: Callable[[str], str]) -> str:
    token_name = token.get("tokenName", "n/a")
    uuid = token.get("uuid", "n/a")
    masked = _mask_token(token.get("token", ""))
    return t("token.list_item").format(name=token_name, token=masked, uuid=uuid)


def build_templates_list(templates: list[dict], t: Callable[[str], str]) -> str:
    if not templates:
        return t("template.list_empty")
    lines = [t("template.list_title").format(total=len(templates))]
    for tpl in sorted(templates, key=lambda x: x.get("viewPosition", 0))[:10]:
        lines.append(
            t("template.list_item").format(
                name=tpl.get("name", "n/a"),
                type=tpl.get("templateType", "n/a"),
                uuid=tpl.get("uuid", "n/a"),
            )
        )
    if len(templates) > 10:
        lines.append(t("template.list_more").format(count=len(templates) - 10))
    lines.append(t("template.list_hint"))
    return "\n".join(lines)


def build_template_summary(template: dict, t: Callable[[str], str]) -> str:
    info = template.get("response", template)
    return t("template.summary").format(
        name=info.get("name", "n/a"),
        type=info.get("templateType", "n/a"),
        uuid=info.get("uuid", "n/a"),
    )


def build_snippets_list(snippets: list[dict], t: Callable[[str], str]) -> str:
    if not snippets:
        return t("snippet.list_empty")
    lines = [t("snippet.list_title").format(total=len(snippets))]
    for snip in snippets[:10]:
        lines.append(t("snippet.list_item").format(name=snip.get("name", "n/a")))
    if len(snippets) > 10:
        lines.append(t("snippet.list_more").format(count=len(snippets) - 10))
    lines.append(t("snippet.list_hint"))
    return "\n".join(lines)


def _pretty_json(data: Any, limit: int = 800) -> str:
    try:
        import json

        text = json.dumps(data, ensure_ascii=False, indent=2)
    except Exception:
        text = str(data)
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def build_snippet_detail(snippet: dict, t: Callable[[str], str]) -> str:
    name = snippet.get("name", "n/a")
    content = snippet.get("snippet")
    content_text = _pretty_json(content)
    return t("snippet.detail").format(name=name, content=content_text)


def build_config_profiles_list(profiles: list[dict], t: Callable[[str], str]) -> str:
    if not profiles:
        return t("config.list_empty")
    lines = [t("config.list_title").format(total=len(profiles))]
    for profile in sorted(profiles, key=lambda p: p.get("viewPosition", 0))[:10]:
        lines.append(
            t("config.list_item").format(
                name=profile.get("name", "n/a"),
                nodes=len(profile.get("nodes", [])),
                uuid=profile.get("uuid", "n/a"),
            )
        )
    if len(profiles) > 10:
        lines.append(t("config.list_more").format(count=len(profiles) - 10))
    lines.append(t("config.list_hint"))
    return "\n".join(lines)


def build_config_profile_detail(profile: dict, t: Callable[[str], str]) -> str:
    info = profile.get("response", profile)
    inbounds = info.get("inbounds", [])
    nodes = info.get("nodes", [])
    return t("config.detail").format(
        name=info.get("name", "n/a"),
        uuid=info.get("uuid", "n/a"),
        inbounds=len(inbounds),
        nodes=len(nodes),
    )


def build_billing_history(records: list[dict], t: Callable[[str], str]) -> str:
    if not records:
        return f"*{t('billing.title').split(':')[0]}*\n\n{t('billing.empty')}"
    lines = [f"*{t('billing.title').format(total=len(records))}*", ""]
    for rec in records[:10]:
        provider = rec.get("provider", {})
        amount = rec.get("amount", NA)
        date = format_datetime(rec.get("billedAt"))
        provider_name = provider.get("name", NA)
        lines.append(
            t("billing.item").format(
                amount=f"*{amount}*",
                provider=f"`{provider_name}`",
                date=f"`{date}`",
            )
        )
    if len(records) > 10:
        lines.append("")
        lines.append(t("billing.more").format(count=len(records) - 10))
    return "\n".join(lines)


def build_infra_providers(providers: list[dict], t: Callable[[str], str]) -> str:
    if not providers:
        return f"*{t('provider.title').split(':')[0]}*\n\n{t('provider.empty')}"
    lines = [f"*{t('provider.title').format(total=len(providers))}*", ""]
    for prov in providers[:10]:
        hist = prov.get("billingHistory", {}) or {}
        nodes = prov.get("billingNodes", []) or []
        lines.append(
            t("provider.item").format(
                name=f"*{prov.get('name', NA)}*",
                totalAmount=f"`{hist.get('totalAmount', NA)}`",
                totalBills=f"`{hist.get('totalBills', NA)}`",
                nodes=f"`{len(nodes)}`",
            )
        )
    if len(providers) > 10:
        lines.append("")
        lines.append(t("provider.more").format(count=len(providers) - 10))
    return "\n".join(lines)


def build_billing_nodes(data: dict, t: Callable[[str], str]) -> str:
    resp = data.get("response", data) or {}
    nodes = resp.get("billingNodes", []) or []
    stats = resp.get("stats", {}) or {}
    if not nodes:
        return f"*{t('billing_nodes.title').split(':')[0]}*\n\n{t('billing_nodes.empty')}"
    upcoming_val = stats.get("upcomingNodesCount", NA)
    month_val = stats.get("currentMonthPayments", NA)
    total_val = stats.get("totalSpent", NA)
    
    lines = [
        f"*{t('billing_nodes.title').format(total=resp.get('totalBillingNodes', len(nodes)))}*",
        "",
        f"*{t('billing_nodes.stats_section')}*",
        f"  {t('billing_nodes.stats_text').format(upcoming=f'*{upcoming_val}*', month=f'`{month_val}`', total=f'*{total_val}*')}",
        "",
        f"*{t('billing_nodes.nodes_section')}*",
    ]
    for item in nodes[:10]:
        node = item.get("node", {})
        prov = item.get("provider", {})
        node_name = node.get("name", NA)
        country_code = node.get("countryCode", NA)
        provider_name = prov.get("name", NA)
        next_billing = format_datetime(item.get("nextBillingAt"))
        lines.append(
            f"  {t('billing_nodes.item').format(node=f'*{node_name}*', country=f'`{country_code}`', provider=f'`{provider_name}`', next=f'`{next_billing}`')}"
        )
    if len(nodes) > 10:
        lines.append("")
        lines.append(t("billing_nodes.more").format(count=len(nodes) - 10))
    return "\n".join(lines)

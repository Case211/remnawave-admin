export const generateXrayLink = (item: any) => {
    if (!item) return "";

    const { protocol, settings, streamSettings, tag } = item;
    const stream = streamSettings || {};
    const security = stream.security || "none";
    const network = stream.network || "tcp";

    // Пытаемся определить адрес и порт (разница между Inbound и Outbound)
    let address = "YOUR_SERVER_IP"; 
    let port = item.port || 0;

    // Если это Аутбаунд, достаем реальный адрес
    if (settings?.vnext?.[0]) {
        address = settings.vnext[0].address;
        port = settings.vnext[0].port;
    } else if (settings?.servers?.[0]) {
        address = settings.servers[0].address;
        port = settings.servers[0].port;
    } else if (settings?.address) {
        address = settings.address;
        port = settings.port || port;
    }

    const params = new URLSearchParams();
    if (security !== "none") params.set("security", security);
    if (network !== "tcp") params.set("type", network);

    // TLS / Reality settings
    const tls = security === 'tls' ? stream.tlsSettings : (security === 'reality' ? stream.realitySettings : null);
    if (tls) {
        if (tls.serverName) params.set("sni", tls.serverName);
        if (security === 'reality') {
            if (tls.publicKey) params.set("pbk", tls.publicKey);
            if (tls.shortId) params.set("sid", tls.shortId);
            if (tls.spiderX) params.set("spx", tls.spiderX);
        }
        if (tls.fingerprint) params.set("fp", tls.fingerprint);
    }

    // Transport specifics
    if (network === 'ws') {
        const ws = stream.wsSettings || {};
        if (ws.path) params.set("path", ws.path);
        if (ws.headers?.Host) params.set("host", ws.headers.Host);
    } else if (network === 'grpc') {
        const grpc = stream.grpcSettings || {};
        if (grpc.serviceName) params.set("serviceName", grpc.serviceName);
    } else if (network === 'xhttp') {
        const x = stream.xhttpSettings || {};
        if (x.path) params.set("path", x.path);
        if (x.host) params.set("host", x.host);
        if (x.mode) params.set("mode", x.mode);
    }

    params.set("sni", params.get("sni") || params.get("host") || "");

    // Достаем ID / Пароль (разница структур)
    const getCredentials = () => {
        // Inbound style
        if (settings?.clients?.[0]) return settings.clients[0].id || settings.clients[0].password;
        if (settings?.users?.[0]) return settings.users[0].password || settings.users[0].id || settings.users[0].auth;
        // Outbound style
        if (settings?.vnext?.[0]?.users?.[0]) return settings.vnext[0].users[0].id;
        if (settings?.servers?.[0]?.users?.[0]) return settings.servers[0].users[0].password;
        if (settings?.servers?.[0]?.password) return settings.servers[0].password;
        // Shadowsocks / Hysteria style
        return settings?.password || settings?.secret || "password";
    };

    const creds = getCredentials();

    // 1. VLESS
    if (protocol === 'vless') {
        const flow = settings?.clients?.[0]?.flow || settings?.vnext?.[0]?.users?.[0]?.flow;
        if (flow) params.set("flow", flow);
        return `vless://${creds}@${address}:${port}?${params.toString()}#${encodeURIComponent(tag || 'VLESS')}`;
    }

    // 2. VMess
    if (protocol === 'vmess') {
        const vmessConfig = {
            v: "2", ps: tag || "VMess", add: address, port: port, id: creds,
            aid: "0", scy: "auto", net: network, type: "none",
            host: params.get("host") || "", path: params.get("path") || "",
            tls: security === "none" ? "" : security, sni: params.get("sni") || "",
            fp: params.get("fp") || ""
        };
        return `vmess://${btoa(JSON.stringify(vmessConfig))}`;
    }

    // 3. Trojan
    if (protocol === 'trojan') {
        return `trojan://${creds}@${address}:${port}?${params.toString()}#${encodeURIComponent(tag || 'Trojan')}`;
    }

    // 4. Shadowsocks
    if (protocol === 'shadowsocks' || protocol === 'shadowsocks-2022') {
        const method = settings?.method || (settings?.servers?.[0]?.method) || "aes-256-gcm";
        const userInfo = btoa(`${method}:${creds}`).replace(/=/g, "");
        return `ss://${userInfo}@${address}:${port}#${encodeURIComponent(tag || 'SS')}`;
    }

    // 5. Hysteria 2
    if (protocol === 'hysteria') {
        return `hysteria2://${creds}@${address}:${port}?${params.toString()}#${encodeURIComponent(tag || 'Hysteria2')}`;
    }

    return "";
};

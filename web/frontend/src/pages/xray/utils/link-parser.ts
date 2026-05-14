// @ts-nocheck
export const parseWireguardConfig = (text: string, mode: 'direct' | 'chained' = 'direct'): any => {
    const lines = text.split('\n');
    const config: any = {
        Interface: {},
        Peers: [] as any[]
    };
    
    let currentSection = "";
    for (let line of lines) {
        line = line.trim();
        if (!line || line.startsWith('#')) continue;
        
        if (line.startsWith('[Interface]')) {
            currentSection = "Interface";
            continue;
        } else if (line.startsWith('[Peer]')) {
            config.Peers.push({});
            currentSection = "Peer";
            continue;
        }

        const parts = line.split('=');
        if (parts.length < 2) continue;
        const key = parts[0].trim();
        const value = parts.slice(1).join('=').trim();

        if (currentSection === "Interface") {
            config.Interface[key] = value;
        } else if (currentSection === "Peer") {
            config.Peers[config.Peers.length - 1][key] = value;
        }
    }

    if (!config.Interface.PrivateKey) return null;

    const outbound: any = {
        tag: "wg-imported-" + Math.floor(Math.random() * 1000),
        protocol: "wireguard",
        settings: {
            secretKey: config.Interface.PrivateKey,
            address: config.Interface.Address ? config.Interface.Address.split(',').map((s: string) => s.trim()) : [],
            mtu: config.Interface.MTU ? parseInt(config.Interface.MTU) : 1280,
            peers: config.Peers.map((p: any) => ({
                publicKey: p.PublicKey,
                endpoint: p.Endpoint,
                allowedIPs: p.AllowedIPs ? p.AllowedIPs.split(',').map((s: string) => s.trim()) : ["0.0.0.0/0", "::/0"],
                keepAlive: p.PersistentKeepalive ? parseInt(p.PersistentKeepalive) : 0
            }))
        },
        streamSettings: {
            network: "udp",
            security: "none"
        }
    };

    // --- AmneziaWG / Finalmask Noise Generation ---
    const isAWG = config.Interface.Jc || config.Interface.Jmin || config.Interface.H1 || config.Interface.I1;
    
    if (isAWG) {
        const noise: any[] = [];
        const extractHex = (val: string) => {
            if (!val) return null;
            const match = val.match(/0x([0-9a-fA-F]+)/);
            return match ? match[1] : null;
        };

        const i1Hex = extractHex(config.Interface.I1);
        if (i1Hex) noise.push({ type: "hex", packet: i1Hex, delay: "5-10" });
        const i2Hex = extractHex(config.Interface.I2);
        if (i2Hex) noise.push({ type: "hex", packet: i2Hex, delay: "5-10" });

        const jc = parseInt(config.Interface.Jc) || 0;
        const jmin = parseInt(config.Interface.Jmin) || 40;
        const jmax = parseInt(config.Interface.Jmax) || 70;
        for (let i = 0; i < jc; i++) {
            noise.push({ rand: `${jmin}-${jmax}`, delay: "5-15" });
        }

        // Smart Reserved
        const isWARP = outbound.settings.peers.some((p: any) => 
            p.endpoint?.includes('cloudflare') || p.endpoint?.includes('162.159.')
        );
        if (isWARP) {
            outbound.settings.reserved = [0, 0, 0];
        } else if (config.Interface.S1 || config.Interface.S2) {
            outbound.settings.reserved = [parseInt(config.Interface.S1) || 0, parseInt(config.Interface.S2) || 0, 0];
        }

        if (mode === 'direct') {
            // МЕТОД 1: Finalmask внутри WG (Xray 1.26+)
            outbound.streamSettings.network = "raw"; 
            outbound.streamSettings.finalmask = {
                udp: [{ type: "noise", settings: { noise } }]
            };
        } else {
            // МЕТОД 2: Цепочка через dialerProxy (Legacy / Старые ядра)
            const noiseTag = outbound.tag + "-obfuscator";
            outbound.streamSettings.sockopt = { dialerProxy: noiseTag };
            
            const obfuscator = {
                tag: noiseTag,
                protocol: "freedom",
                settings: {},
                streamSettings: {
                    network: "raw",
                    finalmask: { udp: [{ type: "noise", settings: { noise } }] }
                }
            };
            return { multiple: true, outbounds: [outbound, obfuscator] };
        }
    }

    return outbound;
};

export const parseXrayLink = (link: string): any => {
  try {
    const url = new URL(link);
    let protocol = url.protocol.replace(':', '');
    
    if (protocol === 'ss') {
        protocol = 'shadowsocks';
    }

    const hashPart = link.includes('#') ? link.split('#')[1] : '';
    const tag = decodeURIComponent(hashPart);
    const query = Object.fromEntries(url.searchParams.entries());

    const baseOutbound = {
      tag: tag || `${protocol}-${Math.floor(Math.random() * 1000)}`,
      protocol: protocol,
      settings: {},
      streamSettings: {
        network: "tcp",
        security: "none",
      }
    };

    // --- VLESS ---
    if (protocol === 'vless') {
      baseOutbound.settings = {
        vnext: [{
          address: url.hostname,
          port: parseInt(url.port) || 443,
          users: [{
            id: url.username,
            email: "generated@xray",
            flow: query.flow || "",
            encryption: query.encryption || "none"
          }]
        }]
      };
    } 
    // --- TROJAN ---
    else if (protocol === 'trojan') {
      baseOutbound.settings = {
        servers: [{
          address: url.hostname,
          port: parseInt(url.port) || 443,
          password: url.username,
          email: "generated@xray",
          level: 0
        }]
      };
    }

    // --- SHADOWSOCKS ---
    else if (protocol === 'shadowsocks') { 
      let method = "";
      let password = "";
      let serverAddr = "";
      let serverPort = 443;

      // 1. Try to parse as ss://BASE64(method:password@host:port)
      const linkBody = link.split('://')[1].split('#')[0];
      
      try {
        // If it's a legacy all-in-one base64 link
        if (!linkBody.includes('@')) {
            const decoded = atob(linkBody.replace(/-/g, '+').replace(/_/g, '/'));
            if (decoded.includes('@')) {
                const [userInfo, hostPort] = decoded.split('@');
                const [m, p] = userInfo.split(':');
                method = m;
                password = p;
                if (hostPort.includes(':')) {
                    const [h, port] = hostPort.split(':');
                    serverAddr = h;
                    serverPort = parseInt(port);
                } else {
                    serverAddr = hostPort;
                }
            }
        }
      } catch (e) {
        // Not a full base64 link
      }

      // 2. Try SIP002 format: ss://BASE64(method:password)@host:port
      if (!serverAddr) {
        const lastAtIndex = linkBody.lastIndexOf('@');
        if (lastAtIndex !== -1) {
          const userInfoRaw = linkBody.substring(0, lastAtIndex);
          const hostPortPart = linkBody.substring(lastAtIndex + 1);
          let decodedUserInfo = "";
          try {
              decodedUserInfo = atob(userInfoRaw.replace(/-/g, '+').replace(/_/g, '/'));
          } catch (e) {
              decodedUserInfo = userInfoRaw;
          }

          if (decodedUserInfo.includes(':')) {
              const parts = decodedUserInfo.split(':');
              method = parts[0];
              password = parts.slice(1).join(':');
          }

          // Handle host:port?query
          const [hostPort, queryStr] = hostPortPart.split('?');
          if (hostPort.includes(':')) {
              const hp = hostPort.split(':');
              serverAddr = hp[0];
              serverPort = parseInt(hp[1]);
          } else {
              serverAddr = hostPort;
          }
        }
      }

      baseOutbound.settings = {
        servers: [{
          address: serverAddr || url.hostname,
          port: serverPort || parseInt(url.port) || 443,
          method: method || "aes-256-gcm",
          password: password,
          uot: true
        }]
      };
    } else {
        throw new Error("Unsupported protocol");
    }

    // --- (Network, TLS, Reality) ---
    const network = query.type || query.net || "tcp";
    baseOutbound.streamSettings.network = network;
    
    if (query.security) baseOutbound.streamSettings.security = query.security;

    if (query.security === 'tls' || query.security === 'reality') {
      const tlsSettings: any = {
        serverName: query.sni || url.hostname,
        fingerprint: query.fp || "chrome",
        alpn: query.alpn ? query.alpn.split(',') : undefined
      };

      if (query.security === 'reality') {
        tlsSettings.publicKey = query.pbk;
        tlsSettings.shortId = query.sid;
        tlsSettings.spiderX = query.spx || query.path || query.serviceName || "/";
        baseOutbound.streamSettings.realitySettings = tlsSettings;
      } else {
        baseOutbound.streamSettings.tlsSettings = tlsSettings;
      }
    }
    
    if (network === 'ws') {
      baseOutbound.streamSettings.wsSettings = { 
          path: query.path || "/", 
          headers: { Host: query.host || "" } 
      };
    }
    if (network === 'grpc') {
      baseOutbound.streamSettings.grpcSettings = { serviceName: query.serviceName || "" };
    }
    if (network === 'xhttp' || network === 'splithttp') {
      const settings = {
          path: query.path || "/",
          mode: query.mode || "auto",
          host: query.host || ""
      };
      if (network === 'xhttp') baseOutbound.streamSettings.xhttpSettings = settings;
      else baseOutbound.streamSettings.splithttpSettings = settings;
    }

    return baseOutbound;
  } catch (e: any) {
    console.error("Parse error:", e);
    return null;
  }
};

/**
 * Парсит JSON-подписку (массив полных конфигов или объектов с remarks)
 * Возвращает массив Outbounds
 */
export const parseJsonSubscription = (jsonText: string): any[] => {
    try {
        const data = JSON.parse(jsonText);
        const outbounds: any[] = [];

        const processConfig = (conf: any) => {
            if (!conf || typeof conf !== 'object') return;
            
            // Если в объекте есть outbounds (классический конфиг Xray)
            if (Array.isArray(conf.outbounds)) {
                // Выгребаем ВСЕ "боевые" прокси (не freedom/dns/blackhole)
                const proxies = conf.outbounds.filter((o: any) => 
                    !['freedom', 'dns', 'blackhole', 'direct', 'block'].includes(o.protocol)
                );

                proxies.forEach((proxy: any, idx: number) => {
                    // Если есть название от родителя (remarks), используем его как базу
                    if (conf.remarks) {
                        const baseTag = conf.remarks.trim();
                        // Если нода одна - просто название. Если несколько - нумеруем: Название-1, Название-2
                        proxy.tag = proxies.length > 1 ? `${baseTag}-${idx + 1}` : baseTag;
                    }
                    outbounds.push(proxy);
                });

                // Если боевых нет вообще, но что-то есть в списке, берем на всякий случай первый
                if (proxies.length === 0 && conf.outbounds.length > 0) {
                    outbounds.push(conf.outbounds[0]);
                }
            } 
            // Если это просто объект прокси
            else if (conf.protocol && conf.settings) {
                outbounds.push(conf);
            }
        };

        if (Array.isArray(data)) {
            data.forEach(processConfig);
        } else {
            processConfig(data);
        }

        return outbounds;
    } catch (e) {
        return [];
    }
};
import validator from 'validator';

const { isIP, isFQDN, isPort, isUUID } = validator;

export interface ValidationError {
    field: string;
    message: string;
}

export const isValidIP = (ip: string) => isIP(ip);

export const isValidDomain = (domain: string) => {
    if (!domain) return false;
    return isFQDN(domain, { require_tld: false, allow_underscores: true });
};

export const isValidAddress = (addr: string) => isValidIP(addr) || isValidDomain(addr);

export const isValidPort = (port: number | string) => {
    const p = typeof port === 'string' ? parseInt(port) : port;
    if (p === 0) return false;
    return isPort(p.toString());
};

export const isValidUUID = (id: string) => isUUID(id);

export const isValidHostDestination = (dest: string): boolean => {
    if (!dest) return false;
    if (isValidIP(dest)) return true;
    if (isValidDomain(dest)) return true;
    if (Array.isArray(dest)) return (dest as string[]).every((d) => isValidHostDestination(d));
    return false;
};

// --- Validators ---

export const validateInbound = (data: any): ValidationError[] => {
    const errors: ValidationError[] = [];
    if (!data.tag) errors.push({ field: 'tag', message: 'Tag is required' });
    if (!data.protocol) errors.push({ field: 'protocol', message: 'Protocol is required' });
    if (data.protocol !== 'tun' && !isValidPort(data.port)) {
        errors.push({ field: 'port', message: 'Invalid port number' });
    }
    return errors;
};

export const validateOutbound = (data: any): ValidationError[] => {
    const errors: ValidationError[] = [];
    if (!data.tag) errors.push({ field: 'tag', message: 'Tag is required' });

    const VALID_PROTOCOLS = [
        'vless', 'vmess', 'trojan', 'shadowsocks', 'socks', 'http',
        'freedom', 'blackhole', 'dns', 'wireguard', 'loopback',
        'dokodemo-door', 'tun', 'hysteria', 'hysteria2', 'shadowsocks-2022',
    ];

    if (!VALID_PROTOCOLS.includes(data.protocol)) {
        errors.push({ field: 'protocol', message: `Protocol "${data.protocol}" is not supported.` });
    }

    if (['vless', 'vmess', 'trojan', 'shadowsocks', 'shadowsocks-2022', 'socks', 'http', 'hysteria', 'hysteria2'].includes(data.protocol)) {
        const settings = data.settings || {};
        let address = '';
        let port = 0;

        if (settings.vnext?.[0]) {
            address = settings.vnext[0].address;
            port = settings.vnext[0].port;
        } else if (settings.servers?.[0]) {
            address = settings.servers[0].address;
            port = settings.servers[0].port;
        } else if (settings.address) {
            address = settings.address;
            port = settings.port;
        }

        if (!address || !isValidAddress(address)) {
            errors.push({ field: 'address', message: 'Invalid server address' });
        }
        if (!port || !isValidPort(port)) {
            errors.push({ field: 'port', message: 'Invalid server port' });
        }
    }

    const stream = data.streamSettings || {};
    const reality = stream.security === 'reality' ? (stream.realitySettings || {}) : null;

    if (reality) {
        if (!reality.publicKey) errors.push({ field: 'reality', message: 'Reality Public Key is required' });
        if (reality.shortId && reality.shortId.length % 2 !== 0) {
            errors.push({ field: 'reality', message: 'ShortID must be hex string with even length' });
        }
    }

    if (stream.network === 'xhttp') {
        const x = stream.xhttpSettings || {};
        if (x.mode === 'stream-up' && stream.security === 'none') {
            errors.push({ field: 'xhttp', message: 'WARNING: stream-up mode is intended for TLS/REALITY.' });
        }
    }

    return errors;
};

export const validateWireguard = (data: any): ValidationError[] => {
    const errors: ValidationError[] = [];
    const settings = data.settings || {};
    if (!settings.secretKey) errors.push({ field: 'secretKey', message: 'Secret Key is required' });
    const peers = settings.peers || [];
    if (peers.length === 0) errors.push({ field: 'peers', message: 'At least one peer is required' });
    peers.forEach((peer: any, i: number) => {
        if (!peer.publicKey) errors.push({ field: `peer_${i}_publicKey`, message: `Public Key for peer #${i + 1} is missing` });
        if (!peer.endpoint) errors.push({ field: `peer_${i}_endpoint`, message: `Endpoint for peer #${i + 1} is missing` });
    });
    return errors;
};

export const validateBalancer = (balancer: any): string[] => {
    if (balancer.tag === 'TORRENT') return [];
    const errors: string[] = [];
    if (!balancer.tag) errors.push('Balancer tag is missing');
    if (!balancer.selector || balancer.selector.length === 0) {
        errors.push(`Balancer [${balancer.tag}] has no selectors`);
    }
    return errors;
};

export const getCriticalRuleErrors = (rule: any): ValidationError[] => {
    const errs: ValidationError[] = [];
    const hasMatcher =
        rule.domain || rule.ip || rule.port || rule.sourcePort ||
        rule.network || rule.source || rule.user || rule.inboundTag ||
        rule.protocol || rule.attrs;

    if (!hasMatcher) errs.push({ field: 'matchers', message: 'Rule has no matchers.' });
    if (!rule.outboundTag && !rule.balancerTag) errs.push({ field: 'target', message: 'Rule must have a destination.' });
    return errs;
};

export const validateRule = (rule: any): ValidationError[] => getCriticalRuleErrors(rule);

export const lintRule = (_rule: any): ValidationError[] => [];

export const checkOutboundDuplication = (current: any, all: any[], currentIndex: number | null) => {
    const getIdentity = (o: any) => {
        const stream = o.streamSettings || {};
        let address = '';
        let port = 0;
        if (o.settings?.vnext?.[0]) { address = o.settings.vnext[0].address; port = o.settings.vnext[0].port; }
        else if (o.settings?.servers?.[0]) { address = o.settings.servers[0].address; port = o.settings.servers[0].port; }
        else if (o.settings?.address) { address = o.settings.address; port = o.settings.port; }
        return `${o.protocol}-${address}:${port}-${stream.security}-${stream.network}`;
    };
    const currentId = getIdentity(current);
    for (let i = 0; i < all.length; i++) {
        if (currentIndex !== null && i === currentIndex) continue;
        if (getIdentity(all[i]) === currentId) return all[i].tag || `Outbound #${i + 1}`;
    }
    return null;
};

export const checkInboundDuplication = (current: any, all: any[], currentIndex: number | null) => {
    for (let i = 0; i < all.length; i++) {
        if (currentIndex !== null && i === currentIndex) continue;
        if (all[i].tag === current.tag) return all[i].tag;
    }
    return null;
};

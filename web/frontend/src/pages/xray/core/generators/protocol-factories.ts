import type { Inbound, Outbound, RoutingRule, Balancer } from '../types';
import { generateUUID } from '../../utils/crypto';

export const createDefaultInbound = (protocol = 'vless'): Inbound => {
    const tag = `in-${Math.floor(Math.random() * 1000)}`;
    const uuid = generateUUID();

    const base: Inbound = {
        tag,
        port: 10808,
        protocol,
        settings: {},
        streamSettings: { network: 'tcp', security: 'none', tcpSettings: {} },
        sniffing: { enabled: true, destOverride: ['http', 'tls'] },
    };

    switch (protocol) {
        case 'vless':
            base.settings = { clients: [{ id: uuid, flow: 'xtls-rprx-vision', level: 0 }], decryption: 'none' };
            break;
        case 'vmess':
            base.settings = { clients: [{ id: uuid, level: 0 }] };
            break;
        case 'trojan':
            base.settings = { clients: [{ password: 'password', level: 0 }] };
            break;
        case 'shadowsocks':
        case 'shadowsocks-2022':
            base.settings = {
                method: protocol === 'shadowsocks-2022' ? '2022-blake3-aes-128-gcm' : 'aes-256-gcm',
                password: 'password',
                network: 'tcp,udp',
            };
            break;
        case 'hysteria':
            base.settings = { version: 2, up_mbps: 100, down_mbps: 100, users: [{ password: 'password' }] };
            base.streamSettings = { network: 'udp', security: 'tls', tlsSettings: { certificates: [] } };
            break;
        case 'socks':
            base.settings = { auth: 'noauth', udp: true };
            break;
        case 'tun':
            delete base.port;
            delete base.listen;
            delete base.streamSettings;
            base.settings = { mtu: 1500, stack: 'system' };
            break;
    }

    return base;
};

export const createDefaultOutbound = (protocol = 'vless'): Outbound => {
    const tag = `out-${Math.floor(Math.random() * 1000)}`;

    const base: Outbound = {
        tag,
        protocol,
        settings: {},
        streamSettings: { network: 'tcp', security: 'none' },
    };

    switch (protocol) {
        case 'freedom':
            base.settings = { domainStrategy: 'AsIs' };
            break;
        case 'blackhole':
            base.settings = { response: { type: 'none' } };
            break;
        case 'dns':
            base.settings = { network: 'tcp', address: '1.1.1.1', port: 53 };
            break;
        case 'wireguard':
            base.settings = {
                secretKey: '',
                address: ['10.0.0.2/32'],
                peers: [{ publicKey: '', endpoint: '' }],
                mtu: 1420,
            };
            base.streamSettings = { network: 'udp' };
            break;
        default:
            if (['vless', 'vmess', 'trojan', 'shadowsocks', 'shadowsocks-2022', 'socks', 'http', 'hysteria', 'hysteria2'].includes(protocol)) {
                base.settings = {
                    vnext: protocol === 'vless' || protocol === 'vmess'
                        ? [{ address: 'example.com', port: 443, users: [{ id: generateUUID(), security: 'auto' }] }]
                        : undefined,
                    servers: ['trojan', 'socks', 'http', 'shadowsocks', 'shadowsocks-2022'].includes(protocol)
                        ? [{
                            address: 'example.com',
                            port: 443,
                            method: protocol.startsWith('shadowsocks')
                                ? protocol === 'shadowsocks-2022' ? '2022-blake3-aes-128-gcm' : 'aes-256-gcm'
                                : undefined,
                            password: 'password',
                            email: 'generated@xray',
                        }]
                        : undefined,
                };
            }
            break;
    }

    return base;
};

export const createDefaultRoutingRule = (): RoutingRule => ({
    type: 'field',
    outboundTag: 'proxy',
    domain: [],
    ip: [],
    protocol: [],
});

export const createDefaultBalancer = (): Balancer => ({
    tag: `balancer-${Math.floor(Math.random() * 1000)}`,
    selector: [],
    strategy: { type: 'random' },
});

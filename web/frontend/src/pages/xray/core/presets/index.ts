import { generateUUID, generateRealityKeyPair } from '../generators/crypto';
import type { XrayConfig } from '../types/xray.types';

export interface Preset {
    name: string;
    description: string;
    icon: string;
    config: Partial<XrayConfig>;
}

const AWG_WARP_BASE = {
    tag: 'warp-amnezia',
    protocol: 'wireguard',
    settings: {
        secretKey: '', // Users must generate this later
        address: ['10.0.0.1/32', 'fd00::1/128'],
        mtu: 1280,
        reserved: [0, 0, 0], // Replaced by S1/S2 later if needed
        peers: [{
            endpoint: 'engage.cloudflareclient.com:2408',
            publicKey: '', // Users must generate this later
            keepAlive: 15,
            allowedIPs: ['0.0.0.0/0', '::/0']
        }]
    },
    streamSettings: {
        network: 'raw',
        finalmask: {
            udp: [] as any[]
        }
    }
};

export const getPresets = (): Preset[] => {
    const keys = generateRealityKeyPair();

    return [
        {
            name: 'WARP Profile A',
            description: 'Cloudflare WARP connectivity with standard AmneziaWG optimization.',
            icon: 'Cloud',
            config: {
                log: { loglevel: 'warning' },
                dns: { servers: ['1.1.1.1', '8.8.8.8'], queryStrategy: 'UseIP' },
                inbounds: [{ tag: 'socks-in', port: 10808, listen: '127.0.0.1', protocol: 'socks', settings: { auth: 'noauth', udp: true } }],
                outbounds: [
                    {
                        ...AWG_WARP_BASE,
                        tag: 'warp-a',
                        streamSettings: {
                            network: 'raw',
                            finalmask: {
                                udp: [{
                                    type: 'noise',
                                    settings: {
                                        noise: [
                                            { type: 'hex', packet: 'ce000000010897a297ecc34cd6dd000044d0ec2e2e1ea2991f467ace4222129b5a098823784694b4897b9986ae0b7280135fa85e196d9ad980b150122129ce2a9379531b0fd3e871ca5fdb883c369832f730e272d7b8b74f393f9f0fa43f11e510ecb2219a52984410c204cf875585340c62238e14ad04dff382f2c200e0ee22fe743b9c6b8b043121c5710ec289f471c91ee414fca8b8be8419ae8ce7ffc53837f6ade262891895f3f4cecd31bc93ac5599e18e4f01b472362b8056c3172b513051f8322d1062997ef4a383b01706598d08d48c221d30e74c7ce000cdad36b706b1bf9b0607c32ec4b3203a4ee21ab64df336212b9758280803fcab14933b0e7ee1e04a7becce3e2633f4852585c567894a5f9efe9706a151b615856647e8b7dba69ab357b3982f554549bef9256111b2d67afde0b496f16962d4957ff654232aa9e845b61463908309cfd9de0a6abf5f425f577d7e5f6440652aa8da5f73588e82e9470f3b21b27b28c649506ae1a7f5f15b876f56abc4615f49911549b9bb39dd804fde182bd2dcec0c33bad9b138ca07d4a4a1650a2c2686acea05727e2a78962a840ae428f55627516e73c83dd8893b02358e81b524b4d99fda6df52b3a8d7a5291326e7ac9d773c5b43b8444554ef5aea104a738ed650aa979674bbed38da58ac29d87c29d387d80b526065baeb073ce65f075ccb56e47533aef357dceaa8293a523c5f6f790be90e4731123d3c6152a70576e90b4ab5bc5ead01576c68ab633ff7d36dcde2a0b2c68897e1acfc4d6483aaaeb635dd63c96b2b6a7a2bfe042f6aed82e5363aa850aace12ee3b1a93f30d8ab9537df483152a5527faca21efc9981b304f11fc95336f5b9637b174c5a0659e2b22e159a9fed4b8e93047371175b1d6d9cc8ab745f3b2281537d1c75fb9451871864efa5d184c38c185fd203de206751b92620f7c369e031d2041e152040920ac2c5ab5340bfc9d0561176abf10a147287ea90758575ac6a9f5ac9f390d0d5b23ee12af583383d994e22c0cf42383834bcd3ada1b3825a0664d8f3fb678261d57601ddf94a8a68a7c273a18c08aa99c7ad8c6c42eab67718843597ec9930457359dfdfbce024afc2dcf9348579a57d8d3490b2fa99f278f1c37d87dad9b221acd575192ffae1784f8e60ec7cee4068b6b988f0433d96d6a1b1865f4e155e9fe020279f434f3bf1bd117b717b92f6cd1cc9bea7d45978bcc3f24bda631a36910110a6ec06da35f8966c9279d130347594f13e9e07514fa370754d1424c0a1545c5070ef9fb2acd14233e8a50bfc5978b5bdf8bc1714731f798d21e2004117c61f2989dd44f0cf027b27d4019e81ed4b5c31db347c4a3a4d85048d7093cf16753d7b0d15e078f5c7a5205dc2f87e', delay: '5-10' },
                                            { rand: '40-70', delay: '5-15' },
                                            { rand: '40-70', delay: '5-15' },
                                            { rand: '40-70', delay: '5-15' },
                                            { rand: '40-70', delay: '5-15' }
                                        ]
                                    }
                                }]
                            }
                        }
                    },
                    { tag: 'direct', protocol: 'freedom', settings: {} },
                ],
                routing: { domainStrategy: 'AsIs', rules: [{ type: 'field', outboundTag: 'warp-a', network: 'tcp,udp' }] },
            }
        },
        {
            name: 'WARP Profile B',
            description: 'Cloudflare WARP connectivity with alternative AmneziaWG optimization.',
            icon: 'CloudCheck',
            config: {
                log: { loglevel: 'warning' },
                dns: { servers: ['1.1.1.1', '8.8.8.8'], queryStrategy: 'UseIP' },
                inbounds: [{ tag: 'socks-in', port: 10808, listen: '127.0.0.1', protocol: 'socks', settings: { auth: 'noauth', udp: true } }],
                outbounds: [
                    {
                        ...AWG_WARP_BASE,
                        tag: 'warp-b',
                        streamSettings: {
                            network: 'raw',
                            finalmask: {
                                udp: [{
                                    type: 'noise',
                                    settings: {
                                        noise: [
                                            { type: 'hex', packet: 'c7000000010809a1ed4edbbe7615000044d017a61a0d774f04290f119e701ef0035df2b0ed571b0b575e6a07246b856eb6ec036fef07f1e07b861251ad737abeb67e64be714c1dcd865312b1b6c35c089c997aeb5c18f808696fe97289513945d84ca846467603e94e44224877f2c1d3261e4ac18740be4bd064369c94fc08978d99b54bf615250998639010c1284248e1d73004b81fcb20b559d8a17eced7eab3964b5b88ca7a3b8579fc8c1c934189e77143b4ac434138114b1048651b56545b87acbef0952763538f3ddeb37cfc6d58b4881c3b719d7ff78f6ee1324a2914a32381c05a64c700466d280be007253bb030d179c4f1b3dc221e1974e2ee6d6e2b9e8d709159b5ef22e1783dbba845c20ca1c83b066c73835920ad70b806df0aee0351e3fc9ab1e42e8b2a30fe235ff0612eee19744949cecee0463b76514ad90c1f7ceaa557c18586ab561d49482e73c85d0143785da14a441bf82f78783b61cccd44aecb1947516e79b5ca5a6b3a8aed6040fae0eeabdc55a88dc19ade832d99fca90c7a629cacc07192d7e47e3c6a271b95b0ea3392562a06a1cab79f40ea92916ebee197b7b5f14b251824e1ed20ff2ca80b1f03a43e45157589bc61b978e97851025b3b7ccc17d291e1cb60fe48a5c26829dce11dd23c2e73265a9ebf8617c985e4fee4681e863f990061f4dea465a7d2524bd0edcf4b48d4b8f25fc359b15babd2637284a4774077dca60091f1a781cfee1bef9713dd5943a579d7470bc5970542fbb27fdf77880a8d8751b1f642c7a3f019a05ab94bf63d3525ef34e9290b5c8d477f2714e6d6e3e4d35c1983f5e16fda57fcdf071b513f8f088dbe8d5a97577d17a5383a496c3f313adfdd47c962bbaebd6aa13b46439eb742622c29ca067db0ec1853064c3cbbffe0a215a19fce47d49703ed58ebbd89721172d256d1cf30188106fb2f863186511401fad54d087aa2fb3d1b85768db386bd7102e8060ac157bac011acdcdae2799b9aee1467c3424013455bd028fcaacdc3c77d28ea199967d617ea7d0d0815f3cc407934a76d1293dccba210d1709a13e5dd67c9ba47cd113f5bdd740358eff13164159fd09bc2f7ec6cfa64d9df7e2e2f88706b0ff3a92ccf6f078456cfe0bdd89292cfe2680badc1eac9f7d36efe8eb6912c7b164508d13e6c0911c15f73c233cbe4fc70ff2ade1e1be4bbb738e0939159e2078a9438f05b756a003371f4861481c38f1cdd2d7b06deb62869e9fe79a8abaa920646fa2e8fa28f0d80c136376c7b56046bae4c05c0cdf64efb8c47bbfc5a1a4c0b045061ef0d71618e0d206a1d7f245fd5c03191b152673ba8dff8e1b8de7c50234a93cba91e3888adb228cc02beded4b1c0946797d3ef02dec2edb6ad0ac21f89f4', delay: '5-10' },
                                            { rand: '40-70', delay: '5-15' },
                                            { rand: '40-70', delay: '5-15' },
                                            { rand: '40-70', delay: '5-15' },
                                            { rand: '40-70', delay: '5-15' }
                                        ]
                                    }
                                }]
                            }
                        }
                    },
                    { tag: 'direct', protocol: 'freedom', settings: {} },
                ],
                routing: { domainStrategy: 'AsIs', rules: [{ type: 'field', outboundTag: 'warp-b', network: 'tcp,udp' }] },
            }
        },
        {
            name: 'WARP Profile C',
            description: 'Cloudflare WARP connectivity with aggressive AmneziaWG optimization.',
            icon: 'CloudFog',
            config: {
                log: { loglevel: 'warning' },
                dns: { servers: ['1.1.1.1', '8.8.8.8'], queryStrategy: 'UseIP' },
                inbounds: [{ tag: 'socks-in', port: 10808, listen: '127.0.0.1', protocol: 'socks', settings: { auth: 'noauth', udp: true } }],
                outbounds: [
                    {
                        ...AWG_WARP_BASE,
                        tag: 'warp-c',
                        streamSettings: {
                            network: 'raw',
                            finalmask: {
                                udp: [{
                                    type: 'noise',
                                    settings: {
                                        noise: [
                                            { type: 'hex', packet: '494e56495445207369703a626f624062696c6f78692e636f6d205349502f322e300d0a5669613a205349502f322e302f55445020706333332e61746c616e74612e636f6d3b6272616e63683d7a39684734624b3737366173646864730d0a4d61782d466f7277617264733a2037300d0a546f3a20426f62203c7369703a626f624062696c6f78692e636f6d3e0d0a46726f6d3a20416c696365203c7369703a616c6963654061746c616e74612e636f6d3b7461673d313932383330313737340d0a43616c6c2d49443a20613834623463373665363637313040706333332e61746c616e74612e636f6d0d0a435365713a2033313431353920494e564954450d0a436f6e74656e742d547970653a206170706c69636174696f6e2f7364700d0a436f6e74656e742d4c656e6774683a20300d0a0d0a', delay: '5-10' },
                                            { type: 'hex', packet: '5349502f322e302031303020547279696e670d0a5669613a205349502f322e302f55445020706333332e61746c616e74612e636f6d3b6272616e63683d7a39684734624b3737366173646864730d0a4d61782d466f7277617264733a2037300d0a546f3a20426f62203c7369703a626f624062696c6f78692e636f6d3e0d0a46726f6d3a20416c696365203c7369703a616c6963654061746c616e74612e636f6d3e3b7461673d313932383330313737340d0a43616c6c2d49443a20613834623463373665363637313040706333332e61746c616e74612e636f6d0d0a435365713a2033313431353920494e564954450d0a436f6e74656e742d547970653a206170706c69636174696f6e2f7364700d0a436f6e74656e742d4c656e6774683a20300d0a0d0a', delay: '5-10' },
                                            { rand: '40-70', delay: '5-15' },
                                            { rand: '40-70', delay: '5-15' },
                                            { rand: '40-70', delay: '5-15' },
                                            { rand: '40-70', delay: '5-15' }
                                        ]
                                    }
                                }]
                            }
                        }
                    },
                    { tag: 'direct', protocol: 'freedom', settings: {} },
                ],
                routing: { domainStrategy: 'AsIs', rules: [{ type: 'field', outboundTag: 'warp-c', network: 'tcp,udp' }] },
            }
        },
        {
            name: 'Minimal (Skeleton)',
            description: 'Basic structure with Direct & Block outbounds. Best for starting from scratch.',
            icon: 'Square',
            config: {
                log: { loglevel: 'warning' },
                inbounds: [],
                outbounds: [
                    { tag: 'direct', protocol: 'freedom', settings: {} },
                    { tag: 'block', protocol: 'blackhole', settings: {} },
                ],
                routing: {
                    domainStrategy: 'AsIs',
                    rules: [],
                    balancers: [],
                },
            },
        },
        {
            name: 'Standard Client',
            description: 'Socks5/HTTP inbounds + VLESS Proxy. Includes basic routing rules.',
            icon: 'Laptop',
            config: {
                log: { loglevel: 'warning' },
                dns: {
                    servers: ['1.1.1.1', '8.8.8.8', 'localhost'],
                    queryStrategy: 'UseIP',
                },
                inbounds: [
                    {
                        tag: 'socks-in',
                        port: 10808,
                        listen: '127.0.0.1',
                        protocol: 'socks',
                        sniffing: { enabled: true, destOverride: ['http', 'tls'] },
                        settings: { auth: 'noauth', udp: true },
                    },
                    {
                        tag: 'http-in',
                        port: 10809,
                        listen: '127.0.0.1',
                        protocol: 'http',
                        sniffing: { enabled: true, destOverride: ['http', 'tls'] },
                        settings: { allowTransparent: false },
                    },
                ],
                outbounds: [
                    {
                        tag: 'proxy',
                        protocol: 'vless',
                        settings: {
                            vnext: [{
                                address: 'example.com',
                                port: 443,
                                users: [{ id: generateUUID(), encryption: 'none', flow: 'xtls-rprx-vision' }],
                            }],
                        },
                        streamSettings: {
                            network: 'tcp',
                            security: 'tls',
                            tlsSettings: { serverName: 'example.com', fingerprint: 'chrome' },
                        },
                    },
                    { tag: 'direct', protocol: 'freedom', settings: {} },
                    { tag: 'block', protocol: 'blackhole', settings: {} },
                ],
                routing: {
                    domainStrategy: 'IPIfNonMatch',
                    rules: [
                        { type: 'field', outboundTag: 'block', domain: ['geosite:category-ads-all'] },
                        { type: 'field', outboundTag: 'direct', domain: ['geosite:cn'] },
                        { type: 'field', outboundTag: 'direct', ip: ['geoip:cn', 'geoip:private'] },
                        { type: 'field', outboundTag: 'proxy', network: 'tcp,udp' },
                    ],
                },
            },
        },
        {
            name: 'Reality Server',
            description: 'VLESS-Reality Inbound configuration for server side.',
            icon: 'Server',
            config: {
                log: {
                    loglevel: 'warning',
                    access: '/var/log/xray/access.log',
                    error: '/var/log/xray/error.log',
                },
                inbounds: [
                    {
                        tag: 'vless-reality',
                        port: 443,
                        protocol: 'vless',
                        settings: {
                            clients: [{ id: generateUUID(), flow: 'xtls-rprx-vision', email: 'user1' }],
                            decryption: 'none',
                            fallbacks: [],
                        },
                        streamSettings: {
                            network: 'tcp',
                            security: 'reality',
                            realitySettings: {
                                show: false,
                                dest: 'www.google.com:443',
                                serverNames: ['www.google.com', 'google.com'],
                                privateKey: keys.privateKey,
                                shortIds: ['', Math.random().toString(16).substring(2, 10)],
                            },
                        },
                        sniffing: { enabled: true, destOverride: ['http', 'tls', 'quic'] },
                    },
                ],
                outbounds: [
                    { tag: 'direct', protocol: 'freedom', settings: {} },
                    { tag: 'block', protocol: 'blackhole', settings: {} },
                ],
            },
        },
    ];
};

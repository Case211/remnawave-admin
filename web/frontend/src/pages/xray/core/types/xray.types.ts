// ============================================================
// Xray-core TypeScript types
// Fully decoupled from React / Zustand — pure domain types
// ============================================================

export interface LogConfig {
    access?: string;
    error?: string;
    loglevel?: 'debug' | 'info' | 'warning' | 'error' | 'none';
    dnsLog?: boolean;
    maskAddress?: string;
}

export interface ApiConfig {
    tag?: string;
    listen?: string;
    services?: string[];
}

export interface DnsServerObject {
    address?: string;
    port?: number;
    domains?: string[];
    expectIPs?: string[];
    skipFallback?: boolean;
    clientIp?: string;
    queryStrategy?: 'UseIP' | 'UseIPv4' | 'UseIPv6';
    disableCache?: boolean;
    tag?: string;
}

export interface DnsConfig {
    servers?: (string | DnsServerObject)[];
    hosts?: Record<string, string | string[]>;
    clientIp?: string;
    queryStrategy?: 'UseIP' | 'UseIPv4' | 'UseIPv6';
    disableCache?: boolean;
    disableFallback?: boolean;
    disableFallbackIfMatch?: boolean;
    tag?: string;
}

export interface RoutingRule {
    type?: string;
    ruleTag?: string;
    domain?: string[];
    ip?: string[];
    port?: string;
    sourcePort?: string;
    network?: string;
    source?: string[];
    user?: string[];
    inboundTag?: string[];
    protocol?: string[];
    attrs?: Record<string, string>;
    outboundTag?: string;
    balancerTag?: string;
}

export interface Balancer {
    tag: string;
    selector: string[];
    strategy?: {
        type: 'random' | 'roundRobin' | 'leastPing' | 'leastLoad';
    };
    fallbackTag?: string;
}

export interface RoutingConfig {
    domainStrategy?: 'AsIs' | 'IPIfNonMatch' | 'IPOnDemand';
    rules?: RoutingRule[];
    balancers?: Balancer[];
}

export interface Inbound {
    tag?: string;
    port?: number | string;
    listen?: string;
    protocol: string;
    settings?: Record<string, unknown>;
    streamSettings?: Record<string, unknown>;
    sniffing?: {
        enabled?: boolean;
        destOverride?: string[];
        metadataOnly?: boolean;
        routeOnly?: boolean;
    };
    allocate?: {
        strategy?: string;
        refresh?: number;
        concurrency?: number;
    };
}

export interface Outbound {
    tag?: string;
    sendThrough?: string;
    protocol: string;
    settings?: Record<string, unknown>;
    streamSettings?: Record<string, unknown>;
    proxySettings?: {
        tag?: string;
        transportLayer?: boolean;
    };
    mux?: {
        enabled?: boolean;
        concurrency?: number;
        xudpConcurrency?: number;
        xudpProxyUDP443?: string;
    };
}

export interface PolicyLevel {
    handshake?: number;
    connIdle?: number;
    uplinkOnly?: number;
    downlinkOnly?: number;
    statsUserUplink?: boolean;
    statsUserDownlink?: boolean;
    bufferSize?: number;
}

export interface PolicyConfig {
    levels?: Record<string, PolicyLevel>;
    system?: {
        statsInboundUplink?: boolean;
        statsInboundDownlink?: boolean;
        statsOutboundUplink?: boolean;
        statsOutboundDownlink?: boolean;
    };
}

export type StatsConfig = Record<string, never>;

export interface ReverseConfig {
    bridges?: { tag: string; domain: string }[];
    portals?: { tag: string; domain: string }[];
}

export interface FakednsPool {
    ipPool: string;
    poolSize: number;
}

export interface ObservatoryConfig {
    subjectSelector?: string[];
    probeUrl?: string;
    probeInterval?: string;
}

export interface BurstObservatoryConfig {
    subjectSelector?: string[];
    pingConfig?: {
        destination?: string;
        connectivity?: string;
        interval?: string;
        sampling?: number;
        timeout?: string;
        httpMethod?: string;
    };
}

export interface XrayConfig {
    log?: LogConfig;
    api?: ApiConfig;
    dns?: DnsConfig;
    routing?: RoutingConfig;
    policy?: PolicyConfig;
    inbounds?: Inbound[];
    outbounds?: Outbound[];
    transport?: Record<string, unknown>;
    stats?: StatsConfig;
    reverse?: ReverseConfig;
    fakedns?: FakednsPool[];
    observatory?: ObservatoryConfig;
    burstObservatory?: BurstObservatoryConfig;
    [key: string]: unknown;
}

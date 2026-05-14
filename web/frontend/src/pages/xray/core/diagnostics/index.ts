// @ts-nocheck
import type { XrayConfig } from '../types/xray.types';
import type { ValidationError } from '../validators';

export type DiagnosticSeverity = 'critical' | 'warning' | 'info';

export interface Diagnostic {
    section: string;
    itemIndex?: number;
    field?: string;
    message: string;
    severity: DiagnosticSeverity;
    suggestion?: string;
}

export const runFullDiagnostics = (config: XrayConfig | null): Diagnostic[] => {
    const diagnostics: Diagnostic[] = [];

    if (!config) return diagnostics;

    // Defensive null-filter: Panel может вернуть массив с null элементами
    // (например, если запись была удалена в БД, но осталась ссылка в JSON).
    // Без фильтрации `o.tag` на null крашит весь Xray-редактор при mount —
    // юзер ловит «Cannot read properties of null (reading 'tag')».
    const inbounds = (config.inbounds || []).filter(Boolean);
    const outbounds = (config.outbounds || []).filter(Boolean);
    const routing = config.routing || {};
    const rules = (routing.rules || []).filter(Boolean);
    const balancers = (routing.balancers || []).filter(Boolean);

    const allOutboundTags = new Set(outbounds.map((o: any) => o.tag).filter(Boolean));
    const allBalancerTags = new Set(balancers.map((b: any) => b.tag).filter(Boolean));

    // Tags that may exist in external systems (e.g. Remnawave)
    const KNOWN_EXTERNAL_TAGS = new Set(['TORRENT', 'DIRECT', 'REJECT', 'BLOCK', 'DNS']);
    const allTargetTags = new Set([...allOutboundTags, ...allBalancerTags, ...KNOWN_EXTERNAL_TAGS]);

    const checkOutbound = (o: any, i: number) => {
        const stream = o.streamSettings || {};
        const net = stream.network || 'tcp';
        const sec = stream.security || 'none';

        if (net === 'grpc') {
            const grpc = stream.grpcSettings || {};
            if (!grpc.serviceName) {
                diagnostics.push({
                    section: 'outbounds', itemIndex: i, field: 'grpcSettings',
                    severity: 'critical', message: 'gRPC requires "serviceName" to be set.',
                    suggestion: 'Add a service name (e.g., "GunService").',
                });
            }
        }

        if (sec === 'reality') {
            const r = stream.realitySettings || {};
            if (!r.publicKey) {
                diagnostics.push({
                    section: 'outbounds', itemIndex: i, field: 'realitySettings',
                    severity: 'critical', message: 'REALITY requires "publicKey" for outbounds.',
                });
            }
            if (!r.serverName) {
                diagnostics.push({
                    section: 'outbounds', itemIndex: i, field: 'realitySettings',
                    severity: 'warning', message: 'REALITY usually requires "serverName" (SNI) to match the destination.',
                });
            }
        }

        const flow = (o.settings?.vnext?.[0]?.users?.[0]?.flow) || (o.settings?.users?.[0]?.flow);
        const mux = o.mux || {};

        if (flow === 'xtls-rprx-vision' && mux.enabled) {
            diagnostics.push({
                section: 'outbounds', itemIndex: i, field: 'mux',
                severity: 'critical', message: 'XTLS-Vision is incompatible with Mux/XUDP.',
                suggestion: 'Disable Mux for this outbound to use Vision flow.',
            });
        }

        if (sec === 'reality' && mux.enabled) {
            diagnostics.push({
                section: 'outbounds', itemIndex: i, field: 'mux',
                severity: 'warning', message: 'Using Mux with REALITY is not recommended (affects fingerprint).',
                suggestion: 'Consider disabling Mux for Reality outbounds.',
            });
        }

        if (net === 'xhttp') {
            const x = stream.xhttpSettings || {};
            if (x.mode === 'stream-up' && sec === 'none') {
                diagnostics.push({
                    section: 'outbounds', itemIndex: i,
                    severity: 'critical', message: 'XHTTP "stream-up" mode MANDATORY requires TLS or REALITY.',
                    suggestion: 'Enable Security or change mode to "packet-up".',
                });
            }
        }
    };

    const checkInbound = (inb: any, i: number) => {
        const stream = inb.streamSettings || {};
        const sec = stream.security || 'none';

        if (sec === 'reality') {
            const r = stream.realitySettings || {};
            if (!r.dest || !r.privateKey) {
                diagnostics.push({
                    section: 'inbounds', itemIndex: i, field: 'realitySettings',
                    severity: 'critical', message: 'REALITY Inbound requires "dest" and "privateKey".',
                    suggestion: 'Configure a fallback destination and generate a private key.',
                });
            }
        }

        if (sec === 'tls') {
            const tls = stream.tlsSettings || {};
            if (!tls.certificates || tls.certificates.length === 0) {
                diagnostics.push({
                    section: 'inbounds', itemIndex: i, field: 'tlsSettings',
                    severity: 'critical', message: 'TLS Inbound requires at least one certificate.',
                });
            }
        }
    };

    inbounds.forEach(checkInbound);
    outbounds.forEach(checkOutbound);

    rules.forEach((rule: any, i: number) => {
        if (rule.outboundTag && !allTargetTags.has(rule.outboundTag)) {
            diagnostics.push({
                section: 'routing', itemIndex: i, field: 'outboundTag',
                severity: 'critical', message: `Rule targets unknown outbound: "${rule.outboundTag}"`,
            });
        }
        if (rule.balancerTag && !allTargetTags.has(rule.balancerTag)) {
            diagnostics.push({
                section: 'routing', itemIndex: i, field: 'balancerTag',
                severity: 'critical', message: `Rule targets unknown balancer: "${rule.balancerTag}"`,
            });
        }
    });

    return diagnostics;
};

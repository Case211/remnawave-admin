// @ts-nocheck
import React from 'react';
import { Card } from '../../ui/Card';
import { FormField } from '../../ui/FormField';
import { Switch } from '../../ui/Switch';
import { Select } from '../../ui/Select';

export const OutboundServer = ({ outbound, onChange, errors = {} }: any) => {
    const server = outbound.settings?.vnext?.[0] || outbound.settings?.servers?.[0] || {};
    
    // Logic to handle different protocol nested structures
    const updateServerField = (field: string, value: any) => {
        if (outbound.protocol === 'vmess' || outbound.protocol === 'vless') {
            const vnext = [...(outbound.settings?.vnext || [{ users: [{ id: '' }] }])];
            vnext[0] = { ...vnext[0], [field]: field === 'port' ? parseInt(value) || 0 : value };
            onChange('settings', { ...outbound.settings, vnext });
        } else {
            const servers = [...(outbound.settings?.servers || [{}])];
            servers[0] = { ...servers[0], [field]: field === 'port' ? parseInt(value) || 0 : value };
            onChange('settings', { ...outbound.settings, servers });
        }
    };

    const updateUserId = (id: string) => {
        if (outbound.protocol === 'vmess' || outbound.protocol === 'vless') {
            const vnext = [...(outbound.settings?.vnext || [{ users: [{ id: '' }] }])];
            vnext[0].users[0].id = id;
            onChange('settings', { ...outbound.settings, vnext });
        } else if (outbound.protocol === 'trojan' || outbound.protocol === 'shadowsocks' || outbound.protocol === 'shadowsocks-2022') {
            const servers = [...(outbound.settings?.servers || [{}])];
            servers[0] = { ...servers[0], password: id };
            onChange('settings', { ...outbound.settings, servers });
        }
    };

    const updateMethod = (method: string) => {
        if (outbound.protocol === 'shadowsocks' || outbound.protocol === 'shadowsocks-2022') {
            const servers = [...(outbound.settings?.servers || [{}])];
            servers[0] = { ...servers[0], method };
            onChange('settings', { ...outbound.settings, servers });
        }
    };

    const getUserId = () => {
        if (outbound.protocol === 'vmess' || outbound.protocol === 'vless') return server.users?.[0]?.id || "";
        if (outbound.protocol === 'trojan' || outbound.protocol === 'shadowsocks' || outbound.protocol === 'shadowsocks-2022') return server.password || "";
        return "";
    };

    const isShadowsocks = outbound.protocol === 'shadowsocks' || outbound.protocol === 'shadowsocks-2022';
    const isBlackhole = outbound.protocol === 'blackhole';
    const isDns = outbound.protocol === 'dns';
    const isFreedom = outbound.protocol === 'freedom';

    if (isBlackhole) {
        return (
            <Card title="Blackhole" icon="NoEntry" className="mt-4">
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg mb-4">
                    <p className="text-[11px] text-slate-400 leading-relaxed italic">
                        The <b>Blackhole</b> outbound drops all outgoing traffic. It is primarily used to block specific domains or IPs (e.g., for ad-blocking or preventing telemetry) by routing them here.
                    </p>
                </div>
                <Select 
                    label="Тип ответа"
                    hint="Determines what the client receives when traffic is blocked."
                    value={outbound.settings?.response?.type || "none"}
                    onChange={val => onChange('settings', { ...outbound.settings, response: { type: val } })}
                    options={[
                        { value: "none", label: "Нет", description: "Silent Drop" },
                        { value: "http", label: "HTTP", description: "Return 403 Forbidden" },
                    ]}
                />
            </Card>
        );
    }

    if (isDns) {
        return (
            <Card title="DNS-outbound" icon="Globe" className="mt-4">
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg mb-4">
                    <p className="text-[11px] text-slate-400 leading-relaxed italic">
                        The <b>DNS</b> outbound is used to intercept and forward DNS queries. When a query is routed here, Xray will handle it using internal DNS logic.
                    </p>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="md:col-span-3">
                        <FormField label="Адрес DNS-сервера">
                            <input className="input-base" 
                                value={outbound.settings?.address || ""} 
                                onChange={e => onChange('settings', { ...outbound.settings, address: e.target.value })} 
                            />
                        </FormField>
                    </div>
                    <FormField label="Порт">
                        <input type="number" className="input-base" 
                            value={outbound.settings?.port || 53} 
                            onChange={e => onChange('settings', { ...outbound.settings, port: parseInt(e.target.value) || 53 })} 
                        />
                    </FormField>
                </div>
            </Card>
        );
    }

    if (isFreedom) {
        return (
            <Card title="Freedom (прямое подключение)" icon="ArrowSquareOut" className="mt-4">
                <div className="p-3 bg-slate-950 border border-slate-800 rounded-lg">
                    <p className="text-[11px] text-slate-400 leading-relaxed italic">
                        The <b>Freedom</b> outbound sends traffic directly to its destination without any proxy. This is typically used for local traffic or bypassing the VPN.
                    </p>
                </div>
                <div className="mt-4">
                        <Select 
                            label="Стратегия доменов"
                            hint="How to resolve domain names when connecting."
                            value={outbound.settings?.domainStrategy || "AsIs"}
                            onChange={val => onChange('settings', { ...outbound.settings, domainStrategy: val })}
                            options={[
                                { value: "AsIs", label: "As Is", description: "Use system DNS" },
                                { value: "UseIP", label: "Use IP", description: "Resolve via Xray DNS" },
                                { value: "UseIPv4", label: "Use IPv4" },
                                { value: "UseIPv6", label: "Use IPv6" },
                            ]}
                        />
                </div>
            </Card>
        );
    }

    return (
        <Card title="Параметры сервера" icon="Cloud" className="mt-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="md:col-span-3">
                    <FormField label="Адрес (IP или домен)" error={errors.address}>
                        <input 
                            className="input-base" 
                            placeholder="example.com"
                            value={server.address || ""} 
                            onChange={e => updateServerField('address', e.target.value)} 
                        />
                    </FormField>
                </div>
                <FormField label="Порт" error={errors.port}>
                    <input 
                        type="number"
                        className="input-base" 
                        placeholder="443"
                        value={server.port || ""} 
                        onChange={e => updateServerField('port', e.target.value)} 
                    />
                </FormField>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-2">
                <FormField label={isShadowsocks || outbound.protocol === 'trojan' ? "Пароль" : "UUID / ID"}>
                    <input 
                        className="input-base font-mono text-xs" 
                        value={getUserId()} 
                        onChange={e => updateUserId(e.target.value)} 
                    />
                </FormField>

                {isShadowsocks && (
                    <Select 
                        label="Метод"
                        value={server.method || (outbound.protocol === 'shadowsocks-2022' ? "2022-blake3-aes-128-gcm" : "aes-256-gcm")}
                        onChange={val => updateMethod(val)}
                        options={outbound.protocol === 'shadowsocks' ? [
                            { value: "aes-256-gcm", label: "aes-256-gcm" },
                            { value: "aes-128-gcm", label: "aes-128-gcm" },
                            { value: "chacha20-ietf-poly1305", label: "chacha20-ietf-poly1305" },
                            { value: "xchacha20-ietf-poly1305", label: "xchacha20-ietf-poly1305" },
                        ] : [
                            { value: "2022-blake3-aes-128-gcm", label: "2022-blake3-aes-128-gcm" },
                            { value: "2022-blake3-aes-256-gcm", label: "2022-blake3-aes-256-gcm" },
                            { value: "2022-blake3-chacha20-poly1305", label: "2022-blake3-chacha20-poly1305" },
                        ]}
                    />
                )}

                {isShadowsocks && (
                    <div className="flex items-center gap-2 pt-6">
                        <Switch 
                            checked={server.uot === true}
                            onChange={checked => {
                                const servers = [...(outbound.settings?.servers || [{}])];
                                servers[0] = { ...servers[0], uot: checked };
                                onChange('settings', { ...outbound.settings, servers });
                            }}
                            label="UDP поверх TCP (UOT)"
                        />
                    </div>
                )}
            </div>
        </Card>
    );
};

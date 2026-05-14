// @ts-nocheck
import React, { useState } from 'react';
import { Icon } from '../../ui/Icon';
import { Help } from '../../ui/Help';
import { SmartTagInput } from '../../ui/SmartTagInput';
import { TagSelector } from '../../ui/TagSelector';
import { JsonField } from '../../ui/JsonField';
import { Select } from '../../ui/Select';
import { validateRule, lintRule } from '../../../utils/validator';
import { TagDetailsModal } from '../TagDetailsModal';
import { useEffect } from 'react';

const AttrsEditor = ({ value, onChange }: any) => {
    const [text, setText] = useState(value ? JSON.stringify(value, null, 2) : "");
    const [error, setError] = useState(false);

    useEffect(() => {
        const currentText = value ? JSON.stringify(value, null, 2) : "";
        try {
            if (JSON.stringify(JSON.parse(text)) === JSON.stringify(value)) return;
        } catch (e) { }
        setText(currentText);
    }, [value]);

    const handleChange = (v: string) => {
        setText(v);
        if (!v.trim()) {
            onChange(undefined);
            setError(false);
            return;
        }
        try {
            const parsed = JSON.parse(v);
            onChange(parsed);
            setError(false);
        } catch (e) {
            setError(true);
        }
    };

    return (
        <div className="flex-1 flex flex-col relative">
            <textarea
                className={`input-base font-mono text-xs flex-1 min-h-[140px] resize-none bg-slate-950/50 border-slate-800/80 focus:border-indigo-500/50 transition-all p-3 ${error ? 'ring-1 ring-rose-500/30 border-rose-500/50' : ''}`}
                placeholder='{":method": "GET"}'
                value={text}
                onChange={e => handleChange(e.target.value)}
            />
            {error && (
                <div className="absolute bottom-2 right-2 text-[9px] font-bold text-rose-500 bg-rose-950/80 px-2 py-0.5 rounded border border-rose-500/30 animate-pulse">
                    INVALID JSON
                </div>
            )}
        </div>
    );
};

export const RuleEditor = ({
    rule,
    onChange,
    outboundTags,
    balancerTags,
    inboundTags,
    geoData,
    rawMode
}: any) => {
    // Стейт для просмотра деталей тега по клику
    const [viewTag, setViewTag] = useState<string | null>(null);

    if (!rule) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center text-slate-600 h-full">
                <Icon name="ArrowsSplit" className="text-6xl mb-4 opacity-10" />
                <p>Select a rule to configure routing logic</p>
            </div>
        );
    }

    if (rawMode) {
        return (
            <div className="flex-1 w-full h-full bg-slate-950 overflow-hidden">
                <JsonField label="Raw Rule JSON" value={rule} onChange={onChange} className="h-full" schemaMode="rule" />
            </div>
        );
    }

    const update = (field: string, val: any) => {
        const newRule = { ...rule };
        if (val === undefined || val === "" || (Array.isArray(val) && val.length === 0)) {
            delete newRule[field];
        } else {
            newRule[field] = val;
        }
        if (field === 'outboundTag') delete newRule.balancerTag;
        if (field === 'balancerTag') delete newRule.outboundTag;
        onChange(newRule);
    };

    const handleAutofixMatchers = () => onChange({ ...rule, network: "tcp,udp" });
    const handleAutofixCase = () => onChange({
        ...rule,
        ...(rule.domain ? { domain: rule.domain.map((d: string) => d.toLowerCase()) } : {}),
        ...(rule.ip ? { ip: rule.ip.map((ip: string) => ip.toLowerCase()) } : {}),
    });

    const errors = validateRule(rule);
    const warnings = lintRule(rule);

    const hasMissingMatchers = errors.some((e: any) => e.field === 'matchers');
    const missingTarget = errors.some((e: any) => e.field === 'target');

    const invalidDomains = errors
        .filter((e: any) => e.field.startsWith('domain_'))
        .map((e: any) => (rule.domain || [])[parseInt(e.field.replace('domain_', ''), 10)] as string | undefined)
        .filter((v): v is string => v !== undefined);

    const invalidIPs = errors
        .filter((e: any) => e.field.startsWith('ip_'))
        .map((e: any) => (rule.ip || [])[parseInt(e.field.replace('ip_', ''), 10)] as string | undefined)
        .filter((v): v is string => v !== undefined);

    const warnDomains = warnings
        .filter((e: any) => e.field.startsWith('domain_'))
        .map((e: any) => (rule.domain || [])[parseInt(e.field.replace('domain_', ''), 10)] as string | undefined)
        .filter((v): v is string => v !== undefined);

    const warnIPs = warnings
        .filter((e: any) => e.field.startsWith('ip_'))
        .map((e: any) => (rule.ip || [])[parseInt(e.field.replace('ip_', ''), 10)] as string | undefined)
        .filter((v): v is string => v !== undefined);

    const currentTarget = rule.balancerTag ? `bal:${rule.balancerTag}` : (rule.outboundTag || "");

    return (
        <div className="flex-1 w-full overflow-y-auto custom-scroll p-6 space-y-6 bg-slate-950/30 h-full relative">

            {errors.length > 0 && (
                <div className="p-3.5 bg-rose-950/50 border border-rose-500/60 rounded-xl flex items-start gap-2.5 animate-in fade-in slide-in-from-top-2">
                    <Icon name="WarningOctagon" weight="fill" className="text-rose-400 text-xl shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0 space-y-1.5">
                        <ul className="space-y-1 text-[11px] text-rose-200">
                            {errors.map((e: any, i: number) => <li key={i}>{e.message}</li>)}
                        </ul>
                        {hasMissingMatchers && (
                            <button
                                onClick={handleAutofixMatchers}
                                className="flex items-center gap-1.5 text-[11px] font-bold text-blue-300 hover:text-blue-200 bg-blue-900/30 hover:bg-blue-800/40 border border-blue-700/40 rounded-lg px-3 py-1.5 transition-colors"
                            >
                                <Icon name="MagicWand" />
                                Auto-fix: add network: tcp,udp (proper catch-all)
                            </button>
                        )}
                    </div>
                </div>
            )}

            {warnings.length > 0 && (
                <div className="p-3 bg-amber-950/30 border border-amber-500/40 rounded-xl flex items-start gap-2.5 animate-in fade-in">
                    <Icon name="Warning" weight="fill" className="text-amber-400 text-base shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0 space-y-1.5">
                        <p className="text-[10px] text-amber-400/70 font-bold uppercase tracking-wide">Style lint</p>
                        <ul className="space-y-0.5 text-[11px] text-amber-200/80">
                            {warnings.map((w: any, i: number) => <li key={i}>{w.message}</li>)}
                        </ul>
                        <button
                            onClick={handleAutofixCase}
                            className="flex items-center gap-1.5 text-[11px] font-bold text-amber-300 hover:text-amber-200 bg-amber-900/20 hover:bg-amber-800/30 border border-amber-700/30 rounded-lg px-3 py-1.5 transition-colors"
                        >
                            <Icon name="MagicWand" />
                            Auto-fix: convert to lowercase
                        </button>
                    </div>
                </div>
            )}

            <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl shadow-lg border-l-4 border-l-indigo-500">
                <label className="label-xs text-indigo-400">Rule Alias / Name (ruleTag)</label>
                <input
                    className="input-base mt-1 font-bold"
                    placeholder="e.g. Block Ads, Global Proxy..."
                    value={rule.ruleTag || ""}
                    onChange={e => update('ruleTag', e.target.value)}
                />
                <p className="text-[10px] text-slate-500 mt-1 italic">
                    This name will be shown in UI and Xray logs when matched.
                </p>
            </div>

            <div className={`bg-slate-900 border p-4 rounded-xl shadow-lg ${missingTarget ? 'border-rose-500/60' : 'border-slate-800'}`}>
                <div className="flex justify-between items-center mb-2">
                    <label className="text-[10px] font-bold text-indigo-400 uppercase tracking-widest">Traffic Destination</label>
                    <div className="text-[10px] text-slate-500 font-mono">Where to send traffic</div>
                </div>
                <div className="flex gap-2">
                    <Select
                        className="flex-1"
                        value={currentTarget}
                        placeholder="Select Target..."
                        onChange={val => {
                            if (val.startsWith('bal:')) update('balancerTag', val.replace('bal:', ''));
                            else update('outboundTag', val);
                        }}
                        options={[
                            ...outboundTags.map((t: string) => ({ value: t, label: t, description: 'Outbound' })),
                            ...balancerTags.map((t: string) => ({ value: `bal:${t}`, label: `⚡ ${t}`, description: 'Load Balancer' }))
                        ]}
                    />
                    <input
                        className={`w-1/3 input-base text-slate-300 ${missingTarget ? 'border-rose-500 bg-rose-500/10' : ''}`}
                        placeholder="Custom tag..."
                        value={rule.outboundTag || rule.balancerTag || ""}
                        onChange={e => update('outboundTag', e.target.value)}
                    />
                </div>
                {missingTarget && (
                    <p className="text-[10px] text-rose-400 mt-1.5">
                        Required — select or type a destination tag, otherwise Xray will crash.
                    </p>
                )}
            </div>

            <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="col-span-2">
                        <SmartTagInput
                            label={<span className="flex items-center">Domains (GeoSite) <Help>List of domains to match. Use geosite:google for predefined groups.</Help></span>}
                            prefix="geosite:"
                            placeholder="google, geosite:netflix..."
                            value={rule.domain || []}
                            onChange={v => update('domain', v)}
                            suggestions={geoData.sites}
                            isLoading={geoData.loading}
                            invalidTags={invalidDomains}
                            warnTags={warnDomains}
                            onTagClick={setViewTag}
                        />
                    </div>
                    <div className="col-span-2">
                        <SmartTagInput
                            label={<span className="flex items-center">IPs (GeoIP & CIDR) <Help>List of IP addresses or CIDR ranges. Use geoip:cn for country-based matching.</Help></span>}
                            prefix="geoip:"
                            placeholder="8.8.8.8, geoip:cn..."
                            value={rule.ip || []}
                            onChange={v => update('ip', v)}
                            suggestions={geoData.ips}
                            isLoading={geoData.loading}
                            invalidTags={invalidIPs}
                            warnTags={warnIPs}
                            onTagClick={setViewTag}
                        />
                    </div>
                </div>

                <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800/50 space-y-4">
                    <label className="text-[10px] font-bold text-slate-500 uppercase tracking-widest block border-b border-slate-800 pb-2">
                        Advanced Matchers
                    </label>
                    <div className="grid grid-cols-2 gap-6">
                        <div>
                            <TagSelector
                                label={<span className="flex items-center">Inbound Source <Help>Filter traffic by the tag of the inbound connection.</Help></span>}
                                availableTags={inboundTags} selected={rule.inboundTag || []}
                                onChange={v => update('inboundTag', v)} multi={true} />
                        </div>
                        <div>
                            <TagSelector
                                label="Network"
                                availableTags={['tcp', 'udp']}
                                selected={rule.network ? rule.network.split(',') : []}
                                onChange={v => update('network', Array.isArray(v) ? v.join(',') : v)}
                                multi={true}
                            />
                            {hasMissingMatchers && (
                                <p className="text-[10px] text-blue-400 mt-1">
                                    ↑ Select tcp + udp for a proper catch-all
                                </p>
                            )}
                        </div>
                        <div>
                            <TagSelector label="Протокол" availableTags={['http', 'tls', 'bittorrent']} selected={rule.protocol || []}
                                onChange={v => update('protocol', v)} multi={true} />
                        </div>

                        {/* Domain Strategy (Force IP) */}
                        <div className="flex flex-col gap-1.5">
                            <label className="label-xs flex items-center gap-1.5 text-slate-400">
                                Domain Strategy (Force IP) <Help>UseIP will force Xray to resolve the domain before matching.</Help>
                            </label>
                            <Select
                                value={rule.domainStrategy || ""}
                                onChange={val => update('domainStrategy', val || undefined)}
                                options={[
                                    { value: "", label: "Default (Inherit)" },
                                    { value: "AsIs", label: "AsIs" },
                                    { value: "UseIP", label: "UseIP" },
                                    { value: "UseIPv4", label: "UseIPv4" },
                                    { value: "UseIPv6", label: "UseIPv6" },
                                ]}
                                className="w-full"
                            />
                        </div>

                        <div className="col-span-2 grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-4 pt-6 mt-2 border-t border-slate-800/50">
                            <div className="flex flex-col gap-1.5">
                                <label className="label-xs text-slate-500">Target Port</label>
                                <input className="input-base text-xs font-mono bg-slate-950/30" placeholder="e.g. 443"
                                    value={rule.port || ""} onChange={e => update('port', e.target.value)} />
                            </div>
                            <div className="flex flex-col gap-1.5">
                                <label className="label-xs text-slate-500">Source Port</label>
                                <input className="input-base text-xs font-mono bg-slate-950/30" placeholder="e.g. 1000-2000"
                                    value={rule.sourcePort || ""} onChange={e => update('sourcePort', e.target.value)} />
                            </div>
                            <div className="flex flex-col gap-1.5">
                                <label className="label-xs text-slate-500">Local Port</label>
                                <input className="input-base text-xs font-mono bg-slate-950/30" placeholder="e.g. 53"
                                    value={rule.localPort || ""} onChange={e => update('localPort', e.target.value)} />
                            </div>
                            <div className="flex flex-col gap-1.5">
                                <label className="label-xs flex items-center gap-1.5 text-slate-500">vlessRoute <Help>e.g. 1 or 14514</Help></label>
                                <input className="input-base text-xs font-mono bg-slate-950/30" placeholder="e.g. 1"
                                    value={rule.vlessRoute || ""} onChange={e => update('vlessRoute', e.target.value)} />
                            </div>
                            <div className="flex flex-col gap-1.5">
                                <label className="label-xs text-slate-500">Source IP (CIDR)</label>
                                <input className="input-base text-xs font-mono bg-slate-950/30" placeholder="10.0.0.1"
                                    value={(rule.sourceIP || rule.source || []).join(',')}
                                    onChange={e => update('sourceIP', e.target.value ? e.target.value.split(',') : undefined)} />
                            </div>
                            <div className="flex flex-col gap-1.5">
                                <label className="label-xs text-slate-500">Local IP</label>
                                <input className="input-base text-xs font-mono bg-slate-950/30" placeholder="192.168.0.1"
                                    value={(rule.localIP || []).join(',')}
                                    onChange={e => update('localIP', e.target.value ? e.target.value.split(',') : undefined)} />
                            </div>
                            <div className="flex flex-col gap-1.5">
                                <label className="label-xs text-slate-500">User (Email)</label>
                                <input className="input-base text-xs font-mono bg-slate-950/30" placeholder="user@xray.com"
                                    value={(rule.user || []).join(',')}
                                    onChange={e => update('user', e.target.value ? e.target.value.split(',') : undefined)} />
                            </div>
                            <div className="flex flex-col gap-1.5">
                                <label className="label-xs flex items-center gap-1.5 text-slate-500">Process <Help>e.g. curl, xray/</Help></label>
                                <input className="input-base text-xs font-mono bg-slate-950/30" placeholder="curl, self/"
                                    value={(rule.process || []).join(',')}
                                    onChange={e => update('process', e.target.value ? e.target.value.split(',') : undefined)} />
                            </div>
                        </div>
                    </div>
                </div>

                {/* HTTP Attrs & Webhook */}
                <div className="bg-slate-900/40 p-5 rounded-2xl border border-slate-800/60 space-y-5">
                    <label className="text-[10px] font-bold text-slate-500 uppercase tracking-[0.2em] block border-b border-slate-800 pb-3">
                        Advanced Features
                    </label>
                    <div className="grid grid-cols-2 gap-8">
                        <div className="flex flex-col gap-2 h-full">
                            <label className="label-xs flex items-center gap-1.5 text-slate-400">
                                HTTP Attributes (JSON) <Help>{`e.g. {":method": "GET", ":path": "/test"}`}</Help>
                            </label>
                            <AttrsEditor value={rule.attrs} onChange={(v: any) => update('attrs', v)} />
                        </div>
                        <div className="flex flex-col gap-2 h-full">
                            <label className="label-xs flex items-center gap-1.5 text-slate-400">
                                Webhook Notification <Help>Send HTTP POST notification on match.</Help>
                            </label>
                            <div className="flex flex-col gap-4 flex-1">
                                <div className="flex flex-col gap-1.5">
                                    <label className="text-[9px] uppercase font-bold text-slate-600 ml-1">Callback URL</label>
                                    <input className="input-base text-xs font-mono bg-slate-950/50 border-slate-800/80" placeholder="https://api.site.com/hook"
                                        value={rule.webhook?.url || ""}
                                        onChange={e => update('webhook', { ...rule.webhook, url: e.target.value })} />
                                </div>
                                <div className="flex flex-col gap-1.5">
                                    <label className="text-[9px] uppercase font-bold text-slate-600 ml-1">Deduplication (seconds)</label>
                                    <input className="input-base text-xs font-mono bg-slate-950/50 border-slate-800/80" type="number" placeholder="10"
                                        value={rule.webhook?.deduplication || ""}
                                        onChange={e => update('webhook', { ...rule.webhook, deduplication: Number(e.target.value) })} />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Рендерим модалку деталей тега поверх формы */}
            {viewTag && <TagDetailsModal tag={viewTag} onClose={() => setViewTag(null)} />}
        </div>
    );
};
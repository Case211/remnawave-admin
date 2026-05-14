// @ts-nocheck
import React from 'react';
import { Switch } from '../../ui/Switch';
import { Select } from '../../ui/Select';

export const DnsGeneral = ({ dns, onChange }) => {
    const update = (field: string, val: any) => {
        onChange({ ...dns, [field]: val });
    };

    return (
        <div className="space-y-6 animate-in fade-in">
            {/* Main Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                    <label className="label-xs">DNS Tag (Inbound)</label>
                    <input 
                        className="input-base font-bold text-emerald-400" 
                        value={dns.tag || ""} 
                        onChange={e => update('tag', e.target.value)} 
                        placeholder="dns_inbound"
                    />
                </div>
                <div>
                    <label className="label-xs">Client IP</label>
                    <input 
                        className="input-base font-mono" 
                        value={dns.clientIp || ""} 
                        onChange={e => update('clientIp', e.target.value)} 
                        placeholder="Your public IP (for ECS)"
                    />
                </div>
                    <Select 
                        label="Query Strategy"
                        value={dns.queryStrategy || "UseIP"} 
                        onChange={val => update('queryStrategy', val)}
                        options={[
                            { value: "UseIP", label: "UseIP", description: "Dual stack (A + AAAA)" },
                            { value: "UseIPv4", label: "UseIPv4", description: "IPv4 only (A)" },
                            { value: "UseIPv6", label: "UseIPv6", description: "IPv6 only (AAAA)" },
                        ]}
                    />
            </div>

            {/* Toggles */}
            <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800 space-y-4">
                <h4 className="label-xs border-b border-slate-700/50 pb-2 mb-2">Behavior Flags</h4>
                
                <div className="space-y-3">
                    <Switch 
                        checked={dns.disableCache || false}
                        onChange={checked => update('disableCache', checked)} 
                        label="Disable Cache"
                    />

                    <Switch 
                        checked={dns.disableFallback || false}
                        onChange={checked => update('disableFallback', checked)} 
                        label="Disable Fallback"
                    />

                    <Switch 
                        checked={dns.disableFallbackIfMatch || false}
                        onChange={checked => update('disableFallbackIfMatch', checked)} 
                        label="Disable Fallback If Match"
                    />
                </div>
            </div>
        </div>
    );
};
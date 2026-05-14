// @ts-nocheck
import React from 'react';
import { TagSelector } from '../../ui/TagSelector';
import { Switch } from '../../ui/Switch';
import { Select } from '../../ui/Select';

export const OutboundProxyMux = ({ outbound, onChange, allTags }) => {
    const availableProxies = allTags.filter(t => t !== outbound.tag);

    const updateProxy = (tag) => {
        if (!tag) {
            onChange('proxySettings', undefined);
        } else {
            onChange('proxySettings', { tag });
        }
    };

    const updateMux = (enabled) => {
        if (!enabled) {
            onChange('mux', undefined);
        } else {
            onChange('mux', { enabled: true, concurrency: 8, xudpConcurrency: 8, xudpProxyUDP443: "reject" });
        }
    };

    const updateMuxField = (field, val) => {
        onChange(['mux', field], val);
    };

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-4">
            
            {/* Proxy Chain */}
            <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800">
                <h4 className="label-xs text-slate-400 mb-3">Proxy Chaining (Optional)</h4>
                <TagSelector 
                    availableTags={availableProxies}
                    selected={outbound.proxySettings?.tag || ""}
                    onChange={v => updateProxy(v)}
                    placeholder="Прямой (без проксирования)"
                />
            </div>

            {/* Mux */}
            <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800">
                <div className="flex justify-between items-center mb-3">
                    <h4 className="label-xs text-slate-400">Mux (Multiplexing)</h4>
                    <Switch
                        checked={outbound.mux?.enabled || false}
                        onChange={checked => updateMux(checked)}
                    />
                </div>
                
                {outbound.mux?.enabled && (
                    <div className="space-y-3 animate-in fade-in">
                        <div className="grid grid-cols-2 gap-2">
                            <div>
                                <label className="label-xs">TCP Concurrency</label>
                                <input type="number" className="input-base" 
                                    value={outbound.mux.concurrency || 8}
                                    onChange={e => updateMuxField('concurrency', parseInt(e.target.value))}
                                />
                            </div>
                            <div>
                                <label className="label-xs">XUDP Concurrency</label>
                                <input type="number" className="input-base" 
                                    value={outbound.mux.xudpConcurrency || 8}
                                    onChange={e => updateMuxField('xudpConcurrency', parseInt(e.target.value))}
                                />
                            </div>
                        </div>
                        
                        <Select 
                            label="UDP 443 Strategy (QUIC)"
                            value={outbound.mux.xudpProxyUDP443 || "reject"}
                            onChange={val => updateMuxField('xudpProxyUDP443', val)}
                            options={[
                                { value: "reject", label: "Reject", description: "Recommended" },
                                { value: "allow", label: "Allow" },
                                { value: "skip", label: "Skip" },
                            ]}
                        />
                    </div>
                )}
                {!outbound.mux?.enabled && <p className="text-[10px] text-slate-500">Enable to reduce handshake latency.</p>}
            </div>
        </div>
    );
};
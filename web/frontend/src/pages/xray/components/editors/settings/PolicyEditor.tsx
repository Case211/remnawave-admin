// @ts-nocheck
import React from 'react';
import { Switch } from '../../ui/Switch';
import { Card } from '../../ui/Card';

export const PolicyEditor = ({ policy, onChange, onToggle }) => {
    const enabled = !!policy;
    const localPolicy = policy || { 
        system: { statsInboundUplink: true, statsInboundDownlink: true },
        levels: { "0": { handshake: 4, connIdle: 300, uplinkOnly: 2, downlinkOnly: 5, bufferSize: 4 } }
    };

    const updateSystem = (field: string, val: boolean) => {
        const sys = { ...localPolicy.system, [field]: val };
        onChange({ ...localPolicy, system: sys });
    };

    const updateLevel0 = (field: string, val: number) => {
        const lvls = JSON.parse(JSON.stringify(localPolicy.levels || { "0": {} }));
        if (!lvls["0"]) lvls["0"] = {};
        lvls["0"][field] = val;
        onChange({ ...localPolicy, levels: lvls });
    };

    const l0 = localPolicy.levels?.["0"] || {};

    return (
        <Card 
            title="Local Policy" 
            icon="ShieldCheck"
            headerExtra={
                <Switch 
                    checked={enabled}
                    onChange={() => onToggle({
                        system: { statsInboundUplink: true, statsInboundDownlink: true },
                        levels: { "0": { handshake: 4, connIdle: 300 } }
                    })}
                />
            }
        >
            <p className="text-xs text-slate-500 mb-2">Timeouts & System Stats</p>

            {enabled && (
                <div className="animate-in fade-in slide-in-from-top-2 space-y-4 pt-2 border-t border-slate-800/50">
                    {/* System Stats */}
                    <div className="p-4 border border-slate-800 rounded-xl bg-slate-950/50">
                        <label className="label-xs mb-3">System Traffic Counters</label>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                            {['statsInboundUplink', 'statsInboundDownlink', 'statsOutboundUplink', 'statsOutboundDownlink'].map(k => (
                                <div key={k} className="flex items-center h-8">
                                    <Switch 
                                        checked={localPolicy.system?.[k] || false}
                                        onChange={checked => updateSystem(k, checked)}
                                        label={k}
                                    />
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Level 0 Timeouts */}
                    <div className="p-4 border border-slate-800 rounded-xl bg-slate-950/50">
                        <label className="label-xs mb-3">Level 0 (Default User) Timeouts (sec)</label>
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                            <div>
                                <label className="text-[10px] text-slate-500 block mb-1">Handshake</label>
                                <input type="number" className="input-base" value={l0.handshake || 4} onChange={e => updateLevel0('handshake', parseInt(e.target.value))} />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-500 block mb-1">Conn Idle</label>
                                <input type="number" className="input-base" value={l0.connIdle || 300} onChange={e => updateLevel0('connIdle', parseInt(e.target.value))} />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-500 block mb-1">Buffer Size (kB)</label>
                                <input type="number" className="input-base" value={l0.bufferSize || 4} onChange={e => updateLevel0('bufferSize', parseInt(e.target.value))} />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-500 block mb-1">Uplink Only</label>
                                <input type="number" className="input-base" value={l0.uplinkOnly || 2} onChange={e => updateLevel0('uplinkOnly', parseInt(e.target.value))} />
                            </div>
                            <div>
                                <label className="text-[10px] text-slate-500 block mb-1">Downlink Only</label>
                                <input type="number" className="input-base" value={l0.downlinkOnly || 5} onChange={e => updateLevel0('downlinkOnly', parseInt(e.target.value))} />
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </Card>
    );
};
// @ts-nocheck
import React from 'react';
import { Select } from '../../ui/Select';

export const InboundTun = ({ inbound, onChange }: any) => {
    const settings = inbound.settings || {};

    const update = (field: string, val: any) => {
        onChange(['settings', field], val);
    };

    return (
        <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800 mt-4 animate-in fade-in">
            <h4 className="text-xs font-bold text-slate-400 uppercase mb-3 border-b border-slate-700/50 pb-2">
                TUN Interface Settings
            </h4>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* MTU */}
                <div>
                    <label className="label-xs">MTU</label>
                    <input 
                        type="number" 
                        className="input-base font-mono"
                        value={settings.mtu || 1500} 
                        onChange={e => update('mtu', parseInt(e.target.value) || 1500)}
                    />
                    <p className="text-[10px] text-slate-500 mt-1">Default: 1500</p>
                </div>

                {/* Network Stack */}
                    <Select 
                        label="Сетевой стек"
                        value={settings.stack || "system"} 
                        onChange={val => update('stack', val)}
                        options={[
                            { value: "system", label: "System", description: "Standard OS stack (Recommended)" },
                            { value: "gvisor", label: "gVisor", description: "Google's userspace network stack" },
                            { value: "mixed", label: "Mixed", description: "Hybrid system/gvisor" },
                            { value: "lwip", label: "LwIP", description: "Lightweight IP stack" },
                        ]}
                    />

                {/* Endpoint (Optional for gVisor/System) */}
                <div className="md:col-span-2">
                    <label className="label-xs">Endpoint Address (Optional)</label>
                    <div className="flex gap-2">
                         <input 
                            className="input-base flex-1 font-mono"
                            placeholder="127.0.0.1" 
                            value={settings.endpointAddress || ""} 
                            onChange={e => update('endpointAddress', e.target.value)}
                        />
                         <input 
                            type="number"
                            className="input-base w-24 font-mono"
                            placeholder="Порт" 
                            value={settings.endpointPort || ""} 
                            onChange={e => update('endpointPort', parseInt(e.target.value) || undefined)}
                        />
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1">Leave empty usually. Used for specific stack configurations.</p>
                </div>
            </div>
        </div>
    );
};
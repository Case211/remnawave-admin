// @ts-nocheck
import React from 'react';
import { TagSelector } from '../../ui/TagSelector';
import { Help } from '../../ui/Help';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { useConfigStore } from '../../../store/configStore';
import { Select } from '../../ui/Select';

export const SockoptEditor = ({ sockopt, onChange, isClient }: any) => {
    const local = sockopt || {};
    const config = useConfigStore(state => state.config);
    const outboundTags = (config?.outbounds || []).map((o: any) => o.tag).filter(Boolean);

    const update = (field: string, val: any) => {
        // Чистим пустые/NaN значения чтобы не мусорить в JSON
        if (val === "" || Number.isNaN(val)) {
            const newObj = { ...local };
            delete newObj[field];
            onChange(newObj);
        } else {
            onChange({ ...local, [field]: val });
        }
    };

    if (!sockopt) {
        return (
            <div className="border-t border-slate-800 pt-4 space-y-4 animate-in fade-in">
                <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-blue-400 flex items-center gap-2">
                        <Icon name="Sliders" size={14} /> Socket Options (Sockopt)
                    </label>
                    <button className="bg-blue-500/10 border border-blue-500/50 text-blue-500 hover:bg-blue-500/20 text-[10px] font-bold px-2 py-0.5 rounded transition-colors" onClick={() => onChange({})}>
                        ADD
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="border-t border-slate-800/60 pt-6 space-y-4">
            <div className="flex items-center justify-between">
                <label className="text-xs font-bold text-blue-400 flex items-center gap-2">
                    <Icon name="Sliders" size={14} /> Socket Options (Sockopt)
                </label>
                <button className="bg-rose-500/10 border border-rose-500/50 text-rose-500 hover:bg-rose-500/20 text-[10px] font-bold px-2 py-0.5 rounded transition-colors" onClick={() => onChange(null)}>
                    REMOVE
                </button>
            </div>

            <div className="bg-slate-950/40 p-4 rounded-xl border border-slate-800/60 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* GENERAL / ROUTING */}
                    <div>
                        <label className="label-xs">Mark (Routing)</label>
                        <input type="number" className="input-base font-mono"
                            placeholder="255"
                            value={local.mark || ""}
                            onChange={e => update('mark', parseInt(e.target.value))}
                        />
                    </div>

                    <div>
                        <label className="label-xs">Interface (Bind)</label>
                        <input className="input-base font-mono"
                            placeholder="eth0 or wg0"
                            value={local.interface || ""}
                            onChange={e => update('interface', e.target.value)}
                        />
                    </div>

                    {/* INBOUND ONLY */}
                    {!isClient && (
                        <>
                                <Select 
                                    label="TProxy (Linux)"
                                    value={local.tproxy || "off"}
                                    onChange={val => update('tproxy', val)}
                                    options={[
                                        { value: "off", label: "Off" },
                                        { value: "tproxy", label: "TProxy" },
                                        { value: "redirect", label: "Redirect" },
                                    ]}
                                />
                                <Select 
                                    label="Accept PROXY Protocol"
                                    value={local.acceptProxyProtocol === true ? "true" : "false"}
                                    onChange={val => update('acceptProxyProtocol', val === "true")}
                                    options={[
                                        { value: "false", label: "Отключено" },
                                        { value: "true", label: "Включено" },
                                    ]}
                                />
                                <Select 
                                    label="V6 Only (Bind ::)"
                                    value={local.v6only === true ? "true" : "false"}
                                    onChange={val => update('v6only', val === "true")}
                                    options={[
                                        { value: "false", label: "Отключено" },
                                        { value: "true", label: "Включено" },
                                    ]}
                                />
                        </>
                    )}

                    {/* OUTBOUND ONLY */}
                    {isClient && (
                        <>
                            <div className="md:col-span-2">
                                <TagSelector
                                    label={
                                        <span className="flex items-center gap-1">
                                            Dialer Proxy (Outbound Tag)
                                            <Help>Forwards this outbound's traffic through another outbound (tag). Used to "wrap" protocols like WireGuard into obfuscation layers like Freedom+Finalmask.</Help>
                                        </span>
                                    }
                                    availableTags={outboundTags}
                                    selected={local.dialerProxy || ""}
                                    onChange={v => update('dialerProxy', v as string)}
                                    multi={false}
                                    placeholder="Select outbound..."
                                />
                            </div>
                                <Select 
                                    label="Стратегия доменов"
                                    value={local.domainStrategy || "AsIs"}
                                    onChange={val => update('domainStrategy', val)}
                                    options={[
                                        { value: "AsIs", label: "AsIs" },
                                        { value: "UseIP", label: "UseIP" },
                                        { value: "UseIPv4", label: "UseIPv4" },
                                        { value: "UseIPv6", label: "UseIPv6" },
                                        { value: "UseIPv4v6", label: "UseIPv4v6" },
                                        { value: "UseIPv6v4", label: "UseIPv6v4" },
                                    ]}
                                />
                        </>
                    )}

                    {/* TCP ADVANCED / KERNEL */}
                                <Select 
                                    label="TCP Fast Open"
                                    value={local.tcpFastOpen === true ? "true" : "false"}
                                    onChange={val => update('tcpFastOpen', val === "true")}
                                    options={[
                                        { value: "false", label: "Отключено" },
                                        { value: "true", label: "Включено" },
                                    ]}
                                />

                                <Select 
                                    label="TCP MPTCP"
                                    hint="Linux 5.6+"
                                    value={local.tcpMptcp === true ? "true" : "false"}
                                    onChange={val => update('tcpMptcp', val === "true")}
                                    options={[
                                        { value: "false", label: "Отключено" },
                                        { value: "true", label: "Включено" },
                                    ]}
                                />
                </div>

                {/* EXTENDED TCP TIMEOUTS & WINDOWS */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-slate-800/50">
                    <div className="col-span-full">
                        <label className="label-xs text-slate-500">Low-level TCP Tuning (Leave empty for OS defaults)</label>
                    </div>
                    <div>
                        <label className="label-xs text-[10px]">TCP Keep-Alive Idle (s)</label>
                        <input type="number" className="input-base font-mono text-xs"
                            placeholder="300"
                            value={local.tcpKeepAliveIdle || ""}
                            onChange={e => update('tcpKeepAliveIdle', parseInt(e.target.value))}
                        />
                    </div>
                    <div>
                        <label className="label-xs text-[10px]">TCP Keep-Alive Interval</label>
                        <input type="number" className="input-base font-mono text-xs"
                            placeholder="0"
                            value={local.tcpKeepAliveInterval || ""}
                            onChange={e => update('tcpKeepAliveInterval', parseInt(e.target.value))}
                        />
                    </div>
                    <div>
                        <label className="label-xs text-[10px]">TCP User Timeout (ms)</label>
                        <input type="number" className="input-base font-mono text-xs"
                            placeholder="10000"
                            value={local.tcpUserTimeout || ""}
                            onChange={e => update('tcpUserTimeout', parseInt(e.target.value))}
                        />
                    </div>
                    <div>
                        <label className="label-xs text-[10px]">TCP Max Segment (MTU)</label>
                        <input type="number" className="input-base font-mono text-xs"
                            placeholder="1440"
                            value={local.tcpMaxSeg || ""}
                            onChange={e => update('tcpMaxSeg', parseInt(e.target.value))}
                        />
                    </div>
                    <div>
                        <label className="label-xs text-[10px]">TCP Congestion</label>
                        <input type="text" className="input-base font-mono text-xs"
                            placeholder="bbr, cubic..."
                            value={local.tcpCongestion || ""}
                            onChange={e => update('tcpCongestion', e.target.value)}
                        />
                    </div>
                    <div>
                        <label className="label-xs text-[10px]">TCP Window Clamp</label>
                        <input type="number" className="input-base font-mono text-xs"
                            placeholder="600"
                            value={local.tcpWindowClamp || ""}
                            onChange={e => update('tcpWindowClamp', parseInt(e.target.value))}
                        />
                    </div>
                </div>
            </div>
        </div>
    );
};
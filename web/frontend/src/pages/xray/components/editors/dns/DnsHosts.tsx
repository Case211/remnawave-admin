// @ts-nocheck
import React, { useState, useEffect, useRef } from 'react';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { isValidDomain, isValidHostDestination } from '../../../utils/validator';

export const DnsHosts = ({ hosts = {}, onChange }: any) => {
    const [entries, setEntries] = useState<{ domain: string, ips: string[] }[]>(() => 
        Object.entries(hosts).map(([domain, ips]) => ({ 
            domain, 
            ips: Array.isArray(ips) ? [...ips] : [ips]
        }))
    );
    
    const isInternalChange = useRef(false);

    useEffect(() => {
        if (isInternalChange.current) {
            isInternalChange.current = false;
            return;
        }
        
        const incomingEntries = Object.entries(hosts);
        const currentValidCount = entries.filter(e => e.domain.trim() !== "").length;

        if (incomingEntries.length !== currentValidCount) {
            const newEntries = incomingEntries.map(([domain, ips]) => ({ 
                domain, 
                ips: Array.isArray(ips) ? [...ips] : [ips]
            }));
            setEntries(newEntries);
        }
    }, [hosts]);

    const saveToStore = (currentEntries: typeof entries) => {
        const result: Record<string, any> = {};

        currentEntries.forEach(e => {
            const domain = e.domain.trim();
            if (!domain || !isValidDomain(domain)) return;

            const validIps = e.ips.map(ip => ip.trim()).filter(ip => ip !== "" && isValidHostDestination(ip));
            if (validIps.length === 0) return;

            result[domain] = validIps.length === 1 ? validIps[0] : validIps;
        });

        isInternalChange.current = true;
        onChange(result);
    };

    const addHost = () => {
        setEntries(prev => [...prev, { domain: "", ips: [""] }]);
    };

    const updateDomain = (hIdx: number, val: string) => {
        const newEntries = entries.map((item, i) => 
            i === hIdx ? { ...item, domain: val } : item
        );
        setEntries(newEntries);
        saveToStore(newEntries);
    };

    const updateIpValue = (hIdx: number, ipIdx: number, val: string) => {
        const newEntries = entries.map((item, i) => {
            if (i !== hIdx) return item;
            return {
                ...item,
                ips: item.ips.map((ip, j) => j === ipIdx ? val : ip)
            };
        });
        setEntries(newEntries);
        saveToStore(newEntries);
    };

    const removeHost = (hIdx: number) => {
        const newEntries = entries.filter((_, i) => i !== hIdx);
        setEntries(newEntries);
        saveToStore(newEntries);
    };

    return (
        <div className="h-full flex flex-col">
            <div className="flex justify-between items-center mb-6 px-1">
                <div>
                    <label className="label-xs text-emerald-400">DNS Static Mapping</label>
                    <p className="text-[10px] text-slate-500">Map domains to specific IP addresses.</p>
                </div>
                <Button variant="secondary" className="px-3 py-1.5 text-xs" onClick={addHost} icon="Plus">
                    Add Host
                </Button>
            </div>
            
            <div className="flex-1 overflow-y-auto custom-scroll space-y-4 pr-2 pb-10">
                {entries.map((host, hIdx) => {
                    const domainIsInvalid = host.domain !== "" && !isValidDomain(host.domain);
                    
                    return (
                        <div key={hIdx} className={`bg-slate-900/50 border rounded-xl p-4 relative group transition-all duration-200 
                            ${domainIsInvalid ? 'border-rose-500/50 bg-rose-500/5' : 'border-slate-800 hover:border-slate-700 shadow-lg'}`}>
                            
                            <button onClick={() => removeHost(hIdx)} className="absolute top-4 right-4 text-slate-600 hover:text-rose-500 transition-colors">
                                <Icon name="Trash" size={18} />
                            </button>

                            <div className="grid grid-cols-1 md:grid-cols-12 gap-4 mt-2">
                                <div className="md:col-span-5">
                                    <label className={`label-xs mb-1.5 block ${domainIsInvalid ? 'text-rose-400' : 'text-slate-500'}`}>
                                        Domain Name {domainIsInvalid && "(Invalid)"}
                                    </label>
                                    <input 
                                        className={`input-base text-sm font-bold ${domainIsInvalid ? 'border-rose-500 text-rose-200 bg-rose-950' : 'text-white'}`} 
                                        placeholder="example.com"
                                        value={host.domain}
                                        onChange={e => updateDomain(hIdx, e.target.value)}
                                    />
                                </div>

                                <div className="md:col-span-7 space-y-2">
                                    <label className="label-xs text-slate-500 mb-1.5 block">IP Addresses</label>
                                    {host.ips.map((ip, ipIdx) => (
                                        <input 
                                            key={ipIdx}
                                            className="input-base text-xs font-mono text-emerald-400" 
                                            placeholder="1.2.3.4"
                                            value={ip}
                                            onChange={e => updateIpValue(hIdx, ipIdx, e.target.value)}
                                        />
                                    ))}
                                </div>
                            </div>
                        </div>
                    );
                })}

                {entries.length === 0 && (
                    <div className="text-center py-16 border-2 border-dashed border-slate-800 rounded-2xl">
                        <Icon name="Globe" size={48} className="mx-auto text-slate-800 mb-4" />
                        <p className="text-slate-500 text-sm">No static hosts configured.</p>
                    </div>
                )}
            </div>
        </div>
    );
};
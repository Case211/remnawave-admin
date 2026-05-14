// @ts-nocheck
import React, { useEffect, useState } from 'react';
import { Button } from '../../ui/Button';
import { SmartTagInput } from '../../ui/SmartTagInput';
import { Switch } from '../../ui/Switch';
import { getDefaultGeoList } from '../../../utils/geo-data';

export const DnsServerEditor = ({ server, onChange, onCancel }) => {
    const isString = typeof server === 'string';
    const[local, setLocal] = useState(isString ? { address: server } : { ...server });

    const[geoSites, setGeoSites] = useState([]);
    const [geoIps, setGeoIps] = useState([]);
    const [loadingGeo, setLoadingGeo] = useState(false);

    useEffect(() => {
        if (!isString) { 
            let isMounted = true;
            setLoadingGeo(true);
            Promise.all([
                getDefaultGeoList('geosite'),
                getDefaultGeoList('geoip')
            ]).then(([sites, ips]) => {
                if (isMounted) {
                    setGeoSites(sites);
                    setGeoIps(ips);
                    setLoadingGeo(false);
                }
            });
            return () => { isMounted = false; };
        }
    }, [isString]);

    const update = (field: string, val: any) => {
        setLocal(prev => ({ ...prev, [field]: val }));
    };

    const handleSave = () => {
        // Если это advanced объект, но в нем только адрес и порт (стандартный), можно попытаться упростить до строки?
        // Нет, Xray различает: строка = UDP/53 (обычно), объект = гибкость.
        // Просто сохраняем как есть.
        onChange(local);
    };

    const convertToAdvanced = () => {
        // Конвертируем строку в объект и перерендерим
        onChange({ address: server, domains: [], expectIPs: [] });
    };

    if (isString) {
        return (
            <div className="bg-slate-900 border border-slate-800 p-6 rounded-xl space-y-6">
                <h3 className="text-sm font-bold text-white">Simple DNS Server</h3>
                <div>
                    <label className="label-xs">Address</label>
                    <input className="input-base font-mono" 
                        value={server} 
                        onChange={e => onChange(e.target.value)} 
                        placeholder="8.8.8.8 or https://..."
                    />
                </div>
                <div className="bg-slate-800/50 p-4 rounded-lg border border-slate-700/50 text-center">
                    <p className="text-xs text-slate-400 mb-3">Need domains filtering or specific IPs?</p>
                    <Button variant="secondary" className="text-xs w-full" onClick={convertToAdvanced}>Convert to Advanced Object</Button>
                </div>
                <div className="flex justify-end gap-2 pt-4">
                    <Button variant="ghost" onClick={onCancel}>Done</Button>
                </div>
            </div>
        );
    }

    return (
        <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl space-y-4 h-full flex flex-col">
            <div className="flex justify-between items-center border-b border-slate-800 pb-2">
                <h3 className="text-sm font-bold text-indigo-400">Advanced Server Config</h3>
                <Button variant="ghost" onClick={() => onChange(local)}>Save & Close</Button>
            </div>

            <div className="overflow-y-auto custom-scroll flex-1 space-y-4 pr-2">
                <div className="grid grid-cols-3 gap-4">
                    <div className="col-span-2">
                        <label className="label-xs">Address</label>
                        <input className="input-base font-mono" 
                            value={local.address || ""} 
                            onChange={e => update('address', e.target.value)} 
                        />
                    </div>
                    <div>
                        <label className="label-xs">Port</label>
                        <input type="number" className="input-base font-mono" 
                            value={local.port || ""} 
                            onChange={e => update('port', parseInt(e.target.value) || undefined)} 
                            placeholder="53"
                        />
                    </div>
                </div>

                <div>
                    <SmartTagInput 
                        label="Domains (Routing)" 
                        prefix="geosite:" 
                        placeholder="geosite:cn, google.com..." 
                        value={local.domains || []} 
                        onChange={v => update('domains', v)}
                        suggestions={geoSites}
                        isLoading={loadingGeo}
                    />
                </div>

                <div>
                    <SmartTagInput 
                        label="Expect IPs (Optional)" 
                        prefix="geoip:" 
                        placeholder="geoip:cn..." 
                        value={local.expectIPs || []} 
                        onChange={v => update('expectIPs', v)}
                        suggestions={geoIps}
                        isLoading={loadingGeo}
                    />
                </div>

                <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-3">
                    <Switch 
                        checked={local.skipFallback || false}
                        onChange={checked => update('skipFallback', checked)}
                        label="Skip Fallback (Critical)"
                    />
                    <Switch 
                        checked={local.queryStrategy === 'UseIPv4'}
                        onChange={checked => update('queryStrategy', checked ? 'UseIPv4' : undefined)}
                        label="Force IPv4 (A Record)"
                    />
                </div>
            </div>
        </div>
    );
};
// @ts-nocheck
import React, { useState } from 'react';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { Help } from '../../ui/Help';
import { toast } from 'sonner';
import { Switch } from '../../ui/Switch';
import { Select } from '../../ui/Select';
import { FormField } from '../../ui/FormField';
import { generateWarpAccount } from '../../../utils/generators';
import { useConfigStore } from '../../../store/configStore';

export const OutboundWireguard = ({ outbound, onChange, errors = {} as any }: any) => {
    if (outbound.protocol !== 'wireguard') return null;

    const { warpWorkerUrl } = useConfigStore();
    const settings = outbound.settings || { secretKey: "", address: ["10.0.0.1/24"], peers: [] };
    const [loading, setLoading] = useState(false);

    const update = (field: string, value: any) => {
        onChange('settings', { ...settings, [field]: value });
    };

    const addPeer = () => {
        const peers = settings.peers || [];
        update('peers', [...peers, { endpoint: "", publicKey: "", keepAlive: 0 }]);
    };

    const updatePeer = (idx: number, field: string, val: any) => {
        const peers = [...(settings.peers || [])];
        peers[idx] = { ...peers[idx], [field]: val };
        update('peers', peers);
    };

    const removePeer = (idx: number) => {
        const peers = [...(settings.peers || [])];
        peers.splice(idx, 1);
        update('peers', peers);
    };

    const handleGenerateWarp = async () => {
        setLoading(true);
        try {
            const warp = await generateWarpAccount(warpWorkerUrl);
            onChange('settings', {
                ...settings,
                secretKey: warp.privateKey,
                address: [`${warp.ipv4}/32`, `${warp.ipv6}/128`],
                reserved: warp.reserved,
                peers: [{
                    endpoint: warp.endpoint,
                    publicKey: warp.peerPublicKey,
                    keepAlive: 15
                }]
            });
            toast.success("WARP account generated successfully");
        } catch (e) {
            toast.error("Failed to generate WARP account", {
                description: "CORS error or proxy is down. Check your settings."
            });
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800 mt-4 space-y-6">
            <div className="flex justify-between items-center border-b border-slate-800 pb-3">
                <h4 className="text-xs uppercase text-slate-400 font-bold flex items-center gap-2">
                    <Icon name="Shield" /> WireGuard Settings
                </h4>
                <Button variant="secondary" className="px-3 py-1.5 text-xs bg-indigo-600/20 text-indigo-400 border-indigo-500/50 hover:bg-indigo-600 hover:text-white" onClick={handleGenerateWarp} disabled={loading}>
                    {loading ? "Generating..." : "Generate WARP"}
                </Button>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <FormField label="Секретный ключ" error={errors.secretKey}>
                    <input className={`input-base font-mono text-rose-300 ${errors.secretKey ? 'border-rose-500 bg-rose-500/10' : ''}`} value={settings.secretKey || ""} onChange={e => update('secretKey', e.target.value)} placeholder="Приватный ключ" />
                </FormField>
                <FormField label="Локальный адрес (CIDR)">
                    <input className="input-base font-mono" value={(settings.address || []).join(', ')} onChange={e => update('address', e.target.value.split(',').map((s: string) => s.trim()))} placeholder="10.0.0.1/24, fd00::1/64" />
                </FormField>
            </div>

            {/* Advanced WG Settings */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 bg-slate-950/50 p-4 rounded-xl border border-slate-800/50">
                <FormField label="MTU" help="Maximum Transmission Unit. По умолчанию 1280 для WARP.">
                    <input type="number" className="input-base" placeholder="1280" value={settings.mtu || ""} onChange={e => update('mtu', parseInt(e.target.value) || 0)} />
                </FormField>
                <FormField label="Reserved (CSV)" help="[n,n,n] — подстановка байт заголовка. Для стандартного WARP — [0,0,0].">
                    <input className="input-base font-mono" 
                        placeholder="0, 0, 0" 
                        value={(settings.reserved || []).map((v: any) => isNaN(v) ? 0 : v).join(', ')} 
                        onChange={e => {
                            const raw = e.target.value.replace(/[^0-9,]/g, '');
                            const vals = raw.split(',')
                                .map(s => s.trim())
                                .filter(s => s !== "")
                                .map(s => parseInt(s))
                                .filter(n => !isNaN(n))
                                .slice(0, 3);
                            update('reserved', vals);
                        }} 
                    />
                </FormField>
                <div className="flex flex-col justify-center pt-5">
                    <Switch
                        checked={settings.noKernelTun || false}
                        onChange={checked => update('noKernelTun', checked)}
                        label="Без kernel TUN"
                    />
                    <p className="text-[10px] text-slate-500 mt-1">Enabled: use gVisor (no root). Disabled: system (faster).</p>
                </div>
            </div>

            <div>
                <div className="flex justify-between items-center mb-3">
                    <h4 className="text-xs uppercase text-slate-500 font-bold">Peers</h4>
                    <Button variant="ghost" onClick={addPeer} className="px-2 py-1 text-xs" icon="Plus">Add Peer</Button>
                </div>
                {errors.peers && (
                    <div className="mb-3 p-3 bg-rose-900/20 border border-rose-500/40 rounded-xl text-rose-300 text-xs flex items-center gap-2">
                        <Icon name="Warning" /> {errors.peers}
                    </div>
                )}
                <div className="space-y-4">
                    {(settings.peers || []).map((peer: any, i: number) => {
                        const epErr = errors[`peer_${i}_endpoint`] as string | undefined;
                        const pkErr = errors[`peer_${i}_publicKey`] as string | undefined;
                        return (
                            <div key={i} className="bg-slate-950 p-4 rounded-xl border border-slate-700/50 flex flex-col gap-4 relative group">
                                <button onClick={() => removePeer(i)} className="absolute top-3 right-3 text-slate-600 hover:text-rose-500 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
                                    <Icon name="Trash" />
                                </button>
                                
                                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pr-6">
                                    <FormField label="Endpoint" error={epErr}>
                                        <input className={`input-base font-mono ${epErr ? 'border-rose-500' : ''}`} value={peer.endpoint || ""} onChange={e => updatePeer(i, 'endpoint', e.target.value)} placeholder="engage.cloudflareclient.com:2408" />
                                    </FormField>
                                    <FormField label="Публичный ключ" error={pkErr}>
                                        <input className={`input-base font-mono text-emerald-300 ${pkErr ? 'border-rose-500' : ''}`} value={peer.publicKey || ""} onChange={e => updatePeer(i, 'publicKey', e.target.value)} placeholder="Публичный ключ" />
                                    </FormField>
                                </div>
                                
                                <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                                    <div className="col-span-1 lg:col-span-3">
                                        <FormField label="Pre-shared Key">
                                            <input className="input-base font-mono" value={peer.preSharedKey || ""} onChange={e => updatePeer(i, 'preSharedKey', e.target.value)} placeholder="Необязательно" />
                                        </FormField>
                                    </div>
                                    <div className="col-span-1 lg:col-span-2">
                                        <FormField label="Keep-alive (s)">
                                            <input type="number" className="input-base font-mono" value={peer.keepAlive || 0} onChange={e => updatePeer(i, 'keepAlive', parseInt(e.target.value) || 0)} />
                                        </FormField>
                                    </div>
                                    <div className="col-span-1 lg:col-span-7">
                                        <div className="flex flex-col gap-1.5 h-full">
                                            <div className="flex justify-between items-center h-[18px]">
                                                <label className="text-[10px] uppercase font-bold text-slate-500 tracking-wider">Allowed IPs</label>
                                                <button 
                                                    onClick={() => {
                                                        const isExcluding = peer.allowedIPs?.length > 2;
                                                        const newList = isExcluding ? ["0.0.0.0/0", "::/0"] : [
                                                            "0.0.0.0/5", "8.0.0.0/7", "11.0.0.0/8", "12.0.0.0/6", "16.0.0.0/4", "32.0.0.0/3", 
                                                            "64.0.0.0/2", "128.0.0.0/3", "160.0.0.0/5", "168.0.0.0/6", "172.0.0.0/12", 
                                                            "172.32.0.0/11", "172.64.0.0/10", "172.128.0.0/9", "173.0.0.0/8", "174.0.0.0/7", 
                                                            "176.0.0.0/4", "192.0.0.0/9", "192.64.0.0/10", "192.128.0.0/11", "192.160.0.0/13", 
                                                            "192.169.0.0/16", "192.170.0.0/15", "192.172.0.0/14", "192.176.0.0/12", 
                                                            "192.192.0.0/10", "193.0.0.0/8", "194.0.0.0/7", "196.0.0.0/6", "200.0.0.0/5", 
                                                            "208.0.0.0/4", "::/0"
                                                        ];
                                                        updatePeer(i, 'allowedIPs', newList);
                                                    }}
                                                    className={`text-[9px] font-bold px-2 py-0.5 rounded transition-colors uppercase ${peer.allowedIPs?.length > 2 ? 'bg-amber-500/10 text-amber-500 hover:bg-amber-500/20' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}
                                                >
                                                    {peer.allowedIPs?.length > 2 ? 'Restore 0.0.0.0/0' : 'Exclude Local'}
                                                </button>
                                            </div>
                                            <textarea 
                                                className="input-base font-mono text-xs h-full min-h-[42px] custom-scroll resize-y" 
                                                value={(peer.allowedIPs || []).join(', ')} 
                                                onChange={e => updatePeer(i, 'allowedIPs', e.target.value.split(',').map(s => s.trim()))} 
                                                placeholder="0.0.0.0/0, ::/0" 
                                            />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                    {(settings.peers || []).length === 0 && <div className="text-sm text-slate-500 text-center py-6 italic border border-dashed border-slate-700 rounded-xl">No peers added</div>}
                </div>
            </div>

            {/* General WG Engine Settings */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-slate-800 pt-4">
                <Select 
                    label="Стратегия доменов"
                    hint="ForceIP: query DNS locally and use IP. UseIP: resolve IP through system."
                    value={settings.domainStrategy || "AsIs"}
                    onChange={val => update('domainStrategy', val)}
                    options={[
                        { value: 'AsIs', label: 'AsIs (Default)' },
                        { value: 'UseIP', label: 'UseIP' },
                        { value: 'ForceIP', label: 'ForceIP' }
                    ]}
                />
                <FormField label="Воркеров" help="Количество одновременных воркеров. По умолчанию = количество ядер CPU.">
                    <input type="number" className="input-base h-[42px]" placeholder="Авто" value={settings.workers || ""} onChange={e => update('workers', parseInt(e.target.value) || 0)} />
                </FormField>
            </div>
        </div>
    );
};
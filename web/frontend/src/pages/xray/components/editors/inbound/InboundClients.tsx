// @ts-nocheck
import React from 'react';
import { Select } from '../../ui/Select';
import { Button } from '../../ui/Button';
import { Icon } from '../../ui/Icon';
import { Help } from '../../ui/Help';
import { Switch } from '../../ui/Switch';
import { generateUUID, generateShortId } from '../../../utils/generators';


import { useConfigStore } from '../../../store/configStore';

export const InboundClients = ({ inbound, onChange, errors = {} as any }) => {
    const { remnawave } = useConfigStore();
    const [ssPassLen, setSsPassLen] = React.useState(32);
    const proto = inbound.protocol;

    // Remnawave integration: Hide users if connected (only for multi-user protocols)
    if (remnawave.connected && ['vless', 'vmess', 'trojan', 'hysteria'].includes(proto)) {
        return (
            <div className="bg-indigo-900/10 border border-indigo-500/20 p-4 rounded-xl mt-4 flex items-start gap-3">
                <Icon name="Cloud" className="text-indigo-400 text-lg shrink-0 mt-0.5" />
                <div>
                    <h4 className="text-xs font-bold text-indigo-300 uppercase mb-1">Managed by Remnawave</h4>
                    <p className="text-[10px] text-slate-500 leading-relaxed italic">
                        User management for this inbound is handled dynamically by your Remnawave panel. 
                        Manually adding clients here is not required.
                    </p>
                </div>
            </div>
        );
    }

    // 1. Shadowsocks / SS-2022
    if (proto === 'shadowsocks' || proto === 'shadowsocks-2022') {
        const is2022 = proto === 'shadowsocks-2022';
        return (
            <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800 mt-4">
                <h4 className="text-xs font-bold text-slate-400 uppercase mb-3 flex items-center gap-2">
                    <Icon name="Key" /> {is2022 ? 'SS-2022' : 'Shadowsocks'} Credentials
                    {remnawave.connected && <span className="text-[10px] text-indigo-400 ml-auto flex items-center gap-1 font-normal"><Icon name="Cloud" /> Remnawave Active</span>}
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <Select 
                            label="Метод"
                            hint="Encryption algorithm for Shadowsocks."
                            value={inbound.settings?.method || (is2022 ? "2022-blake3-aes-128-gcm" : "aes-256-gcm")}
                            onChange={val => onChange(['settings', 'method'], val)}
                            options={!is2022 ? [
                                { value: "aes-256-gcm", label: "aes-256-gcm" },
                                { value: "aes-128-gcm", label: "aes-128-gcm" },
                                { value: "chacha20-ietf-poly1305", label: "chacha20-ietf-poly1305" },
                                { value: "xchacha20-ietf-poly1305", label: "xchacha20-ietf-poly1305" },
                                { value: "2022-blake3-aes-128-gcm", label: "2022-blake3-aes-128-gcm" },
                                { value: "2022-blake3-aes-256-gcm", label: "2022-blake3-aes-256-gcm" },
                                { value: "2022-blake3-chacha20-poly1305", label: "2022-blake3-chacha20-poly1305" },
                            ] : [
                                { value: "2022-blake3-aes-128-gcm", label: "2022-blake3-aes-128-gcm" },
                                { value: "2022-blake3-aes-256-gcm", label: "2022-blake3-aes-256-gcm" },
                                { value: "2022-blake3-chacha20-poly1305", label: "2022-blake3-chacha20-poly1305" },
                            ]}
                        />
                    <div>
                        <label className="label-xs flex items-center justify-between">
                            <span>Password / Pre-shared Key</span>
                            <div className="flex items-center gap-2">
                                <span className="text-[9px] text-slate-500 font-bold uppercase">Length:</span>
                                <input 
                                    type="number" 
                                    className="w-10 bg-transparent border-none text-[10px] text-indigo-400 font-bold p-0 focus:ring-0" 
                                    value={ssPassLen}
                                    onChange={e => setSsPassLen(parseInt(e.target.value) || 0)}
                                />
                            </div>
                        </label>
                        <div className="flex gap-2">
                            <input className={`input-base font-mono ${errors.password ? 'border-rose-500 bg-rose-500/10' : ''}`}
                                value={inbound.settings?.password || ""}
                                onChange={e => onChange(['settings', 'password'], e.target.value)}
                            />
                            <button onClick={() => onChange(['settings', 'password'], generateShortId(ssPassLen))}
                                className="bg-slate-800 p-2 rounded text-slate-400 hover:text-white transition-colors">
                                <Icon name="DiceFive" />
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    // 2. Hysteria 2
    if (proto === 'hysteria') {
        const users = inbound.settings?.users || [];
        const addUser = () => onChange(['settings', 'users'], [...users, { password: generateShortId() }]);
        const removeUser = (i: number) => {
            const next = [...users];
            next.splice(i, 1);
            onChange(['settings', 'users'], next);
        };
        const updateUser = (i: number, val: string) => {
            const next = [...users];
            next[i] = { ...next[i], password: val };
            onChange(['settings', 'users'], next);
        };

        return (
            <div className="space-y-4 mt-4">
                <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800">
                    <h4 className="text-xs font-bold text-slate-400 uppercase mb-3 flex items-center gap-2">
                        <Icon name="Gauge" /> Bandwidth & Global Settings
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        <div>
                            <label className="label-xs flex items-center">
                                Up (Mbps)
                                <Help>Maximum upload speed in Mbps for Hysteria 2 protocol.</Help>
                            </label>
                            <input type="number" className="input-base font-mono" 
                                value={inbound.settings?.up_mbps || ""} 
                                onChange={e => onChange(['settings', 'up_mbps'], parseInt(e.target.value))} />
                        </div>
                        <div>
                            <label className="label-xs flex items-center">
                                Down (Mbps)
                                <Help>Maximum download speed in Mbps for Hysteria 2 protocol.</Help>
                            </label>
                            <input type="number" className="input-base font-mono" 
                                value={inbound.settings?.down_mbps || ""} 
                                onChange={e => onChange(['settings', 'down_mbps'], parseInt(e.target.value))} />
                        </div>
                        <div className="flex items-center gap-2 pt-6">
                            <Switch 
                                checked={inbound.settings?.ignore_client_bandwidth === true}
                                onChange={checked => onChange(['settings', 'ignore_client_bandwidth'], checked)}
                                label="Игнорировать лимит клиента"
                            />
                            <Help>If enabled, the server will ignore the bandwidth limits requested by the client.</Help>
                        </div>
                    </div>
                </div>

                <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800">
                    <div className="flex justify-between items-center mb-4">
                        <h4 className="text-xs font-bold text-slate-400 uppercase flex items-center gap-2">
                            <Icon name="Users" /> Hysteria 2 Users
                        </h4>
                        <Button variant="ghost" className="px-2 py-1 text-xs" onClick={addUser} icon="Plus">Add</Button>
                    </div>
                    <div className="space-y-2 max-h-[200px] overflow-y-auto custom-scroll pr-1">
                        {users.map((u: any, i: number) => (
                            <div key={i} className="bg-slate-950 border border-slate-800 rounded-lg p-3 relative group flex items-center gap-3">
                                <Icon name="Key" className="text-indigo-400 shrink-0" />
                                <input className="input-base py-1.5 text-xs font-mono"
                                    placeholder="Пароль"
                                    value={u.password || ""}
                                    onChange={e => updateUser(i, e.target.value)}
                                />
                                <button onClick={() => removeUser(i)} className="text-slate-600 hover:text-rose-500 transition-opacity">
                                    <Icon name="Trash" />
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        );
    }

    // 2. Socks / HTTP
    if (proto === 'socks' || proto === 'http') {
        const accounts = inbound.settings?.accounts || [];
        const addAccount = () => onChange(['settings', 'accounts'], [...accounts, { user: 'admin', pass: generateShortId() }]);
        const removeAccount = (i: number) => {
            const next = [...accounts];
            next.splice(i, 1);
            onChange(['settings', 'accounts'], next);
        };
        const updateAccount = (i: number, field: string, val: string) => {
            const next = [...accounts];
            next[i] = { ...next[i], [field]: val };
            onChange(['settings', 'accounts'], next);
        };

        return (
            <div className="space-y-4 mt-4">
                <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800">
                    <h4 className="text-xs font-bold text-slate-400 uppercase mb-3 flex items-center gap-2">
                        <Icon name="Gear" /> {proto.toUpperCase()} Settings
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {proto === 'socks' && (
                            <Select 
                                label="Тип авторизации"
                                value={inbound.settings?.auth || "noauth"}
                                onChange={val => onChange(['settings', 'auth'], val)}
                                options={[
                                    { value: "noauth", label: "No Auth" },
                                    { value: "password", label: "Пароль" },
                                ]}
                            />
                        )}
                        <div className="flex items-center gap-6">
                            {proto === 'socks' && (
                                <div className="flex items-center gap-2">
                                    <Switch 
                                        id="socks-udp"
                                        checked={inbound.settings?.udp === true}
                                        onChange={checked => onChange(['settings', 'udp'], checked)}
                                        label="Поддержка UDP"
                                    />
                                    <Help>Enable UDP associate for SOCKS5.</Help>
                                </div>
                            )}
                            {proto === 'http' && (
                                <div className="flex items-center gap-2">
                                    <Switch 
                                        id="http-transparent"
                                        checked={inbound.settings?.allowTransparent === true}
                                        onChange={checked => onChange(['settings', 'allowTransparent'], checked)}
                                        label="Прозрачный режим"
                                    />
                                    <Help>Allow transparent proxying for HTTP.</Help>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {(proto === 'http' || (proto === 'socks' && inbound.settings?.auth === 'password')) && (
                    <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800">
                        <div className="flex justify-between items-center mb-4">
                            <h4 className="text-xs font-bold text-slate-400 uppercase flex items-center gap-2">
                                <Icon name="Users" /> {proto.toUpperCase()} Accounts
                            </h4>
                            <Button variant="ghost" className="px-2 py-1 text-xs" onClick={addAccount} icon="Plus">Add Account</Button>
                        </div>
                        <div className="space-y-3 max-h-[250px] overflow-y-auto custom-scroll pr-1">
                            {accounts.map((acc: any, i: number) => (
                                <div key={i} className="bg-slate-950 border border-slate-800 rounded-lg p-3 relative group flex flex-col md:flex-row items-end gap-3 hover:border-slate-600 transition-colors">
                                    <div className="flex-1 w-full">
                                        <label className="label-xs">Username</label>
                                        <input className="input-base py-1.5 text-xs"
                                            value={acc.user || ""}
                                            onChange={e => updateAccount(i, 'user', e.target.value)}
                                        />
                                    </div>
                                    <div className="flex-1 w-full">
                                        <label className="label-xs">Password</label>
                                        <div className="flex gap-2">
                                            <input className="input-base py-1.5 text-xs font-mono"
                                                value={acc.pass || ""}
                                                onChange={e => updateAccount(i, 'pass', e.target.value)}
                                            />
                                            <button onClick={() => updateAccount(i, 'pass', generateShortId())}
                                                title="Generate Password"
                                                className="bg-slate-800 p-2 rounded text-slate-400 hover:text-white transition-colors">
                                                <Icon name="DiceFive" />
                                            </button>
                                        </div>
                                    </div>
                                    <button onClick={() => removeAccount(i)} 
                                        className="bg-slate-800/50 p-2 rounded text-slate-600 hover:text-rose-500 transition-colors shrink-0"
                                        title="Remove Account">
                                        <Icon name="Trash" />
                                    </button>
                                </div>
                            ))}
                            {accounts.length === 0 && (
                                <div className="text-center text-slate-600 text-xs py-6 italic border border-dashed border-slate-800 rounded-lg">
                                    No accounts defined. {proto === 'http' ? 'Auth is disabled.' : 'Add one to enable password auth.'}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        );
    }

    // 3. VLESS / VMess / Trojan
    if (!['vless', 'vmess', 'trojan'].includes(proto)) return null;

    const clients = inbound.settings?.clients || [];
    const idKey = proto === 'trojan' ? 'password' : 'id';

    const addClient = () => {
        const newClient: any = { email: `user${clients.length}@xray` };
        newClient[idKey] = idKey === 'id' ? generateUUID() : generateShortId();
        if (proto === 'vless') newClient.flow = "xtls-rprx-vision";
        onChange(['settings', 'clients'], [...clients, newClient]);
    };

    const updateClient = (index, field, val) => {
        const newClients = [...clients];
        newClients[index] = { ...newClients[index], [field]: val };
        onChange(['settings', 'clients'], newClients);
    };

    const removeClient = (index) => {
        const newClients = [...clients];
        newClients.splice(index, 1);
        onChange(['settings', 'clients'], newClients);
    };

    return (
        <div className="bg-slate-900/50 p-4 rounded-xl border border-slate-800 mt-4">
            <div className="flex justify-between items-center mb-4">
                <h4 className="text-xs font-bold text-slate-400 uppercase flex items-center gap-2">
                    <Icon name="Users" /> Clients / Users
                </h4>
                <Button variant="ghost" className="px-2 py-1 text-xs" onClick={addClient} icon="Plus">Add</Button>
            </div>

            {errors.clients && (
                <div className="mb-3 p-2 bg-rose-900/20 border border-rose-500/40 rounded text-rose-300 text-[11px]">
                    ⚠ {errors.clients}
                </div>
            )}
            <div className="space-y-3 max-h-[300px] overflow-y-auto custom-scroll pr-1">
                {clients.map((c, i) => (
                    <div key={i} className="bg-slate-950 border border-slate-800 rounded-lg p-3 relative group hover:border-slate-600 transition-colors">
                        <button onClick={() => removeClient(i)} className="absolute top-2 right-2 text-slate-600 hover:text-rose-500 md:opacity-0 md:group-hover:opacity-100 transition-opacity">
                            <Icon name="Trash" />
                        </button>

                        {/* Адаптивный грид клиентов */}
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pr-6">
                            <div>
                                <label className="label-xs">Email</label>
                                <input className="input-base py-1.5 text-xs"
                                    value={c.email || ""}
                                    onChange={e => updateClient(i, 'email', e.target.value)}
                                />
                            </div>
                            <div>
                                <label className="label-xs">{idKey === 'id' ? 'UUID' : 'Password'}</label>
                                <div className="flex gap-2">
                                    <input className="input-base py-1.5 text-xs font-mono"
                                        value={c[idKey] || ""}
                                        onChange={e => updateClient(i, idKey, e.target.value)}
                                    />
                                    <button onClick={() => updateClient(i, idKey, idKey === 'id' ? generateUUID() : generateShortId())}
                                        className="text-slate-500 hover:text-white transition-colors">
                                        <Icon name="DiceFive" />
                                    </button>
                                </div>
                            </div>
                            {proto === 'vless' && (
                                    <Select 
                                        label="Flow"
                                        value={c.flow || ""}
                                        onChange={val => updateClient(i, 'flow', val)}
                                        options={[
                                            { value: "", label: "Нет" },
                                            { value: "xtls-rprx-vision", label: "xtls-rprx-vision" },
                                        ]}
                                    />
                            )}
                        </div>
                    </div>
                ))}
                {clients.length === 0 && (
                    <div className="text-center text-slate-600 text-xs py-4 italic">No users defined. Click Add to create one.</div>
                )}
            </div>
        </div>
    );
};
// @ts-nocheck
import React, { useState } from 'react';
import { Icon } from '../../ui/Icon';
import { Button } from '../../ui/Button';
import { Help } from '../../ui/Help';
import { generateX25519Keys } from '../../../utils/crypto';
import { generateRealitySpiderX, generateRealityShortIds } from '../../../utils/generators';
import { SockoptEditor } from './SockoptEditor';
import { TagSelector } from '../../ui/TagSelector';
import { XhttpSettingsEditor } from './XhttpSettingsEditor';
import { FinalmaskEditor } from './FinalmaskEditor';
import { Switch } from '../../ui/Switch';
import { Select } from '../../ui/Select';

interface TransportProps {
    streamSettings: any;
    onChange: (newSettings: any) => void;
    isClient?: boolean;
    errors?: Record<string, string | undefined>;
    protocol?: string;
}

export const TransportSettings = ({ streamSettings = {}, onChange, isClient = false, errors = {}, protocol }: TransportProps) => {
    const [tempPublicKey, setTempPublicKey] = useState<string | null>(null);

    const update = (path: string[], value: any) => {
        const newObj = JSON.parse(JSON.stringify(streamSettings));
        let curr = newObj;
        for (let i = 0; i < path.length - 1; i++) {
            if (!curr[path[i]]) curr[path[i]] = {};
            curr = curr[path[i]];
        }
        curr[path[path.length - 1]] = value;
        onChange(newObj);
    };

    const net = streamSettings.network || "tcp";
    const sec = streamSettings.security || "none";

    const handleGenKeys = () => {
        const keys = generateX25519Keys();
        if (isClient) {
            update(['realitySettings', 'privateKey'], keys.privateKey);
            update(['realitySettings', 'publicKey'], keys.publicKey);
        } else {
            update(['realitySettings', 'privateKey'], keys.privateKey);
            setTempPublicKey(keys.publicKey);
            if (!streamSettings.realitySettings?.shortIds) {
                update(['realitySettings', 'shortIds'], [Math.random().toString(16).substring(2, 10)]);
            }
        }
    };

    return (
        <div className="bg-slate-900/40 p-5 rounded-2xl border border-slate-800/80 space-y-6 animate-in fade-in duration-300">
            <div className="flex items-center justify-between border-b border-slate-800/60 pb-3">
                <h4 className="text-[11px] font-black text-indigo-400 uppercase tracking-[0.2em] flex items-center gap-2.5">
                    <Icon name="GlobeHemisphereWest" size={18} /> Stream Settings
                </h4>
            </div>

            {/* --- MAIN SELECTORS --- */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <Select 
                        label="Network"
                        hint="Transport protocol used to deliver data."
                        value={net} 
                        onChange={val => update(['network'], val)}
                        options={[
                            { value: "tcp", label: "TCP", description: "Standard reliable stream" },
                            { value: "ws", label: "WebSocket", description: "Standard web transport" },
                            { value: "xhttp", label: "XHTTP", description: "Next-gen HTTP transport" },
                            { value: "splithttp", label: "SplitHTTP", description: "High-performance split stream" },
                            { value: "grpc", label: "gRPC", description: "Modern RPC framework" },
                            { value: "http", label: "HTTP", description: "Standard HTTP proxying" },
                            { value: "quic", label: "QUIC", description: "UDP-based transport (HTTP/3)" },
                            { value: "kcp", label: "mKCP", description: "Aggressive UDP transport" },
                            { value: "raw", label: "RAW", description: "Raw socket access" },
                            { value: "httpupgrade", label: "HTTP Upgrade", description: "Modern WebSocket alternative" },
                        ]}
                    />
                    <Select 
                        label="Security"
                        hint="Encryption layer (TLS/Reality)."
                        value={sec} 
                        onChange={val => update(['security'], val)}
                        options={[
                            { value: "none", label: "NONE", description: "Plaintext (unsafe)" },
                            { value: "tls", label: "TLS", description: "Standard SSL/TLS encryption" },
                            ...(['vless', 'vmess', 'trojan', 'shadowsocks'].includes(protocol || '') ? [
                                { value: "reality", label: "REALITY", description: "Next-gen stealth encryption" }
                            ] : []),
                        ]}
                    />
            </div>

            <div className="border-t border-slate-800/50 my-2" />

            {/* --- NETWORK SPECIFIC SETTINGS --- */}

            {/* RAW (for Finalmask) */}
            {net === 'raw' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-slate-800/50 pt-4">
                    <div className="col-span-full flex items-center gap-2">
                        <span className="text-xs font-bold text-emerald-400">RAW Socket Settings</span>
                        <Help>Used primarily with Finalmask for obfuscation.</Help>
                    </div>
                </div>
            )}

            {/* HTTP Upgrade */}
            {net === 'httpupgrade' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-slate-800/50 pt-4">
                    <div className="col-span-full flex items-center gap-2">
                        <span className="text-xs font-bold text-blue-400">HTTP Upgrade Configuration</span>
                    </div>
                    <div><label className="label-xs">Path</label><input className="input-base font-mono" placeholder="/" value={streamSettings.httpupgradeSettings?.path || ""} onChange={e => update(['httpupgradeSettings', 'path'], e.target.value)} /></div>
                    <div><label className="label-xs">Host</label><input className="input-base font-mono" placeholder="example.com" value={streamSettings.httpupgradeSettings?.host || ""} onChange={e => update(['httpupgradeSettings', 'host'], e.target.value)} /></div>
                </div>
            )}

            {/* TCP (RAW) */}
            {net === 'tcp' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-slate-800/50 pt-4">
                    <div className="col-span-full flex items-center justify-between gap-2">
                        <span className="text-xs font-bold text-slate-400">TCP (RAW) Settings</span>
                        {!isClient && (
                            <Switch
                                checked={streamSettings.tcpSettings?.acceptProxyProtocol || false}
                                onChange={checked => update(['tcpSettings', 'acceptProxyProtocol'], checked)}
                                label={<span className="text-[10px] text-slate-300 font-bold uppercase tracking-wider">Accept PROXY Protocol</span>}
                            />
                        )}
                    </div>
                        <Select 
                            label="Header Type (Obfuscation)"
                            value={streamSettings.tcpSettings?.header?.type || "none"}
                            onChange={val => update(['tcpSettings', 'header', 'type'], val)}
                            options={[
                                { value: "none", label: "Нет", description: "No obfuscation" },
                                { value: "http", label: "HTTP", description: "Simulate HTTP request" },
                            ]}
                        />

                    {streamSettings.tcpSettings?.header?.type === 'http' && (
                        <div className="md:col-span-2 space-y-2 bg-slate-950 p-3 rounded border border-slate-800">
                            <label className="label-xs text-yellow-500">HTTP Request (Legacy Obfuscation)</label>
                            <div className="grid grid-cols-2 gap-2">
                                <input className="input-base text-xs font-mono" placeholder="Path (e.g. /)"
                                    value={streamSettings.tcpSettings?.header?.request?.path?.[0] || "/"}
                                    onChange={e => update(['tcpSettings', 'header', 'request', 'path'], [e.target.value])} />
                                <input className="input-base text-xs font-mono" placeholder="Host (e.g. bing.com)"
                                    value={streamSettings.tcpSettings?.header?.request?.headers?.Host?.[0] || ""}
                                    onChange={e => update(['tcpSettings', 'header', 'request', 'headers', 'Host'], [e.target.value])} />
                            </div>
                        </div>
                    )}
                </div>
            )}

            {(net === 'xhttp' || net === 'splithttp') && (
                <div className="border-t border-slate-800 pt-4">
                    <div className="flex items-center gap-2 mb-4">
                        <span className="text-xs font-bold text-blue-400 uppercase tracking-wider">{net.toUpperCase()} Configuration</span>
                        <span className="text-[10px] text-white bg-blue-600 px-1.5 py-0.5 rounded font-bold animate-pulse">BEYOND REALITY</span>
                    </div>
                    <XhttpSettingsEditor
                        xhttpSettings={streamSettings.xhttpSettings || streamSettings.splithttpSettings}
                        onChange={v => update([net === 'splithttp' ? 'splithttpSettings' : 'xhttpSettings'], v)}
                        isClient={isClient}
                    />
                </div>
            )}

            {net === 'ws' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-slate-800/50 pt-4">
                    <div className="col-span-full flex items-center justify-between gap-2">
                        <span className="text-xs font-bold text-indigo-400">WebSocket</span>
                        {!isClient && (
                            <Switch
                                checked={streamSettings.wsSettings?.acceptProxyProtocol || false}
                                onChange={checked => update(['wsSettings', 'acceptProxyProtocol'], checked)}
                                label={<span className="text-[10px] text-slate-300 font-bold uppercase tracking-wider">Accept PROXY Protocol</span>}
                            />
                        )}
                    </div>
                    <div><label className="label-xs">Path</label><input className="input-base font-mono" value={streamSettings.wsSettings?.path || "/"} onChange={e => update(['wsSettings', 'path'], e.target.value)} /></div>
                    <div><label className="label-xs">Host</label><input className="input-base font-mono" placeholder="host.com" value={streamSettings.wsSettings?.headers?.Host || ""} onChange={e => update(['wsSettings', 'headers', 'Host'], e.target.value)} /></div>
                    <div><label className="label-xs">Heartbeat Period (s)</label><input className="input-base font-mono" type="number" placeholder="10" value={streamSettings.wsSettings?.heartbeatPeriod || ""} onChange={e => update(['wsSettings', 'heartbeatPeriod'], Number(e.target.value))} /></div>
                </div>
            )}

            {net === 'grpc' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-slate-800 pt-4 animate-in fade-in">
                    <div className="col-span-full text-xs font-bold text-indigo-400">gRPC</div>
                    <div className="md:col-span-2"><label className="label-xs">Service Name</label><input className="input-base font-mono" placeholder="GunService" value={streamSettings.grpcSettings?.serviceName || ""} onChange={e => update(['grpcSettings', 'serviceName'], e.target.value)} /></div>
                    <div><label className="label-xs">Authority</label><input className="input-base font-mono" placeholder="grpc.example.com" value={streamSettings.grpcSettings?.authority || ""} onChange={e => update(['grpcSettings', 'authority'], e.target.value)} /></div>
                    {isClient && (
                        <>
                            <div><label className="label-xs flex items-center">Multi Mode <Help>Experimental feature. Can improve performance by ~20%.</Help></label>
                                <Switch
                                    checked={streamSettings.grpcSettings?.multiMode || false}
                                    onChange={checked => update(['grpcSettings', 'multiMode'], checked)}
                                    label="Enable Multi Mode"
                                />
                            </div>
                            <div><label className="label-xs">User Agent</label><input className="input-base font-mono" placeholder="custom user agent" value={streamSettings.grpcSettings?.user_agent || ""} onChange={e => update(['grpcSettings', 'user_agent'], e.target.value)} /></div>
                            <div><label className="label-xs">Idle Timeout (s)</label><input className="input-base font-mono" type="number" placeholder="60" value={streamSettings.grpcSettings?.idle_timeout || ""} onChange={e => update(['grpcSettings', 'idle_timeout'], Number(e.target.value))} /></div>
                            <div><label className="label-xs">Health Check Timeout (s)</label><input className="input-base font-mono" type="number" placeholder="20" value={streamSettings.grpcSettings?.health_check_timeout || ""} onChange={e => update(['grpcSettings', 'health_check_timeout'], Number(e.target.value))} /></div>
                            <div><label className="label-xs">Initial Windows Size</label><input className="input-base font-mono" type="number" placeholder="0" value={streamSettings.grpcSettings?.initial_windows_size || ""} onChange={e => update(['grpcSettings', 'initial_windows_size'], Number(e.target.value))} /></div>
                            <div><label className="label-xs">Permit Without Stream</label>
                                <Switch
                                    checked={streamSettings.grpcSettings?.permit_without_stream || false}
                                    onChange={checked => update(['grpcSettings', 'permit_without_stream'], checked)}
                                    label="Enable"
                                />
                            </div>
                        </>
                    )}
                </div>
            )}

            {net === 'kcp' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-slate-800 pt-4 animate-in fade-in">
                    <div className="col-span-full text-xs font-bold text-indigo-400">mKCP</div>
                        <Select 
                            label="Header Type"
                            value={streamSettings.kcpSettings?.header?.type || "none"}
                            onChange={val => update(['kcpSettings', 'header', 'type'], val)}
                            options={[
                                { value: "none", label: "Нет" },
                                { value: "srtp", label: "SRTP", description: "Video call simulation" },
                                { value: "utp", label: "uTP", description: "BitTorrent simulation" },
                                { value: "wechat-video", label: "WeChat", description: "WeChat video call" },
                                { value: "dtls", label: "DTLS", description: "DTLS 1.2 simulation" },
                                { value: "wireguard", label: "WireGuard", description: "WireGuard simulation" },
                            ]}
                        />
                    <div><label className="label-xs">Seed</label><input className="input-base font-mono" placeholder="password" value={streamSettings.kcpSettings?.seed || ""} onChange={e => update(['kcpSettings', 'seed'], e.target.value)} /></div>
                    <div><label className="label-xs">MTU</label><input className="input-base font-mono" type="number" placeholder="1350" value={streamSettings.kcpSettings?.mtu || ""} onChange={e => update(['kcpSettings', 'mtu'], Number(e.target.value))} /></div>
                    <div><label className="label-xs">TTI (ms)</label><input className="input-base font-mono" type="number" placeholder="50" value={streamSettings.kcpSettings?.tti || ""} onChange={e => update(['kcpSettings', 'tti'], Number(e.target.value))} /></div>
                    <div><label className="label-xs">Uplink Capacity (MB/s)</label><input className="input-base font-mono" type="number" placeholder="5" value={streamSettings.kcpSettings?.uplinkCapacity || ""} onChange={e => update(['kcpSettings', 'uplinkCapacity'], Number(e.target.value))} /></div>
                    <div><label className="label-xs">Downlink Capacity (MB/s)</label><input className="input-base font-mono" type="number" placeholder="20" value={streamSettings.kcpSettings?.downlinkCapacity || ""} onChange={e => update(['kcpSettings', 'downlinkCapacity'], Number(e.target.value))} /></div>
                    <div><label className="label-xs">Read Buffer Size (MB)</label><input className="input-base font-mono" type="number" placeholder="2" value={streamSettings.kcpSettings?.readBufferSize || ""} onChange={e => update(['kcpSettings', 'readBufferSize'], Number(e.target.value))} /></div>
                    <div><label className="label-xs">Write Buffer Size (MB)</label><input className="input-base font-mono" type="number" placeholder="2" value={streamSettings.kcpSettings?.writeBufferSize || ""} onChange={e => update(['kcpSettings', 'writeBufferSize'], Number(e.target.value))} /></div>
                    <div className="md:col-span-2">
                        <Switch
                            checked={streamSettings.kcpSettings?.congestion || false}
                            onChange={checked => update(['kcpSettings', 'congestion'], checked)}
                            label="Enable Congestion Control"
                        />
                    </div>
                </div>
            )}

            {net === 'quic' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-slate-800 pt-4 animate-in fade-in">
                    <div className="col-span-full text-xs font-bold text-indigo-400">QUIC</div>
                        <Select 
                            label="Security"
                            value={streamSettings.quicSettings?.security || "none"}
                            onChange={val => update(['quicSettings', 'security'], val)}
                            options={[
                                { value: "none", label: "Нет" },
                                { value: "aes-128-gcm", label: "AES-128-GCM" },
                                { value: "chacha20-poly1305", label: "ChaCha20" },
                            ]}
                        />
                        <Select 
                            label="Header Type"
                            value={streamSettings.quicSettings?.header?.type || "none"}
                            onChange={val => update(['quicSettings', 'header', 'type'], val)}
                            options={[
                                { value: "none", label: "Нет" },
                                { value: "srtp", label: "SRTP" },
                                { value: "utp", label: "uTP" },
                                { value: "wechat-video", label: "WeChat" },
                                { value: "dtls", label: "DTLS" },
                                { value: "wireguard", label: "WireGuard" },
                            ]}
                        />
                    <div className="md:col-span-2"><label className="label-xs">Key</label><input className="input-base font-mono" placeholder="key" value={streamSettings.quicSettings?.key || ""} onChange={e => update(['quicSettings', 'key'], e.target.value)} /></div>
                </div>
            )}

            {/* --- SECURITY SETTINGS --- */}

            {/* 1. REALITY SETTINGS */}
            {sec === 'reality' && (
                <div className="space-y-4 border-t border-slate-800 pt-4 animate-in fade-in">
                    <div className="flex justify-between items-center">
                        <span className="text-xs font-bold text-purple-400 flex items-center">
                            REALITY Keys
                            <Help>Reality: A TLS extension for mimicking popular websites to bypass firewalls.</Help>
                        </span>
                        <Button variant="secondary" className="px-2 py-1 text-[10px]" onClick={handleGenKeys}>Gen Keys Pair</Button>
                    </div>

                    {!isClient && tempPublicKey && (
                        <div className="bg-emerald-900/20 border border-emerald-500/50 p-3 rounded-lg">
                            <label className="label-xs text-emerald-400">Generated Public Key</label>
                            <div className="flex gap-2">
                                <code className="flex-1 bg-black/30 p-2 rounded text-xs font-mono break-all text-emerald-200">{tempPublicKey}</code>
                                <Button variant="ghost" icon="Копировать" onClick={() => navigator.clipboard.writeText(tempPublicKey)} />
                            </div>
                        </div>
                    )}

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {isClient ? (
                            <>
                                {/* Public Key — единственное обязательное поле для клиента */}
                                <div>
                                    <label className="label-xs text-purple-400">Public Key</label>
                                    <input
                                        className={`input-base font-mono ${errors.reality ? 'border-rose-500 bg-rose-500/10 focus:border-rose-500' : ''}`}
                                        value={streamSettings.realitySettings?.publicKey || ""}
                                        onChange={e => update(['realitySettings', 'publicKey'], e.target.value)}
                                    />
                                    {errors.reality && (
                                        <span className="text-[10px] text-rose-500 mt-1 block">{errors.reality}</span>
                                    )}
                                </div>
                                <div>
                                    <label className="label-xs text-purple-400 flex items-center justify-between">
                                        Short ID
                                        <button onClick={() => update(['realitySettings', 'shortId'], generateRealityShortIds(1)[0])} className="text-[10px] text-slate-500 hover:text-indigo-400">Gen</button>
                                    </label>
                                    <input className="input-base font-mono" value={streamSettings.realitySettings?.shortId || ""} onChange={e => update(['realitySettings', 'shortId'], e.target.value)} />
                                </div>
                                <div className="md:col-span-2">
                                    <label className="label-xs text-purple-400 flex items-center justify-between">
                                        SpiderX
                                        <button onClick={() => update(['realitySettings', 'spiderX'], generateRealitySpiderX())} className="text-[10px] text-slate-500 hover:text-indigo-400">Gen</button>
                                    </label>
                                    <input className="input-base font-mono" value={streamSettings.realitySettings?.spiderX || ""} onChange={e => update(['realitySettings', 'spiderX'], e.target.value)} />
                                </div>
                            </>
                        ) : (
                            <>
                                <div>
                                    <label className="label-xs">Dest</label>
                                    <input className="input-base font-mono" placeholder="google.com:443" value={streamSettings.realitySettings?.dest || ""} onChange={e => update(['realitySettings', 'dest'], e.target.value)} />
                                </div>
                                <div>
                                    <label className="label-xs">Private Key</label>
                                    <input className="input-base font-mono text-emerald-400" value={streamSettings.realitySettings?.privateKey || ""} onChange={e => update(['realitySettings', 'privateKey'], e.target.value)} />
                                </div>
                                <div>
                                    <label className="label-xs flex items-center justify-between">
                                        Short IDs (CSV)
                                        <button onClick={() => update(['realitySettings', 'shortIds'], generateRealityShortIds(3))} className="text-[10px] text-slate-500 hover:text-indigo-400">Gen List</button>
                                    </label>
                                    <input className="input-base font-mono" placeholder="a1b2, c3d4" value={(streamSettings.realitySettings?.shortIds || []).join(', ')} onChange={e => update(['realitySettings', 'shortIds'], e.target.value.split(',').map((s: string) => s.trim()))} />
                                </div>
                            </>
                        )}

                        <div className="md:col-span-2">
                            <label className="label-xs flex items-center">
                                Server Names (SNI) <Help>Allowed domains for Reality.</Help>
                            </label>
                            <input className="input-base font-mono"
                                placeholder="example.com, www.example.com"
                                value={isClient ? (streamSettings.realitySettings?.serverName || "") : (streamSettings.realitySettings?.serverNames || []).join(', ')}
                                onChange={e => {
                                    const val = e.target.value;
                                    update(['realitySettings', isClient ? 'serverName' : 'serverNames'], isClient ? val : val.split(',').map((s: string) => s.trim()));
                                }}
                            />
                        </div>

                        {isClient && (
                                <Select 
                                    label="uTLS Fingerprint"
                                    hint="Mimic specific browser fingerprints."
                                    value={streamSettings.realitySettings?.fingerprint || ""}
                                    onChange={val => update(['realitySettings', 'fingerprint'], val)}
                                    options={[
                                        { value: "", label: "Нет" },
                                        { value: "chrome", label: "Chrome" },
                                        { value: "firefox", label: "Firefox" },
                                        { value: "safari", label: "Safari" },
                                        { value: "ios", label: "iOS" },
                                        { value: "android", label: "Android" },
                                        { value: "edge", label: "Edge" },
                                        { value: "360", label: "360" },
                                        { value: "qq", label: "QQ" },
                                        { value: "random", label: "Random" },
                                        { value: "randomized", label: "Randomized" },
                                    ]}
                                />
                        )}
                    </div>
                </div>
            )}

            {/* 2. STANDARD TLS SETTINGS */}
            {sec === 'tls' && (
                <div className="space-y-4 border-t border-slate-800 pt-4 animate-in fade-in">
                    <div className="text-xs font-bold text-blue-400">Standard TLS Settings</div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="md:col-span-2">
                            <label className="label-xs flex items-center">Server Name (SNI) <Help>Target domain.</Help></label>
                            <input className="input-base font-mono" value={streamSettings.tlsSettings?.serverName || ""} onChange={e => update(['tlsSettings', 'serverName'], e.target.value)} />
                        </div>

                        <div className="md:col-span-2">
                            <TagSelector
                                label={<span className="flex items-center">ALPN <Help>Application-Layer Protocol Negotiation (e.g. h2, http/1.1).</Help></span>}
                                availableTags={['h2', 'http/1.1', 'h3']}
                                selected={streamSettings.tlsSettings?.alpn || []}
                                onChange={v => update(['tlsSettings', 'alpn'], v)}
                                multi={true}
                                placeholder="Custom ALPN..."
                            />
                        </div>

                        {!isClient && (
                            <div className="md:col-span-2">
                                <label className="label-xs">Certificates (Paths)</label>
                                <div className="flex gap-2 mb-2">
                                    <input className="input-base text-xs flex-1" placeholder="/path/to/fullchain.crt"
                                        value={streamSettings.tlsSettings?.certificates?.[0]?.certificateFile || ""}
                                        onChange={e => update(['tlsSettings', 'certificates'], [{ ...streamSettings.tlsSettings?.certificates?.[0], certificateFile: e.target.value }])} />
                                    <input className="input-base text-xs flex-1" placeholder="/path/to/private.key"
                                        value={streamSettings.tlsSettings?.certificates?.[0]?.keyFile || ""}
                                        onChange={e => update(['tlsSettings', 'certificates'], [{ ...streamSettings.tlsSettings?.certificates?.[0], keyFile: e.target.value }])} />
                                </div>
                            </div>
                        )}

                        <Select 
                            label="Min TLS Version"
                            value={streamSettings.tlsSettings?.minVersion || "1.2"}
                            onChange={val => update(['tlsSettings', 'minVersion'], val)}
                            options={[
                                { value: "1.0", label: "1.0" },
                                { value: "1.1", label: "1.1" },
                                { value: "1.2", label: "1.2" },
                                { value: "1.3", label: "1.3" },
                            ]}
                        />
                        <Select 
                            label="Max TLS Version"
                            value={streamSettings.tlsSettings?.maxVersion || "1.3"}
                            onChange={val => update(['tlsSettings', 'maxVersion'], val)}
                            options={[
                                { value: "1.0", label: "1.0" },
                                { value: "1.1", label: "1.1" },
                                { value: "1.2", label: "1.2" },
                                { value: "1.3", label: "1.3" },
                            ]}
                        />

                        {isClient && (
                                <Select 
                                    label="uTLS Fingerprint"
                                    hint="Mimic specific browser fingerprints."
                                    value={streamSettings.tlsSettings?.fingerprint || ""}
                                    onChange={val => update(['tlsSettings', 'fingerprint'], val)}
                                    options={[
                                        { value: "", label: "None (Go TLS)" },
                                        { value: "chrome", label: "Chrome" },
                                        { value: "firefox", label: "Firefox" },
                                        { value: "safari", label: "Safari" },
                                        { value: "ios", label: "iOS" },
                                        { value: "android", label: "Android" },
                                        { value: "edge", label: "Edge" },
                                        { value: "360", label: "360" },
                                        { value: "qq", label: "QQ" },
                                        { value: "random", label: "Random" },
                                        { value: "randomized", label: "Randomized" },
                                    ]}
                                />
                        )}

                        <div className="md:col-span-2 grid grid-cols-2 gap-4 bg-slate-950 p-3 rounded-lg border border-slate-800">
                            {isClient && (
                                <Switch
                                    checked={streamSettings.tlsSettings?.allowInsecure || false}
                                    onChange={checked => update(['tlsSettings', 'allowInsecure'], checked)}
                                    label="Allow Insecure"
                                />
                            )}
                            <Switch
                                checked={streamSettings.tlsSettings?.rejectUnknownSni || false}
                                onChange={checked => update(['tlsSettings', 'rejectUnknownSni'], checked)}
                                label="Reject Unknown SNI"
                            />
                        </div>
                    </div>
                </div>
            )}

            {/* FINALMASK (UDP/TCP Noise & QUIC) */}
            <FinalmaskEditor
                finalmask={streamSettings.finalmask}
                onChange={v => {
                    if (v === null) {
                        const newSettings = { ...streamSettings };
                        delete newSettings.finalmask;
                        onChange(newSettings);
                    } else {
                        update(['finalmask'], v);
                    }
                }}
            />

            {/* --- SOCKOPT (Advanced) --- */}
            <SockoptEditor
                sockopt={streamSettings.sockopt}
                onChange={v => {
                    if (v === null) {
                        const newSettings = { ...streamSettings };
                        delete newSettings.sockopt;
                        onChange(newSettings);
                    } else {
                        update(['sockopt'], v);
                    }
                }}
                isClient={isClient}
            />
        </div>
    );
};